"""Counterexamples for the resumed reader-mode acceptance gate."""

from argparse import Namespace

import pytest
from test_documentation import _record, _write_routes

from organvm_engine.cli.context import cmd_context_sync
from organvm_engine.cli.docs import cmd_docs_audit
from organvm_engine.contextmd.sync import sync_all
from organvm_engine.documentation.privacy import (
    private_only_repository_slugs,
    redact_private_references,
    repository_reference_pattern,
)
from organvm_engine.documentation.record import validate_project_record


@pytest.mark.parametrize("suffix", [".md", ".json", ".github.io", ".tar.gz", ".yaml", ".html"])
@pytest.mark.parametrize("qualified", [False, True])
@pytest.mark.parametrize("prefix", ["", "docs."])
def test_private_references_remain_private_with_file_or_hostname_suffix(suffix, qualified, prefix):
    private = {"owner/secret-repo"}
    pattern = repository_reference_pattern(private, {"secret-repo"}, set())
    identifier = "owner/secret-repo" if qualified else "secret-repo"
    rendered = redact_private_references({"note": prefix + identifier + suffix}, pattern)
    assert rendered == {"note": prefix + "[private repository]" + suffix}
    assert any(match.lastgroup != "public_full" for match in pattern.finditer(prefix + identifier + suffix))


@pytest.mark.parametrize("private", [{"owner/project"}, {"owner/project.md"}])
def test_suffix_matching_preserves_longest_known_repository_identity(private):
    public = {"owner/project", "owner/project.md"} - private
    pattern = repository_reference_pattern(private, private_only_repository_slugs(private, public), public)
    private_name, public_name = next(iter(private)), next(iter(public))
    assert redact_private_references(public_name + ".json", pattern) == public_name + ".json"
    assert redact_private_references(private_name + ".json", pattern) == "[private repository].json"
    assert redact_private_references("owner/project-extra", pattern) == "owner/project-extra"


def test_upstream_fork_can_link_to_actual_fork_repository(tmp_path):
    record = _record("F")
    record["repository_role"] = "upstream-fork"
    record["links"]["repository"] = "https://github.com/contributor/example"
    record["claim_references"][1]["scope"] = "provenance"
    _write_routes(tmp_path, record)
    assert validate_project_record(record, root=tmp_path, actual_repository="contributor/example") == []


@pytest.mark.parametrize("role", ["canonical", "mirror", "deployment-artifact"])
def test_declared_canonical_link_roles_still_require_canonical_target(tmp_path, role):
    record = _record("B" if role == "canonical" else "D")
    record["repository_role"] = role
    record["links"]["repository"] = "https://github.com/contributor/example"
    if role != "canonical":
        record["redirect"] = {"status": "active", "target": "https://github.com/organvm/example"}
    _write_routes(tmp_path, record)
    errors = validate_project_record(record, root=tmp_path)
    assert "canonical_repository must agree with links.repository GitHub owner/name" in errors


def test_receipt_request_in_dry_run_fails_before_workspace_read(tmp_path):
    with pytest.raises(ValueError, match="receipt.*dry.run"):
        sync_all(workspace=tmp_path / "missing", registry_path=str(tmp_path / "missing.json"),
                 receipt_path=tmp_path / "receipt.json", dry_run=True)
    assert not list(tmp_path.iterdir())


def test_context_cli_rejects_receipt_without_write(tmp_path, capsys, monkeypatch):
    import organvm_engine.contextmd.sync as module

    def unexpected_sync(**_kwargs):
        pytest.fail("invalid receipt options must fail before synchronization")

    monkeypatch.setattr(module, "sync_all", unexpected_sync)
    assert cmd_context_sync(Namespace(write=False, receipt=str(tmp_path / "receipt.json"))) == 1
    assert "--receipt requires --write" in capsys.readouterr().err


@pytest.mark.parametrize("invalid_kind", ["missing", "file", "empty"])
def test_explicit_audit_paths_must_all_name_existing_directories(tmp_path, capsys, monkeypatch, invalid_kind):
    import organvm_engine.cli.docs as module

    valid = tmp_path / "valid"
    valid.mkdir()
    invalid = tmp_path / "invalid"
    if invalid_kind == "file":
        invalid.write_text("ordinary file", encoding="utf-8")

    def unexpected_audit(_path):
        pytest.fail("validate the full explicit path list before producing any audit")

    monkeypatch.setattr(module, "audit_repository", unexpected_audit)
    output = tmp_path / "report.json"
    args = Namespace(paths=[str(valid), "" if invalid_kind == "empty" else str(invalid)],
                     workspace=None, format="json", json=True, output=str(output), strict=False)
    assert cmd_docs_audit(args) == 1
    assert "explicit audit path" in capsys.readouterr().err
    assert not output.exists()
