"""Tests for the evidence collector (organvm-engine #189).

The wired path is exercised offline: a fake fetch returns captured payloads,
so no test touches the network or a credential. The two captured runs are the
evidence record itself — the September zero-step failure (run 34762163480)
and the current main run (44909979065 at 1e4bec99).
"""
import copy
import json
from pathlib import Path

import pytest

from organvm_engine.ci.evidence_collector import collect_run_evidence, load_required_steps

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "ci_evidence"

HEAD = "a" * 40
REQUIRED = {"test": ["Run tests"]}


def _payload(**overrides):
    run = {"repository": {"id": 1}, "workflow_id": 2, "id": 3, "run_attempt": 1,
           "head_sha": HEAD, "status": "completed", "conclusion": "success",
           "created_at": "2026-09-13T13:00:00Z", "run_started_at": "2026-09-13T13:00:01Z",
           "updated_at": "2026-09-13T13:01:00Z"}
    job = {"id": 4, "run_id": 3, "run_attempt": 1, "head_sha": HEAD, "name": "test",
           "runner_id": 5, "status": "completed", "conclusion": "success",
           "created_at": "2026-09-13T13:00:02Z", "started_at": "2026-09-13T13:00:03Z",
           "completed_at": "2026-09-13T13:00:59Z", "updated_at": "2026-09-13T13:01:00Z",
           "steps": [{"number": 1, "name": "Run tests", "status": "completed",
                      "conclusion": "success", "started_at": "2026-09-13T13:00:04Z",
                      "completed_at": "2026-09-13T13:00:58Z"}]}
    data = {"run": run, "jobs_pages": [{"total_count": 1, "jobs": [job]}],
            "expected_repository_id": 1, "expected_workflow_id": 2,
            "expected_run_id": 3, "expected_attempt": 1, "expected_revision": HEAD,
            "required_steps": copy.deepcopy(REQUIRED),
            "observed_at": "2026-09-13T14:00:00Z"}
    data.update(overrides)
    return data


def _fetch_for(data):
    run_id = data["expected_run_id"]
    calls = []

    def fetch(url):
        calls.append(url)
        if url.endswith(f"/actions/runs/{run_id}"):
            return copy.deepcopy(data["run"])
        if "/jobs?" in url:
            return copy.deepcopy(data["jobs_pages"][0])
        raise AssertionError(f"unexpected url {url}")

    fetch.calls = calls
    return fetch


def _collect(data, **kwargs):
    return collect_run_evidence(
        owner="4444J99", repo="organvm-engine", run_id=data["expected_run_id"],
        expected_repository_id=data["expected_repository_id"],
        expected_revision=data["expected_revision"],
        expected_workflow_id=data["expected_workflow_id"],
        expected_run_id=data["expected_run_id"],
        expected_attempt=data["expected_attempt"],
        required_steps=data["required_steps"],
        observed_at=data["observed_at"],
        fetch=_fetch_for(data),
        **kwargs,
    )


def test_wired_path_reports_executed_pass():
    report = _collect(_payload())
    assert report["decision"] == "executed_pass"
    assert report["jobs"][0]["state"] == "executed_pass"
    assert report["jobs"][0]["runner_id"] == 5
    assert report["collection"]["pages_fetched"] == 1
    assert report["collection"]["token_source"] == "injected-fetch"
    assert report["collection"]["run_source"].endswith("/actions/runs/3")
    assert not report["authorizes_release"] and not report["authorizes_execution"]


def test_wired_path_reproduces_captured_zero_step_failure():
    data = json.loads((FIXTURES / "github-ci-34762163480.input.json").read_text())
    report = _collect(data)
    assert report["decision"] == "not_executed"
    assert all(job["state"] == "not_executed" for job in report["jobs"])
    expected = json.loads((FIXTURES / "github-ci-34762163480.report.json").read_text())
    assert report["decision"] == expected["decision"]
    assert report["payload_digest"] == expected["payload_digest"]


