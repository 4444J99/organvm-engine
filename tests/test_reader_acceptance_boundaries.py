"""Counterexamples for the September 9 reader-mode acceptance findings."""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from test_documentation import _load_assertion, _record, _write_assertion, _write_routes

from organvm_engine.contextmd.sync import sync_all
from organvm_engine.documentation.audit import audit_repository
from organvm_engine.documentation.record import validate_project_record

NOW = datetime(2026, 9, 9, 12, tzinfo=timezone.utc)
FIXTURES = Path(__file__).parent / "fixtures"


def _live_assertion(root, fact):
    assertion = _load_assertion(root)
    assertion["fact"] = fact
    assertion["assertion_class"] = "current_state"
    assertion["freshness"] = {
        "status": "fresh", "verified_at": NOW.isoformat(), "max_age_seconds": 3600,
    }
    artifact = assertion["evidence_references"][0]
    assertion["evidence_references"] = [
        {**artifact, "evidence_id": "owner", "evidence_type": "owner_record"},
        {**artifact, "evidence_id": "verifier", "evidence_type": "fresh_verifier_receipt", "observed_at": NOW.isoformat()},
    ]
    return assertion


@pytest.mark.parametrize("defect", ["missing", "wrong-subject", "wrong-value", "unverified", "proposed"])
def test_implementation_status_needs_its_own_verified_fact(tmp_path, defect):
    record = _record()
    _write_routes(tmp_path, record)
    path = tmp_path / "docs/evidence/claims/status.json"
    assertion = json.loads(path.read_text())
    assert validate_project_record(record, root=tmp_path, now=NOW) == []
    if defect == "missing":
        assertion.pop("fact")
    elif defect == "wrong-subject":
        assertion["fact"]["subject"] = "unrelated/project"
    elif defect == "wrong-value":
        assertion["fact"]["value"] = "ACTIVE"
    elif defect == "unverified":
        assertion["verification_state"] = "unverified"
    else:
        record["claim_references"][0]["claim_posture"] = "proposed"
    path.write_text(json.dumps(assertion))
    assert any("implementation_status" in error for error in validate_project_record(record, root=tmp_path, now=NOW))


@pytest.mark.parametrize("defect", ["history", "missing-subject", "wrong-subject", "expired"])
def test_live_deployment_needs_fresh_repository_bound_fact(tmp_path, defect):
    record = _record()
    _write_routes(tmp_path, record)
    record["deployment_status"] = "public"
    record["claim_references"][1]["scope"] = "deployment"
    assertion = _live_assertion(tmp_path, {
        "predicate": "deployment_status", "subject": "organvm/example", "value": "public",
    })
    _write_assertion(tmp_path, assertion)
    assert validate_project_record(record, root=tmp_path, now=NOW) == []
    if defect == "history":
        assertion["assertion_class"] = "historical_record"
        assertion.pop("freshness")
    elif defect == "expired":
        assertion["freshness"]["verified_at"] = "2025-01-01T00:00:00Z"
    elif defect == "missing-subject":
        assertion["fact"].pop("subject")
    else:
        assertion["fact"]["subject"] = "unrelated/project"
    _write_assertion(tmp_path, assertion)
    assert any("deployment_status" in error for error in validate_project_record(record, root=tmp_path, now=NOW))


@pytest.mark.parametrize("defect", ["history", "wrong-industry", "wrong-project", "wrong-state", "missing-fact", "expired"])
def test_industry_needs_exact_fresh_delivery_fact(tmp_path, defect):
    record = _record()
    _write_routes(tmp_path, record)
    record["industries"] = [{"name": "Education", "status": "piloted", "claim_references": ["validation"]}]
    record["claim_references"][1]["scope"] = "adoption"
    assertion = _live_assertion(tmp_path, {
        "predicate": "industry_status", "subject": "Education", "value": "piloted",
        "project_repository": "organvm/example",
    })
    _write_assertion(tmp_path, assertion)
    assert validate_project_record(record, root=tmp_path, now=NOW) == []
    if defect == "history":
        assertion["assertion_class"] = "historical_record"
        assertion.pop("freshness")
    elif defect == "expired":
        assertion["freshness"]["verified_at"] = "2025-01-01T00:00:00Z"
    elif defect == "missing-fact":
        assertion.pop("fact")
    else:
        field, value = {"wrong-industry": ("subject", "Finance"), "wrong-project": ("project_repository", "unrelated/project"), "wrong-state": ("value", "deployed")}[defect]
        assertion["fact"][field] = value
    _write_assertion(tmp_path, assertion)
    assert any("industry_status" in error for error in validate_project_record(record, root=tmp_path, now=NOW))


