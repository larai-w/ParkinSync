import copy
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from fhir_roundtrip import RoundTripError, verify_roundtrip


ROOT = Path(__file__).resolve().parents[1]
BUNDLE_PATH = (
    ROOT
    / "fhir"
    / "weekly"
    / "generated"
    / "bundle-synthetic-weekly-transaction-bundle.json"
)


def rewrite_references(value, full_url_identities):
    if isinstance(value, list):
        return [rewrite_references(item, full_url_identities) for item in value]
    if not isinstance(value, dict):
        return value
    rewritten = {}
    for key, item in value.items():
        if key == "reference" and item in full_url_identities:
            rewritten[key] = full_url_identities[item]
        else:
            rewritten[key] = rewrite_references(item, full_url_identities)
    return rewritten


class MockFhirHandler(BaseHTTPRequestHandler):
    stored = {}
    fhir_version = "4.0.1"
    post_status = 200
    omit_response_entry = False
    bad_location = False
    omit_location = False
    changed_identity = None

    def _send(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/fhir+json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/fhir/metadata":
            self._send(
                200,
                {
                    "resourceType": "CapabilityStatement",
                    "fhirVersion": self.fhir_version,
                    "software": {"name": "Mock FHIR", "version": "test"},
                    "rest": [{"mode": "server"}],
                },
            )
            return
        prefix = "/fhir/"
        identity = path[len(prefix) :] if path.startswith(prefix) else ""
        resource = self.stored.get(identity)
        if resource is None:
            self._send(404, {"resourceType": "OperationOutcome"})
            return
        resource = copy.deepcopy(resource)
        if identity == self.changed_identity:
            resource["valueQuantity"]["value"] = 99.9
        self._send(200, resource)

    def do_POST(self):
        if urlparse(self.path).path != "/fhir":
            self._send(404, {"resourceType": "OperationOutcome"})
            return
        if self.post_status != 200:
            self._send(self.post_status, {"resourceType": "OperationOutcome"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        bundle = json.loads(self.rfile.read(length))
        full_url_identities = {
            entry["fullUrl"]: entry["request"]["url"] for entry in bundle["entry"]
        }
        response_entries = []
        for entry in bundle["entry"]:
            identity = entry["request"]["url"]
            resource = rewrite_references(
                copy.deepcopy(entry["resource"]), full_url_identities
            )
            resource.setdefault("meta", {}).update(
                {"versionId": "1", "lastUpdated": "2035-01-08T00:00:00Z"}
            )
            self.stored[identity] = resource
            location = identity + "/_history/1"
            if self.bad_location and not response_entries:
                location = "Patient/wrong-id/_history/1"
            response = {"status": "201 Created", "location": location}
            if self.omit_location and not response_entries:
                response.pop("location")
            response_entries.append({"response": response})
        if self.omit_response_entry:
            response_entries.pop()
        self._send(
            200,
            {
                "resourceType": "Bundle",
                "type": "transaction-response",
                "entry": response_entries,
            },
        )

    def log_message(self, format, *args):
        return


class FhirRoundTripTests(unittest.TestCase):
    def setUp(self):
        self.bundle = json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))
        MockFhirHandler.stored = {}
        MockFhirHandler.fhir_version = "4.0.1"
        MockFhirHandler.post_status = 200
        MockFhirHandler.omit_response_entry = False
        MockFhirHandler.bad_location = False
        MockFhirHandler.omit_location = False
        MockFhirHandler.changed_identity = None
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), MockFhirHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}/fhir"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_verifies_every_resource_after_transaction(self):
        report = verify_roundtrip(self.base_url, self.bundle)

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["classification"], "synthetic")
        self.assertEqual(report["resource_count"], 30)
        self.assertEqual(report["checks"]["semantic_matches"], 30)
        self.assertEqual(report["checks"]["synthetic_tags"], 30)
        self.assertEqual(report["checks"]["subject_references_resolved"], 29)
        self.assertEqual(report["transaction_outcomes"], {"201": 30})

    def test_rejects_non_r4_server(self):
        MockFhirHandler.fhir_version = "4.0.0"

        with self.assertRaisesRegex(RoundTripError, "must declare R4 4.0.1"):
            verify_roundtrip(self.base_url, self.bundle)

    def test_rejects_transaction_http_failure(self):
        MockFhirHandler.post_status = 422

        with self.assertRaisesRegex(RoundTripError, "POST / returned HTTP 422"):
            verify_roundtrip(self.base_url, self.bundle)

    def test_rejects_missing_transaction_response_entry(self):
        MockFhirHandler.omit_response_entry = True

        with self.assertRaisesRegex(RoundTripError, "entry count does not match"):
            verify_roundtrip(self.base_url, self.bundle)

    def test_rejects_wrong_transaction_location(self):
        MockFhirHandler.bad_location = True

        with self.assertRaisesRegex(RoundTripError, "location does not match"):
            verify_roundtrip(self.base_url, self.bundle)

    def test_rejects_missing_transaction_location(self):
        MockFhirHandler.omit_location = True

        with self.assertRaisesRegex(RoundTripError, "has no resource location"):
            verify_roundtrip(self.base_url, self.bundle)

    def test_rejects_non_synthetic_resource_before_post(self):
        resource = self.bundle["entry"][0]["resource"]
        resource["meta"]["tag"] = []

        with self.assertRaisesRegex(RoundTripError, "lacks synthetic classification"):
            verify_roundtrip(self.base_url, self.bundle)
        self.assertEqual(MockFhirHandler.stored, {})

    def test_rejects_non_loopback_server_before_post(self):
        with self.assertRaisesRegex(RoundTripError, "must use a loopback URL"):
            verify_roundtrip("https://example.org/fhir", self.bundle)
        self.assertEqual(MockFhirHandler.stored, {})

    def test_rejects_missing_read_back_resource(self):
        missing_identity = "CarePlan/synthetic-weekly-observation-plan"
        original_do_post = MockFhirHandler.do_POST

        def do_post_and_remove(handler):
            original_do_post(handler)
            handler.stored.pop(missing_identity, None)

        MockFhirHandler.do_POST = do_post_and_remove
        try:
            with self.assertRaisesRegex(RoundTripError, "returned HTTP 404"):
                verify_roundtrip(self.base_url, self.bundle)
        finally:
            MockFhirHandler.do_POST = original_do_post

    def test_rejects_changed_clinical_value(self):
        MockFhirHandler.changed_identity = (
            "Observation/synthetic-20350101-observation-body-temperature"
        )

        with self.assertRaisesRegex(RoundTripError, "valueQuantity.value"):
            verify_roundtrip(self.base_url, self.bundle)


if __name__ == "__main__":
    unittest.main()
