import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release_pack", ROOT / "scripts/lambda_release_pack.py")
pack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pack)
COMMIT = "a" * 40


class LambdaReleasePackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        (self.repo / "src").mkdir(parents=True)
        self.sources = {"ocr": b"# OCR synthetic test module\n", "iot": b"# IoT synthetic test module\n"}
        for target, data in self.sources.items():
            (self.repo / pack.TARGETS[target][0]).write_bytes(data)
        def git(repo, *args):
            if args == ("rev-parse", "HEAD"):
                return (COMMIT + "\n").encode()
            for target in self.sources:
                if args == ("show", f"{COMMIT}:{pack.TARGETS[target][0]}"):
                    return self.sources[target]
            raise AssertionError(f"Unexpected git operation: {args}")
        self.mock_git = patch.object(pack, "git", side_effect=git)
        self.mock_git.start()
        self.addCleanup(self.mock_git.stop)

    def test_targets_preserve_source_bytes_and_verify(self):
        for target in self.sources:
            with self.subTest(target=target):
                out = self.root / target
                result = pack.build(self.repo, target, COMMIT, out)
                self.assertEqual(pack.verify(self.repo, target, COMMIT, out), result)
                with zipfile.ZipFile(out / "lambda.zip") as archive:
                    self.assertEqual(archive.namelist(), ["lambda_function.py"])
                    self.assertEqual(archive.read("lambda_function.py"), self.sources[target])
                self.assertEqual(result["deploymentStatus"], "not_deployed")
                self.assertIsNone(result["awsReadback"])

    def test_repeated_packs_are_byte_identical(self):
        first, second = self.root / "first", self.root / "second"
        pack.build(self.repo, "ocr", COMMIT, first)
        pack.build(self.repo, "ocr", COMMIT, second)
        for name in ("lambda.zip", "receipt.json"):
            self.assertEqual((first / name).read_bytes(), (second / name).read_bytes())

    def test_existing_output_and_symlink_are_preserved(self):
        out = self.root / "existing"
        out.mkdir()
        (out / "sentinel").write_bytes(b"keep")
        link = self.root / "link"
        link.symlink_to(out, target_is_directory=True)
        for path in (out, link):
            with self.subTest(path=path):
                with self.assertRaises(FileExistsError):
                    pack.build(self.repo, "ocr", COMMIT, path)
        self.assertEqual(list(out.iterdir()), [out / "sentinel"])
        self.assertEqual((out / "sentinel").read_bytes(), b"keep")

    def test_invalid_identity_leaves_no_output(self):
        for target, commit in (("all", COMMIT), ("ocr", "HEAD"), ("ocr", "b" * 40)):
            with self.subTest(target=target, commit=commit):
                out = self.root / "invalid"
                with self.assertRaises(ValueError):
                    pack.build(self.repo, target, commit, out)
                self.assertFalse(out.exists())

    def test_changed_or_symlinked_source_is_rejected(self):
        path = self.repo / pack.TARGETS["ocr"][0]
        path.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "working source"):
            pack.build(self.repo, "ocr", COMMIT, self.root / "changed")
        path.unlink()
        path.symlink_to(self.repo / pack.TARGETS["iot"][0])
        with self.assertRaisesRegex(ValueError, "regular file"):
            pack.build(self.repo, "ocr", COMMIT, self.root / "symlink")

    def test_output_inside_repo_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            pack.build(self.repo, "ocr", COMMIT, self.repo / "output")

    def test_tampered_zip_even_with_recomputed_receipt_is_rejected(self):
        out = self.root / "tampered"
        pack.build(self.repo, "ocr", COMMIT, out)
        source = b"replacement source"
        artifact = pack.package(source)
        (out / "lambda.zip").write_bytes(artifact)
        (out / "receipt.json").write_text(json.dumps(pack.receipt("ocr", COMMIT, source, artifact)))
        with self.assertRaisesRegex(ValueError, "trusted source"):
            pack.verify(self.repo, "ocr", COMMIT, out)

    def test_altered_receipt_or_wrong_target_is_rejected(self):
        out = self.root / "receipt"
        pack.build(self.repo, "ocr", COMMIT, out)
        with self.assertRaises(ValueError):
            pack.verify(self.repo, "iot", COMMIT, out)
        metadata = json.loads((out / "receipt.json").read_text())
        metadata["intendedSettings"]["timeoutSeconds"] = 900
        (out / "receipt.json").write_text(json.dumps(metadata))
        with self.assertRaises(ValueError):
            pack.verify(self.repo, "ocr", COMMIT, out)

    def test_incomplete_pack_is_rejected(self):
        out = self.root / "partial"
        out.mkdir()
        (out / "lambda.zip").write_bytes(pack.package(self.sources["ocr"]))
        with self.assertRaises(FileNotFoundError):
            pack.verify(self.repo, "ocr", COMMIT, out)


if __name__ == "__main__":
    unittest.main()
