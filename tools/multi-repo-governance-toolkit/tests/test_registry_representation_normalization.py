"""Mechanical spelling repairs must preserve lifecycle and custody evidence."""

import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location(
    "normalizer", Path(__file__).parents[1] / "scripts/normalize-registry-representations.py"
)
normalizer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(normalizer)


class NormalizationTests(unittest.TestCase):
    def test_only_known_representations_change_and_second_pass_is_empty(self):
        rows = [
            {"ci_workflow": "", "last_validated": "historical", "private": True},
            {"ci_workflow": ".github/workflows/ci.yml", "functional_class": "infrastructure",
             "promotion_obligations": [{"status": "COMPLETE"}], "id": 123},
            {"ci_workflow": "quality.yml", "revenue_status": None},
        ]
        data = {"organs": {"test": {"public_visibility": "MOSTLY PUBLIC", "repositories": rows}}}
        result, counts = normalizer.normalize(data)
        self.assertEqual(counts, {"empty_workflow": 1, "workflow_prefix": 1, "class_case": 1,
                                 "visibility_caption": 0})
        expected = [dict(r) for r in rows]
        expected[0]["ci_workflow"] = None
        expected[1].update(ci_workflow="ci.yml", functional_class="INFRASTRUCTURE")
        self.assertEqual(result, {"organs": {"test": {
            "public_visibility": "MOSTLY PUBLIC", "repositories": expected}}})
        self.assertEqual(rows[0]["ci_workflow"], "")
        again, counts = normalizer.normalize(result)
        self.assertEqual(again, result)
        self.assertFalse(any(counts.values()))

    def test_unknown_or_malformed_values_remain_visible(self):
        rows = [{"ci_workflow": value} for value in (
            False, [], {}, None, ".github/workflows/../ci.yml", ".github/workflows/ci.yml\n")]
        data = {"organs": {"test": {"repositories": rows}}}
        result, counts = normalizer.normalize(data)
        self.assertEqual(result, data)
        self.assertFalse(any(counts.values()))

    def test_historical_captions_survive_without_becoming_live_counts(self):
        for caption, policy in (
            ("MIXED (4 private, 18 public)", "MIXED"),
            ("SEMI-PUBLIC (Governance visible, implementation details private)", "SEMI-PUBLIC"),
            ("SEMI-PUBLIC (invitations, participation)", "SEMI-PUBLIC"),
        ):
            data = {"organs": {"test": {"public_visibility": caption, "repositories": []}}}
            result, counts = normalizer.normalize(data)
            self.assertEqual(result["organs"]["test"], {
                "public_visibility": policy, "public_visibility_note": caption, "repositories": []})
            self.assertEqual(counts["visibility_caption"], 1)
            self.assertFalse(any(normalizer.normalize(result)[1].values()))

    def test_conflicting_notes_are_not_overwritten(self):
        data = {"organs": {"test": {"public_visibility": "MIXED (4 private, 18 public)",
                                  "public_visibility_note": "another policy qualifier", "repositories": []}}}
        with self.assertRaises(ValueError):
            normalizer.normalize(data)
