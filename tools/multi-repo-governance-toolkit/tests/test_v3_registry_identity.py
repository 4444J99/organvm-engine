"""Regression checks for the V3 stable-ID reconciliation path (stdlib only)."""

import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "v3-registry-reconciliation.py"
SPEC = importlib.util.spec_from_file_location("v3_registry", SCRIPT)
V3 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(V3)


def fixture():
    registry = {"organs": {"ORGAN-I": {"repositories": [
        {"org": "old", "name": "alpha", "public": True,
         "implementation_status": "ACTIVE", "promotion_status": "LOCAL",
         "last_validated": "2020-01-01"},
        {"org": "new", "name": "beta", "public": False,
         "implementation_status": "ARCHIVED", "promotion_status": "ARCHIVED",
         "last_validated": "2020-01-01"},
    ]}}}
    raw = json.dumps(registry).encode()
    snapshot = {
        "snapshot_version": "organvm.registry-identity-snapshot.v1",
        "observed_at": "2026-09-08T15:00:00Z",
        "registry_blob_sha": hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest(),
        "installation_catalogue": [{"id": 3, "owner": "new"}],
        "installation_pages": [{"installation_id": 3, "owner": "new", "pages": [
            {"page_index": 0, "requested_page_size": 100, "repositories": ["10", "20"]},
        ]}],
        "collaborator_pages": [{"page_index": 0, "requested_page_size": 100, "repositories": []}],
        "repositories": [
            {"id": "10", "full_name": "new/alpha", "name": "alpha",
             "visibility": "public", "archived": False, "installation_id": 3},
            {"id": "20", "full_name": "new/beta", "name": "beta",
             "visibility": "private", "archived": True, "installation_id": 3},
        ],
        "resolutions": [
            {"row_key": "ORGAN-I:0", "requested_full_name": "old/alpha",
             "status": "resolved", "repository_id": "10", "full_name": "new/alpha"},
            {"row_key": "ORGAN-I:1", "requested_full_name": "new/beta",
             "status": "resolved", "repository_id": "20", "full_name": "new/beta"},
        ],
    }
    return registry, snapshot, raw


def rebind_bytes(registry, snapshot):
    raw = json.dumps(registry).encode()
    snapshot["registry_blob_sha"] = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    return raw


