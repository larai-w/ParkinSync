import json
import unittest
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "caregiver-observation.synthetic.json"
SCHEMA = ROOT / "docs" / "schemas" / "caregiver-observation-v1.schema.json"


class CaregiverObservationContractTests(unittest.TestCase):
    def test_schema_declares_the_public_v1_boundary(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(schema["$id"], "https://veai.jp/schemas/caregiver-observation/v1.json")
        self.assertEqual(schema["properties"]["schemaVersion"]["const"], "caregiver-observation/v1")
        self.assertEqual(
            schema["properties"]["observationType"]["enum"],
            ["fall", "assistance_required"],
        )
        self.assertEqual(schema["properties"]["actorRole"]["const"], "caregiver")
        self.assertEqual(schema["additionalProperties"], False)

    def test_synthetic_fixture_preserves_actor_and_missingness(self):
        events = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(len(events), 2)
        for event in events:
            self.assertEqual(event["schemaVersion"], "caregiver-observation/v1")
            self.assertEqual(event["eventType"], "caregiver_observation")
            self.assertEqual(event["actorRole"], "caregiver")
            self.assertIn(event["missingness"], {"observed", "confirmed_none", "not_recorded"})
            self.assertEqual(event["provenance"]["source"], "parkinsync")
            datetime.fromisoformat(event["observedAt"])
            datetime.fromisoformat(event["recordedAt"])

    def test_unknown_observation_type_is_not_part_of_v1(self):
        event = json.loads(FIXTURE.read_text(encoding="utf-8"))[0]
        event["observationType"] = "gait_risk"
        self.assertNotIn(event["observationType"], {"fall", "assistance_required"})


if __name__ == "__main__":
    unittest.main()