def test_wired_path_reproduces_captured_main_run():
    data = json.loads((FIXTURES / "github-ci-44909979065.input.json").read_text())
    report = _collect(data)
    assert report["decision"] == "executed_pass"
    assert {job["name"]: job["state"] for job in report["jobs"]} == {
        "test-matrix (3.11)": "executed_pass",
        "test-matrix (3.12)": "executed_pass",
        "test": "executed_pass",
    }
    expected = json.loads((FIXTURES / "github-ci-44909979065.report.json").read_text())
    assert report["decision"] == expected["decision"]
    assert report["payload_digest"] == expected["payload_digest"]
    assert report["requirements_digest"] == expected["requirements_digest"]


@pytest.mark.parametrize("field,value", [
    ("expected_repository_id", 9), ("expected_run_id", 9),
    ("expected_workflow_id", 9), ("expected_attempt", 2),
    ("expected_revision", "b" * 40),
])
def test_wrong_pinned_identity_is_rejected(field, value):
    with pytest.raises(ValueError):
        _collect(_payload(**{field: value}))


def test_mixed_attempt_job_is_rejected():
    data = _payload()
    data["jobs_pages"][0]["jobs"][0]["run_attempt"] = 2
    with pytest.raises(ValueError):
        _collect(data)


def test_wrong_head_job_is_rejected():
    data = _payload()
    data["jobs_pages"][0]["jobs"][0]["head_sha"] = "b" * 40
    with pytest.raises(ValueError):
        _collect(data)


def test_zero_step_payload_through_wired_path_is_not_executed():
    data = _payload()
    data["run"]["conclusion"] = "failure"
    data["jobs_pages"][0]["jobs"][0].update(runner_id=0, steps=[], conclusion="failure")
    report = _collect(data)
    assert report["decision"] == "not_executed"
    assert report["jobs"][0]["executed_required"] == 0


def test_paginated_jobs_are_assembled():
    data = _payload()
    job = data["jobs_pages"][0]["jobs"][0]
    second = copy.deepcopy(job)
    second.update(id=6, name="test-matrix (3.11)", steps=[
        {"number": 1, "name": "Run tests", "status": "completed", "conclusion": "success",
         "started_at": "2026-09-13T13:00:04Z", "completed_at": "2026-09-13T13:00:58Z"}])
    pages = [{"total_count": 2, "jobs": [job]}, {"total_count": 2, "jobs": [second]}]
    calls = []

    def fetch(url):
        calls.append(url)
        if url.endswith("/actions/runs/3"):
            return copy.deepcopy(data["run"])
        page = int(url.rsplit("page=", 1)[1])
        return copy.deepcopy(pages[page - 1])

    report = collect_run_evidence(
        owner="4444J99", repo="organvm-engine", run_id=3,
        expected_repository_id=1, expected_revision=HEAD, expected_workflow_id=2,
        expected_run_id=3, expected_attempt=1,
        required_steps={"test": ["Run tests"], "test-matrix (3.11)": ["Run tests"]},
        observed_at="2026-09-13T14:00:00Z", fetch=fetch,
    )
    assert report["decision"] == "executed_pass"
    assert report["collection"]["pages_fetched"] == 2
    assert report["observed_job_count"] == 2
    assert len(calls) == 3  # run + 2 jobs pages


def test_inconsistent_page_total_is_rejected():
    data = _payload()
    data["jobs_pages"][0]["total_count"] = 2  # claims 2 jobs, returns 1
    with pytest.raises(ValueError):
        _collect(data)


