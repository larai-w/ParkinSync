"""Exercise the real shell deployment flow with an isolated AWS CLI substitute."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
AWS_STUB = r'''
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
path = Path(os.environ["CALL_LOG"])
calls = json.loads(path.read_text()) if path.exists() else []
calls.append(args)
path.write_text(json.dumps(calls))
operation = args[1]
failure = os.environ.get("FAIL_AT", "")
label = operation
if operation == "wait":
    label = "config-wait" if sum(c[1] == "wait" for c in calls) == 1 else "code-wait"
if label == failure:
    print("synthetic injected failure", file=sys.stderr)
    sys.exit(254)
if operation == "get-alias":
    error = os.environ.get("ALIAS_ERROR", "")
    if error:
        print(error, file=sys.stderr)
        sys.exit(254)
if operation == "publish-version":
    print("23")
'''


class DeployAliasSafetyTests(unittest.TestCase):
    def run_deploy(self, alias_error="", fail_at="", target="iot", dry_run="0"):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copyfile(ROOT / "deploy.sh", root / "deploy.sh")
            (root / "src").mkdir()
            for name in ("ParkinSync_OCR_Handler.py", "indoor_temp_logger.py"):
                (root / "src" / name).write_text("# synthetic inert deployment input\n")
            (root / "bin").mkdir()
            stub = root / "bin" / "aws"
            stub.write_text(f"#!{sys.executable}\n" + AWS_STUB)
            stub.chmod(0o700)
            log = root / "calls.json"
            # A closed environment prevents profile/credential inheritance. The
            # script's only AWS executable is this local, inert substitute.
            env = {"PATH": f"{root / 'bin'}:/usr/bin:/bin", "HOME": str(root),
                   "TMPDIR": str(root), "DEPLOY_TARGET": target,
                   "DRY_RUN": dry_run, "VENDOR_DEPS": "0", "CALL_LOG": str(log),
                   "ALIAS_ERROR": alias_error, "FAIL_AT": fail_at,
                   "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"}
            result = subprocess.run(["/bin/bash", str(root / "deploy.sh")],
                                    cwd=root, env=env, capture_output=True, text=True,
                                    timeout=20)
            calls = json.loads(log.read_text()) if log.exists() else []
            return result, calls

    def assert_stopped(self, error, target="iot"):
        result, calls = self.run_deploy(alias_error=error, target=target)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls[-1][1], "get-alias")
        self.assertFalse(any(c[1] in ("create-alias", "update-alias") for c in calls))
        self.assertNotIn("Published ", result.stdout)
        self.assertIn(error, result.stderr)
        return calls

    def test_existing_alias_updates_only(self):
        result, calls = self.run_deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls[-1][1], "update-alias")
        self.assertFalse(any(c[1] == "create-alias" for c in calls))

    def test_explicit_missing_alias_creates_only(self):
        for prefix in ("", "aws: [ERROR]: "):
            with self.subTest(prefix=prefix):
                result, calls = self.run_deploy(alias_error=prefix +
                    "An error occurred (ResourceNotFoundException) when calling the GetAlias operation: synthetic alias missing")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(calls[-1][1], "create-alias")
                self.assertFalse(any(c[1] == "update-alias" for c in calls))

    def test_access_denied_stops_without_alias_mutation(self):
        self.assert_stopped("An error occurred (AccessDeniedException) when calling the GetAlias operation: synthetic denied")

    def test_throttling_stops_without_alias_mutation(self):
        self.assert_stopped("An error occurred (TooManyRequestsException) when calling the GetAlias operation: synthetic throttle")

    def test_transport_failure_stops_without_alias_mutation(self):
        self.assert_stopped("Could not connect to the endpoint URL: synthetic endpoint")

    def test_invalid_profile_stops_without_alias_mutation(self):
        for error in (
            "The config profile (synthetic) could not be found",
            '{"Code":"ResourceNotFoundException","Message":"synthetic missing"}',
            "synthetic unrelated text (ResourceNotFoundException) when calling the GetAlias operation: not a recognized response",
        ):
            with self.subTest(error=error):
                self.assert_stopped(error)

    def test_prior_mutation_failures_stop_later_steps(self):
        for stage in ("update-function-configuration", "config-wait",
                      "update-function-code", "code-wait", "publish-version", "update-alias"):
            with self.subTest(stage=stage):
                result, calls = self.run_deploy(fail_at=stage)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("Published ", result.stdout)
                if stage not in ("publish-version", "update-alias"):
                    self.assertFalse(any(c[1] == "publish-version" for c in calls))

    def test_all_target_failure_stops_before_indoor_target(self):
        calls = self.assert_stopped("synthetic unknown alias lookup failure", target="all")
        self.assertFalse(any("ParkinSync_IndoorTemp_Logger" in c for c in calls))

    def test_dry_run_never_calls_aws(self):
        result, calls = self.run_deploy(target="all", dry_run="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
