"""Replay the captured zero-step CI payload (run 34762163480) through the adapter.

The run's three jobs were assigned no runner (runner_id 0, no steps) and GitHub
badged them failure/cancelled. That is infrastructure non-execution, not a test
failure and never a pass. The fixture is the exact-field transcription recorded
in the provenance file; it is not a raw-response archive.
"""
import json
from pathlib import Path

import pytest

from organvm_engine.ci.runtime_evidence import evaluate_run, main

FIXTURES = Path(__file__).parent / "fixtures" / "ci_evidence"
STEM = "github-ci-34762163480"


def _load(kind: str) -> dict:
    return json.loads((FIXTURES / f"{STEM}.{kind}.json").read_text())


def test_live_zero_step_payload_reproduces_recorded_report():
    actual, recorded = evaluate_run(**_load("input")), _load("report")
    # The recorded report lists jobs in a different job order; compare by job id.
    for report in (actual, recorded):
        report["jobs"] = sorted(report["jobs"], key=lambda job: job["job_id"])
    assert actual == recorded


def test_live_zero_step_payload_is_not_executed_not_failure():
    report = evaluate_run(**_load("input"))
    assert report["decision"] == "not_executed"
    assert all(job["state"] == "not_executed" and job["executed_required"] == 0
               for job in report["jobs"])
    assert not report["authorizes_release"] and not report["authorizes_execution"]


def test_provenance_discloses_no_authentication_and_no_write():
    provenance = _load("provenance")
    assert provenance["no_authentication_claim_from_adapter"] is True
    assert provenance["no_merge"] is True and provenance["no_rerun"] is True
    assert provenance["job_coverage"].startswith("three returned unique rows")


@pytest.mark.parametrize("mutation", ["wrong_head", "wrong_repository", "wrong_attempt"])
def test_live_payload_with_wrong_pin_is_refused(mutation):
    data = _load("input")
    if mutation == "wrong_head":
        data["expected_revision"] = "0" * 40
    elif mutation == "wrong_repository":
        data["expected_repository_id"] += 1
    else:
        data["expected_attempt"] = 2
    with pytest.raises(ValueError):
        evaluate_run(**data)


def test_live_payload_missing_job_page_is_incomplete_not_not_executed():
    data = _load("input")
    data["jobs_pages"][0]["total_count"] = 4
    assert evaluate_run(**data)["decision"] == "incomplete"


def test_cli_exit_codes_on_live_payload(capsys):
    assert main([str(FIXTURES / f"{STEM}.input.json")]) == 1
    assert json.loads(capsys.readouterr().out)["decision"] == "not_executed"
