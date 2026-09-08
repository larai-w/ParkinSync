import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import p4_run_all as runner


class RunnerTests(unittest.TestCase):
    def test_relative_output_uses_caller_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            previous = Path.cwd()
            os.chdir(tmp)
            calls = []
            def fake(command, cwd):
                calls.append(command)
                return {'returnCode': 0}
            try:
                with patch.object(sys, 'argv', ['runner', '--output-dir', 'result']), patch.object(runner, 'run', fake), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(runner.main(), 0)
                self.assertTrue((Path(tmp) / 'result/manifest.json').is_file())
                for command in calls:
                    for flag in ('--labels', '--output'):
                        if flag in command:
                            self.assertTrue(Path(command[command.index(flag) + 1]).is_absolute())
            finally:
                os.chdir(previous)

    def test_existing_evidence_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / 'manifest.json'
            marker.write_text('old evidence')
            with patch.object(sys, 'argv', ['runner', '--output-dir', tmp]), patch.object(runner, 'run') as run, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    runner.main()
                run.assert_not_called()
            self.assertEqual(marker.read_text(), 'old evidence')
