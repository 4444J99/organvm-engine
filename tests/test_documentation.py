"""Tests for reader-mode documentation records and repository audits."""

from __future__ import annotations

import hashlib
import json
import subprocess
from argparse import Namespace
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from organvm_engine.cli import build_parser
from organvm_engine.cli.docs import cmd_docs_audit, cmd_docs_validate
from organvm_engine.documentation.audit import audit_repository, discover_repositories
from organvm_engine.documentation.record import validate_project_record


def _record(doc_class: str = "B") -> dict:
    audiences = [
        {
            "mode": "general",
            "path": "docs/audiences/general.md",
            "primary_question": "What is this and why does it matter?",
            "surface": "public",
        },
        {
            "mode": "technical",
            "path": "docs/audiences/technical.md",
            "primary_question": "How is the project implemented and verified?",
            "surface": "public",
        },
    ]
    if doc_class == "A":
        audiences.extend(
            [
                {
                    "mode": "humanities",
                    "path": "docs/audiences/humanities.md",
                    "primary_question": "What ideas and cultural problems does it engage?",
                    "surface": "public",
                },
                {
                    "mode": "business",
                    "path": "docs/audiences/business.md",
                    "primary_question": "What operational problem does this change?",
                    "surface": "public",
                },
                {
                    "mode": "evaluator",
                    "path": "docs/audiences/evaluator.md",
                    "primary_question": "What was built and where is the evidence?",
                    "surface": "public",
                },
            ],
        )
    elif doc_class in {"D", "F"}:
        audiences = []
    record = {
        "contract_name": "project-record.v1",
        "contract_version": 1,
        "project_id": "example",
        "name": "Example",
        "canonical_repository": "organvm/example",
        "repository_role": "canonical",
        "documentation_class": doc_class,
        "one_sentence": "A sufficiently specific ordinary-language project definition.",
        "problem": "Different readers require different routes through the same facts.",
        "intended_users": ["maintainers"],
        "implementation_status": "PROTOTYPE",
        "deployment_status": "not-deployed",
        "authorship": {
            "owner": "Anthony James Padavano",
            "role": "designer and implementer",
            "contributions": ["architecture"],
        },
        "claim_references": [
            {
                "id": "project-status",
                "assertion_contract": "assertion-evidence.v1",
                "assertion_id": "project-status",
                "assertion_ref": "docs/evidence/claims/status.json",
                "scope": "status",
                "claim_posture": "implemented",
            },
            {
                "id": "validation",
                "assertion_contract": "assertion-evidence.v1",
                "assertion_id": "validation",
                "assertion_ref": "docs/evidence/claims/validation.json",
                "scope": "capability",
                "claim_posture": "implemented",
            },
        ],
        "limitations": [{"id": "no-adoption", "statement": "No adoption claim is made."}],
        "audience_routes": audiences,
        "industries": [],
        "concepts": ["progressive-disclosure"],
        "search_intents": [],
        "links": {
            "repository": "https://github.com/organvm/example",
            "documentation": (
                "README.md" if doc_class in {"D", "F"} else "docs/audiences/general.md"
            ),
            "evidence": "docs/evidence/README.md",
        },
        "generated_at": "2026-08-31T20:00:00Z",
        "verified_at": "2026-08-31T20:00:00Z",
    }
    if doc_class == "A":
        record["claim_references"].append(
            {
                "id": "authorship",
                "assertion_contract": "assertion-evidence.v1",
                "assertion_id": "validation",
                "assertion_ref": "docs/evidence/claims/validation.json",
                "scope": "authorship",
                "claim_posture": "implemented",
            },
        )
    return record


def _write_routes(root: Path, record: dict) -> None:
    for route in record["audience_routes"]:
        path = root / route["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {route['mode']}\n", encoding="utf-8")
    documentation_path = root / record["links"]["documentation"]
    if not documentation_path.is_file():
        documentation_path.parent.mkdir(parents=True, exist_ok=True)
        documentation_path.write_text("# Project documentation\n", encoding="utf-8")
    evidence_readme = root / "docs/evidence/README.md"
    evidence_readme.parent.mkdir(parents=True, exist_ok=True)
    evidence_readme.write_text("# Evidence\n", encoding="utf-8")
    evidence_source = root / "docs/evidence/sources/validation.txt"
    evidence_source.parent.mkdir(parents=True, exist_ok=True)
    evidence_source.write_text("committed validation receipt\n", encoding="utf-8")
    digest = "sha256:" + hashlib.sha256(evidence_source.read_bytes()).hexdigest()
    assertion = root / "docs/evidence/claims/validation.json"
    assertion.parent.mkdir(parents=True, exist_ok=True)
    assertion.write_text(
        json.dumps(
            {
                "contract_name": "assertion-evidence.v1",
                "contract_version": 1,
                "assertion_id": "validation",
                "assertion_class": "historical_record",
                "statement": "The local validation fixture exists.",
                "verification_state": "verified",
                "evidence_references": [
                    {
                        "evidence_id": "validation-receipt",
                        "independence_group": "local-fixture",
                        "evidence_type": "artifact",
                        "reference": "docs/evidence/sources/validation.txt",
                        "body_hash": digest,
                    },
                ],
            },
        ),
        encoding="utf-8",
    )
    status_assertion = json.loads(assertion.read_text(encoding="utf-8"))
    status_assertion["assertion_id"] = "project-status"
    status_source = root / "docs/evidence/sources/status.txt"
    status_source.write_bytes(b"committed implementation status\n")
    status_assertion["evidence_references"][0].update({
        "reference": status_source.relative_to(root).as_posix(),
        "body_hash": "sha256:" + hashlib.sha256(status_source.read_bytes()).hexdigest(),
    })
    status_assertion["fact"] = {
        "predicate": "implementation_status",
        "subject": record["canonical_repository"],
        "value": record["implementation_status"],
    }
    (assertion.parent / "status.json").write_text(
        json.dumps(status_assertion), encoding="utf-8",
    )


