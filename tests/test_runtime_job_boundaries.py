"""Each required step belongs to its own job, independent of enumeration order."""

import copy

import pytest

from organvm_engine.ci.runtime_evidence import evaluate_run

HEAD = "a" * 40


def moment(minutes):
    """Return a synthetic UTC timestamp inside the captured run's bounds."""
    return f"2026-09-13T12:{minutes:02d}:00Z"


def payload():
    """Build two sequential jobs with nonoverlapping execution windows."""
    run = {"repository": {"id": 1}, "workflow_id": 2, "id": 3, "run_attempt": 1,
           "head_sha": HEAD, "status": "completed", "conclusion": "success",
           "created_at": moment(0), "run_started_at": moment(0),
           "updated_at": "2026-09-13T13:00:00Z"}
    jobs = []
    for identity, name, start in [(4, "test", 2), (6, "lint", 22)]:
        jobs.append({
            "id": identity, "run_id": 3, "run_attempt": 1, "head_sha": HEAD,
            "name": name, "runner_id": identity + 100, "status": "completed",
            "conclusion": "success", "created_at": moment(start - 1),
            "started_at": moment(start), "completed_at": moment(start + 8),
            "updated_at": moment(start + 9),
            "steps": [{"number": 1, "name": "Run " + name, "status": "completed",
                       "conclusion": "success", "started_at": moment(start + 1),
                       "completed_at": moment(start + 2)}],
        })
    return {"run": run, "jobs_pages": [{"total_count": 2, "jobs": jobs}],
            "expected_repository_id": 1, "expected_workflow_id": 2,
            "expected_run_id": 3, "expected_attempt": 1, "expected_revision": HEAD,
            "required_steps": {"test": ["Run test"], "lint": ["Run lint"]},
            "observed_at": "2026-09-13T14:00:00Z"}


@pytest.mark.parametrize("reverse_jobs", [False, True])
@pytest.mark.parametrize("reverse_requirements", [False, True])
@pytest.mark.parametrize("split_pages", [False, True])
def test_valid_job_windows_do_not_depend_on_enumeration_order(
        reverse_jobs, reverse_requirements, split_pages):
    """Job ID, not the final row or a requirement position, owns timestamps."""
    data = payload()
    jobs = data["jobs_pages"][0]["jobs"]
    if reverse_jobs:
        jobs.reverse()
    if reverse_requirements:
        data["required_steps"] = dict(reversed(list(data["required_steps"].items())))
    if split_pages:
        data["jobs_pages"] = [{"total_count": 2, "jobs": [job]} for job in jobs]
    report = evaluate_run(**data)
    assert report["decision"] == "executed_pass"
    assert {job["job_id"] for job in report["jobs"]} == {4, 6}
    assert all(job["executed_required"] == 1 for job in report["jobs"])
    assert not report["authorizes_execution"] and not report["authorizes_release"]


@pytest.mark.parametrize("other_bounds", ["absent", "broad"])
@pytest.mark.parametrize("violated_bound", ["created_at", "started_at", "completed_at", "updated_at"])
def test_unrelated_job_cannot_erase_or_replace_required_job_bounds(other_bounds, violated_bound):
    """Each available parent bound rejects its own invalid child step."""
    data = payload()
    first, other = data["jobs_pages"][0]["jobs"]
    data["required_steps"] = {"test": ["Run test"]}
    bound_names = ("created_at", "started_at", "completed_at", "updated_at")
    for name in bound_names:
        first.pop(name)
        other.pop(name)
    first[violated_bound] = moment(10)
    early = violated_bound in {"created_at", "started_at"}
    first["steps"][0].update(started_at=moment(5 if early else 15),
                             completed_at=moment(6 if early else 16))
    if other_bounds == "broad":
        other.update(created_at=moment(0), started_at=moment(0),
                     completed_at=moment(59), updated_at=moment(59))
    with pytest.raises(ValueError, match="parent job"):
        evaluate_run(**data)


def test_nonrequired_sibling_cannot_reject_a_valid_required_job():
    """A later optional job's narrower window is unrelated to earlier tests."""
    data = payload()
    data["required_steps"] = {"test": ["Run test"]}
    assert evaluate_run(**data)["decision"] == "executed_pass"


def test_valid_bound_failure_is_preserved_across_jobs():
    """Correct timestamp association must not hide an executed test failure."""
    data = payload()
    first = data["jobs_pages"][0]["jobs"][0]
    first["conclusion"] = first["steps"][0]["conclusion"] = "failure"
    data["run"]["conclusion"] = "failure"
    assert evaluate_run(**data)["decision"] == "executed_failure"


def test_unexecuted_sibling_remains_unexecuted():
    """A successful first job does not turn a zero-step sibling into a pass."""
    data = payload()
    data["jobs_pages"][0]["jobs"][1].update(runner_id=0, steps=[], conclusion="failure")
    data["run"]["conclusion"] = "failure"
    assert evaluate_run(**data)["decision"] == "not_executed"


def test_partial_pagination_remains_incomplete():
    """Timestamp repair does not waive independent enumeration completeness."""
    data = payload()
    data["jobs_pages"][0]["jobs"] = data["jobs_pages"][0]["jobs"][:1]
    assert evaluate_run(**data)["decision"] == "incomplete"


def test_required_step_must_still_fit_parent_run():
    """Missing job bounds never erase an available run observation boundary."""
    data = payload()
    first = data["jobs_pages"][0]["jobs"][0]
    for field in ("created_at", "started_at", "completed_at", "updated_at"):
        first.pop(field)
    first["steps"][0].update(started_at="2026-09-13T13:10:00Z",
                             completed_at="2026-09-13T13:11:00Z")
    with pytest.raises(ValueError, match="parent run"):
        evaluate_run(**data)


def test_input_payload_is_not_mutated():
    """Indexing parsed timestamps must not modify captured collector evidence."""
    data = payload()
    original = copy.deepcopy(data)
    evaluate_run(**data)
    assert data == original