def test_reference_definitions_do_not_cross_document_boundaries(tmp_path):
    (tmp_path / "README.md").write_text("[dependency]\n\n[other]\n")
    (tmp_path / "definitions.md").write_text("[dependency]: https://github.com/example/one\n[other]: https://github.com/example/two\n")
    assert audit_repository(tmp_path)["signals"]["cross_linking"] == 0
    (tmp_path / "README.md").write_text("[dependency]\n\n[dependency]: https://github.com/example/one\n")
    assert audit_repository(tmp_path)["signals"]["cross_linking"] == 1


def _isolate(monkeypatch):
    monkeypatch.setattr("organvm_engine.contextmd.receipt.generator_git_identity", lambda **kw: {"commit": "a" * 40, "tree": "b" * 40})
    monkeypatch.setattr("organvm_engine.pulse.emitter.emit_engine_event", lambda **kw: None)
    monkeypatch.setattr("organvm_engine.ledger.emit.testament_emit", lambda **kw: None)


def test_relative_workspace_parent_spelling_still_receipts(tmp_path, monkeypatch):
    _isolate(monkeypatch)
    workspace = tmp_path / "estate"
    workspace.mkdir()
    caller = tmp_path / "caller"
    caller.mkdir()
    monkeypatch.chdir(caller)
    result = sync_all(workspace="../estate", registry_path=str(FIXTURES / "registry-minimal.json"), additional_workspace_roots=[], receipt_path=workspace / "receipt.json")
    assert result["errors"] == []
    assert (workspace / "receipt.json").is_file()
    assert (workspace / "CLAUDE.md").is_file()


@pytest.mark.parametrize("stage", ["parent-fsync", "cas-fsync", "parent-close", "cas-close"])
def test_post_install_failure_preserves_receipt_bound_context(tmp_path, monkeypatch, stage):
    import organvm_engine.contextmd.receipt as receipt_mod

    _isolate(monkeypatch)
    workspace = tmp_path / "estate"
    workspace.mkdir()
    target = workspace / "receipt.json"
    original = b"manual context\n"
    (workspace / "AGENTS.md").write_bytes(original)
    real_fsync = os.fsync
    real_close = os.close
    failed = False
    receipt_descriptors = {}
    real_open_parent = receipt_mod._open_absolute_parent_no_follow
    real_open_cas = receipt_mod._open_receipt_cas

    def capture_parent(path, subject, **kwargs):
        result = real_open_parent(path, subject, **kwargs)
        if path == target and kwargs.get("create_parents"):
            receipt_descriptors["parent-close"] = result[0]
        return result

    def capture_cas(*args, **kwargs):
        descriptor = real_open_cas(*args, **kwargs)
        receipt_descriptors["cas-close"] = descriptor
        return descriptor

    monkeypatch.setattr(receipt_mod, "_open_absolute_parent_no_follow", capture_parent)
    monkeypatch.setattr(receipt_mod, "_open_receipt_cas", capture_cas)

    def fail_after_receipt_install(descriptor):
        nonlocal failed
        opened = os.fstat(descriptor)
        parent = target.parent.stat()
        is_parent = (opened.st_dev, opened.st_ino) == (parent.st_dev, parent.st_ino)
        if stage.endswith("fsync") and target.exists() and not failed and (is_parent == (stage == "parent-fsync")):
            failed = True
            raise OSError("simulated post-install fsync failure")
        return real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fail_after_receipt_install)

    def fail_parent_close(descriptor):
        nonlocal failed
        real_close(descriptor)
        if target.exists() and not failed and descriptor == receipt_descriptors.get(stage):
            failed = True
            raise OSError("simulated post-install close failure")

    monkeypatch.setattr(os, "close", fail_parent_close)
    with pytest.raises(RuntimeError, match="receipt installed"):
        sync_all(workspace=workspace, registry_path=str(FIXTURES / "registry-minimal.json"), additional_workspace_roots=[], receipt_path=target)
    assert failed
    receipt = json.loads(target.read_text())
    for binding in receipt["outputs"]:
        output = workspace / binding["path"]
        assert "sha256:" + hashlib.sha256(output.read_bytes()).hexdigest() == binding["sha256"]
    assert (workspace / "AGENTS.md").read_bytes() != original
