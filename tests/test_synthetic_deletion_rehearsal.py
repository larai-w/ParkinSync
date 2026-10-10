import contextlib
from copy import deepcopy
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('deletion', Path(__file__).resolve().parents[1] / 'analytics/synthetic_deletion_rehearsal.py')
deletion = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deletion)

class DeletionRehearsalTests(unittest.TestCase):
    def test_unknown_subject_is_rejected(self):
        with self.assertRaises(ValueError):
            deletion.rehearse('NOT-A-SYNTHETIC-SUBJECT')

    def test_cli_unknown_subject_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'new'
            out, err = io.StringIO(), io.StringIO()
            with patch('sys.argv', ['rehearse', '--subject', 'PRIVATE-SENTINEL', '--output-dir', str(output)]), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                self.assertEqual(deletion.main(), 3)
            self.assertFalse(output.exists())
            self.assertNotIn('PRIVATE-SENTINEL', out.getvalue() + err.getvalue())

    def test_same_count_other_event_mutation_is_red(self):
        real = deletion.withdraw
        def broken(events, mapping, subject):
            result, new_mapping, removed = real(events, mapping, subject)
            result[0]['payload']['changed'] = True
            return result, new_mapping, removed
        with patch.object(deletion, 'withdraw', broken):
            report = deletion.rehearse()
        self.assertEqual(report['result'], 'RED')
        self.assertFalse(report['otherSubjectsIntact'])

    def test_other_mapping_mutation_is_red(self):
        real = deletion.withdraw
        def broken(events, mapping, subject):
            result, new_mapping, removed = real(events, mapping, subject)
            new_mapping['synthetic-person-002'] = 'CHANGED'
            return result, new_mapping, removed
        with patch.object(deletion, 'withdraw', broken):
            report = deletion.rehearse()
        self.assertEqual(report['result'], 'RED')
        self.assertFalse(report['otherSubjectsIntact'])

    def test_each_known_subject_removes_only_their_records(self):
        for subject in ('synthetic-person-001', 'synthetic-person-002'):
            with self.subTest(subject=subject):
                report = deletion.rehearse(subject)
                self.assertEqual(report['result'], 'GREEN')
                self.assertEqual(report['removedEventCount'], 10)
                self.assertEqual(report['storeEventsAfter'], 10)
                self.assertEqual(report['mappingEntriesAfter'], 1)
                self.assertTrue(report['otherSubjectsIntact'])

if __name__ == '__main__': unittest.main()
