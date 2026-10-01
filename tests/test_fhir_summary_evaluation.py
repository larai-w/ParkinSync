import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

from fhir_summary import validate_summary_candidate
from fhir_summary_evaluation import evaluate_summary_gate

ROOT = Path(__file__).resolve().parents[1]


class SummaryEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.bundle = json.loads((ROOT / 'fhir/generated/bundle-synthetic-transaction-bundle.json').read_text())

    def test_audit_is_repeatable_does_not_mutate_and_separates_evidence(self):
        before = copy.deepcopy(self.bundle)
        result = evaluate_summary_gate(self.bundle)
        self.assertEqual(result, evaluate_summary_gate(self.bundle))
        self.assertEqual(self.bundle, before)
        self.assertEqual(len({r['id'] for r in result['cases']}), 12)
        self.assertFalse(result['model_called'])
        self.assertFalse(result['sharing_permitted'])
        for row in result['cases']:
            if row['stage'] != 'candidate':
                self.assertNotEqual(row['outcome'], 'detected')
        self.assertTrue(all(r['control_accepted'] for r in result['cases'] if r['stage'] == 'candidate'))

    def test_always_rejecting_gate_is_not_scored_as_detection(self):
        def reject(candidate, facts):
            return {'validation': {'accepted': False, 'errors': [{'code': 'reject-all'}]}}
        result = evaluate_summary_gate(self.bundle, reject)
        rows = [r for r in result['cases'] if r['stage'] == 'candidate']
        self.assertTrue(rows)
        self.assertTrue(all(r['outcome'] == 'control_rejected' for r in rows))

    def test_always_accepting_gate_exposes_all_candidate_mutations(self):
        def accept(candidate, facts):
            return {'validation': {'accepted': True, 'errors': []}}
        result = evaluate_summary_gate(self.bundle, accept)
        self.assertTrue(all(r['outcome'] == 'missed' for r in result['cases'] if r['stage'] == 'candidate'))

    def test_mutations_are_assessed_against_valid_synthetic_facts(self):
        def inspect(candidate, facts):
            self.assertEqual(facts['classification'], 'synthetic')
            self.assertEqual(facts['status'], 'ready')
            return validate_summary_candidate(candidate, facts)
        evaluate_summary_gate(self.bundle, inspect)

    def test_cli_exit_status_reports_unresolved_gaps(self):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/evaluate_summary_gate.py')], capture_output=True, text=True, cwd=ROOT.parent)
        report = json.loads(result.stdout)
        unresolved = any(r['outcome'] in {'missed', 'control_rejected', 'source_not_blocked'} for r in report['cases'])
        self.assertEqual(result.returncode, int(unresolved), result.stderr)

    def test_incomplete_source_is_not_scored(self):
        self.bundle['entry'] = []
        with self.assertRaisesRegex(ValueError, 'ready synthetic'):
            evaluate_summary_gate(self.bundle)
