"""The portable DONE-ID validator must read the selected corpus checkout."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check-done-id.py"


def prepare_corpus(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "done-id-counter.json").write_text(json.dumps({"next_id": 43}))
    (tmp_path / "INST-INDEX-RERUM-FACIENDARUM.md").write_text("| DONE-42 | Finished work |\n")


@pytest.mark.parametrize("staged", [False, True])
def test_explicit_corpus_root_works_outside_the_toolkit(tmp_path, staged):
    prepare_corpus(tmp_path)
    flags = []
    if staged:
        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
        flags.append("--staged")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(tmp_path), *flags],
        text=True, capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert "max=DONE-42" in result.stdout


def test_current_directory_is_the_default_corpus_root(tmp_path):
    prepare_corpus(tmp_path)
    result = subprocess.run([sys.executable, str(SCRIPT)], cwd=tmp_path,
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


def test_missing_corpus_inputs_report_a_configuration_error(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(tmp_path)],
        text=True, capture_output=True,
    )
    assert result.returncode == 2
    assert "--repo-root" in result.stderr
    assert "Traceback" not in result.stderr