class IdentityReconciliationTests(unittest.TestCase):
    def test_requested_page_size_is_required_and_full_small_page_is_not_terminal(self):
        for page in ({"page_index": 0, "repositories": ["10"]},
                     {"page_index": 0, "requested_page_size": 1, "repositories": ["10"]}):
            with self.assertRaises(ValueError):
                V3._page_ids([page], "test")
        self.assertEqual(V3._page_ids([
            {"page_index": 0, "requested_page_size": 1, "repositories": ["10"]},
            {"page_index": 1, "requested_page_size": 1, "repositories": []},
        ], "test"), {"10"})

    def test_archived_override_requires_exact_boolean(self):
        for value in (1, 0, "true", None):
            registry, snapshot, _ = fixture()
            registry["organs"]["ORGAN-I"]["repositories"][1]["archived"] = value
            with self.assertRaisesRegex(ValueError, "archived override"):
                V3.reconcile_identity_snapshot(registry, snapshot, rebind_bytes(registry, snapshot))

    def test_nonempty_organ_mapping_with_zero_rows_is_rejected(self):
        registry, snapshot, _ = fixture()
        registry["organs"]["ORGAN-I"]["repositories"] = []
        with self.assertRaisesRegex(ValueError, "repository rows"):
            V3.reconcile_identity_snapshot(registry, snapshot, rebind_bytes(registry, snapshot))

    def test_transfer_is_bound_by_returned_id_and_activation_stays_unknown(self):
        registry, snapshot, raw = fixture()
        before = copy.deepcopy(registry)
        report = V3.reconcile_identity_snapshot(registry, snapshot, raw)
        self.assertEqual(report["summary"]["redirect_rows"], 1)
        self.assertFalse(report["reconciled"])
        self.assertIn("redirect_rows", report["blockers"])
        self.assertFalse(report["activation_verified"])
        self.assertTrue(all(row["activation_status"] == "unknown" for row in report["inventory_map"]))
        self.assertEqual(before, registry)

    def test_same_name_does_not_repair_failed_old_path(self):
        registry, snapshot, raw = fixture()
        snapshot["resolutions"][0].update(status="unavailable", repository_id=None, full_name=None)
        report = V3.reconcile_identity_snapshot(registry, snapshot, raw)
        self.assertEqual(report["registry_rows"][0]["same_name_candidates"][0]["repository_id"], "10")
        self.assertIsNone(report["registry_rows"][0]["repository_id"])
        self.assertFalse(report["reconciled"])

    def test_two_rows_resolving_one_id_require_alias_decision(self):
        registry, snapshot, _ = fixture()
        registry["organs"]["ORGAN-I"]["repositories"][1].update(org="other", name="alpha")
        snapshot["resolutions"][1].update(requested_full_name="other/alpha", repository_id="10", full_name="new/alpha")
        raw = rebind_bytes(registry, snapshot)
        report = V3.reconcile_identity_snapshot(registry, snapshot, raw)
        self.assertEqual(report["summary"]["bound_rows"], 2)
        self.assertEqual(report["summary"]["bound_unique_ids"], 1)
        self.assertEqual(report["duplicate_identities"][0]["disposition"], "alias-or-merge-decision-required")
        self.assertEqual(len(report["inventory_map"]), 2)

    def test_metadata_checks_include_redirects(self):
        registry, snapshot, raw = fixture()
        snapshot["repositories"][0].update(visibility="private", archived=True)
        report = V3.reconcile_identity_snapshot(registry, snapshot, raw)
        self.assertEqual(report["registry_rows"][0]["metadata_mismatches"], ["visibility", "archive"])
        self.assertFalse(report["reconciled"])

    def test_local_requires_explicit_local_evidence(self):
        registry, snapshot, _ = fixture()
        entry = registry["organs"]["ORGAN-I"]["repositories"][0]
        entry.update(org="local", note="Local-only (no remote).")
        snapshot["resolutions"][0].update(requested_full_name="local/alpha", status="unavailable", repository_id=None, full_name=None)
        raw = rebind_bytes(registry, snapshot)
        report = V3.reconcile_identity_snapshot(registry, snapshot, raw)
        self.assertEqual(report["registry_rows"][0]["binding"], "explicit-local")
        entry.pop("note")
        raw = rebind_bytes(registry, snapshot)
        report = V3.reconcile_identity_snapshot(registry, snapshot, raw)
        self.assertEqual(report["registry_rows"][0]["binding"], "unavailable")

    def test_wrong_registry_blob_is_rejected(self):
        registry, snapshot, raw = fixture()
        with self.assertRaisesRegex(ValueError, "blob SHA"):
            V3.reconcile_identity_snapshot(registry, snapshot, raw + b"\n")

    def test_skipped_page_index_is_rejected(self):
        registry, snapshot, raw = fixture()
        snapshot["installation_pages"][0]["pages"][0]["page_index"] = 100
        with self.assertRaisesRegex(ValueError, "contiguous"):
            V3.reconcile_identity_snapshot(registry, snapshot, raw)

    def test_unexhausted_hundred_result_page_is_rejected(self):
        registry, snapshot, raw = fixture()
        snapshot["installation_pages"][0]["pages"][0]["repositories"] = [str(n) for n in range(1, 101)]
        with self.assertRaisesRegex(ValueError, "not exhausted"):
            V3.reconcile_identity_snapshot(registry, snapshot, raw)

    def test_missing_installation_is_rejected(self):
        registry, snapshot, raw = fixture()
        snapshot["installation_catalogue"].append({"id": 4, "owner": "other"})
        with self.assertRaisesRegex(ValueError, "complete catalogue"):
            V3.reconcile_identity_snapshot(registry, snapshot, raw)

    def test_missing_inventory_id_is_rejected(self):
        registry, snapshot, raw = fixture()
        snapshot["repositories"].pop()
        with self.assertRaisesRegex(ValueError, "paginated ID union"):
            V3.reconcile_identity_snapshot(registry, snapshot, raw)

    def test_duplicate_inventory_id_is_rejected(self):
        registry, snapshot, raw = fixture()
        snapshot["repositories"].append(copy.deepcopy(snapshot["repositories"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate stable"):
            V3.reconcile_identity_snapshot(registry, snapshot, raw)

    def test_numeric_id_alias_cannot_create_a_second_identity(self):
        registry, snapshot, raw = fixture()
        snapshot["installation_pages"][0]["pages"][0]["repositories"].append("010")
        snapshot["repositories"].append(dict(snapshot["repositories"][0],
            id="010", full_name="new/other", name="other"))
        with self.assertRaisesRegex(ValueError, "invalid repository ID"):
            V3.reconcile_identity_snapshot(registry, snapshot, raw)

    def test_inventory_rejects_noncanonical_id_without_page_alias(self):
        registry, snapshot, raw = fixture()
        snapshot["repositories"][0]["id"] = "010"
        with self.assertRaisesRegex(ValueError, "invalid or duplicate stable"):
            V3.reconcile_identity_snapshot(registry, snapshot, raw)

    def test_page_ids_require_canonical_positive_ascii_decimal(self):
        for value in ("0", "00", "01", "+1", "-1", "1.0", "１", "", 1, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                V3._page_ids([{"page_index": 0, "requested_page_size": 100, "repositories": [value]}], "test")

    def test_nonpositive_installation_ids_are_invalid(self):
        for value in (0, -1, True):
            registry, snapshot, raw = fixture()
            snapshot["installation_catalogue"][0]["id"] = value
            snapshot["installation_pages"][0]["installation_id"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                V3.reconcile_identity_snapshot(registry, snapshot, raw)

    def test_malformed_receipt_objects_fail_as_invalid_input(self):
        for field in ("installation_catalogue", "installation_pages", "repositories", "resolutions"):
            registry, snapshot, raw = fixture()
            snapshot[field][0] = None
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "object"):
                V3.reconcile_identity_snapshot(registry, snapshot, raw)
        registry, snapshot, raw = fixture()
        snapshot["collaborator_pages"][0] = None
        with self.assertRaisesRegex(ValueError, "object"):
            V3.reconcile_identity_snapshot(registry, snapshot, raw)

    def test_cli_malformed_snapshot_exits_two_without_writing_report(self):
        registry, snapshot, raw = fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "registry.json").write_bytes(raw)
            (root / "snapshot.json").write_text("[]")
            with redirect_stderr(StringIO()) as stderr:
                result = V3.main(["--registry", str(root / "registry.json"), "--identity-snapshot", str(root / "snapshot.json"), "--output", str(root / "report.json")])
            self.assertEqual(result, 2)
            self.assertIn("INPUT INVALID", stderr.getvalue())
            self.assertFalse((root / "report.json").exists())

    def test_malformed_timestamps_are_invalid_input(self):
        for value in (None, 1, [], {}):
            registry, snapshot, raw = fixture()
            snapshot["observed_at"] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "timestamp"):
                V3.reconcile_identity_snapshot(registry, snapshot, raw)

    def test_malformed_summary_is_invalid_input(self):
        for value in (None, 1, [], "summary"):
            registry, snapshot, _ = fixture()
            registry["summary"] = value
            raw = rebind_bytes(registry, snapshot)
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "summary"):
                V3.reconcile_identity_snapshot(registry, snapshot, raw)

    def test_malformed_local_note_is_invalid_input(self):
        for value in (None, 1, [], {}):
            registry, snapshot, _ = fixture()
            registry["organs"]["ORGAN-I"]["repositories"][0].update(org="local", note=value)
            snapshot["resolutions"][0].update(requested_full_name="local/alpha", status="unavailable", repository_id=None, full_name=None)
            raw = rebind_bytes(registry, snapshot)
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "note"):
                V3.reconcile_identity_snapshot(registry, snapshot, raw)

    def test_wrong_canonical_resolution_is_rejected(self):
        registry, snapshot, raw = fixture()
        snapshot["resolutions"][0]["full_name"] = "new/beta"
        with self.assertRaisesRegex(ValueError, "disagrees"):
            V3.reconcile_identity_snapshot(registry, snapshot, raw)

    def test_missing_resolution_is_rejected(self):
        registry, snapshot, raw = fixture()
        snapshot["resolutions"].pop()
        with self.assertRaisesRegex(ValueError, "missing or wrong"):
            V3.reconcile_identity_snapshot(registry, snapshot, raw)

    def test_aggregate_output_contains_no_private_identifiers(self):
        registry, snapshot, raw = fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "registry.json").write_bytes(raw)
            (root / "snapshot.json").write_text(json.dumps(snapshot))
            with redirect_stdout(StringIO()) as stdout:
                result = V3.main(["--registry", str(root / "registry.json"), "--identity-snapshot", str(root / "snapshot.json"), "--output", str(root / "report.json"), "--aggregate-only"])
            text = (root / "report.json").read_text() + stdout.getvalue()
            self.assertEqual(result, 1)
            self.assertNotIn("beta", text)
            self.assertNotIn("new/alpha", text)
            self.assertEqual(json.loads((root / "report.json").read_text())["report_version"],
                             "organvm.v3-identity-reconciliation.aggregate.v1")
            self.assertEqual((root / "report.json").stat().st_mode & 0o777, 0o600)

    def test_output_cannot_overwrite_registry(self):
        registry, snapshot, raw = fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "registry.json").write_bytes(raw)
            (root / "snapshot.json").write_text(json.dumps(snapshot))
            with self.assertRaises(SystemExit):
                V3.main(["--registry", str(root / "registry.json"), "--identity-snapshot", str(root / "snapshot.json"), "--output", str(root / "registry.json")])
            self.assertEqual((root / "registry.json").read_bytes(), raw)

    def test_local_promotion_does_not_mean_local_repository(self):
        registry, snapshot, raw = fixture()
        snapshot["resolutions"][0].update(status="unavailable", repository_id=None, full_name=None)
        report = V3.reconcile_identity_snapshot(registry, snapshot, raw)
        self.assertEqual(report["registry_rows"][0]["binding"], "unavailable")

    def test_empty_registry_does_not_report_reconciled(self):
        registry, snapshot, _ = fixture()
        registry["organs"] = {}
        raw = rebind_bytes(registry, snapshot)
        with self.assertRaisesRegex(ValueError, "nonempty organ"):
            V3.reconcile_identity_snapshot(registry, snapshot, raw)

    def test_declared_count_drift_is_rejected(self):
        registry, snapshot, _ = fixture()
        registry["summary"] = {"total_repos": 3}
        raw = rebind_bytes(registry, snapshot)
        with self.assertRaisesRegex(ValueError, "declared total"):
            V3.reconcile_identity_snapshot(registry, snapshot, raw)


if __name__ == "__main__":
    unittest.main()
