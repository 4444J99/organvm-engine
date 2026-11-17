"""Registered CI workflows survive seed generation without path injection."""

import importlib.util
from pathlib import Path
import unittest

import yaml


SPEC = importlib.util.spec_from_file_location(
    "seed_generator", Path(__file__).parents[1] / "scripts/generate-seed-yaml.py"
)
generator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generator)


class WorkflowRepresentationTests(unittest.TestCase):
    def seed(self, workflow):
        return yaml.safe_load(generator.generate_seed_yaml(
            {"name": "sample", "org": "example", "ci_workflow": workflow},
            "ORGAN-I", "I", "Theory", "Python",
        ))

    def test_custom_and_template_workflows_survive_generation(self):
        for name in ("ci.yml", "quality.yml", "python-package.yml", "ci-pipeline.yml",
                     "ci-python.yml", "ci-typescript.yml", "ci-mixed.yml",
                     "ci-minimal.yml", "test_suite.yaml"):
            with self.subTest(name=name):
                self.assertEqual(self.seed(name)["agents"][0]["workflow"],
                                 f".github/workflows/{name}")

    def test_legacy_exact_path_is_normalized_once(self):
        self.assertEqual(self.seed(".github/workflows/ci.yml")["agents"][0]["workflow"],
                         ".github/workflows/ci.yml")

    def test_unknown_workflow_does_not_invent_an_agent(self):
        for value in (None, ""):
            self.assertEqual(self.seed(value)["agents"], [])

    def test_malformed_values_fail_instead_of_omitting_ci(self):
        for value in (False, 0, [], {}, "../ci.yml", "/ci.yml", "sub/ci.yml",
                      "ci.yml\n", "ci.yml\n  injected: true", "ci.txt",
                      ".github/workflows/../ci.yml", "ci.yml@main"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.seed(value)
