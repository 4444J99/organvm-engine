import os, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_sample_registry_missing_target_is_caught(tmp_path):
    env = dict(os.environ, REGISTRY_PATH=str(ROOT / "examples" / "sample-registry.json"),
               V4_REPORT=str(tmp_path / "v4-report.json"))
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "v4-dependency-validation.py")],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 1
    assert "example-org/web -> example-org/auth (NOT IN REGISTRY)" in r.stdout
    assert "Total violations: 1" in r.stdout