def _assertion_path(root: Path) -> Path:
    return root / "docs/evidence/claims/validation.json"


def _load_assertion(root: Path) -> dict:
    return json.loads(_assertion_path(root).read_text(encoding="utf-8"))


def _write_assertion(root: Path, assertion: dict) -> None:
    _assertion_path(root).write_text(json.dumps(assertion), encoding="utf-8")


def _current_state_assertion(assertion: dict) -> dict:
    assertion["assertion_class"] = "current_state"
    assertion["freshness"] = {
        "status": "fresh",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "max_age_seconds": 3600,
    }
    artifact = assertion["evidence_references"][0]
    assertion["evidence_references"] = [
        {**artifact, "evidence_id": "owner", "evidence_type": "owner_record"},
        {
            **artifact, "evidence_id": "verifier", "evidence_type": "fresh_verifier_receipt",
            "observed_at": assertion["freshness"]["verified_at"],
        },
    ]
    return assertion


def _git(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
    )
    return result.stdout


def _commit_fixture(root: Path) -> str:
    _git(root, "init")
    _git(root, "config", "user.name", "Reader Mode Tests")
    _git(root, "config", "user.email", "reader-mode@example.test")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "fixture")
    return _git(root, "rev-parse", "HEAD").decode().strip()


def test_validate_project_record_accepts_complete_class_a(tmp_path):
    record = _record("A")
    _write_routes(tmp_path, record)
    assert validate_project_record(record, root=tmp_path) == []


def test_validate_project_record_rejects_duplicate_and_unknown_evidence(tmp_path):
    record = _record()
    _write_routes(tmp_path, record)
    record["claim_references"].append(dict(record["claim_references"][0]))
    record["industries"] = [
        {"name": "Education", "status": "piloted", "claim_references": ["missing"]},
    ]
    errors = validate_project_record(record, root=tmp_path)
    assert "duplicate claim reference id: project-status" in errors
    assert any("unknown claim id: missing" in error for error in errors)


def test_deployed_industry_requires_evidence(tmp_path):
    record = _record()
    _write_routes(tmp_path, record)
    record["industries"] = [{"name": "Education", "status": "deployed"}]
    errors = validate_project_record(record, root=tmp_path)
    assert any("requires claim_references" in error for error in errors)


def test_proposed_industry_does_not_require_deployment_evidence(tmp_path):
    record = _record()
    _write_routes(tmp_path, record)
    record["industries"] = [{"name": "Education", "status": "proposed"}]
    assert validate_project_record(record, root=tmp_path) == []


def test_limitation_assertion_reference_is_loaded_and_id_bound(tmp_path):
    record = _record()
    _write_routes(tmp_path, record)
    record["limitations"][0].update(
        {
            "assertion_id": "wrong-id",
            "assertion_ref": "docs/evidence/claims/validation.json",
        },
    )

    errors = validate_project_record(record, root=tmp_path)
    assert (
        "limitations[0] assertion_id does not match docs/evidence/claims/validation.json"
        in errors
    )


def test_industry_evidence_scope_verification_and_proposed_inference(tmp_path):
    record = _record()
    _write_routes(tmp_path, record)
    record["industries"] = [
        {
            "name": "Education",
            "status": "piloted",
            "claim_references": ["validation"],
        },
    ]
    assertion = _load_assertion(tmp_path)
    assertion["verification_state"] = "unverified"
    _write_assertion(tmp_path, assertion)

    errors = validate_project_record(record, root=tmp_path)
    assert any("must use deployment or adoption scope" in error for error in errors)
    assert any("must resolve to a verified assertion" in error for error in errors)

    proposed = _record()
    _write_routes(tmp_path, proposed)
    proposed["industries"] = [
        {
            "name": "Education",
            "status": "proposed",
            "claim_references": ["validation"],
        },
    ]
    proposed_errors = validate_project_record(proposed, root=tmp_path)
    assert any("requires claim_posture 'proposed'" in error for error in proposed_errors)
    assert any("must resolve to a labeled inference" in error for error in proposed_errors)


def test_validate_project_record_checks_all_local_documentation_paths(tmp_path):
    record = _record()
    _write_routes(tmp_path, record)
    record["links"]["evidence"] = "docs/evidence/missing.md"
    record["industries"] = [
        {"name": "Education", "status": "proposed", "path": "docs/industries/education.md"},
    ]
    record["limitations"][0]["assertion_ref"] = "docs/evidence/claims/missing.json"
    record["limitations"][0]["assertion_id"] = "missing"

    errors = validate_project_record(record, root=tmp_path)
    assert "links.evidence does not exist: docs/evidence/missing.md" in errors
    assert "industries[0] path does not exist: docs/industries/education.md" in errors
    assert (
        "limitations[0] assertion path does not exist: docs/evidence/claims/missing.json"
        in errors
    )


