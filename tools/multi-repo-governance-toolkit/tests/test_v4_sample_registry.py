import os, subprocess, sys
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_sample_registry_missing_target_is_caught(tmp_path):
    env = dict(os.environ, REGISTRY_PATH=str(ROOT / "examples" / "sample-registry.json"),
               V4_REPORT=str(tmp_path / "v4-report.json"))
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "v4-dependency-validation.py")],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 1
    assert "example-org/web -> example-org/auth (NOT IN REGISTRY)" in r.stdout
    assert "Total violations: 1" in r.stdout


@pytest.mark.parametrize("source_organ,target_organ,violation", [
    ("ORGAN-I", "ORGAN-III", True),
    ("ORGAN-II", "ORGAN-III", True),
    ("ORGAN-III", "ORGAN-II", True),
    ("ORGAN-III", "ORGAN-I", False),
])
def test_organ_rules_survive_github_owner_changes(tmp_path, source_organ, target_organ, violation):
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"organs": {
        source_organ: {"repositories": [{
            "org": "renamed-owner", "name": "source", "dependencies": ["renamed-owner/target"],
        }]},
        target_organ: {"repositories": [{"org": "renamed-owner", "name": "target"}]},
    }}))
    report_path = tmp_path / "report.json"
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "v4-dependency-validation.py")],
        capture_output=True, text=True,
        env=dict(os.environ, REGISTRY_PATH=str(registry), V4_REPORT=str(report_path)),
    )
    assert result.returncode == int(violation), result.stdout + result.stderr
    report = json.loads(report_path.read_text())
    assert report["back_edges"] == int(violation)
    assert report["missing_targets"] == 0
