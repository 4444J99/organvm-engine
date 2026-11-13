"""Tests for the read-only promotion queue and the dry-run promotion check."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from organvm_engine.governance import promotion_queue as pq
from organvm_engine.governance.state_machine import execute_transition


def _entry(name, status, **kw):
    base = {
        "name": name,
        "org": "acme",
        "promotion_status": status,
        "tier": "standard",
        "functional_class": "ENGINE",
    }
    base.update(kw)
    return base


@pytest.fixture
def infra(monkeypatch):
    """Control the infrastructure audit: failures keyed by repo name."""
    failures: dict[str, list[str]] = {}

    def fake(repo_path, repo_name, organ, org, current_status, target_status, tier):
        f = failures.get(repo_name, [])
        return (not f), list(f)

    monkeypatch.setattr("organvm_engine.ci.audit.check_promotion_infrastructure", fake)
    return failures


def test_terminal_states_have_no_forward_step():
    for state in ("GRADUATED", "ARCHIVED"):
        assert pq.assess_repo("ORGAN-I", _entry("x", state), repo_path=None) is None


def test_no_checkout_is_unverified_not_ready():
    a = pq.assess_repo("ORGAN-I", _entry("x", "LOCAL"), repo_path=None)
    assert a.status == pq.STATUS_UNVERIFIED
    assert (a.current, a.target) == ("LOCAL", "CANDIDATE")
    assert a.checkout is None


def test_clean_checkout_is_ready(infra, tmp_path):
    a = pq.assess_repo("ORGAN-I", _entry("x", "CANDIDATE"), repo_path=tmp_path)
    assert a.status == pq.STATUS_READY
    assert a.target == "PUBLIC_PROCESS"
    assert a.blockers == []


def test_missing_functional_class_blocks(infra, tmp_path):
    entry = _entry("x", "LOCAL")
    del entry["functional_class"]
    a = pq.assess_repo("ORGAN-I", entry, repo_path=tmp_path)
    assert a.status == pq.STATUS_BLOCKED
    assert "registry: missing functional_class" in a.blockers


def test_infrastructure_failures_become_blockers(infra, tmp_path):
    infra["x"] = ["ci_workflow", "readme"]
    a = pq.assess_repo("ORGAN-I", _entry("x", "LOCAL"), repo_path=tmp_path)
    assert a.status == pq.STATUS_BLOCKED
    assert a.blockers == ["infrastructure: ci_workflow", "infrastructure: readme"]


def test_audit_crash_is_a_blocker_not_a_crash(monkeypatch, tmp_path):
    def boom(**_kw):
        raise RuntimeError("disk gone")

    monkeypatch.setattr("organvm_engine.ci.audit.check_promotion_infrastructure", boom)
    a = pq.assess_repo("ORGAN-I", _entry("x", "LOCAL"), repo_path=tmp_path)
    assert a.status == pq.STATUS_BLOCKED
    assert a.blockers == ["audit-error: RuntimeError: disk gone"]


def _registry():
    return {
        "organs": {
            "ORGAN-I": {
                "repositories": [
                    _entry("blocked-one", "LOCAL", functional_class=""),
                    _entry("ready-one", "CANDIDATE"),
                    _entry("done", "GRADUATED"),
                ],
            },
            "ORGAN-II": {"repositories": [_entry("other", "PUBLIC_PROCESS")]},
        },
    }


def test_build_queue_orders_and_filters(infra, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "organvm_engine.ci.mandate._resolve_repo_path",
        lambda org, name, organ, ws, key_to_dir: None if name == "other" else tmp_path,
    )
    queue = pq.build_queue(_registry(), workspace=tmp_path)
    assert [a.repo for a in queue] == ["ready-one", "other", "blocked-one"]
    assert [a.status for a in queue] == ["ready", "unverified", "blocked"]

    only_ii = pq.build_queue(_registry(), workspace=tmp_path, organ="ORGAN-II")
    assert [a.repo for a in only_ii] == ["other"]


def test_summary_and_format(infra, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "organvm_engine.ci.mandate._resolve_repo_path",
        lambda *a, **k: tmp_path,
    )
    queue = pq.build_queue(_registry(), workspace=tmp_path)
    s = pq.summarize(queue)
    assert s["total"] == 3
    assert s["by_status"] == {"ready": 2, "blocked": 1}
    assert s["by_step"]["LOCAL->CANDIDATE"] == 1
    assert s["top_blockers"][0]["blocker"] == "registry: missing functional_class"
    text = pq.format_queue(queue, limit=1)
    assert "3 repos with a forward step" in text
    assert "2 more" in text
    json.dumps([a.to_dict() for a in queue])


def test_dry_run_emits_nothing_and_records_no_history(monkeypatch, tmp_path: Path):
    emitted = []
    monkeypatch.setattr(
        "organvm_engine.governance.state_machine._emit_spine_event",
        lambda **kw: emitted.append(kw),
    )
    monkeypatch.setattr(
        "organvm_engine.governance.state_machine.emit_promotion_event",
        lambda *a, **k: emitted.append(a),
    )
    entry = _entry("x", "LOCAL")
    ok, msg = execute_transition(
        "x", "LOCAL", "CANDIDATE", registry_entry=entry, enforce_infrastructure=False,
        dry_run=True,
    )
    assert ok and "dry run" in msg
    assert emitted == []
    assert "promotion_history" not in entry

    ok, _ = execute_transition(
        "x", "LOCAL", "CANDIDATE", registry_entry=entry, enforce_infrastructure=False,
    )
    assert ok and len(emitted) == 2
    assert entry.get("promotion_history")


def test_dry_run_still_rejects_invalid_transition():
    ok, msg = execute_transition("x", "LOCAL", "GRADUATED", dry_run=True)
    assert not ok
    assert "Cannot transition" in msg