def test_validate_project_record_rejects_duplicate_semantic_keys(tmp_path):
    record = _record()
    _write_routes(tmp_path, record)
    record["limitations"].append(dict(record["limitations"][0]))
    record["industries"] = [
        {"name": "Education", "status": "proposed"},
        {"name": "education", "status": "proposed"},
    ]
    record["search_intents"] = [
        {"intent": "technical", "terms": ["project schema"]},
        {"intent": "technical", "terms": ["documentation schema"]},
    ]

    errors = validate_project_record(record, root=tmp_path)
    assert "duplicate limitation id: no-adoption" in errors
    assert "duplicate industry name: education" in errors
    assert "duplicate search intent: technical" in errors


def test_duplicate_audience_route_paths_are_rejected(tmp_path):
    record = _record()
    record["audience_routes"].append(
        {
            "mode": "business",
            "path": "docs/audiences/general.md",
            "primary_question": "What operational problem does this address?",
            "surface": "public",
        },
    )
    _write_routes(tmp_path, record)

    assert "duplicate audience route path: docs/audiences/general.md" in (
        validate_project_record(record, root=tmp_path)
    )


def test_status_deployment_and_evaluator_claim_coverage(tmp_path):
    record = _record()
    _write_routes(tmp_path, record)
    record["claim_references"] = [
        claim for claim in record["claim_references"] if claim["scope"] != "status"
    ]
    assert "project record requires a 'status' claim reference" in (
        validate_project_record(record, root=tmp_path)
    )

    public = _record()
    public["deployment_status"] = "public"
    _write_routes(tmp_path, public)
    assert "deployment_status 'public' requires a 'deployment' claim reference" in (
        validate_project_record(public, root=tmp_path)
    )

    evaluator = _record()
    evaluator["audience_routes"].append(
        {
            "mode": "evaluator",
            "path": "docs/audiences/evaluator.md",
            "primary_question": "What was built and where is the evidence?",
            "surface": "public",
        },
    )
    _write_routes(tmp_path, evaluator)
    assert "evaluator audience route requires an 'authorship' claim reference" in (
        validate_project_record(evaluator, root=tmp_path)
    )


def test_pilot_and_public_deployments_require_bounded_verified_claims(tmp_path):
    for deployment_status in ("pilot", "public"):
        record = _record()
        _write_routes(tmp_path, record)
        deployment_claim = {
            **record["claim_references"][1],
            "id": f"{deployment_status}-deployment",
            "scope": "deployment",
            "claim_posture": "proposed",
        }
        record["deployment_status"] = deployment_status
        record["claim_references"].append(deployment_claim)

        errors = validate_project_record(record, root=tmp_path)
        assert any(
            "requires at least one deployment claim with claim_posture" in error
            for error in errors
        )

        deployment_claim["claim_posture"] = "partial"
        assertion = _load_assertion(tmp_path)
        assertion["fact"] = {
            "predicate": "deployment_status",
            "value": deployment_status,
            "subject": record["canonical_repository"],
        }
        _write_assertion(tmp_path, _current_state_assertion(assertion))
        assert validate_project_record(record, root=tmp_path) == []

        assertion["verification_state"] = "unverified"
        _write_assertion(tmp_path, assertion)
        assert any(
            "qualifying deployment claim that resolves to a verified assertion"
            in error
            for error in validate_project_record(record, root=tmp_path)
        )


def test_retired_deployment_requires_verified_history_or_unavailability(tmp_path):
    record = _record()
    _write_routes(tmp_path, record)
    deployment_claim = {
        **record["claim_references"][1],
        "id": "retired-deployment",
        "scope": "deployment",
        "claim_posture": "contradicted",
    }
    record["deployment_status"] = "retired"
    record["claim_references"].append(deployment_claim)
    assertion = _load_assertion(tmp_path)
    assertion["fact"] = {"predicate": "deployment_status", "value": "retired"}
    _write_assertion(tmp_path, assertion)
    assert validate_project_record(record, root=tmp_path) == []

    deployment_claim["claim_posture"] = "proposed"
    assert any(
        "requires at least one deployment claim with claim_posture" in error
        for error in validate_project_record(record, root=tmp_path)
    )

    deployment_claim["claim_posture"] = "contradicted"
    assertion["verification_state"] = "unverified"
    _write_assertion(tmp_path, assertion)
    assert any(
        "qualifying deployment claim that resolves to a verified assertion" in error
        for error in validate_project_record(record, root=tmp_path)
    )


def test_project_record_timestamp_order_and_future_are_rejected(tmp_path):
    record = _record()
    _write_routes(tmp_path, record)
    record["verified_at"] = "2026-08-31T20:01:00Z"
    now = datetime(2026, 8, 31, 20, 0, 30, tzinfo=timezone.utc)

    errors = validate_project_record(record, root=tmp_path, now=now)
    assert "verified_at cannot be in the future" in errors
    assert "verified_at must be less than or equal to generated_at" in errors

    record["verified_at"] = "2026-08-31T20:00:00Z"
    record["generated_at"] = "2026-08-31T20:01:00Z"
    assert "generated_at cannot be in the future" in validate_project_record(
        record,
        root=tmp_path,
        now=now,
    )


