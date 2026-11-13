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


def initialize_corpus_index(tmp_path):
    prepare_corpus(tmp_path)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=Test Fixture",
                    "-c", "user.email=fixture@example.invalid", "commit", "-qm", "initial corpus"], check=True)


def invoke_corpus(tmp_path, *flags):
    return subprocess.run([sys.executable, str(SCRIPT), "--repo-root", str(tmp_path), *flags],
                          text=True, capture_output=True)


def test_staged_assignment_cannot_reuse_an_unchanged_assignment(tmp_path):
    initialize_corpus_index(tmp_path)
    irf = tmp_path / "INST-INDEX-RERUM-FACIENDARUM.md"
    irf.write_text(irf.read_text() + "| DONE-42 | Different assignment |\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", str(irf)], check=True)

    result = invoke_corpus(tmp_path, "--staged")

    assert result.returncode == 1
    assert "Duplicate DONE-ID assignment(s)" in result.stderr


def test_staged_counter_must_cover_the_staged_assignment(tmp_path):
    initialize_corpus_index(tmp_path)
    (tmp_path / "data" / "done-id-counter.json").write_text(json.dumps({"next_id": 44}))
    irf = tmp_path / "INST-INDEX-RERUM-FACIENDARUM.md"
    irf.write_text(irf.read_text() + "| DONE-43 | New assignment |\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", str(irf)], check=True)

    result = invoke_corpus(tmp_path, "--staged")

    assert result.returncode == 1
    assert "counter next_id (43)" in result.stderr


def test_rewording_one_staged_assignment_does_not_duplicate_it(tmp_path):
    initialize_corpus_index(tmp_path)
    irf = tmp_path / "INST-INDEX-RERUM-FACIENDARUM.md"
    irf.write_text("| DONE-42 | Revised description |\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", str(irf)], check=True)
    assert invoke_corpus(tmp_path, "--staged").returncode == 0


def test_full_file_mode_rejects_duplicate_assignments(tmp_path):
    prepare_corpus(tmp_path)
    irf = tmp_path / "INST-INDEX-RERUM-FACIENDARUM.md"
    irf.write_text(irf.read_text() + "| DONE-42 | Different assignment |\n")
    result = invoke_corpus(tmp_path)
    assert result.returncode == 1
    assert "Duplicate DONE-ID assignment(s)" in result.stderr


def test_five_digit_ids_are_checked_without_counting_date_form_ids(tmp_path):
    prepare_corpus(tmp_path)
    irf = tmp_path / "INST-INDEX-RERUM-FACIENDARUM.md"
    irf.write_text("| DONE-42 | Refers to DONE-2026-04-30 |\n")
    assert invoke_corpus(tmp_path).returncode == 0
    irf.write_text("| DONE-10000 | Exceeds the counter |\n")
    result = invoke_corpus(tmp_path)
    assert result.returncode == 1
    assert "10000" in result.stderr
