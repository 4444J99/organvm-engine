"""Adversarial regressions for canonical documentation records."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import re
import subprocess
from argparse import Namespace
from datetime import datetime, timezone
from pathlib import Path

import nbformat
import pytest
import yaml

from organvm_engine.cli.docs import cmd_docs_audit, cmd_docs_validate
from organvm_engine.documentation import audit as documentation_audit
from organvm_engine.documentation import record as documentation_record
from organvm_engine.documentation.audit import audit_repository
from organvm_engine.documentation.privacy import (
    PUBLIC_EXACT_REWRITES,
    PUBLIC_PROSE_REWRITES,
    private_only_repository_slugs,
    redact_private_references,
    repository_reference_pattern,
)
from organvm_engine.documentation.record import load_project_record, validate_project_record


def _record() -> dict:
    return {
        "contract_name": "project-record.v1",
        "contract_version": 1,
        "project_id": "example",
        "name": "Example",
        "canonical_repository": "organvm/example",
        "repository_role": "canonical",
        "documentation_class": "B",
        "one_sentence": "A complete test project record.",
        "problem": "Documentation claims need deterministic validation.",
        "intended_users": ["maintainers"],
        "implementation_status": "PROTOTYPE",
        "deployment_status": "not-deployed",
        "authorship": {
            "owner": "Test Maintainer",
            "role": "maintainer",
            "contributions": ["validation"],
        },
        "claim_references": [
            {
                "id": "project-status",
                "assertion_contract": "assertion-evidence.v1",
                "assertion_id": "validation",
                "assertion_ref": "docs/evidence/claims/validation.json",
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
        "limitations": [],
        "audience_routes": [
            {
                "mode": "general",
                "path": "docs/audiences/general.md",
                "primary_question": "What does this project do?",
                "surface": "public",
            },
            {
                "mode": "technical",
                "path": "docs/audiences/technical.md",
                "primary_question": "How is this project implemented?",
                "surface": "public",
            },
        ],
        "search_intents": [],
        "links": {
            "repository": "https://github.com/organvm/example",
            "documentation": "https://docs.example.test/project",
            "evidence": "https://docs.example.test/evidence",
        },
        "generated_at": "2025-01-01T00:00:00Z",
        "verified_at": "2025-01-01T00:00:00Z",
    }


def _git(root: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
    ).stdout


def _write_git_fixture(root: Path) -> dict:
    record = _record()
    for route in record["audience_routes"]:
        route_path = root / route["path"]
        route_path.parent.mkdir(parents=True, exist_ok=True)
        route_path.write_text(f"# {route['mode']}\n", encoding="utf-8")

    evidence_path = root / "docs/evidence/sources/validation.txt"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text("committed evidence\n", encoding="utf-8")
    assertion_path = root / "docs/evidence/claims/validation.json"
    assertion_path.parent.mkdir(parents=True, exist_ok=True)
    assertion_path.write_text(
        json.dumps(
            {
                "contract_name": "assertion-evidence.v1",
                "contract_version": 1,
                "assertion_id": "validation",
                "assertion_class": "historical_record",
                "statement": "The committed validation fixture exists.",
                "verification_state": "verified",
                "evidence_references": [
                    {
                        "evidence_id": "validation-receipt",
                        "independence_group": "local-fixture",
                        "evidence_type": "artifact",
                        "reference": evidence_path.relative_to(root).as_posix(),
                        "body_hash": (
                            "sha256:"
                            + hashlib.sha256(evidence_path.read_bytes()).hexdigest()
                        ),
                    },
                ],
            },
        ),
        encoding="utf-8",
    )
    _git(root, "init")
    _git(root, "config", "user.name", "Record Hardening Tests")
    _git(root, "config", "user.email", "record-hardening@example.test")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "fixture")
    return record


@pytest.mark.parametrize(
    "route",
    [
        "docs/audiences/../private.md",
        "docs/audiences/nested/technical.md",
        "docs/audiences/.md",
        "docs/audiences/technical.txt",
    ],
)
def test_audience_routes_require_one_canonical_slug_file(route: str) -> None:
    record = _record()
    record["audience_routes"][1]["path"] = route

    assert "audience_routes[1] path must match docs/audiences/<slug>.md" in (
        validate_project_record(record)
    )


@pytest.mark.parametrize("slug", ["technical-review", "technical--deep", "technical-"])
def test_audience_route_accepts_schema_permitted_hyphenated_slugs(slug: str) -> None:
    record = _record()
    record["audience_routes"][1]["path"] = f"docs/audiences/{slug}.md"

    assert validate_project_record(record) == []


@pytest.mark.parametrize(
    "repository_url",
    [
        "https://user@github.com/organvm/example",
        "https://user:secret@github.com/organvm/example",
        "https://github.com:443/organvm/example",
        "https://github.com:8443/organvm/example",
        "https://github.com:/organvm/example",
        "https://github.com:not-a-port/organvm/example",
    ],
)
def test_canonical_github_url_rejects_credentials_and_ports(
    repository_url: str,
) -> None:
    record = _record()
    record["links"]["repository"] = repository_url

    assert "links.repository must be a canonical GitHub repository URL" in (
        validate_project_record(record)
    )


@pytest.mark.parametrize(
    ("relative_path", "index_flag", "object_name"),
    [
        (
            "docs/evidence/sources/validation.txt",
            "--assume-unchanged",
            "evidence",
        ),
        (
            "docs/evidence/sources/validation.txt",
            "--skip-worktree",
            "evidence",
        ),
        (
            "docs/evidence/claims/validation.json",
            "--assume-unchanged",
            "assertion",
        ),
        (
            "docs/evidence/claims/validation.json",
            "--skip-worktree",
            "assertion",
        ),
    ],
)
def test_strict_records_reject_hidden_index_flags(
    tmp_path: Path,
    relative_path: str,
    index_flag: str,
    object_name: str,
) -> None:
    record = _write_git_fixture(tmp_path)
    _git(tmp_path, "update-index", index_flag, relative_path)
    target = tmp_path / relative_path
    if target.suffix == ".json":
        assertion = json.loads(target.read_text(encoding="utf-8"))
        assertion["statement"] = "Hidden working-tree assertion bytes."
        target.write_text(json.dumps(assertion), encoding="utf-8")
    else:
        target.write_text("hidden working-tree evidence bytes\n", encoding="utf-8")

    errors = validate_project_record(
        record,
        root=tmp_path,
        require_git_tracked_evidence=True,
    )

    assert any(
        f"{object_name} is marked {index_flag.removeprefix('--')}" in error
        for error in errors
    )


@pytest.mark.parametrize("schema_argument", ["schema", "assertion_schema"])
def test_docs_validate_reports_malformed_schema_as_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    schema_argument: str,
) -> None:
    record_path = tmp_path / "project-record.yml"
    record_path.write_text("{}\n", encoding="utf-8")
    schema_path = tmp_path / f"{schema_argument}.yml"
    schema_path.write_text("properties: [unterminated\n", encoding="utf-8")
    arguments = {
        "record": str(record_path),
        "root": str(tmp_path),
        "schema": None,
        "assertion_schema": None,
        "json": True,
    }
    arguments[schema_argument] = str(schema_path)

    assert cmd_docs_validate(Namespace(**arguments)) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["valid"] is False
    assert payload["errors"]
    assert "while parsing a flow sequence" in payload["errors"][0]


@pytest.mark.parametrize("schema_argument", ["schema", "assertion_schema"])
def test_docs_validate_reports_excessively_nested_schema_as_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    schema_argument: str,
) -> None:
    record_path = tmp_path / "project-record.yml"
    record_path.write_text("{}\n", encoding="utf-8")
    schema_path = tmp_path / f"{schema_argument}.yml"
    schema_path.write_text(
        "nested: " + "[" * 2_000 + "null" + "]" * 2_000,
        encoding="utf-8",
    )
    arguments = {
        "record": str(record_path),
        "root": str(tmp_path),
        "schema": None,
        "assertion_schema": None,
        "json": True,
    }
    arguments[schema_argument] = str(schema_path)

    assert cmd_docs_validate(Namespace(**arguments)) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["valid"] is False
    assert "YAML nesting exceeds supported depth" in payload["errors"][0]


@pytest.mark.parametrize("schema_argument", ["schema", "assertion_schema"])
def test_docs_validate_rejects_oversized_schema_before_parsing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    schema_argument: str,
) -> None:
    record_path = tmp_path / "project-record.yml"
    record_path.write_text("{}\n", encoding="utf-8")
    schema_path = tmp_path / f"{schema_argument}.yml"
    schema_path.write_bytes(b"{}\n" + b" " * 2_000_000)
    arguments = {
        "record": str(record_path),
        "root": str(tmp_path),
        "schema": None,
        "assertion_schema": None,
        "json": True,
    }
    arguments[schema_argument] = str(schema_path)

    assert cmd_docs_validate(Namespace(**arguments)) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["valid"] is False
    assert "structured record exceeds 2000000 bytes" in payload["errors"][0]


def test_malformed_yaml_assertion_becomes_an_audit_finding(tmp_path: Path) -> None:
    record = _record()
    for route in record["audience_routes"]:
        route_path = tmp_path / route["path"]
        route_path.parent.mkdir(parents=True, exist_ok=True)
        route_path.write_text(f"# {route['mode']}\n", encoding="utf-8")
    for claim in record["claim_references"]:
        claim["assertion_ref"] = "docs/evidence/claims/validation.yml"
    assertion_path = tmp_path / "docs/evidence/claims/validation.yml"
    assertion_path.parent.mkdir(parents=True, exist_ok=True)
    assertion_path.write_text("evidence_references: [unterminated\n", encoding="utf-8")
    (tmp_path / "project-record.yml").write_text(
        yaml.safe_dump(record, sort_keys=False),
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)

    assert any("cannot load assertion" in error for error in result["record_errors"])
    assert any(
        finding["code"] == "invalid-project-record" for finding in result["findings"]
    )


def test_oversized_assertion_is_rejected_before_parsing(tmp_path: Path) -> None:
    record = _write_git_fixture(tmp_path)
    assertion_path = tmp_path / "docs/evidence/claims/validation.json"
    with assertion_path.open("wb") as stream:
        stream.write(b"{")
        stream.seek(2_000_000)
        stream.write(b"}")

    errors = validate_project_record(record, root=tmp_path)

    assert any("cannot load assertion" in error for error in errors)
    assert any("structured record exceeds 2000000 bytes" in error for error in errors)


@pytest.mark.parametrize(
    "key",
    ["project_page", "demo", "deployment", "documentation", "evidence"],
)
def test_every_web_link_rejects_credentials(key: str) -> None:
    record = _record()
    record["links"][key] = "https://user:password@example.test/path"

    assert any(f"links.{key}" in error for error in validate_project_record(record))


@pytest.mark.parametrize("repository", ["./example", "../..", "organvm/..", "./."])
def test_repository_slugs_reject_dot_segments(repository: str) -> None:
    record = _record()
    record["canonical_repository"] = repository
    record["links"]["repository"] = f"https://github.com/{repository}"

    errors = validate_project_record(record)

    assert "canonical_repository must use owner/name form" in errors
    assert "links.repository must be a canonical GitHub repository URL" in errors


def test_yaml_native_datetimes_are_normalized_before_validation(tmp_path: Path) -> None:
    record_path = tmp_path / "project-record.yml"
    record_path.write_text(
        yaml.safe_dump(_record(), sort_keys=False).replace(
            "'2025-01-01T00:00:00Z'",
            "2025-01-01T00:00:00Z",
        ),
        encoding="utf-8",
    )

    record = load_project_record(record_path)

    assert isinstance(record["generated_at"], str)
    assert validate_project_record(
        record,
        now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    ) == []


def test_recursive_yaml_aliases_are_rejected_without_recursing(tmp_path: Path) -> None:
    record_path = tmp_path / "project-record.yml"
    record_path.write_text(
        "contract_name: project-record.v1\ncycle: &cycle\n  - *cycle\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="recursive YAML aliases are unsupported"):
        load_project_record(record_path)


def test_acyclic_yaml_alias_expansion_is_memoized(tmp_path: Path) -> None:
    record_path = tmp_path / "project-record.yml"
    layers = ["base: &level0 [value, value]"]
    for index in range(1, 28):
        layers.append(
            f"level{index}: &level{index} [*level{index - 1}, *level{index - 1}]",
        )
    record_path.write_text("\n".join(layers) + "\n", encoding="utf-8")

    record = load_project_record(record_path)

    deepest = record["level27"]
    assert deepest[0] is deepest[1]
    assert deepest[0][0] is deepest[0][1]


def test_project_record_yaml_rejects_duplicate_mapping_keys(tmp_path: Path) -> None:
    record_path = tmp_path / "project-record.yml"
    record_path.write_text(
        "contract_name: project-record.v1\n"
        "deployment_status: internal\n"
        "deployment_status: public\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate mapping key: 'deployment_status'"):
        load_project_record(record_path)


def test_assertion_json_rejects_duplicate_mapping_keys(tmp_path: Path) -> None:
    record = _write_git_fixture(tmp_path)
    assertion_path = tmp_path / "docs/evidence/claims/validation.json"
    payload = assertion_path.read_text(encoding="utf-8")
    assertion_path.write_text(
        payload.replace(
            '"verification_state": "verified",',
            '"verification_state": "verified", "verification_state": "unverified",',
            1,
        ),
        encoding="utf-8",
    )

    errors = validate_project_record(record, root=tmp_path)

    assert any("cannot load assertion" in error for error in errors)
    assert any("duplicate mapping key: 'verification_state'" in error for error in errors)


def test_project_record_json_converts_excessive_nesting_to_value_error(
    tmp_path: Path,
) -> None:
    record_path = tmp_path / "project-record.json"
    record_path.write_text(
        '{"nested":' * 2_000 + "null" + "}" * 2_000,
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="JSON nesting exceeds supported depth"):
        load_project_record(record_path)


def test_project_record_yaml_converts_excessive_nesting_to_value_error(
    tmp_path: Path,
) -> None:
    record_path = tmp_path / "project-record.yml"
    record_path.write_text(
        "nested: " + "[" * 2_000 + "null" + "]" * 2_000,
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="YAML nesting exceeds supported depth"):
        load_project_record(record_path)


@pytest.mark.parametrize("status", [None, "deployd", []])
def test_industry_status_requires_the_supported_vocabulary(status: object) -> None:
    record = _record()
    record["industries"] = [{"name": "Education", "status": status}]

    assert (
        f"industries[0] has invalid status: {status!r}"
        in validate_project_record(record)
    )


def test_verified_deployment_status_requires_a_repository_root() -> None:
    record = _record()
    record["deployment_status"] = "public"
    record["claim_references"].append(
        {
            **record["claim_references"][0],
            "id": "public-deployment",
            "scope": "deployment",
            "claim_posture": "partial",
        },
    )

    assert (
        "deployment_status 'public' requires a repository root to verify assertion evidence"
        in validate_project_record(record)
    )


@pytest.mark.parametrize("contract_version", [True, 1.0])
def test_project_contract_version_requires_a_non_boolean_integer(
    contract_version: object,
) -> None:
    record = _record()
    record["contract_version"] = contract_version

    assert (
        f"unsupported contract_version: {contract_version!r}; expected 1"
        in validate_project_record(record)
    )


@pytest.mark.parametrize("repository_role", ["canonica1", [], {}])
def test_repository_role_requires_the_supported_schema_vocabulary(
    repository_role: object,
) -> None:
    record = _record()
    record["repository_role"] = repository_role

    assert (
        f"invalid repository_role: {repository_role!r}"
        in validate_project_record(
            record,
            actual_repository="organvm/different",
        )
    )


@pytest.mark.parametrize("repository_role", ["profile", "governance"])
def test_schema_supported_noncanonical_roles_remain_valid(
    repository_role: str,
) -> None:
    record = _record()
    record["repository_role"] = repository_role

    assert validate_project_record(record) == []


@pytest.mark.parametrize("repository_role", [[], {}])
def test_class_d_rejects_unhashable_repository_roles(
    repository_role: object,
) -> None:
    record = _record()
    record["documentation_class"] = "D"
    record["repository_role"] = repository_role
    record["audience_routes"] = []

    errors = validate_project_record(record)

    assert f"invalid repository_role: {repository_role!r}" in errors
    assert any("documentation_class D requires repository_role" in error for error in errors)


@pytest.mark.parametrize("claim_posture", [[], {}])
def test_deployment_posture_membership_rejects_unhashable_values(
    claim_posture: object,
) -> None:
    record = _record()
    record["deployment_status"] = "public"
    record["claim_references"].append(
        {
            **record["claim_references"][0],
            "id": "public-deployment",
            "scope": "deployment",
            "claim_posture": claim_posture,
        },
    )

    errors = validate_project_record(record)

    assert any("has invalid claim_posture" in error for error in errors)
    assert any("requires at least one deployment claim" in error for error in errors)


def test_industry_evidence_rejects_an_unhashable_claim_scope(tmp_path: Path) -> None:
    record = _write_git_fixture(tmp_path)
    record["claim_references"][0]["scope"] = []
    record["industries"] = [
        {
            "name": "Education",
            "status": "deployed",
            "claim_references": ["project-status"],
        },
    ]

    assert any(
        "must use deployment, adoption, or outcome scope" in error
        for error in validate_project_record(record, root=tmp_path)
    )


def test_markdown_audit_ignores_links_inside_code(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Example\n\n`[Inline](missing-inline.md)`\n\n"
        "```markdown\n[Fenced](missing-fenced.md)\n```\n",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)

    assert not any(
        finding["code"] == "broken-local-links" for finding in result["findings"]
    )


def test_markdown_audit_requires_exact_backtick_run_closers(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Example\n\n`x``` [Guide](missing-guide.md) ``\n",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)

    assert any(
        finding["code"] == "broken-local-links" for finding in result["findings"]
    )


def test_markdown_audit_rejects_backtick_fences_with_backticks_in_info(
    tmp_path: Path,
) -> None:
    (tmp_path / "README.md").write_text(
        "# Example\n\n``` example`\n[Guide](missing-guide.md)\n```\n",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)

    assert any(
        finding["code"] == "broken-local-links" for finding in result["findings"]
    )


@pytest.mark.parametrize(
    "markdown",
    [
        "```` language \\`\n[Hidden](hidden.md)\n",
        "- ```` language \\`\n  [Hidden](hidden.md)\n",
    ],
)
def test_escaped_backticks_are_valid_in_backtick_fence_info(markdown: str) -> None:
    assert documentation_audit._markdown_destinations(markdown) == []


def test_even_backslashes_do_not_escape_backticks_in_fence_info() -> None:
    markdown = "```` language \\\\`\n[Visible](visible.md)\n"

    assert documentation_audit._markdown_destinations(markdown) == ["visible.md"]


def test_markdown_audit_allows_backticks_in_tilde_fence_info(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Example\n\n~~~ example`\n[Guide](missing-guide.md)\n~~~\n",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)

    assert not any(
        finding["code"] == "broken-local-links" for finding in result["findings"]
    )


def test_markdown_audit_ignores_escaped_backticks_as_code_delimiters(
    tmp_path: Path,
) -> None:
    (tmp_path / "README.md").write_text(
        "# Example\n\n\\`[Guide](missing-guide.md)\\`\n",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)

    assert any(
        finding["code"] == "broken-local-links" for finding in result["findings"]
    )


def test_markdown_audit_even_slashes_leave_backtick_delimiters_active(
    tmp_path: Path,
) -> None:
    (tmp_path / "README.md").write_text(
        "# Example\n\n\\\\`[Guide](missing-guide.md)\\\\`\n",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)

    assert not any(
        finding["code"] == "broken-local-links" for finding in result["findings"]
    )


def test_escaped_first_backtick_leaves_the_rest_of_the_run_as_a_delimiter() -> None:
    markdown = "\\```[Hidden](missing.md)``\n"

    assert documentation_audit._markdown_destinations(markdown) == []


def test_escaped_backtick_run_is_not_shortened_inside_an_open_code_span() -> None:
    markdown = "` [Visible](visible.md) \\``\n"

    assert documentation_audit._markdown_destinations(markdown) == ["visible.md"]


def test_backslash_before_a_closer_is_literal_inside_an_open_code_span() -> None:
    markdown = "\\`` [Hidden](hidden.md) \\`\n"

    assert documentation_audit._markdown_destinations(markdown) == []


def test_unmatched_distinct_backtick_runs_have_linear_aggregate_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    original = documentation_audit._markdown_character_is_escaped

    def bounded_escape_check(text: str, position: int) -> bool:
        nonlocal calls
        calls += 1
        if calls > 200:
            raise AssertionError("backtick matching rescanned unmatched later runs")
        return original(text, position)

    monkeypatch.setattr(
        documentation_audit,
        "_markdown_character_is_escaped",
        bounded_escape_check,
    )

    documentation_audit._mask_markdown_code(
        " ".join("`" * length for length in range(1, 101)),
    )

    assert calls <= 100


def test_code_span_pairing_skips_runs_inside_an_already_matched_span() -> None:
    markdown = (
        "` [Inside](inside.md) `` ` "
        "[Outside](outside.md) ``\n"
    )

    assert documentation_audit._markdown_destinations(markdown) == ["outside.md"]


@pytest.mark.parametrize(
    "markdown",
    [
        "- ```markdown\n  [Hidden](hidden.md)\n  ````\n[Visible](visible.md)\n",
        "1. ~~~markdown\n   [Hidden](hidden.md)\n   ~~~~\n[Visible](visible.md)\n",
    ],
)
def test_inline_list_item_fences_mask_through_their_closer(markdown: str) -> None:
    assert documentation_audit._markdown_destinations(markdown) == ["visible.md"]


def test_non_one_ordered_list_fence_cannot_interrupt_an_open_paragraph() -> None:
    markdown = "Paragraph\n2. ~~~\n   [Visible](visible.md)\n   ~~~\n"

    assert documentation_audit._markdown_destinations(markdown) == ["visible.md"]


def test_markdown_audit_ignores_escaped_link_openers(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Example\n\n\\[Literal](missing-literal.md)\n",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)

    assert not any(
        finding["code"] == "broken-local-links" for finding in result["findings"]
    )


def test_markdown_audit_treats_even_backslashes_as_an_unescaped_link(
    tmp_path: Path,
) -> None:
    (tmp_path / "README.md").write_text(
        "# Example\n\n\\\\[Guide](missing-guide.md)\n",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)

    assert any(
        finding["code"] == "broken-local-links" for finding in result["findings"]
    )


def test_markdown_link_opener_matching_has_linear_aggregate_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    original = documentation_audit._markdown_character_is_escaped

    def bounded_escape_check(text: str, position: int) -> bool:
        nonlocal calls
        calls += 1
        if calls > 1_000:
            raise AssertionError("link opener matching rescanned the Markdown prefix")
        return original(text, position)

    monkeypatch.setattr(
        documentation_audit,
        "_markdown_character_is_escaped",
        bounded_escape_check,
    )

    assert documentation_audit._markdown_destinations("](" * 500) == []
    assert calls <= 500


@pytest.mark.parametrize(
    "markdown",
    [
        "[Guide](docs/missing.md",
        '[Guide](docs/missing.md "unfinished title"',
    ],
)
def test_markdown_audit_ignores_unclosed_inline_links(
    tmp_path: Path,
    markdown: str,
) -> None:
    (tmp_path / "README.md").write_text(f"# Example\n\n{markdown}\n", encoding="utf-8")

    result = audit_repository(tmp_path)

    assert not any(
        finding["code"] == "broken-local-links" for finding in result["findings"]
    )


@pytest.mark.parametrize(
    "comment",
    [
        "<!-- [Retired](missing.md) -->",
        "<!-- disabled\n[Retired](missing.md)",
    ],
)
def test_markdown_audit_masks_html_comments(tmp_path: Path, comment: str) -> None:
    (tmp_path / "README.md").write_text(f"# Example\n\n{comment}\n", encoding="utf-8")

    result = audit_repository(tmp_path)

    assert not any(
        finding["code"] == "broken-local-links" for finding in result["findings"]
    )


def test_unclosed_inline_comment_syntax_does_not_hide_rendered_markdown() -> None:
    markdown = "Paragraph <!-- [Visible](visible.md)\n"

    assert documentation_audit._markdown_destinations(markdown) == ["visible.md"]


@pytest.mark.parametrize("tag", ["script", "pre", "style", "textarea"])
def test_markdown_audit_masks_type1_raw_html_until_its_closing_tag(tag: str) -> None:
    markdown = (
        f"<{tag}>\n[Hidden](hidden.md)\n</{tag}>\n"
        "[Visible](visible.md)\n"
    )

    assert documentation_audit._markdown_destinations(markdown) == ["visible.md"]


def test_type1_raw_html_may_close_with_a_different_type1_end_tag() -> None:
    markdown = (
        "<script>\n[Hidden](hidden.md)\n</style>\n"
        "[Visible](visible.md)\n"
    )

    assert documentation_audit._markdown_destinations(markdown) == ["visible.md"]


def test_backticks_inside_raw_html_cannot_pair_with_visible_inline_content() -> None:
    markdown = (
        "<script>\n`\n</script>\n"
        "[Visible](visible.md)\n`\n"
    )

    assert documentation_audit._markdown_destinations(markdown) == ["visible.md"]


@pytest.mark.parametrize(
    ("opening", "closing"),
    [
        ("<!-- raw", "-->"),
        ("<?process", "?>"),
        ("<!DOCTYPE html", ">"),
        ("<![CDATA[", "]]>"),
    ],
)
def test_markdown_audit_masks_type2_through_type5_html_blocks(
    opening: str,
    closing: str,
) -> None:
    markdown = (
        f"{opening}\n[Hidden](hidden.md)\n{closing} [Still hidden](still-hidden.md)\n"
        "[Visible](visible.md)\n"
    )

    assert documentation_audit._markdown_destinations(markdown) == ["visible.md"]


def test_lowercase_declaration_syntax_does_not_start_a_type4_html_block() -> None:
    markdown = "<!not-a-declaration\n[Visible](visible.md)\n>\n"

    assert documentation_audit._markdown_destinations(markdown) == ["visible.md"]


def test_markdown_audit_masks_ordinary_html_blocks_until_a_blank_line() -> None:
    markdown = (
        "<div>\n[Hidden](hidden.md)\n</div>\n"
        "[Still hidden](still-hidden.md)\n\n"
        "[Visible](visible.md)\n"
    )

    assert documentation_audit._markdown_destinations(markdown) == ["visible.md"]


def test_markdown_audit_masks_complete_type7_html_blocks_until_a_blank_line() -> None:
    markdown = (
        '<Warning severity="high">\n[Hidden](hidden.md)\n</Warning>\n\n'
        "[Visible](visible.md)\n"
    )

    assert documentation_audit._markdown_destinations(markdown) == ["visible.md"]


def test_type7_raw_html_cannot_interrupt_an_open_paragraph() -> None:
    markdown = "Paragraph\n<Warning>\n[Visible](visible.md)\n"

    assert documentation_audit._markdown_destinations(markdown) == ["visible.md"]


@pytest.mark.parametrize(
    "paragraph",
    [
        "> Paragraph\n",
        "- Paragraph\n",
    ],
)
def test_type7_raw_html_starts_after_a_paragraph_container_ends(
    paragraph: str,
) -> None:
    markdown = f"{paragraph}<Warning>\n[Hidden](hidden.md)\n</Warning>\n\n"

    assert documentation_audit._markdown_destinations(markdown) == []


def test_type7_raw_html_starts_after_nested_blockquote_depth_drops() -> None:
    markdown = (
        "> > Paragraph\n> <Warning>\n> [Hidden](hidden.md)\n> </Warning>\n\n"
    )

    assert documentation_audit._markdown_destinations(markdown) == []


def test_type7_raw_html_remains_inline_in_a_retained_list_paragraph() -> None:
    markdown = "- Paragraph\n  <Warning>\n  [Visible](visible.md)\n  </Warning>\n"

    assert documentation_audit._markdown_destinations(markdown) == ["visible.md"]


def test_container_only_blank_ends_paragraph_before_type7_html() -> None:
    markdown = (
        "> Paragraph\n> \n> <Warning>\n> [Hidden](hidden.md)\n> </Warning>\n\n"
    )

    assert documentation_audit._markdown_destinations(markdown) == []


@pytest.mark.parametrize(("marker", "indent"), [("-", "  "), ("1.", "   ")])
def test_raw_html_block_scope_ends_with_its_list_container(
    marker: str,
    indent: str,
) -> None:
    markdown = f"{marker} Paragraph\n{indent}<div>\n[Visible](visible.md)\n\n"

    assert documentation_audit._markdown_destinations(markdown) == ["visible.md"]


def test_ordinary_raw_html_can_interrupt_an_open_paragraph() -> None:
    markdown = "Paragraph\n<div>\n[Hidden](hidden.md)\n"

    assert documentation_audit._markdown_destinations(markdown) == []


def test_inline_html_does_not_mask_following_markdown_as_a_raw_block() -> None:
    markdown = "<span>inline\n[Visible](visible.md)\n"

    assert documentation_audit._markdown_destinations(markdown) == ["visible.md"]


def test_unclosed_raw_html_ends_when_its_blockquote_container_ends() -> None:
    markdown = "> <script>\n> [Hidden](hidden.md)\n[Visible](visible.md)\n"

    assert documentation_audit._markdown_destinations(markdown) == ["visible.md"]


@pytest.mark.parametrize(
    "markdown",
    [
        "[Guide](<docs/missing\n-guide.md>)\n",
        "[Guide](<docs/<missing>.md>)\n",
        "[guide]: <docs/missing\n-guide.md>\n\n[Guide][guide]\n",
        "[guide]: <docs/<missing>.md>\n\n[Guide][guide]\n",
    ],
)
def test_angle_destinations_reject_line_endings_and_nested_openers(
    markdown: str,
) -> None:
    assert documentation_audit._markdown_destinations(markdown) == []


def test_angle_destinations_retain_escaped_open_angle_characters() -> None:
    markdown = "[Guide](<docs/a\\<b.md>)\n"

    assert documentation_audit._markdown_destinations(markdown) == ["docs/a<b.md"]


def test_angle_destinations_expand_tabs_at_commonmark_tab_stops() -> None:
    markdown = "[Guide](<docs/a\tb.md>)\n"

    assert documentation_audit._markdown_destinations(markdown) == ["docs/a b.md"]


def test_markdown_audit_ignores_links_inside_indented_code(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Example\n\n"
        "    [Indented](missing-indented.md)\n"
        "\t[Tabbed](missing-tabbed.md)\n"
        "    [Reference][missing]\n"
        "    [missing]: missing-reference.md\n",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)

    assert not any(
        finding["code"] == "broken-local-links" for finding in result["findings"]
    )


def test_markdown_audit_preserves_rendered_links_inside_list_items(
    tmp_path: Path,
) -> None:
    (tmp_path / "README.md").write_text(
        "# Example\n\n- Resources:\n    [Guide](missing-guide.md)\n",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)

    assert any(
        finding["code"] == "broken-local-links" for finding in result["findings"]
    )


def test_markdown_audit_converts_encoded_nul_paths_to_broken_links(
    tmp_path: Path,
) -> None:
    (tmp_path / "README.md").write_text(
        "# Example\n\n[Guide](docs/%00missing.md)\n",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)

    assert any(
        finding["code"] == "broken-local-links" for finding in result["findings"]
    )


def test_markdown_audit_masks_code_nested_inside_list_items(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Example\n\n- Samples:\n\n"
        "      [Indented](missing-indented.md)\n\n"
        "    ```markdown\n"
        "    [Fenced](missing-fenced.md)\n"
        "    ```\n",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)

    assert not any(
        finding["code"] == "broken-local-links" for finding in result["findings"]
    )


def test_markdown_audit_masks_fenced_code_inside_blockquotes(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Example\n\n> ```markdown\n> [Guide](missing-guide.md)\n> ```\n",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)

    assert not any(
        finding["code"] == "broken-local-links" for finding in result["findings"]
    )


def test_markdown_audit_masks_blockquote_fences_inside_lists(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Example\n\n- Samples:\n\n"
        "    > ```markdown\n"
        "    > [Guide](missing-guide.md)\n"
        "    > ```\n",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)

    assert not any(
        finding["code"] == "broken-local-links" for finding in result["findings"]
    )


@pytest.mark.parametrize(
    "fenced_container",
    [
        "> ```markdown\n> code\n",
        "- Samples:\n\n    ```markdown\n    code\n",
    ],
)
def test_unclosed_fences_end_with_their_container(
    tmp_path: Path,
    fenced_container: str,
) -> None:
    (tmp_path / "README.md").write_text(
        f"# Example\n\n{fenced_container}[Guide](missing-guide.md)\n",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)

    assert any(
        finding["code"] == "broken-local-links" for finding in result["findings"]
    )


def test_list_fence_stack_ends_with_its_enclosing_blockquote() -> None:
    markdown = "> - ```\n  [Visible](visible.md)\n  ```\n[Hidden](hidden.md)\n"

    assert documentation_audit._markdown_destinations(markdown) == ["visible.md"]


def test_indented_lazy_paragraph_lines_remain_visible_across_multiple_lines() -> None:
    markdown = "Paragraph\n    [First](first.md)\n    [Second](second.md)\n"

    assert documentation_audit._markdown_destinations(markdown) == [
        "first.md",
        "second.md",
    ]


@pytest.mark.parametrize(
    "markdown",
    [
        "> Paragraph\n> \n>     [Hidden](hidden.md)\n[Visible](visible.md)\n",
        (
            "- > Paragraph\n  > \n  >     [Hidden](hidden.md)\n"
            "[Visible](visible.md)\n"
        ),
    ],
)
def test_container_only_blank_enables_following_indented_code(markdown: str) -> None:
    assert documentation_audit._markdown_destinations(markdown) == ["visible.md"]


def test_list_exit_before_blockquote_does_not_reuse_stale_list_indent() -> None:
    markdown = "- Paragraph\n>     [Hidden](hidden.md)\n"

    assert documentation_audit._markdown_destinations(markdown) == []


@pytest.mark.parametrize(
    "markdown",
    [
        "- > ```\n  > [Hidden](hidden.md)\n  > ```\n[Visible](visible.md)\n",
        "1. > ~~~\n   > [Hidden](hidden.md)\n   > ~~~\n[Visible](visible.md)\n",
        "- - ```\n    [Hidden](hidden.md)\n    ```\n[Visible](visible.md)\n",
        "- 1. ~~~\n     [Hidden](hidden.md)\n     ~~~\n[Visible](visible.md)\n",
    ],
)
def test_interleaved_container_fences_mask_only_their_own_block(markdown: str) -> None:
    assert documentation_audit._markdown_destinations(markdown) == ["visible.md"]


@pytest.mark.parametrize(
    "markdown",
    [
        "- >     [Hidden](hidden.md)\n[Visible](visible.md)\n",
        "- -     [Hidden](hidden.md)\n[Visible](visible.md)\n",
    ],
)
def test_interleaved_container_indented_code_is_masked(markdown: str) -> None:
    assert documentation_audit._markdown_destinations(markdown) == ["visible.md"]


def test_open_fence_does_not_consume_extra_blockquote_markers_as_a_closer() -> None:
    markdown = "```\n> [Hidden](hidden.md)\n> ```\n[Also hidden](also-hidden.md)\n"

    assert documentation_audit._markdown_destinations(markdown) == []


def test_indented_paragraph_continuations_remain_rendered(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Example\n\nText\n    [Guide](missing-guide.md)\n",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)

    assert any(
        finding["code"] == "broken-local-links" for finding in result["findings"]
    )


def test_multiline_inline_links_support_crlf(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_bytes(
        b"# Example\r\n\r\n[Guide](\r\n docs/missing.md)\r\n",
    )

    result = audit_repository(tmp_path)

    assert any(
        finding["code"] == "broken-local-links" for finding in result["findings"]
    )


def test_markdown_audit_does_not_read_an_oversized_root_readme(
    tmp_path: Path,
) -> None:
    readme = tmp_path / "README.md"
    with readme.open("wb") as stream:
        stream.write(b"# Oversized\n")
        stream.seek(2_000_000)
        stream.write(b"x")

    result = audit_repository(tmp_path)

    assert result["has_readme"] is False
    assert result["markdown_files"] == 0
    assert any(finding["code"] == "missing-readme" for finding in result["findings"])


@pytest.mark.parametrize(
    ("limit_name", "limit"),
    [
        ("MAX_MARKDOWN_FILES", 1),
        ("MAX_MARKDOWN_REPOSITORY_BYTES", 12),
    ],
)
def test_markdown_audit_fails_closed_on_repository_wide_input_limits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    limit_name: str,
    limit: int,
) -> None:
    monkeypatch.setattr(documentation_audit, limit_name, limit)
    (tmp_path / "README.md").write_text("# Example\n", encoding="utf-8")
    (tmp_path / "SECOND.md").write_text("# Second document\n", encoding="utf-8")

    result = audit_repository(tmp_path)

    assert result["markdown_input_limit_exceeded"] is True
    assert any(
        finding["code"] == "markdown-input-limit"
        and finding["severity"] == "error"
        for finding in result["findings"]
    )


def test_markdown_audit_bounds_project_record_reads(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Example\n", encoding="utf-8")
    record_path = tmp_path / "project-record.yml"
    with record_path.open("wb") as stream:
        stream.write(b"contract_name: project-record.v1\n")
        stream.seek(2_000_000)
        stream.write(b"x")

    result = audit_repository(tmp_path)

    assert any("structured record exceeds 2000000 bytes" in error for error in result["record_errors"])
    assert any(
        finding["code"] == "invalid-project-record" for finding in result["findings"]
    )


def test_markdown_audit_rejects_outside_symlink_content(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("[Secret](token-from-outside.txt)\n", encoding="utf-8")
    (repository / "README.md").symlink_to(outside)

    result = audit_repository(repository)

    assert result["has_readme"] is False
    assert result["markdown_files"] == 0
    assert "token-from-outside" not in json.dumps(result)


def test_malformed_absolute_markdown_url_is_a_finding(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Example\n\n[Link](http://[)\n", encoding="utf-8")

    result = audit_repository(tmp_path)

    assert any(
        finding["code"] == "broken-local-links" for finding in result["findings"]
    )


def test_builder_scans_python_except_for_exact_structural_labels() -> None:
    builder_path = (
        Path(__file__).parents[1] / "docs/audits/build_reader_mode_estate_audit.py"
    )
    tree = ast.parse(builder_path.read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "bare_slug_scan_payload"
    )
    namespace = {
        "INPUT_MANIFEST": Path("reader-mode-input-manifest.json"),
        "Path": Path,
        "SOURCE_FILES": {
            "personal": "personal.json",
            "ergon": "ergon.json",
        },
        "PUBLIC_PROSE_REWRITES": (
            ("current personal profile", "current individual profile"),
        ),
        "PUBLIC_EXACT_REWRITES": {"contrib": "contribution"},
        "ast": ast,
        "io": __import__("io"),
        "json": json,
        "nbformat": nbformat,
        "re": re,
        "tokenize": __import__("tokenize"),
    }
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(builder_path), "exec"), namespace)

    payload = (
        'SOURCE_FILES = {\n    "personal": "personal.json",\n'
        '    "unrelated": "secretproject",  # personal\n}\n'
        'PUBLIC_PROSE_REWRITES = (("current personal profile", "safe"),)\n'
        'PUBLIC_EXACT_REWRITES = {"contrib": "contribution"}\n'
        'note = "personal.json"\n'
        'queue = ["personal", "contrib", "secretproject"]\n'
    )
    scan_payload = namespace["bare_slug_scan_payload"](Path("builder.py"), payload)

    assert '"personal": "personal.json"' not in scan_payload
    assert '"unrelated": "secretproject",  # personal' in scan_payload
    assert 'note = "personal.json"' in scan_payload
    assert 'queue = ["personal", "contrib", "secretproject"]' in scan_payload
    assert "secretproject" in scan_payload

    notebook = nbformat.v4.new_notebook(
        cells=[
            nbformat.v4.new_code_cell(
                'SOURCE_FILES = {"personal": "personal.json"}\n'
                'queue = ["personal", "secretproject"]\n',
            ),
        ],
    )
    notebook_payload = namespace["bare_slug_scan_payload"](
        Path("audit.ipynb"),
        nbformat.writes(notebook),
    )

    assert '"personal": "personal.json"' not in notebook_payload
    assert 'queue = ["personal", "secretproject"]' in notebook_payload


def test_builder_privacy_pattern_distinguishes_structural_and_private_names() -> None:
    private_identifiers = {
        "secret/personal",
        "secret/contrib",
        "secret/edu-organism",
        "secret/hidden-project",
    }
    public_identifiers = {"organvm/public-project"}
    private_only = private_only_repository_slugs(
        private_identifiers,
        public_identifiers,
    )
    pattern = repository_reference_pattern(
        private_identifiers,
        private_only,
        public_identifiers,
    )

    matches = [
        (match.lastgroup, match.group(0))
        for match in pattern.finditer(
            "current personal profile and contrib guide; `personal`; edu-organism; "
            "organvm/public-project; secret/hidden-project; "
            "https://github.com/secret/hidden-project.git; "
            "https://github.com/organvm/public-project.git",
        )
    ]

    assert matches == [
        ("private_slug", "personal"),
        ("private_slug", "contrib"),
        ("private_slug", "personal"),
        ("private_slug", "edu-organism"),
        ("public_full", "organvm/public-project"),
        ("private_full", "secret/hidden-project"),
        ("private_full", "secret/hidden-project"),
        ("public_full", "organvm/public-project"),
    ]
    redacted = redact_private_references(
        {
            "summary": "current personal profile for secret/hidden-project",
            "exact": "contrib",
            "nested": ["organvm/public-project", "edu-organism"],
        },
        pattern,
    )
    assert redacted == {
        "summary": "current individual profile for [private repository]",
        "exact": "contribution",
        "nested": ["organvm/public-project", "[private repository]"],
    }
    assert PUBLIC_PROSE_REWRITES[1] == (
        "current personal profile",
        "current individual profile",
    )
    assert PUBLIC_EXACT_REWRITES == {"contrib": "contribution"}


def test_committed_notebook_uses_pinned_inputs_and_explicit_integrity_gates() -> None:
    notebook_path = (
        Path(__file__).parents[1]
        / "docs/audits/2026-08-31-reader-mode-estate-audit.ipynb"
    )
    notebook = nbformat.read(notebook_path, as_version=4)
    code = "\n".join(
        cell.source for cell in notebook.cells if cell.cell_type == "code"
    )

    assert "pinned_input_manifest" in code
    assert "input_manifest = pinned_input_manifest" in code
    assert 'generated_at = pinned_input_manifest["generated_at"]' in code
    assert "datetime.now" not in code
    assert "verify_integrity=True" not in code
    assert "input_manifest = {" not in code
    assert "assert " not in code
    assert "def normalize_archived" in code
    assert 'inventory["repository"].str.casefold().nunique() == 323' in code
    for cell in notebook.cells:
        expected_id = hashlib.sha256(
            f"{cell.cell_type}\0{cell.source}".encode(),
        ).hexdigest()[:8]
        assert cell.id == expected_id


def test_lifecycle_assertion_fact_must_match_the_project_state(tmp_path: Path) -> None:
    record = _write_git_fixture(tmp_path)
    record["deployment_status"] = "public"
    record["claim_references"].append(
        {
            **record["claim_references"][0],
            "id": "public-deployment",
            "scope": "deployment",
            "claim_posture": "partial",
        },
    )
    assertion_path = tmp_path / "docs/evidence/claims/validation.json"
    assertion = json.loads(assertion_path.read_text(encoding="utf-8"))
    assertion["fact"] = {"predicate": "deployment_status", "value": "public"}
    assertion_path.write_text(json.dumps(assertion), encoding="utf-8")

    assert validate_project_record(record, root=tmp_path) == []

    invalid_facts = [
        None,
        {"predicate": "capability", "value": "public"},
        {"predicate": "deployment_status", "value": "pilot"},
    ]
    for fact in invalid_facts:
        candidate = dict(assertion)
        if fact is None:
            candidate.pop("fact")
        else:
            candidate["fact"] = fact
        assertion_path.write_text(json.dumps(candidate), encoding="utf-8")

        assert any(
            "fact predicate/value exactly matches deployment_status" in error
            for error in validate_project_record(record, root=tmp_path)
        )


def test_non_lifecycle_assertions_do_not_require_a_deployment_fact(tmp_path: Path) -> None:
    record = _write_git_fixture(tmp_path)

    assert validate_project_record(record, root=tmp_path) == []


def test_verified_assertion_requires_nonempty_evidence(tmp_path: Path) -> None:
    record = _write_git_fixture(tmp_path)
    assertion_path = tmp_path / "docs/evidence/claims/validation.json"
    assertion = json.loads(assertion_path.read_text(encoding="utf-8"))
    assertion.pop("evidence_references")
    assertion_path.write_text(json.dumps(assertion), encoding="utf-8")

    assert any(
        "verified assertion requires a non-empty evidence_references list" in error
        for error in validate_project_record(record, root=tmp_path)
    )


@pytest.mark.parametrize("contract_version", [None, True, 1.0])
def test_assertion_contract_version_requires_a_non_boolean_integer(
    tmp_path: Path,
    contract_version: object,
) -> None:
    record = _write_git_fixture(tmp_path)
    assertion_path = tmp_path / "docs/evidence/claims/validation.json"
    assertion = json.loads(assertion_path.read_text(encoding="utf-8"))
    if contract_version is None:
        assertion.pop("contract_version")
    else:
        assertion["contract_version"] = contract_version
    assertion_path.write_text(json.dumps(assertion), encoding="utf-8")

    assert any(
        "unsupported assertion contract_version" in error
        for error in validate_project_record(record, root=tmp_path)
    )


def test_assertion_class_requires_the_supported_vocabulary(tmp_path: Path) -> None:
    record = _write_git_fixture(tmp_path)
    assertion_path = tmp_path / "docs/evidence/claims/validation.json"
    assertion = json.loads(assertion_path.read_text(encoding="utf-8"))
    assertion["assertion_class"] = "current-state"
    assertion["evidence_references"] = ["not-a-mapping"]
    assertion_path.write_text(json.dumps(assertion), encoding="utf-8")

    errors = validate_project_record(record, root=tmp_path)

    assert any("invalid assertion_class: 'current-state'" in error for error in errors)
    assert any("evidence_references[0] must be a mapping" in error for error in errors)


def test_assertion_verification_state_requires_the_supported_vocabulary(
    tmp_path: Path,
) -> None:
    record = _write_git_fixture(tmp_path)
    assertion_path = tmp_path / "docs/evidence/claims/validation.json"
    assertion = json.loads(assertion_path.read_text(encoding="utf-8"))
    assertion["verification_state"] = "verifyd"
    assertion_path.write_text(json.dumps(assertion), encoding="utf-8")

    assert any(
        "invalid verification_state: 'verifyd'" in error
        for error in validate_project_record(record, root=tmp_path)
    )


def test_freshness_max_age_is_bounded_before_datetime_arithmetic(
    tmp_path: Path,
) -> None:
    record = _write_git_fixture(tmp_path)
    assertion_path = tmp_path / "docs/evidence/claims/validation.json"
    assertion = json.loads(assertion_path.read_text(encoding="utf-8"))
    assertion["assertion_class"] = "current_state"
    assertion["freshness"] = {
        "verified_at": "2025-01-01T00:00:00Z",
        "status": "fresh",
        "max_age_seconds": 10**30,
    }
    assertion_path.write_text(json.dumps(assertion), encoding="utf-8")

    errors = validate_project_record(
        record,
        root=tmp_path,
        now=datetime(2025, 1, 1, 0, 1, tzinfo=timezone.utc),
    )

    assert any("315576000" in error for error in errors)


@pytest.mark.parametrize("status", [[], {}])
def test_operator_directive_freshness_rejects_unhashable_status(
    tmp_path: Path,
    status: object,
) -> None:
    record = _write_git_fixture(tmp_path)
    assertion_path = tmp_path / "docs/evidence/claims/validation.json"
    assertion = json.loads(assertion_path.read_text(encoding="utf-8"))
    assertion["assertion_class"] = "operator_directive"
    assertion["freshness"] = {
        "status": status,
        "verified_at": "2025-01-01T00:00:00Z",
    }
    assertion_path.write_text(json.dumps(assertion), encoding="utf-8")

    assert any(
        "requires non-stale freshness" in error
        for error in validate_project_record(record, root=tmp_path)
    )


@pytest.mark.parametrize(
    "malformed_entry",
    [
        {},
        "not-a-mapping",
        {
            "evidence_id": "",
            "independence_group": "",
            "evidence_type": "unsupported",
            "reference": "",
            "body_hash": "sha256:not-a-digest",
        },
        {
            "evidence_id": [],
            "independence_group": {},
            "evidence_type": ["artifact"],
            "reference": [],
            "body_hash": {},
        },
    ],
)
def test_verified_assertion_rejects_malformed_evidence_entries(
    tmp_path: Path,
    malformed_entry: object,
) -> None:
    record = _write_git_fixture(tmp_path)
    assertion_path = tmp_path / "docs/evidence/claims/validation.json"
    assertion = json.loads(assertion_path.read_text(encoding="utf-8"))
    assertion["evidence_references"] = [malformed_entry]
    assertion_path.write_text(json.dumps(assertion), encoding="utf-8")

    errors = validate_project_record(record, root=tmp_path)

    assert any("evidence_references[0]" in error for error in errors)


def test_local_evidence_hashing_streams_without_path_read_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _write_git_fixture(tmp_path)
    evidence_path = tmp_path / "docs/evidence/sources/validation.txt"
    payload = b"streamed evidence\n" * 200_000
    evidence_path.write_bytes(payload)
    assertion_path = tmp_path / "docs/evidence/claims/validation.json"
    assertion = json.loads(assertion_path.read_text(encoding="utf-8"))
    assertion["evidence_references"][0]["body_hash"] = (
        "sha256:" + hashlib.sha256(payload).hexdigest()
    )
    assertion_path.write_text(json.dumps(assertion), encoding="utf-8")

    def reject_read_bytes(_path: Path) -> bytes:
        raise AssertionError("evidence hashing must stream")

    monkeypatch.setattr(Path, "read_bytes", reject_read_bytes)

    assert validate_project_record(record, root=tmp_path) == []


def test_repeated_local_evidence_references_share_one_streamed_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _write_git_fixture(tmp_path)
    assertion_path = tmp_path / "docs/evidence/claims/validation.json"
    assertion = json.loads(assertion_path.read_text(encoding="utf-8"))
    first = assertion["evidence_references"][0]
    assertion["evidence_references"] = [
        {**first, "evidence_id": f"validation-receipt-{index}"}
        for index in range(32)
    ]
    assertion_path.write_text(json.dumps(assertion), encoding="utf-8")
    original = documentation_record._stream_sha256
    stream_calls = 0

    def counted_stream(path: Path) -> str:
        nonlocal stream_calls
        stream_calls += 1
        return original(path)

    monkeypatch.setattr(documentation_record, "_stream_sha256", counted_stream)

    errors = validate_project_record(record, root=tmp_path)

    assert not any("body_hash does not match" in error for error in errors)
    assert stream_calls == 1


def test_repeated_git_evidence_references_share_one_streamed_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _write_git_fixture(tmp_path)
    commit = _git(tmp_path, "rev-parse", "HEAD").decode().strip()
    assertion_path = tmp_path / "docs/evidence/claims/validation.json"
    assertion = json.loads(assertion_path.read_text(encoding="utf-8"))
    first = assertion["evidence_references"][0]
    first["reference"] = (
        f"git:{commit}:docs/evidence/sources/validation.txt"
    )
    assertion["evidence_references"] = [
        {**first, "evidence_id": f"validation-receipt-{index}"}
        for index in range(4)
    ]
    assertion_path.write_text(json.dumps(assertion), encoding="utf-8")
    original = documentation_record._stream_git_object_sha256
    stream_calls = 0

    def counted_stream(
        root: Path,
        object_type: str,
        object_name: str,
    ) -> tuple[str | None, int]:
        nonlocal stream_calls
        stream_calls += 1
        return original(root, object_type, object_name)

    monkeypatch.setattr(
        documentation_record,
        "_stream_git_object_sha256",
        counted_stream,
    )

    errors = validate_project_record(record, root=tmp_path)

    assert not any("body_hash does not match" in error for error in errors)
    assert stream_calls == 1


@pytest.mark.parametrize("commit_available", [True, False])
def test_repeated_git_evidence_resolves_identity_once_per_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    commit_available: bool,
) -> None:
    record = _write_git_fixture(tmp_path)
    commit = (
        _git(tmp_path, "rev-parse", "HEAD").decode().strip()
        if commit_available
        else "f" * 40
    )
    evidence_path = "docs/evidence/sources/validation.txt"
    evidence_reference = f"git:{commit}:{evidence_path}"
    assertion_path = tmp_path / "docs/evidence/claims/validation.json"
    assertion = json.loads(assertion_path.read_text(encoding="utf-8"))
    first = assertion["evidence_references"][0]
    first["reference"] = evidence_reference
    assertion["evidence_references"] = [
        {**first, "evidence_id": f"validation-receipt-{index}"}
        for index in range(32)
    ]
    assertion_path.write_text(json.dumps(assertion), encoding="utf-8")
    record["limitations"] = [
        {
            "id": "shared-assertion-consumer",
            "statement": "The evidence is shared across these claims.",
            "assertion_id": "validation",
            "assertion_ref": "docs/evidence/claims/validation.json",
        },
    ]

    original_run_git = documentation_record._run_git
    identity_resolution_processes = 0
    revision = f"{commit}:{evidence_path}"

    def counted_run_git(
        root: Path,
        *args: str,
    ) -> subprocess.CompletedProcess[bytes]:
        nonlocal identity_resolution_processes
        if args == ("rev-parse", "--verify", revision):
            identity_resolution_processes += 1
        return original_run_git(root, *args)

    monkeypatch.setattr(documentation_record, "_run_git", counted_run_git)

    first_errors = validate_project_record(record, root=tmp_path)
    assert identity_resolution_processes == 1
    second_errors = validate_project_record(record, root=tmp_path)
    assert identity_resolution_processes == 2
    assert second_errors == first_errors
    if commit_available:
        assert first_errors == []
    else:
        assert any("git commit is unavailable locally" in error for error in first_errors)


@pytest.mark.parametrize("reference_kind", ["local", "hardlink", "git"])
def test_external_fact_independence_requires_distinct_resolved_objects(
    tmp_path: Path,
    reference_kind: str,
) -> None:
    record = _write_git_fixture(tmp_path)
    assertion_path = tmp_path / "docs/evidence/claims/validation.json"
    assertion = json.loads(assertion_path.read_text(encoding="utf-8"))
    evidence = assertion["evidence_references"][0]
    hardlink_reference: str | None = None
    second_git_reference: str | None = None
    if reference_kind == "git":
        commit = _git(tmp_path, "rev-parse", "HEAD").decode().strip()
        evidence["reference"] = (
            f"git:{commit}:docs/evidence/sources/validation.txt"
        )
        _git(tmp_path, "commit", "--allow-empty", "-m", "same evidence object")
        second_commit = _git(tmp_path, "rev-parse", "HEAD").decode().strip()
        second_git_reference = (
            f"git:{second_commit}:docs/evidence/sources/validation.txt"
        )
    elif reference_kind == "hardlink":
        hardlink = tmp_path / "docs/evidence/sources/validation-alias.txt"
        hardlink.hardlink_to(tmp_path / evidence["reference"])
        hardlink_reference = hardlink.relative_to(tmp_path).as_posix()
    assertion["assertion_class"] = "external_fact"
    second = dict(evidence)
    second["evidence_id"] = "same-object-second-label"
    second["independence_group"] = "second-group"
    if hardlink_reference is not None:
        second["reference"] = hardlink_reference
    if second_git_reference is not None:
        second["reference"] = second_git_reference
    assertion["evidence_references"].append(second)
    assertion_path.write_text(json.dumps(assertion), encoding="utf-8")

    errors = validate_project_record(record, root=tmp_path)

    assert any("distinct resolved evidence objects" in error for error in errors)


def test_operator_directive_types_require_distinct_resolved_objects(
    tmp_path: Path,
) -> None:
    record = _write_git_fixture(tmp_path)
    assertion_path = tmp_path / "docs/evidence/claims/validation.json"
    assertion = json.loads(assertion_path.read_text(encoding="utf-8"))
    assertion["assertion_class"] = "operator_directive"
    assertion["freshness"] = {
        "verified_at": "2025-01-01T00:00:00Z",
        "status": "not_applicable",
    }
    first = assertion["evidence_references"][0]
    first["evidence_type"] = "immutable_source_event"
    second = dict(first)
    second["evidence_id"] = "same-object-constitutional-label"
    second["independence_group"] = "constitutional-record"
    second["evidence_type"] = "ratified_constitutional_record"
    assertion["evidence_references"].append(second)
    assertion_path.write_text(json.dumps(assertion), encoding="utf-8")

    errors = validate_project_record(record, root=tmp_path)

    assert any(
        "ratified constitutional record to resolve to distinct evidence objects"
        in error
        for error in errors
    )


@pytest.mark.parametrize("max_age_seconds", [None, 0, -1, True, "60"])
def test_verified_fresh_current_state_requires_positive_max_age(
    tmp_path: Path,
    max_age_seconds: object,
) -> None:
    record = _write_git_fixture(tmp_path)
    assertion_path = tmp_path / "docs/evidence/claims/validation.json"
    assertion = json.loads(assertion_path.read_text(encoding="utf-8"))
    assertion["assertion_class"] = "current_state"
    assertion["freshness"] = {
        "verified_at": "2025-01-01T00:00:00Z",
        "status": "fresh",
    }
    if max_age_seconds is not None:
        assertion["freshness"]["max_age_seconds"] = max_age_seconds
    assertion_path.write_text(json.dumps(assertion), encoding="utf-8")

    errors = validate_project_record(
        record,
        root=tmp_path,
        now=datetime(2025, 1, 1, 0, 1, tzinfo=timezone.utc),
    )

    assert any(
        "max_age_seconds to be a positive integer" in error for error in errors
    )


@pytest.mark.parametrize("status", [None, "none", "unsupported", 7, ["active"]])
def test_canonical_redirect_requires_supported_non_none_status(status: object) -> None:
    record = _record()
    record["documentation_class"] = "D"
    record["repository_role"] = "deployment-artifact"
    record["audience_routes"] = []
    record["links"]["documentation"] = "README.md"
    record["redirect"] = {
        "target": "https://github.com/organvm/example",
    }
    if status is not None:
        record["redirect"]["status"] = status

    assert any(
        "requires redirect.status to be one of: active, planned, retired" in error
        for error in validate_project_record(record)
    )


@pytest.mark.parametrize("git_component", [".GIT", ".Git", ".gIt"])
def test_evidence_paths_reject_git_metadata_case_insensitively(
    tmp_path: Path,
    git_component: str,
) -> None:
    record = _write_git_fixture(tmp_path)
    assertion_path = tmp_path / "docs/evidence/claims/validation.json"
    assertion = json.loads(assertion_path.read_text(encoding="utf-8"))
    assertion["evidence_references"][0]["reference"] = f"{git_component}/config"
    assertion["evidence_references"][0]["body_hash"] = (
        "sha256:" + "0" * 64
    )
    assertion_path.write_text(json.dumps(assertion), encoding="utf-8")

    assert any(
        "reference under .git is forbidden" in error
        for error in validate_project_record(record, root=tmp_path)
    )


@pytest.mark.parametrize("git_component", [".GIT", ".Git", ".gIt"])
def test_assertion_paths_reject_git_metadata_case_insensitively(
    tmp_path: Path,
    git_component: str,
) -> None:
    record = _write_git_fixture(tmp_path)
    record["claim_references"][0]["assertion_ref"] = f"{git_component}/config"

    assert any(
        "assertion path under .git is forbidden" in error
        for error in validate_project_record(record, root=tmp_path)
    )


@pytest.mark.parametrize("git_component", [".GIT", ".Git", ".gIt"])
def test_git_object_paths_reject_git_metadata_case_insensitively(
    tmp_path: Path,
    git_component: str,
) -> None:
    record = _write_git_fixture(tmp_path)
    commit = _git(tmp_path, "rev-parse", "HEAD").decode().strip()
    assertion_path = tmp_path / "docs/evidence/claims/validation.json"
    assertion = json.loads(assertion_path.read_text(encoding="utf-8"))
    assertion["evidence_references"][0]["reference"] = (
        f"git:{commit}:{git_component}/config"
    )
    assertion_path.write_text(json.dumps(assertion), encoding="utf-8")

    assert any(
        "git evidence path is not contained" in error
        for error in validate_project_record(record, root=tmp_path)
    )


@pytest.mark.parametrize("workspace_argument", ["empty-directory", ""])
def test_docs_audit_explicit_empty_workspace_fails_closed(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    workspace_argument: str,
) -> None:
    workspace = tmp_path / workspace_argument if workspace_argument else ""
    if workspace_argument:
        workspace.mkdir()
    args = Namespace(
        paths=[],
        workspace=str(workspace),
        format="json",
        json=True,
        output=None,
        strict=False,
    )

    assert cmd_docs_audit(args) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "no Git repositories discovered under explicit workspace" in captured.err


def test_strict_git_binding_treats_pathspec_magic_as_a_literal(tmp_path: Path) -> None:
    record = _write_git_fixture(tmp_path)
    magic_name = ":(glob)**"
    magic_path = tmp_path / magic_name
    magic_path.write_text("untracked magic evidence\n", encoding="utf-8")
    assertion_path = tmp_path / "docs/evidence/claims/validation.json"
    assertion = json.loads(assertion_path.read_text(encoding="utf-8"))
    assertion["evidence_references"][0]["reference"] = magic_name
    assertion["evidence_references"][0]["body_hash"] = (
        "sha256:" + hashlib.sha256(magic_path.read_bytes()).hexdigest()
    )
    assertion_path.write_text(json.dumps(assertion), encoding="utf-8")
    _git(tmp_path, "add", "--", "docs/evidence/claims/validation.json")
    _git(tmp_path, "commit", "-m", "bind magic path fixture")

    assert any(
        "evidence is ignored or untracked" in error
        for error in validate_project_record(
            record,
            root=tmp_path,
            require_git_tracked_evidence=True,
        )
    )


@pytest.mark.parametrize(
    "uri",
    [
        "https://:443/path",
        "https://example.test:notaport/path",
        "https://example.test:99999/path",
    ],
)
def test_web_uris_require_a_valid_host_and_port(uri: str) -> None:
    record = _record()
    record["links"]["demo"] = uri

    assert "links.demo must be an absolute HTTP(S) URI" in validate_project_record(record)


def test_duplicate_detection_does_not_rescan_the_input_list() -> None:
    class CountForbiddenList(list[str]):
        def count(self, value: str) -> int:
            raise AssertionError(f"quadratic count called for {value!r}")

    values = CountForbiddenList(["beta", "alpha", "beta", "alpha", "gamma"])

    assert documentation_record._duplicates(values) == ["alpha", "beta"]


def test_timezone_conversion_overflow_is_a_validation_error() -> None:
    record = _record()
    record["generated_at"] = "0001-01-01T00:00:00+23:59"
    record["verified_at"] = "0001-01-01T00:00:00+23:59"

    errors = validate_project_record(record)

    assert "generated_at must be an ISO 8601 date-time with a timezone" in errors
    assert "verified_at must be an ISO 8601 date-time with a timezone" in errors


def test_reference_style_markdown_links_are_audited(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Example\n\n[Guide][guide]\n\n[guide]: docs/missing.md\n",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)

    assert any(
        finding["code"] == "broken-local-links" for finding in result["findings"]
    )


@pytest.mark.parametrize(
    "definition",
    [
        '[guide]: docs/missing.md "unterminated\n',
        '[guide]: docs/missing.md "title" trailing\n',
        "[guide]: <docs/missing.md> trailing\n",
        "[guide]: docs/missing.md (nested(title))\n",
    ],
)
def test_malformed_reference_definition_suffixes_invalidate_the_definition(
    definition: str,
) -> None:
    markdown = f"{definition}\n[Guide][guide]\n"

    assert documentation_audit._markdown_destinations(markdown) == []


@pytest.mark.parametrize(
    "title",
    ['"double title"', "'single title'", "(parenthesized title)"],
)
def test_reference_definitions_accept_complete_inline_titles(title: str) -> None:
    markdown = f"[guide]: docs/missing.md {title}\n\n[Guide][guide]\n"

    assert documentation_audit._markdown_destinations(markdown) == [
        "docs/missing.md",
    ]


def test_reference_definitions_accept_a_complete_next_line_title() -> None:
    markdown = (
        '[guide]: docs/missing.md\n          "Guide title"\n\n'
        "[Guide][guide]\n"
    )

    assert documentation_audit._markdown_destinations(markdown) == [
        "docs/missing.md",
    ]


def test_malformed_next_line_title_does_not_invalidate_a_complete_definition() -> None:
    markdown = (
        '[guide]: docs/missing.md\n"not a complete title\n'
        "[Guide][guide]\n"
    )

    assert documentation_audit._markdown_destinations(markdown) == [
        "docs/missing.md",
    ]


@pytest.mark.parametrize(
    "markdown",
    [
        "Paragraph\n[guide]: docs/missing.md\n[Guide][guide]\n",
        "Paragraph\n    continuation\n[guide]: docs/missing.md\n[Guide][guide]\n",
        "Paragraph\n2. [guide]: docs/missing.md\n[Guide][guide]\n",
        "- Paragraph\n  [guide]: docs/missing.md\n[Guide][guide]\n",
        "> Paragraph\n> [guide]: docs/missing.md\n[Guide][guide]\n",
        "- Paragraph\n[guide]: docs/missing.md\n\n[Guide][guide]\n",
        "> Paragraph\n[guide]: docs/missing.md\n\n[Guide][guide]\n",
    ],
)
def test_reference_definitions_cannot_interrupt_an_open_paragraph(
    markdown: str,
) -> None:
    assert documentation_audit._markdown_destinations(markdown) == []


@pytest.mark.parametrize(
    "markdown",
    [
        "Paragraph\n\n[guide]: docs/missing.md\n[Guide][guide]\n",
        "# Heading\n[guide]: docs/missing.md\n[Guide][guide]\n",
        "> # Heading\n[guide]: docs/missing.md\n[Guide][guide]\n",
        "- # Heading\n[guide]: docs/missing.md\n[Guide][guide]\n",
        "- Paragraph\n- [guide]: docs/missing.md\n[Guide][guide]\n",
        "10. Paragraph\n\n    [guide]: docs/missing.md\n[Guide][guide]\n",
    ],
)
def test_reference_definitions_are_recognized_at_valid_block_boundaries(
    markdown: str,
) -> None:
    assert documentation_audit._markdown_destinations(markdown) == [
        "docs/missing.md",
    ]


@pytest.mark.parametrize(
    "markdown",
    [
        "> Paragraph\n2. [guide]: docs/missing.md\n\n[Guide][guide]\n",
        "- Paragraph\n2. [guide]: docs/missing.md\n\n[Guide][guide]\n",
    ],
)
def test_reference_definitions_follow_a_new_block_after_container_exit(
    markdown: str,
) -> None:
    assert documentation_audit._markdown_destinations(markdown) == [
        "docs/missing.md",
    ]


@pytest.mark.parametrize(
    "markdown",
    [
        "> > Paragraph\n> [guide]: docs/missing.md\n\n[Guide][guide]\n",
        "> - Paragraph\n> [guide]: docs/missing.md\n\n[Guide][guide]\n",
    ],
)
def test_reference_definitions_remain_lazy_inside_a_common_container(
    markdown: str,
) -> None:
    assert documentation_audit._markdown_destinations(markdown) == []


@pytest.mark.parametrize(
    ("definition", "usage"),
    [
        ("> [multi\nline]: docs/missing.md\n", "multi line"),
        ("- [multi\nline]: docs/missing.md\n", "multi line"),
        ("> [multi]:\ndocs/missing.md\n", "multi"),
        ("- [multi]:\ndocs/missing.md\n", "multi"),
        ('> [multi]: docs/missing.md "first\nsecond"\n', "multi"),
        ('- [multi]: docs/missing.md "first\nsecond"\n', "multi"),
    ],
)
def test_reference_definitions_allow_lazy_container_continuations(
    definition: str,
    usage: str,
) -> None:
    markdown = f"{definition}\n[Multi][{usage}]\n"

    assert documentation_audit._markdown_destinations(markdown) == [
        "docs/missing.md",
    ]


@pytest.mark.parametrize(
    "definition",
    [
        '> [multi]: docs/missing.md "first\n> > second"\n',
        "> [multi]:\n> > docs/missing.md\n",
        "> [multi\n> > line]: docs/missing.md\n",
        '- [multi]: docs/missing.md "first\n  - second"\n',
        "- [multi]:\n  - docs/missing.md\n",
        "- [multi\n  - line]: docs/missing.md\n",
    ],
)
def test_reference_definition_continuations_reject_new_nested_blocks(
    definition: str,
) -> None:
    markdown = f"{definition}\n[Multi][multi]\n"

    assert documentation_audit._markdown_destinations(markdown) == []


@pytest.mark.parametrize(
    "definition",
    [
        '> [multi]: docs/missing.md "first\n2. second"\n',
        '- [multi]: docs/missing.md "first\n2. second"\n',
    ],
)
def test_reference_definition_container_exit_accepts_any_new_list_start(
    definition: str,
) -> None:
    markdown = f"{definition}\n[Multi][multi]\n"

    assert documentation_audit._markdown_destinations(markdown) == []


@pytest.mark.parametrize(
    "definition",
    [
        '> [multi]: docs/missing.md "first\n> 2. second"\n',
        '- [multi]: docs/missing.md "first\n  2. second"\n',
    ],
)
def test_retained_container_allows_ordered_start_two_in_lazy_title_text(
    definition: str,
) -> None:
    markdown = f"{definition}\n[Multi][multi]\n"

    assert documentation_audit._markdown_destinations(markdown) == [
        "docs/missing.md",
    ]


@pytest.mark.parametrize(
    "indent",
    ["    ", "        "],
)
def test_indented_lazy_reference_definition_continuations_remain_paragraphs(
    indent: str,
) -> None:
    markdown = f"> [multi\n{indent}line]: docs/missing.md\n\n[Multi line]\n"

    assert documentation_audit._markdown_destinations(markdown) == [
        "docs/missing.md",
    ]


@pytest.mark.parametrize(
    "usage",
    [
        "> [Multi\n    line][multi line]",
        "> [multi\n    line][]",
        "> [multi\n    line]",
    ],
)
def test_indented_lazy_multiline_reference_usages_remain_paragraphs(
    usage: str,
) -> None:
    markdown = f"[multi line]: docs/missing.md\n\n{usage}\n"

    assert documentation_audit._markdown_destinations(markdown) == [
        "docs/missing.md",
    ]


@pytest.mark.parametrize(
    "usage",
    [
        "[multi\n- line]",
        "[multi\n1. line]",
        "[multi\n# line]",
        "- [multi\n  - line]",
        "- [multi\n  1. line]",
        "- [multi\n  # line]",
    ],
)
def test_multiline_reference_usages_reject_interrupting_blocks(usage: str) -> None:
    markdown = (
        "[multi - line]: docs/missing.md\n"
        "[multi 1. line]: docs/one.md\n"
        "[multi # line]: docs/hash.md\n\n"
        f"{usage}\n"
    )

    assert documentation_audit._markdown_destinations(markdown) == []


@pytest.mark.parametrize(
    "usage",
    [
        "[multi\n2. line]",
        "- [multi\n  2. line]",
    ],
)
def test_ordered_list_start_two_remains_a_lazy_reference_label(usage: str) -> None:
    markdown = f"[multi 2. line]: docs/missing.md\n\n{usage}\n"

    assert documentation_audit._markdown_destinations(markdown) == [
        "docs/missing.md",
    ]


def test_reference_usage_quote_depth_is_scanned_once_per_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = documentation_audit._markdown_reference_containers
    calls = 0

    def counted(value: str) -> tuple[str, tuple[tuple[str, int], ...]]:
        nonlocal calls
        calls += 1
        return original(value)

    monkeypatch.setattr(
        documentation_audit,
        "_markdown_reference_containers",
        counted,
    )

    assert len(list(documentation_audit._markdown_reference_usages("[x] " * 4_096))) == 4_096
    assert calls == 1


def test_multiline_reference_style_destinations_are_audited(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Example\n\n[Guide][guide]\n\n[guide]:\n          docs/missing.md\n",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)

    assert any(
        finding["code"] == "broken-local-links" for finding in result["findings"]
    )


def test_blockquote_reference_style_destinations_are_audited(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Example\n\n> [guide]: docs/missing.md\n\n[Guide][guide]\n",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)

    assert any(
        finding["code"] == "broken-local-links" for finding in result["findings"]
    )


def test_nested_blockquote_multiline_reference_destinations_are_audited(
    tmp_path: Path,
) -> None:
    (tmp_path / "README.md").write_text(
        "# Example\n\n> > [guide]:\n> >   docs/missing.md\n\n[Guide][guide]\n",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)

    assert any(
        finding["code"] == "broken-local-links" for finding in result["findings"]
    )


@pytest.mark.parametrize(
    ("definition", "continuation"),
    [
        ("- - > [guide]: docs/missing.md", "    > [Guide]"),
        ("- 1. > [guide]: docs/missing.md", "     > [Guide]"),
        ("1. - > [guide]: docs/missing.md", "     > [Guide]"),
        ("1. 1. > [guide]: docs/missing.md", "      > [Guide]"),
    ],
)
def test_reference_definitions_retain_ordered_interleaved_containers(
    definition: str,
    continuation: str,
) -> None:
    markdown = f"{definition}\n{continuation}\n"

    assert documentation_audit._markdown_destinations(markdown) == [
        "docs/missing.md",
    ]


def test_reference_definition_starts_after_nested_container_relative_blank() -> None:
    markdown = (
        "- - > paragraph\n"
        "    > \n"
        "    > [guide]: docs/missing.md\n\n"
        "[Guide]\n"
    )

    assert documentation_audit._markdown_destinations(markdown) == [
        "docs/missing.md",
    ]


@pytest.mark.parametrize(
    "markdown",
    [
        "<x>\n    ```\n[hidden](hidden.md)\n",
        "<div>\n    code\n[hidden](hidden.md)\n",
    ],
)
def test_raw_html_scope_is_resolved_before_block_code_masking(markdown: str) -> None:
    assert documentation_audit._markdown_destinations(markdown) == []


def test_indented_explicit_html_terminator_remains_effective() -> None:
    markdown = "<!--\n    -->\n[visible](visible.md)\n"

    assert documentation_audit._markdown_destinations(markdown) == ["visible.md"]


def test_html_looking_content_inside_a_fence_remains_code() -> None:
    markdown = "```html\n<div>\n[hidden](hidden.md)\n```\n"

    assert documentation_audit._markdown_destinations(markdown) == []


@pytest.mark.parametrize("marker", ["1. ", "+ ", "* "])
def test_empty_list_item_does_not_interrupt_a_paragraph(marker: str) -> None:
    markdown = f"> paragraph\n> {marker}\n      [visible](visible.md)\n"

    assert documentation_audit._markdown_destinations(markdown) == ["visible.md"]


def test_empty_hyphen_line_remains_a_setext_interrupt() -> None:
    markdown = "> paragraph\n> - \n      [hidden](hidden.md)\n"

    assert documentation_audit._markdown_destinations(markdown) == []


def test_partial_container_blank_closes_paragraph_before_indented_code() -> None:
    markdown = "> 1. paragraph\n> \n      [hidden](hidden.md)\n"

    assert documentation_audit._markdown_destinations(markdown) == []


def test_unmarked_blank_closes_stale_quote_list_before_indented_code() -> None:
    markdown = "> - paragraph\n\n>     [hidden](hidden.md)\n"

    assert documentation_audit._markdown_destinations(markdown) == []


@pytest.mark.parametrize(
    "markdown",
    [
        "`code`\n[ref]: visible.md\n\n[ref]\n",
        "> `code`\n> [ref]: visible.md\n\n[ref]\n",
    ],
)
def test_inline_code_only_paragraph_stays_nonblank_when_masked(markdown: str) -> None:
    assert documentation_audit._markdown_destinations(markdown) == []


def test_html_mask_retains_list_container_for_following_markdown() -> None:
    markdown = "1. > <x>\n      [visible](visible.md)\n"

    assert documentation_audit._markdown_destinations(markdown) == ["visible.md"]


def test_lost_fence_containers_do_not_leave_stale_list_state() -> None:
    markdown = "> 1. ```\n   \n   >     [hidden](hidden.md)\n"

    assert documentation_audit._markdown_destinations(markdown) == []


def test_setext_underline_does_not_open_a_list_container() -> None:
    markdown = "> paragraph\n> - \n   >     [hidden](hidden.md)\n"

    assert documentation_audit._markdown_destinations(markdown) == []


def test_empty_list_after_exited_quote_retains_its_root_container() -> None:
    markdown = "> paragraph\n- \n    [visible](visible.md)\n"

    assert documentation_audit._markdown_destinations(markdown) == ["visible.md"]


def test_html_mask_preserves_nonempty_list_item_padding() -> None:
    markdown = "- <!A\n  > [ref]: destination.md\n    > p [visible](visible.md)\n"

    assert documentation_audit._markdown_destinations(markdown) == ["visible.md"]


@pytest.mark.parametrize(
    "definition",
    [
        "- [guide]: docs/missing.md\n",
        "10. [guide]:\n    docs/missing.md\n",
        "> - [guide]:\n>   docs/missing.md\n",
        "[guide]:\ndocs/missing.md\n",
    ],
)
def test_list_and_unindented_reference_destinations_are_audited(
    tmp_path: Path,
    definition: str,
) -> None:
    (tmp_path / "README.md").write_text(
        f"# Example\n\n{definition}\n[Guide][guide]\n",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)

    assert any(
        finding["code"] == "broken-local-links" for finding in result["findings"]
    )


def test_reference_destinations_decode_commonmark_punctuation_escapes(
    tmp_path: Path,
) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/a(b).md").write_text("# Guide\n", encoding="utf-8")
    (tmp_path / "README.md").write_text(
        "# Example\n\n[Guide][guide]\n\n[guide]: docs/a\\(b\\).md\n",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)

    assert not any(
        finding["code"] == "broken-local-links" for finding in result["findings"]
    )


@pytest.mark.parametrize(
    ("reference", "expected"),
    [
        ("docs/a&amp;b.md", "docs/a&b.md"),
        ("docs/a&#38;b.md", "docs/a&b.md"),
        ("docs/a&#x26;b.md", "docs/a&b.md"),
        ("docs/a&ampb.md", "docs/a&ampb.md"),
        ("docs/a&#38b.md", "docs/a&#38b.md"),
        ("docs/a&#x26b.md", "docs/a&#x26b.md"),
        ("docs/a&notaname;.md", "docs/a&notaname;.md"),
        ("docs/a\\&amp;b.md", "docs/a&amp;b.md"),
    ],
)
def test_markdown_destinations_decode_only_complete_character_references(
    reference: str,
    expected: str,
) -> None:
    markdown = f"[Guide]({reference})\n"

    assert documentation_audit._markdown_destinations(markdown) == [expected]


@pytest.mark.parametrize(
    "usage",
    [
        "[Guide][multi\n line]",
        "[multi\n line][]",
        "[multi\n line]",
    ],
)
def test_multiline_full_collapsed_and_shortcut_reference_labels(
    usage: str,
) -> None:
    markdown = f"[multi\n line]: docs/missing.md\n\n{usage}\n"

    assert documentation_audit._markdown_destinations(markdown) == [
        "docs/missing.md",
    ]


@pytest.mark.parametrize(
    "usage",
    [
        "> [Guide][multi\n>  line]",
        "> [multi\n>  line][]",
        "> [multi\n>  line]",
    ],
)
def test_multiline_reference_labels_strip_their_blockquote_container(
    usage: str,
) -> None:
    markdown = f"[multi line]: docs/missing.md\n\n{usage}\n"

    assert documentation_audit._markdown_destinations(markdown) == [
        "docs/missing.md",
    ]


def test_root_multiline_label_does_not_consume_a_new_blockquote() -> None:
    markdown = "[multi > line]: docs/missing.md\n\n[Guide][multi\n> line]\n"

    assert documentation_audit._markdown_destinations(markdown) == []


@pytest.mark.parametrize(
    "markdown",
    [
        "[multi\n\n line]: docs/missing.md\n\n[multi line]\n",
        "[multi line]: docs/missing.md\n\n[multi\n\n line]\n",
    ],
)
def test_reference_labels_cannot_contain_blank_lines(markdown: str) -> None:
    assert documentation_audit._markdown_destinations(markdown) == []


def test_reference_label_matching_does_not_parse_inline_escapes_or_entities() -> None:
    markdown = (
        "[escaped\\!]: docs/escaped.md\n"
        "[entity&amp;]: docs/entity.md\n\n"
        "[Escaped!][escaped!]\n"
        "[Entity&][entity&]\n"
    )

    assert documentation_audit._markdown_destinations(markdown) == []


def test_excess_list_padding_keeps_reference_definitions_in_code(
    tmp_path: Path,
) -> None:
    (tmp_path / "README.md").write_text(
        "# Example\n\n-     [guide]: docs/missing.md\n\n[Guide][guide]\n",
        encoding="utf-8",
    )

    result = audit_repository(tmp_path)

    assert not any(
        finding["code"] == "broken-local-links" for finding in result["findings"]
    )


def test_symlinked_project_record_is_not_read(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "README.md").write_text("# Repository\n", encoding="utf-8")
    outside = tmp_path / "outside.yml"
    outside.write_text(
        "documentation_class: SECRET_OUTSIDE_RECORD\n",
        encoding="utf-8",
    )
    (repository / "project-record.yml").symlink_to(outside)

    result = audit_repository(repository)

    assert result["has_project_record"] is False
    assert "SECRET_OUTSIDE_RECORD" not in json.dumps(result)


@pytest.mark.parametrize(
    ("audience", "signal"),
    [
        ("technical", "technical_depth"),
        ("humanities", "conceptual_depth"),
        ("business", "commercial_relevance"),
    ],
)
def test_symlinked_audience_file_does_not_award_a_signal_bonus(
    tmp_path: Path,
    audience: str,
    signal: str,
) -> None:
    repository = tmp_path / "repository"
    audience_dir = repository / "docs/audiences"
    audience_dir.mkdir(parents=True)
    (repository / "README.md").write_text("# Repository\n", encoding="utf-8")
    outside = tmp_path / f"{audience}.md"
    outside.write_text("outside audience material\n", encoding="utf-8")
    (audience_dir / f"{audience}.md").symlink_to(outside)

    result = audit_repository(repository)

    assert result["signals"][signal] == 0


def test_workspace_discovery_keeps_repositories_named_like_generated_dirs(
    tmp_path: Path,
) -> None:
    expected = []
    for name in ("build", "vendor"):
        repository = tmp_path / name
        (repository / ".git").mkdir(parents=True)
        expected.append(repository.resolve())

    from organvm_engine.documentation.audit import discover_repositories

    assert discover_repositories(tmp_path) == expected


def test_builder_rejects_explicit_invalid_visibility() -> None:
    builder_path = (
        Path(__file__).parents[1] / "docs/audits/build_reader_mode_estate_audit.py"
    )
    tree = ast.parse(builder_path.read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "source_visibility"
    )
    namespace: dict[str, object] = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(builder_path), "exec"), namespace)

    with pytest.raises(RuntimeError, match="invalid visibility"):
        namespace["source_visibility"](
            {"visibility": "internal", "metadata": {"public": True}},
            source="fixture",
            index=0,
        )


@pytest.mark.parametrize("value", ["false", 0, None, []])
def test_builder_rejects_nonboolean_archived_values(value: object) -> None:
    builder_path = (
        Path(__file__).parents[1] / "docs/audits/build_reader_mode_estate_audit.py"
    )
    tree = ast.parse(builder_path.read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "source_archived"
    )
    namespace: dict[str, object] = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(builder_path), "exec"), namespace)

    with pytest.raises(RuntimeError, match="invalid archived value"):
        namespace["source_archived"](
            {"archived": value},
            source="fixture",
            index=0,
        )

    assert namespace["source_archived"](
        {"archived": False},
        source="fixture",
        index=0,
    ) is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("project_id", None),
        ("name", []),
        ("one_sentence", None),
        ("problem", {}),
        ("intended_users", None),
        ("authorship", []),
    ],
)
def test_builtin_project_record_shape_is_enforced_without_external_schema(
    field: str,
    value: object,
) -> None:
    record = _record()
    record[field] = value

    errors = validate_project_record(record)

    assert any(field in error for error in errors)


def test_evidence_hash_rejects_a_path_identity_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _write_git_fixture(tmp_path)
    original_stream = documentation_record._stream_sha256
    replaced = False

    def replace_after_hash(path: Path) -> str:
        nonlocal replaced
        digest = original_stream(path)
        replacement = path.with_name("replacement.txt")
        replacement.write_bytes(path.read_bytes())
        replacement.replace(path)
        replaced = True
        return digest

    monkeypatch.setattr(documentation_record, "_stream_sha256", replace_after_hash)

    errors = validate_project_record(record, root=tmp_path)

    assert replaced is True
    assert any("evidence identity changed while hashing" in error for error in errors)


def test_assertion_read_rejects_an_unstable_path_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _write_git_fixture(tmp_path)
    assertion_path = tmp_path / "docs/evidence/claims/validation.json"
    original_read = documentation_record.read_stable_regular_bytes

    def fail_assertion(path: Path, **kwargs) -> bytes:
        if Path(path) == assertion_path:
            raise documentation_record.StableReadError("simulated assertion replacement")
        return original_read(path, **kwargs)

    monkeypatch.setattr(
        documentation_record,
        "read_stable_regular_bytes",
        fail_assertion,
    )

    errors = validate_project_record(record, root=tmp_path)

    assert any("cannot load assertion" in error for error in errors)


def test_local_evidence_uses_the_documented_evidence_byte_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = tmp_path / "evidence.bin"
    evidence.write_bytes(b"evidence")
    real_read = documentation_record.read_stable_regular_bytes
    observed_limit: int | None = None

    def capture_limit(path: Path, *, maximum_bytes: int) -> bytes:
        nonlocal observed_limit
        observed_limit = maximum_bytes
        return real_read(path, maximum_bytes=maximum_bytes)

    monkeypatch.setattr(documentation_record, "read_stable_regular_bytes", capture_limit)

    documentation_record._stream_sha256(evidence)

    assert observed_limit == documentation_record.MAX_EVIDENCE_BYTES
    assert observed_limit > documentation_record.MAX_STRUCTURED_RECORD_BYTES


def test_git_evidence_stream_stops_at_the_evidence_byte_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _git(tmp_path, "init")
    payload = b"x" * 65
    source = tmp_path / "large-evidence.bin"
    source.write_bytes(payload)
    object_id = _git(tmp_path, "hash-object", "-w", str(source)).decode().strip()
    monkeypatch.setattr(documentation_record, "MAX_EVIDENCE_BYTES", 64)

    with pytest.raises(documentation_record.StableReadError, match="exceeds 64 byte limit"):
        documentation_record._stream_git_object_sha256(tmp_path, "blob", object_id)


def test_commit_bound_assertion_bytes_must_equal_the_head_blob(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _write_git_fixture(tmp_path)
    assertion_path = tmp_path / "docs/evidence/claims/validation.json"
    real_check = documentation_record._git_tracked_path_errors
    replaced = False

    def replace_after_git_check(**kwargs):
        nonlocal replaced
        result = real_check(**kwargs)
        if kwargs.get("object_name") == "assertion" and not replaced:
            assertion_path.write_text(
                assertion_path.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )
            replaced = True
        return result

    monkeypatch.setattr(
        documentation_record,
        "_git_tracked_path_errors",
        replace_after_git_check,
    )

    errors = validate_project_record(
        record,
        root=tmp_path,
        require_git_tracked_evidence=True,
    )

    assert replaced is True
    assert any("assertion bytes do not match HEAD" in error for error in errors)


def test_commit_bound_evidence_bytes_must_equal_the_head_blob(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _write_git_fixture(tmp_path)
    evidence_path = tmp_path / "docs/evidence/sources/validation.txt"
    replacement = b"replacement evidence\n"
    assertion_path = tmp_path / "docs/evidence/claims/validation.json"
    assertion = json.loads(assertion_path.read_text(encoding="utf-8"))
    assertion["evidence_references"][0]["body_hash"] = (
        "sha256:" + hashlib.sha256(replacement).hexdigest()
    )
    assertion_path.write_text(json.dumps(assertion), encoding="utf-8")
    _git(tmp_path, "add", str(assertion_path.relative_to(tmp_path)))
    _git(tmp_path, "commit", "-m", "bind replacement digest")
    real_check = documentation_record._git_tracked_path_errors
    replaced = False

    def replace_after_git_check(**kwargs):
        nonlocal replaced
        result = real_check(**kwargs)
        if kwargs.get("relative") == evidence_path.relative_to(tmp_path).as_posix() and not replaced:
            evidence_path.write_bytes(replacement)
            replaced = True
        return result

    monkeypatch.setattr(
        documentation_record,
        "_git_tracked_path_errors",
        replace_after_git_check,
    )

    errors = validate_project_record(
        record,
        root=tmp_path,
        require_git_tracked_evidence=True,
    )

    assert replaced is True
    assert not any("body_hash does not match raw bytes" in error for error in errors)
    assert any("evidence bytes do not match HEAD" in error for error in errors)


def test_commit_bound_validation_pins_one_head_and_rejects_head_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _write_git_fixture(tmp_path)
    _git(tmp_path, "commit", "--allow-empty", "-m", "validation head")
    pinned_head = _git(tmp_path, "rev-parse", "HEAD").decode().strip()
    prior_head = _git(tmp_path, "rev-parse", "HEAD^").decode().strip()
    real_check = documentation_record._git_tracked_path_errors
    real_stream = documentation_record._stream_git_object_sha256
    blob_names: list[str] = []
    moved = False

    def move_head_after_first_check(**kwargs):
        nonlocal moved
        result = real_check(**kwargs)
        if not moved:
            _git(tmp_path, "checkout", "--detach", prior_head)
            moved = True
        return result

    def capture_blob_name(root: Path, object_type: str, object_name: str):
        if object_type == "blob":
            blob_names.append(object_name)
        return real_stream(root, object_type, object_name)

    monkeypatch.setattr(
        documentation_record,
        "_git_tracked_path_errors",
        move_head_after_first_check,
    )
    monkeypatch.setattr(
        documentation_record,
        "_stream_git_object_sha256",
        capture_blob_name,
    )

    errors = validate_project_record(
        record,
        root=tmp_path,
        require_git_tracked_evidence=True,
    )

    assert moved is True
    assert blob_names
    assert all(name.startswith(f"{pinned_head}:") for name in blob_names)
    assert any("HEAD changed during validation" in error for error in errors)


def test_markdown_audit_skips_an_unstable_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    (repository / "README.md").write_text("# Reader surface\n", encoding="utf-8")

    def fail_stable_read(*_args, **_kwargs):
        raise documentation_audit.StableReadError("simulated Markdown replacement")

    monkeypatch.setattr(
        documentation_audit,
        "read_stable_regular_bytes",
        fail_stable_read,
    )

    result = audit_repository(repository)

    assert result["markdown_files"] == 0


def _load_audit_builder():
    builder_path = (
        Path(__file__).parents[1] / "docs/audits/build_reader_mode_estate_audit.py"
    )
    spec = importlib.util.spec_from_file_location(
        "reader_mode_audit_builder_test",
        builder_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _safe_live_artifacts(module, root: Path) -> dict[Path, bytes]:
    notebook_path = root / module.NOTEBOOK.name
    summary_path = root / "reader-mode-estate-summary.json"
    rollout_path = root / "reader-mode-public-rollout.json"
    report_path = root / "reader-mode-estate-audit.md"
    artifacts = {
        notebook_path: nbformat.writes(
            nbformat.v4.new_notebook(
                cells=[nbformat.v4.new_markdown_cell("old public notebook")],
            ),
        ).encode(),
        summary_path: b'{"scope":{"source_segments":{}},"state":"old"}\n',
        rollout_path: b'{"state":"old"}\n',
        report_path: b"# Old public report\n",
    }
    for path, payload in artifacts.items():
        path.write_bytes(payload)
    return artifacts


def _private_builder_inputs(module) -> tuple[dict[str, bytes], dict[str, dict]]:
    bundles = {
        source: {"repositories": []}
        for source in module.SOURCE_FILES
    }
    bundles["ergon"] = {
        "repositories": [
            {
                "repository": f"secret/private-{index}",
                "visibility": "private",
            }
            for index in range(84)
        ],
    }
    payloads = {
        source: json.dumps(bundle).encode()
        for source, bundle in bundles.items()
    }
    return payloads, bundles


def _configure_builder_main(
    module,
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[bytes, dict[Path, bytes]]:
    monkeypatch.setattr(module, "HERE", root)
    monkeypatch.setattr(module, "NOTEBOOK", root / module.NOTEBOOK.name)
    monkeypatch.setattr(module, "INPUT_MANIFEST", root / module.INPUT_MANIFEST.name)
    manifest_bytes = b'{"sources":[]}\n'
    module.INPUT_MANIFEST.write_bytes(manifest_bytes)
    originals = _safe_live_artifacts(module, root)
    payloads, bundles = _private_builder_inputs(module)
    monkeypatch.setattr(
        module,
        "verify_live_inputs_against_manifest",
        lambda: ({}, manifest_bytes, payloads, bundles),
    )
    return manifest_bytes, originals


def test_importing_audit_builder_has_no_filesystem_side_effects() -> None:
    audit_dir = Path(__file__).parents[1] / "docs/audits"
    paths = [
        audit_dir / "2026-08-31-reader-mode-estate-audit.ipynb",
        audit_dir / "reader-mode-input-manifest.json",
        audit_dir / "reader-mode-estate-summary.json",
        audit_dir / "reader-mode-public-rollout.json",
        audit_dir / "reader-mode-estate-audit.md",
    ]
    before = {path: path.read_bytes() for path in paths}

    _load_audit_builder()

    assert {path: path.read_bytes() for path in paths} == before


def test_builder_executes_from_verified_snapshots_after_live_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_audit_builder()
    monkeypatch.setattr(module, "HERE", tmp_path)
    monkeypatch.setattr(module, "NOTEBOOK", tmp_path / module.NOTEBOOK.name)
    monkeypatch.setattr(module, "INPUT_MANIFEST", tmp_path / module.INPUT_MANIFEST.name)
    originals = _safe_live_artifacts(module, tmp_path)
    live_input_dir = tmp_path / "live-inputs"
    live_input_dir.mkdir()
    source_payloads = {
        source: b'{"repositories":[]}\n'
        for source in module.SOURCE_FILES
    }
    sources = []
    for source, filename in module.SOURCE_FILES.items():
        payload = source_payloads[source]
        (live_input_dir / filename).write_bytes(payload)
        sources.append(
            {
                "source_segment": source,
                "filename": filename,
                "rows": 0,
                "public": 0,
                "private": 0,
                "sha256": hashlib.sha256(payload).hexdigest(),
            },
        )
    manifest = {
        "schema_version": "reader-mode-input-manifest.v1",
        "sources": sources,
        "totals": {
            "source_segments": len(module.SOURCE_FILES),
            "repositories": 0,
            "public": 0,
            "private": 0,
        },
    }
    module.INPUT_MANIFEST.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setenv("ORGANVM_DOC_AUDIT_INPUT_DIR", str(live_input_dir))

    def mutate_live_then_stop(_document, *, input_dir: Path, output_dir: Path):
        first_source = next(iter(module.SOURCE_FILES))
        filename = module.SOURCE_FILES[first_source]
        (live_input_dir / filename).write_bytes(b'{"repositories":[{"leak":true}]}')
        assert (input_dir / filename).read_bytes() == source_payloads[first_source]
        assert input_dir.parent != output_dir
        raise RuntimeError("snapshot verified")

    monkeypatch.setattr(module, "execute_notebook", mutate_live_then_stop)

    with pytest.raises(RuntimeError, match="snapshot verified"):
        module.main()

    assert {path: path.read_bytes() for path in originals} == originals


def test_notebook_failure_cannot_mutate_live_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_audit_builder()
    manifest_bytes, originals = _configure_builder_main(module, tmp_path, monkeypatch)

    def fail_in_stage(_document, *, input_dir: Path, output_dir: Path):
        (output_dir / "reader-mode-estate-audit.md").write_text(
            "unsafe staged output",
            encoding="utf-8",
        )
        raise RuntimeError("simulated notebook failure")

    monkeypatch.setattr(module, "execute_notebook", fail_in_stage)

    with pytest.raises(RuntimeError, match="simulated notebook failure"):
        module.main()

    assert module.INPUT_MANIFEST.read_bytes() == manifest_bytes
    assert {path: path.read_bytes() for path in originals} == originals


def test_privacy_failure_cannot_mutate_live_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_audit_builder()
    manifest_bytes, originals = _configure_builder_main(module, tmp_path, monkeypatch)

    def write_private_candidate(_document, *, input_dir: Path, output_dir: Path):
        (output_dir / "reader-mode-estate-summary.json").write_text(
            '{"scope":{"source_segments":{}}}\n',
            encoding="utf-8",
        )
        (output_dir / "reader-mode-public-rollout.json").write_text(
            "{}\n",
            encoding="utf-8",
        )
        (output_dir / "reader-mode-estate-audit.md").write_text(
            "secret/private-0\n",
            encoding="utf-8",
        )
        return nbformat.v4.new_notebook(
            cells=[nbformat.v4.new_markdown_cell("public notebook")],
        )

    monkeypatch.setattr(module, "execute_notebook", write_private_candidate)

    with pytest.raises(RuntimeError, match="Detected private repository identifier"):
        module.main()

    assert module.INPUT_MANIFEST.read_bytes() == manifest_bytes
    assert {path: path.read_bytes() for path in originals} == originals


def test_safe_candidate_publishes_exact_scanned_bytes_and_preserves_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_audit_builder()
    manifest_bytes, _originals = _configure_builder_main(module, tmp_path, monkeypatch)
    expected_outputs = {
        "reader-mode-estate-summary.json": b'{"scope":{"source_segments":{}},"state":"new"}\n',
        "reader-mode-public-rollout.json": b'{"state":"new"}\n',
        "reader-mode-estate-audit.md": b"# New public report\n",
    }

    def write_safe_candidate(_document, *, input_dir: Path, output_dir: Path):
        for name, payload in expected_outputs.items():
            (output_dir / name).write_bytes(payload)
        return nbformat.v4.new_notebook(
            cells=[nbformat.v4.new_markdown_cell("new public notebook")],
        )

    published: dict[Path, bytes] = {}
    real_publish = module.publish_exact_candidate_bytes

    def capture_publish(candidate_bytes: dict[Path, bytes]) -> None:
        published.update(candidate_bytes)
        real_publish(candidate_bytes)

    monkeypatch.setattr(module, "execute_notebook", write_safe_candidate)
    monkeypatch.setattr(module, "publish_exact_candidate_bytes", capture_publish)

    module.main()

    assert module.INPUT_MANIFEST.read_bytes() == manifest_bytes
    assert set(path.name for path in published) == set(module.PUBLISHED_ARTIFACT_NAMES)
    for path, payload in published.items():
        assert path.read_bytes() == payload
    for name, payload in expected_outputs.items():
        assert (tmp_path / name).read_bytes() == payload
    executed = nbformat.read(tmp_path / module.NOTEBOOK.name, as_version=4)
    assert executed.cells[0].source == "new public notebook"


def test_audit_artifact_publication_restores_the_complete_preimage_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_audit_builder()
    monkeypatch.setattr(module, "HERE", tmp_path)
    targets = [tmp_path / name for name in module.PUBLISHED_ARTIFACT_NAMES]
    originals = {target: f"old:{target.name}\n".encode() for target in targets}
    candidates = {target: f"new:{target.name}\n".encode() for target in targets}
    for target, payload in originals.items():
        target.write_bytes(payload)
    real_link = module.os.link
    candidate_links = 0

    def fail_third_candidate(source, target, **kwargs):
        nonlocal candidate_links
        if source.suffix == ".tmp":
            candidate_links += 1
            if candidate_links == 3:
                raise OSError("simulated publication failure")
        return real_link(source, target, **kwargs)

    monkeypatch.setattr(module.os, "link", fail_third_candidate)

    with pytest.raises(OSError, match="simulated publication failure"):
        module.publish_exact_candidate_bytes(candidates)

    assert {target: target.read_bytes() for target in targets} == originals
    assert not list(tmp_path.glob(".*.tmp"))
    assert not list(tmp_path.glob(".*.rollback"))


def test_audit_publication_preserves_a_concurrent_edit_at_the_swap_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_audit_builder()
    monkeypatch.setattr(module, "HERE", tmp_path)
    targets = [tmp_path / name for name in module.PUBLISHED_ARTIFACT_NAMES]
    candidates = {target: f"new:{target.name}\n".encode() for target in targets}
    for target in targets:
        target.write_text(f"old:{target.name}\n", encoding="utf-8")
    raced_target = targets[1]
    concurrent = b"concurrent user edit\n"
    real_rename = Path.rename
    raced = False

    def edit_before_move(source: Path, target: Path):
        nonlocal raced
        if source == raced_target and not raced:
            source.write_bytes(concurrent)
            raced = True
        return real_rename(source, target)

    monkeypatch.setattr(Path, "rename", edit_before_move)

    with pytest.raises(RuntimeError, match="changed before publication"):
        module.publish_exact_candidate_bytes(candidates)

    assert raced is True
    assert raced_target.read_bytes() == concurrent
    assert targets[0].read_bytes() == f"old:{targets[0].name}\n".encode()
    assert not list(tmp_path.glob(".*.displaced"))
    assert not list(tmp_path.glob(".*.failed"))


def test_audit_rollback_never_overwrites_a_concurrent_edit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_audit_builder()
    monkeypatch.setattr(module, "HERE", tmp_path)
    targets = [tmp_path / name for name in module.PUBLISHED_ARTIFACT_NAMES]
    candidates = {target: f"new:{target.name}\n".encode() for target in targets}
    for target in targets:
        target.write_text(f"old:{target.name}\n", encoding="utf-8")
    concurrently_edited = targets[0]
    concurrent = b"concurrent edit after publication\n"
    real_link = module.os.link
    candidate_links = 0

    def edit_then_fail(source, target, **kwargs):
        nonlocal candidate_links
        if source.suffix == ".tmp":
            candidate_links += 1
            if candidate_links == 3:
                concurrently_edited.write_bytes(concurrent)
                raise OSError("simulated late publication failure")
        return real_link(source, target, **kwargs)

    monkeypatch.setattr(module.os, "link", edit_then_fail)

    with pytest.raises(RuntimeError, match="rollback was incomplete"):
        module.publish_exact_candidate_bytes(candidates)

    assert concurrently_edited.read_bytes() == concurrent
    assert targets[1].read_bytes() == f"old:{targets[1].name}\n".encode()