def test_repository_role_requires_conservative_documentation_class(tmp_path):
    for role, required_class in (
        ("mirror", "D"),
        ("deployment-artifact", "D"),
        ("archive", "F"),
        ("upstream-fork", "F"),
        ("contribution", "F"),
    ):
        record = _record()
        record["repository_role"] = role
        _write_routes(tmp_path, record)
        assert (
            f"repository_role {role!r} requires documentation_class {required_class}"
            in validate_project_record(record, root=tmp_path)
        )


def test_schema_validation_enforces_uri_and_datetime_formats(tmp_path):
    record = _record()
    _write_routes(tmp_path, record)
    record["links"]["repository"] = "not a URI"
    record["verified_at"] = "not a timestamp"

    errors = validate_project_record(record, root=tmp_path)
    assert "links.repository must be an absolute HTTP(S) URI" in errors
    assert "verified_at must be an ISO 8601 date-time with a timezone" in errors


def test_canonical_repository_must_match_github_repository_link(tmp_path):
    record = _record()
    _write_routes(tmp_path, record)
    record["links"]["repository"] = "https://github.com/organvm/different"

    errors = validate_project_record(record, root=tmp_path)
    assert (
        "canonical_repository must agree with links.repository GitHub owner/name"
        in errors
    )


def test_class_a_requires_evidence_link(tmp_path):
    record = _record("A")
    _write_routes(tmp_path, record)
    del record["links"]["evidence"]

    assert "class A requires links.evidence" in validate_project_record(
        record,
        root=tmp_path,
    )


def test_class_b_requires_evidence_link(tmp_path):
    record = _record("B")
    _write_routes(tmp_path, record)
    del record["links"]["evidence"]

    assert "class B requires links.evidence" in validate_project_record(
        record,
        root=tmp_path,
    )


def test_documentation_links_use_local_or_http_policy(tmp_path):
    record = _record()
    _write_routes(tmp_path, record)
    record["links"]["documentation"] = "https://docs.example.test/project"
    record["links"]["evidence"] = "http://evidence.example.test/record"
    assert validate_project_record(record, root=tmp_path) == []

    for key, value in (
        ("documentation", "javascript:alert(1)"),
        ("evidence", "mailto:evidence@example.test"),
        ("documentation", "/tmp/documentation.md"),
    ):
        candidate = _record()
        _write_routes(tmp_path, candidate)
        candidate["links"][key] = value
        assert any(
            f"links.{key} must be a contained local path or absolute HTTP(S) URI"
            in error
            for error in validate_project_record(candidate, root=tmp_path)
        )


def test_public_links_and_redirect_reject_non_http_schemes(tmp_path):
    record = _record()
    _write_routes(tmp_path, record)
    record["links"]["project_page"] = "urn:project:example"
    record["links"]["demo"] = "javascript:alert(1)"
    record["links"]["deployment"] = "mailto:ops@example.test"
    record["redirect"] = {"status": "planned", "target": "ftp://example.test/project"}

    errors = validate_project_record(record, root=tmp_path)
    for key in ("project_page", "demo", "deployment"):
        assert f"links.{key} must be an absolute HTTP(S) URI" in errors
    assert "redirect.target must be an absolute HTTP(S) URI" in errors


def test_remote_assertion_reference_is_rejected_without_fetching(tmp_path):
    record = _record()
    _write_routes(tmp_path, record)
    record["claim_references"][0]["assertion_ref"] = (
        "https://example.invalid/assertion.json"
    )

    errors = validate_project_record(record, root=tmp_path)
    assert any("remote or absolute assertion_ref is unsupported" in error for error in errors)


def test_claim_posture_is_required_and_bounded(tmp_path):
    record = _record()
    _write_routes(tmp_path, record)
    record["claim_references"][0]["claim_posture"] = "verified"

    assert (
        "claim_references[0] has invalid claim_posture: 'verified'"
        in validate_project_record(record, root=tmp_path)
    )


def test_duplicate_evidence_ids_fail_in_every_verification_state(tmp_path):
    record = _record()
    _write_routes(tmp_path, record)
    baseline = _load_assertion(tmp_path)
    duplicate = dict(baseline["evidence_references"][0])
    duplicate["independence_group"] = "second-group"
    baseline["evidence_references"].append(duplicate)

    for state in ("unverified", "verified", "stale", "disputed"):
        assertion = json.loads(json.dumps(baseline))
        assertion["verification_state"] = state
        _write_assertion(tmp_path, assertion)
        errors = validate_project_record(record, root=tmp_path)
        assert any(
            "semantic: evidence_references contain duplicate evidence_id values"
            in error
            for error in errors
        ), state