def test_missing_token_fails_closed(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    with pytest.raises(ValueError, match="no GitHub token"):
        collect_run_evidence(
            owner="4444J99", repo="organvm-engine", run_id=3,
            expected_repository_id=1, expected_revision=HEAD, expected_workflow_id=2,
            required_steps=REQUIRED, observed_at="2026-09-13T14:00:00Z",
        )


def test_token_never_appears_in_report():
    data = _payload()
    report = collect_run_evidence(
        owner="4444J99", repo="organvm-engine", run_id=3,
        expected_repository_id=1, expected_revision=HEAD, expected_workflow_id=2,
        expected_run_id=3, expected_attempt=1, required_steps=REQUIRED,
        observed_at="2026-09-13T14:00:00Z", token="ghp_test-token-value",
        fetch=_fetch_for(data),
    )
    assert "ghp_test-token-value" not in json.dumps(report)


def test_invalid_repository_is_rejected():
    with pytest.raises(ValueError, match="invalid repository"):
        collect_run_evidence(
            owner="bad owner!", repo="organvm-engine", run_id=3,
            expected_repository_id=1, expected_revision=HEAD, expected_workflow_id=2,
            required_steps=REQUIRED, fetch=lambda url: {},
        )


def test_load_required_steps_envelope_and_bare(tmp_path):
    envelope = tmp_path / "contract.json"
    envelope.write_text(json.dumps({
        "schema_version": "organvm.github-execution-evidence.v1",
        "workflow": ".github/workflows/ci.yml",
        "workflow_blob": "f" * 40,
        "required_steps": {"test": ["Run tests"]},
    }))
    mapping, metadata = load_required_steps(envelope)
    assert mapping == {"test": ["Run tests"]}
    assert metadata["workflow_blob"] == "f" * 40

    bare = tmp_path / "bare.json"
    bare.write_text(json.dumps({"test": ["Run tests"]}))
    mapping, metadata = load_required_steps(bare)
    assert mapping == {"test": ["Run tests"]}
    assert metadata == {}


def test_load_required_steps_rejects_bad_contract(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"test": ["Run tests", "Run tests"]}))
    with pytest.raises(ValueError, match="required steps"):
        load_required_steps(bad)
    bad.write_text(json.dumps({}))
    with pytest.raises(ValueError, match="required steps"):
        load_required_steps(bad)


def test_cli_evidence_subcommand_parses():
    from organvm_engine.cli import build_parser

    args = build_parser().parse_args([
        "ci", "evidence", "--repo", "4444J99/organvm-engine", "--run-id", "44909979065",
        "--revision", HEAD, "--repository-id", "1160447354", "--workflow-id", "235510053",
        "--required-steps", "tests/fixtures/ci_evidence/organvm-engine-ci-required-steps.json",
    ])
    assert args.command == "ci" and args.subcommand == "evidence"
    assert args.attempt == 1
    assert args.run_id == 44909979065


def test_contract_fixture_matches_live_workflow():
    mapping, metadata = load_required_steps(
        FIXTURES / "organvm-engine-ci-required-steps.json")
    assert metadata["pinned_base"] == "1e4bec99a450d4c29338923c9a2e3396dc31756a"
    assert set(mapping) == {"test", "test-matrix (3.11)", "test-matrix (3.12)"}
    assert mapping["test"] == ["Require all matrix legs to pass"]


# --- redirect credential handling -------------------------------------------


def _serve(handler_cls):
    import threading
    from http.server import HTTPServer

    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _handler(seen, *, redirect_to=None):
    from http.server import BaseHTTPRequestHandler

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            seen.append(self.headers.get("Authorization"))
            if redirect_to is not None:
                self.send_response(302)
                self.send_header("Location", redirect_to)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body = b'{"ok": true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    return Handler


def test_authorization_dropped_on_cross_origin_redirect():
    from organvm_engine.ci.evidence_collector import _default_fetch

    target_seen: list = []
    origin_seen: list = []
    target = _serve(_handler(target_seen))
    origin = _serve(_handler(
        origin_seen, redirect_to=f"http://127.0.0.1:{target.server_port}/final",
    ))
    try:
        result = _default_fetch(f"http://127.0.0.1:{origin.server_port}/start", "tok-secret")
    finally:
        origin.shutdown()
        target.shutdown()
    assert result == {"ok": True}
    assert origin_seen == ["Bearer tok-secret"]
    assert target_seen == [None]


def test_authorization_kept_on_same_origin_redirect():
    from organvm_engine.ci.evidence_collector import _default_fetch

    seen: list = []
    # Redirect to the same origin: first hop redirects, second serves.
    hops = {"n": 0}
    from http.server import BaseHTTPRequestHandler

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            seen.append(self.headers.get("Authorization"))
            if hops["n"] == 0:
                hops["n"] += 1
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/b")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body = b'{"ok": true}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = _serve(Handler)
    try:
        _default_fetch(f"http://127.0.0.1:{server.server_port}/a", "tok-secret")
    finally:
        server.shutdown()
    assert seen == ["Bearer tok-secret", "Bearer tok-secret"]