def test_verified_assertion_class_rules_are_enforced(tmp_path):
    record = _record()
    _write_routes(tmp_path, record)
    baseline = _load_assertion(tmp_path)
    validation_now = datetime(2026, 8, 31, 13, 0, tzinfo=timezone.utc)

    external = json.loads(json.dumps(baseline))
    external["assertion_class"] = "external_fact"
    _write_assertion(tmp_path, external)
    assert any(
        "a verified external_fact requires at least two independent evidence groups"
        in error
        for error in validate_project_record(record, root=tmp_path, now=validation_now)
    )

    directive = json.loads(json.dumps(baseline))
    directive["assertion_class"] = "operator_directive"
    _write_assertion(tmp_path, directive)
    directive_errors = validate_project_record(record, root=tmp_path, now=validation_now)
    assert any("requires at least two independent evidence groups" in e for e in directive_errors)
    assert any("missing evidence types" in e for e in directive_errors)
    assert any("requires non-stale freshness" in e for e in directive_errors)

    current = json.loads(json.dumps(baseline))
    current["assertion_class"] = "current_state"
    current["freshness"] = {
        "verified_at": "2026-08-31T12:00:00Z",
        "max_age_seconds": 7200,
        "status": "fresh",
    }
    _write_assertion(tmp_path, current)
    current_errors = validate_project_record(record, root=tmp_path, now=validation_now)
    assert any("missing evidence types: fresh_verifier_receipt, owner_record" in e for e in current_errors)


def test_assertion_freshness_rejects_future_and_expired_receipts(tmp_path):
    record = _record()
    _write_routes(tmp_path, record)
    baseline = _load_assertion(tmp_path)
    validation_now = datetime(2026, 8, 31, 13, 0, tzinfo=timezone.utc)

    future = json.loads(json.dumps(baseline))
    future["freshness"] = {
        "verified_at": "2026-08-31T14:00:00Z",
        "max_age_seconds": 7200,
        "status": "fresh",
    }
    _write_assertion(tmp_path, future)
    assert any(
        "freshness.verified_at cannot be in the future" in error
        for error in validate_project_record(record, root=tmp_path, now=validation_now)
    )

    expired = json.loads(json.dumps(baseline))
    expired["freshness"] = {
        "verified_at": "2026-08-31T10:00:00Z",
        "max_age_seconds": 60,
        "status": "fresh",
    }
    _write_assertion(tmp_path, expired)
    assert any(
        "freshness.status 'fresh' is expired at validation time" in error
        for error in validate_project_record(record, root=tmp_path, now=validation_now)
    )


def test_evidence_references_are_local_existing_and_hash_bound(tmp_path):
    record = _record()
    _write_routes(tmp_path, record)
    baseline = _load_assertion(tmp_path)

    mismatch = json.loads(json.dumps(baseline))
    mismatch["evidence_references"][0]["body_hash"] = "sha256:" + "0" * 64
    _write_assertion(tmp_path, mismatch)
    assert any(
        "body_hash does not match raw bytes" in error
        for error in validate_project_record(record, root=tmp_path)
    )

    missing = json.loads(json.dumps(baseline))
    missing["evidence_references"][0]["reference"] = "docs/evidence/missing.txt"
    _write_assertion(tmp_path, missing)
    assert any(
        "reference does not exist: docs/evidence/missing.txt" in error
        for error in validate_project_record(record, root=tmp_path)
    )

    remote = json.loads(json.dumps(baseline))
    remote["evidence_references"][0]["reference"] = "https://status.example.test/health"
    _write_assertion(tmp_path, remote)
    assert any(
        "remote or opaque reference cannot be content-verified" in error
        for error in validate_project_record(record, root=tmp_path)
    )


def test_git_evidence_resolver_binds_full_commit_and_blob_bytes(tmp_path):
    record = _record()
    _write_routes(tmp_path, record)
    commit = _commit_fixture(tmp_path)
    assertion = _load_assertion(tmp_path)

    commit_bytes = _git(tmp_path, "cat-file", "commit", commit)
    assertion["evidence_references"][0]["reference"] = f"git:{commit}"
    assertion["evidence_references"][0]["body_hash"] = (
        "sha256:" + hashlib.sha256(commit_bytes).hexdigest()
    )
    _write_assertion(tmp_path, assertion)
    assert validate_project_record(record, root=tmp_path) == []

    blob_path = "docs/evidence/sources/validation.txt"
    blob_bytes = _git(tmp_path, "cat-file", "blob", f"{commit}:{blob_path}")
    assertion["evidence_references"][0]["reference"] = f"git:{commit}:{blob_path}"
    assertion["evidence_references"][0]["body_hash"] = (
        "sha256:" + hashlib.sha256(blob_bytes).hexdigest()
    )
    _write_assertion(tmp_path, assertion)
    assert validate_project_record(record, root=tmp_path) == []

    assertion["evidence_references"][0]["reference"] = f"git:{commit[:8]}"
    _write_assertion(tmp_path, assertion)
    assert any(
        "git evidence must use git:<full-40-sha>" in error
        for error in validate_project_record(record, root=tmp_path)
    )


def test_commit_bound_evidence_rejects_untracked_ignored_symlink_and_git_paths(tmp_path):
    record = _record()
    _write_routes(tmp_path, record)
    _commit_fixture(tmp_path)
    assert validate_project_record(
        record,
        root=tmp_path,
        require_git_tracked_evidence=True,
    ) == []
    assertion = _load_assertion(tmp_path)

    untracked = tmp_path / "docs/evidence/sources/untracked.txt"
    untracked.write_text("untracked\n", encoding="utf-8")
    assertion["evidence_references"][0]["reference"] = untracked.relative_to(
        tmp_path,
    ).as_posix()
    assertion["evidence_references"][0]["body_hash"] = (
        "sha256:" + hashlib.sha256(untracked.read_bytes()).hexdigest()
    )
    _write_assertion(tmp_path, assertion)
    assert any(
        "evidence is ignored or untracked" in error
        for error in validate_project_record(
            record,
            root=tmp_path,
            require_git_tracked_evidence=True,
        )
    )

    ignored = tmp_path / "ignored-evidence.txt"
    (tmp_path / ".gitignore").write_text("ignored-evidence.txt\n", encoding="utf-8")
    ignored.write_text("ignored\n", encoding="utf-8")
    assertion["evidence_references"][0]["reference"] = "ignored-evidence.txt"
    assertion["evidence_references"][0]["body_hash"] = (
        "sha256:" + hashlib.sha256(ignored.read_bytes()).hexdigest()
    )
    _write_assertion(tmp_path, assertion)
    assert any(
        "evidence is ignored or untracked" in error
        for error in validate_project_record(
            record,
            root=tmp_path,
            require_git_tracked_evidence=True,
        )
    )

    target = tmp_path / "docs/evidence/sources/validation.txt"
    symlink = tmp_path / "docs/evidence/sources/link.txt"
    symlink.symlink_to(target.name)
    assertion["evidence_references"][0]["reference"] = symlink.relative_to(
        tmp_path,
    ).as_posix()
    assertion["evidence_references"][0]["body_hash"] = (
        "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()
    )
    _write_assertion(tmp_path, assertion)
    assert any(
        "symlink evidence is forbidden" in error
        for error in validate_project_record(record, root=tmp_path)
    )

    git_head = tmp_path / ".git/HEAD"
    assertion["evidence_references"][0]["reference"] = ".git/HEAD"
    assertion["evidence_references"][0]["body_hash"] = (
        "sha256:" + hashlib.sha256(git_head.read_bytes()).hexdigest()
    )
    _write_assertion(tmp_path, assertion)
    assert any(
        "reference under .git is forbidden" in error
        for error in validate_project_record(record, root=tmp_path)
    )


def test_commit_bound_validation_binds_assertion_record_itself(tmp_path):
    dirty_root = tmp_path / "dirty"
    dirty_root.mkdir()
    record = _record()
    _write_routes(dirty_root, record)
    _commit_fixture(dirty_root)
    assertion = _load_assertion(dirty_root)
    assertion["statement"] = "A dirty assertion must not establish a claim."
    _write_assertion(dirty_root, assertion)

    assert any(
        "assertion differs from the checked-out commit" in error
        for error in validate_project_record(
            record,
            root=dirty_root,
            require_git_tracked_evidence=True,
        )
    )

    untracked_root = tmp_path / "untracked"
    untracked_root.mkdir()
    record = _record()
    _write_routes(untracked_root, record)
    _commit_fixture(untracked_root)
    assertion_path = _assertion_path(untracked_root)
    _git(
        untracked_root,
        "rm",
        "--cached",
        assertion_path.relative_to(untracked_root).as_posix(),
    )

    assert any(
        "assertion is ignored or untracked" in error
        for error in validate_project_record(
            record,
            root=untracked_root,
            require_git_tracked_evidence=True,
        )
    )

    symlink_root = tmp_path / "symlink"
    symlink_root.mkdir()
    record = _record()
    _write_routes(symlink_root, record)
    assertion_path = _assertion_path(symlink_root)
    target = assertion_path.with_name("target.json")
    target.write_bytes(assertion_path.read_bytes())
    assertion_path.unlink()
    assertion_path.symlink_to(target.name)

    assert any(
        "symlink assertion is forbidden" in error
        for error in validate_project_record(record, root=symlink_root)
    )


def test_commit_bound_evidence_rejects_submodule_boundaries(tmp_path):
    record = _record()
    _write_routes(tmp_path, record)
    commit = _commit_fixture(tmp_path)
    _git(
        tmp_path,
        "update-index",
        "--add",
        "--cacheinfo",
        f"160000,{commit},vendor/submodule",
    )
    _git(tmp_path, "commit", "-m", "add gitlink")
    submodule_evidence = tmp_path / "vendor/submodule/evidence.txt"
    submodule_evidence.parent.mkdir(parents=True)
    submodule_evidence.write_text("nested\n", encoding="utf-8")
    assertion = _load_assertion(tmp_path)
    assertion["evidence_references"][0]["reference"] = "vendor/submodule/evidence.txt"
    assertion["evidence_references"][0]["body_hash"] = (
        "sha256:" + hashlib.sha256(submodule_evidence.read_bytes()).hexdigest()
    )
    _write_assertion(tmp_path, assertion)

    assert any(
        "evidence inside a submodule is forbidden" in error
        for error in validate_project_record(
            record,
            root=tmp_path,
            require_git_tracked_evidence=True,
        )
    )


def test_class_d_redirect_and_class_f_provenance_status_are_enforced(tmp_path):
    deployment = _record("D")
    deployment["repository_role"] = "deployment-artifact"
    _write_routes(tmp_path, deployment)
    assert any(
        "requires a canonical redirect" in error
        for error in validate_project_record(deployment, root=tmp_path)
    )
    deployment["redirect"] = {
        "status": "active",
        "target": "https://github.com/organvm/example",
    }
    assert (
        validate_project_record(
            deployment,
            root=tmp_path,
            actual_repository="organvm/example-deployment",
        )
        == []
    )

    errors = validate_project_record(
        deployment,
        root=tmp_path,
        actual_repository="organvm/example",
    )
    assert any("requires canonical_repository to differ" in error for error in errors)

    canonical_delivery = _record("D")
    canonical_delivery["redirect"] = {
        "status": "active",
        "target": "https://github.com/organvm/example",
    }
    _write_routes(tmp_path, canonical_delivery)
    assert any(
        "documentation_class D requires repository_role" in error
        for error in validate_project_record(canonical_delivery, root=tmp_path)
    )

    archive = _record("F")
    _write_routes(tmp_path, archive)
    archive_errors = validate_project_record(archive, root=tmp_path)
    assert "class F requires a 'provenance' claim reference" in archive_errors

    archive["claim_references"] = []
    for scope in ("provenance", "status"):
        claim = dict(_record()["claim_references"][0])
        claim["id"] = f"archive-{scope}"
        claim["scope"] = scope
        archive["claim_references"].append(claim)
    assert validate_project_record(archive, root=tmp_path) == []


def test_repository_audit_escalates_class_d_and_f_contract_failures(tmp_path):
    for doc_class, expected in (
        ("D", "requires a canonical redirect"),
        ("F", "requires a 'provenance' claim reference"),
    ):
        root = tmp_path / doc_class.lower()
        root.mkdir()
        record = _record(doc_class)
        _write_routes(root, record)
        (root / "project-record.yml").write_text(
            yaml.safe_dump(record, sort_keys=False),
            encoding="utf-8",
        )

        result = audit_repository(root)
        assert any(expected in error for error in result["record_errors"])
        assert any(
            finding["severity"] == "error"
            and finding["code"] == "invalid-project-record"
            and expected in finding["message"]
            for finding in result["findings"]
        )


def test_schema_invalid_types_return_errors_instead_of_raising(tmp_path):
    record = _record()
    _write_routes(tmp_path, record)
    record["documentation_class"] = ["A"]
    record["implementation_status"] = {"state": "PROTOTYPE"}
    record["deployment_status"] = ["not-deployed"]
    record["links"]["repository"] = "https://["
    record["links"]["documentation"] = "https://["
    record["audience_routes"][0]["mode"] = {"general": True}
    record["industries"] = [
        {"name": "Education", "status": ["piloted"], "claim_references": 7},
    ]

    errors = validate_project_record(record, root=tmp_path)
    assert errors
    assert "industries[0].claim_references must be a list" in errors


def test_audit_repository_reports_structural_reader_mode_signals(tmp_path):
    record = _record("A")
    _write_routes(tmp_path, record)
    (tmp_path / "docs/evidence").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs/evidence/README.md").write_text("# Evidence record\nVerified tests.\n")
    (tmp_path / "docs/concepts").mkdir(parents=True)
    (tmp_path / "docs/concepts/trust.md").write_text("# Trust theory and cultural ethics\n")
    (tmp_path / "docs/industries").mkdir(parents=True)
    (tmp_path / "docs/industries/education.md").write_text("# Education workflow and risks\n")
    (tmp_path / "project-record.yml").write_text(yaml.safe_dump(record, sort_keys=False))
    (tmp_path / "README.md").write_text(
        """# Example

> An ordinary-language description of a working documentation system.

## What am I looking at?
## Choose your reading path
| I am reading as | Start here |
|---|---|
| Engineer | [Technical](docs/audiences/technical.md) |
## Current status
Prototype.
## Architecture and data flow
## Quick start and usage
## Tests and verification
## API, security, observability, and failure modes
## Problem statement and primary users
## Workflow, inputs and outputs, integration, constraints, and risks
## Evidence record and limitations
## Authorship and contribution
## Theory, genealogy, aesthetics, interpretation, pedagogy, and ethics
## Related systems
[Another repository](https://github.com/organvm/example-two)
[A third repository](https://github.com/organvm/example-three)
""",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)
    assert result["documentation_class"] == "A"
    assert result["class_source"] == "project-record"
    assert result["signals"]["orientation"] == 4
    assert result["signals"]["technical_depth"] == 4
    assert result["signals"]["evidence"] == 4
    assert result["signals"]["seo_surface"] == 4
    assert "scores" not in result
    assert "documentation_gap" not in result
    assert result["signal_semantics"] == "structural markers only; not a quality score"
    assert result["record_errors"] == []


def test_audit_excludes_broken_local_links_from_cross_link_signals(tmp_path):
    (tmp_path / "README.md").write_text(
        "# Project\n\n[Missing](docs/missing.md)\n",
        encoding="utf-8",
    )
    result = audit_repository(tmp_path)
    assert result["signals"]["cross_linking"] <= 1
    assert any(
        finding["code"] == "broken-local-links" and finding["severity"] == "error"
        for finding in result["findings"]
    )


def test_audit_scans_repositories_below_ancestor_named_like_skipped_directory(tmp_path):
    root = tmp_path / "build" / "repository"
    docs = root / "docs"
    docs.mkdir(parents=True)
    (root / "README.md").write_text("# Project\n", encoding="utf-8")
    (docs / "guide.md").write_text("# Guide\n", encoding="utf-8")

    result = audit_repository(root)

    assert result["markdown_files"] == 2


def test_audit_parses_link_titles_and_case_insensitive_readme_names(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "guide(1).md").write_text("# Guide\n", encoding="utf-8")
    (tmp_path / "README.MD").write_text(
        '# Project\n\n[Guide](docs/guide(1).md "Guide title")\n',
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)

    assert result["has_readme"] is True
    assert result["markdown_files"] == 2
    assert not any(
        finding["code"] in {"missing-readme", "broken-local-links"}
        for finding in result["findings"]
    )


def test_discover_repositories_stops_at_git_root(tmp_path):
    first = tmp_path / "organ" / "one"
    second = tmp_path / "organ" / "two"
    (first / ".git").mkdir(parents=True)
    (second / ".git").mkdir(parents=True)
    (first / "nested" / ".git").mkdir(parents=True)
    assert discover_repositories(tmp_path) == [first.resolve(), second.resolve()]


def test_missing_project_record_is_an_audit_error_and_strict_failure(tmp_path, capsys):
    (tmp_path / "README.md").write_text("# Undeclared repository\n", encoding="utf-8")
    result = audit_repository(tmp_path)
    assert any(
        finding["severity"] == "error"
        and finding["code"] == "missing-project-record"
        for finding in result["findings"]
    )

    args = Namespace(
        paths=[str(tmp_path)],
        workspace=None,
        format="json",
        json=True,
        output=None,
        strict=True,
    )
    assert cmd_docs_audit(args) == 1
    assert "missing-project-record" in capsys.readouterr().out


def test_cli_parser_exposes_docs_commands():
    parser = build_parser()
    args = parser.parse_args(["docs", "audit", ".", "--format", "markdown"])
    assert args.command == "docs"
    assert args.subcommand == "audit"
    assert args.format == "markdown"
    validate_args = parser.parse_args(
        [
            "docs",
            "validate",
            "project-record.yml",
            "--require-git-tracked-evidence",
            "--actual-repository",
            "organvm/example",
        ],
    )
    assert validate_args.require_git_tracked_evidence is True
    assert validate_args.actual_repository == "organvm/example"


def test_docs_validate_cli_json(tmp_path, capsys):
    record = _record()
    _write_routes(tmp_path, record)
    record_path = tmp_path / "project-record.yml"
    record_path.write_text(yaml.safe_dump(record, sort_keys=False))
    args = Namespace(
        record=str(record_path),
        root=str(tmp_path),
        schema=None,
        assertion_schema=None,
        json=True,
    )
    assert cmd_docs_validate(args) == 0
    assert '"valid": true' in capsys.readouterr().out


def test_docs_validate_cli_surfaces_semantic_errors_as_json(tmp_path, capsys):
    record = _record()
    _write_routes(tmp_path, record)
    assertion = _load_assertion(tmp_path)
    assertion["verification_state"] = "unverified"
    assertion["evidence_references"].append(
        dict(assertion["evidence_references"][0]),
    )
    _write_assertion(tmp_path, assertion)
    record_path = tmp_path / "project-record.yml"
    record_path.write_text(yaml.safe_dump(record, sort_keys=False))
    args = Namespace(
        record=str(record_path),
        root=str(tmp_path),
        schema=None,
        assertion_schema=None,
        json=True,
    )

    assert cmd_docs_validate(args) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["valid"] is False
    assert any("duplicate evidence_id" in error for error in payload["errors"])


def test_docs_validate_cli_serializes_schema_invalid_types(tmp_path, capsys):
    record = _record()
    _write_routes(tmp_path, record)
    record["documentation_class"] = ["A"]
    record["audience_routes"][0]["mode"] = ["general"]
    record["industries"] = [
        {"name": "Education", "status": "piloted", "claim_references": 7},
    ]
    record_path = tmp_path / "project-record.yml"
    record_path.write_text(yaml.safe_dump(record, sort_keys=False))
    args = Namespace(
        record=str(record_path),
        root=str(tmp_path),
        schema=None,
        assertion_schema=None,
        json=True,
    )

    assert cmd_docs_validate(args) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["valid"] is False
    assert payload["errors"]


def test_docs_audit_cli_writes_markdown(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Repo\n\n## Overview\nA project.\n")
    output = tmp_path / "audit.md"
    args = Namespace(
        paths=[str(repo)],
        workspace=None,
        format="markdown",
        json=False,
        output=str(output),
        strict=False,
    )
    assert cmd_docs_audit(args) == 0
    assert "Reader-mode documentation audit" in output.read_text()


def test_docs_audit_cli_reports_output_write_errors(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Repo\n", encoding="utf-8")
    output = tmp_path / "missing-parent" / "audit.md"
    args = Namespace(
        paths=[str(repo)],
        workspace=None,
        format="markdown",
        json=False,
        output=str(output),
        strict=False,
    )

    assert cmd_docs_audit(args) == 1
    assert "cannot write documentation audit" in capsys.readouterr().err


def test_audit_reuses_readme_from_markdown_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "README.md").write_text("# Purpose\nArchitecture and usage.\n")
    import organvm_engine.documentation.audit as audit_module
    monkeypatch.setattr(
        audit_module,
        "_read_bounded_markdown",
        lambda _path: (_ for _ in ()).throw(AssertionError("second README read")),
    )
    report = audit_repository(tmp_path)
    assert report["has_readme"] is True
