"""Regression counterexamples for Engine #175's remaining input boundaries."""

from __future__ import annotations

import json
from argparse import Namespace

import pytest
import yaml
from test_documentation_record_hardening import _record, _write_git_fixture

from organvm_engine._stable_io import StableReadError
from organvm_engine.cli.docs import cmd_docs_validate
from organvm_engine.contextmd.generator import resolve_agents_remote_references
from organvm_engine.documentation.record import validate_project_record
from organvm_engine.seed.discover import discover_seeds


@pytest.mark.parametrize("field", ["primary_question", "surface"])
@pytest.mark.parametrize("value", [None, [], "", "missing"])
def test_route_baseline_cannot_be_weakened_by_optional_schema(field, value):
    record = _record()
    if value == "missing":
        del record["audience_routes"][0][field]
    else:
        record["audience_routes"][0][field] = value
    errors = validate_project_record(record, schema={})
    assert any("audience_routes/0" in error and field in error for error in errors)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("limitations", [{"id": "boundary"}]),
        ("limitations", [{"id": "boundary", "statement": []}]),
        ("search_intents", [{"intent": "research"}]),
        ("search_intents", [{"intent": "research", "terms": []}]),
        ("search_intents", [{"intent": "invented", "terms": ["research"]}]),
        ("industries", [{"name": [], "status": "proposed"}]),
    ],
)
def test_nested_contract_shape_is_always_enforced(field, value):
    record = _record()
    record[field] = value
    assert any(field in error for error in validate_project_record(record))


@pytest.mark.parametrize("value", [None, [], "", "missing"])
def test_assertion_statement_is_required_even_with_permissive_schema(tmp_path, value):
    record = _write_git_fixture(tmp_path)
    target = tmp_path / "docs/evidence/claims/validation.json"
    assertion = json.loads(target.read_text())
    if value == "missing":
        del assertion["statement"]
    else:
        assertion["statement"] = value
    target.write_text(json.dumps(assertion))
    errors = validate_project_record(record, root=tmp_path, assertion_schema={})
    assert any("statement" in error for error in errors)


@pytest.mark.parametrize("parent_link", [False, True])
def test_cli_rejects_symlink_record_before_deriving_repository_root(
    tmp_path, capsys, parent_link,
):
    outside = tmp_path / "outside"
    outside.mkdir()
    record = _write_git_fixture(outside)
    (outside / "project-record.yml").write_text(yaml.safe_dump(record))
    repository = tmp_path / "repository"
    repository.mkdir()
    if parent_link:
        (repository / "linked").symlink_to(outside, target_is_directory=True)
        path = repository / "linked/project-record.yml"
    else:
        path = repository / "project-record.yml"
        path.symlink_to(outside / "project-record.yml")
    args = Namespace(record=str(path), root=None, schema=None, json=True)
    assert cmd_docs_validate(args) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["record"] == str(path)
    assert result["valid"] is False


@pytest.mark.parametrize("direction", ["produces", "consumes"])
def test_remote_context_owner_and_default_branch_are_one_identity(direction):
    registry = {"organs": {"META": {"repositories": [
        {"name": "shared", "org": "wrong-owner", "default_branch": "wrong"},
        {"name": "shared", "org": "right-owner", "default_branch": "release/v2"},
    ]}}}
    seed = (
        {"produces": [{"consumers": [{"repo": "shared", "github_org": "right-owner"}]}]}
        if direction == "produces"
        else {"consumes": [{"source": "right-owner/shared"}]}
    )
    references = resolve_agents_remote_references(seed, registry, default_owner="fallback")
    assert len(references) == 1
    assert references[0]["repository"] == "right-owner/shared"
    assert references[0]["ref"] == "release/v2"


@pytest.mark.parametrize("kind", ["symlink", "dangling", "directory", "malformed"])
def test_invalid_workspace_manifest_never_expands_seed_discovery(tmp_path, kind):
    repo = tmp_path / "organvm-i-theoria/private-repo"
    repo.mkdir(parents=True)
    (repo / "seed.yaml").write_text("repo: private-repo\n")
    manifest = tmp_path / "workspace-manifest.yaml"
    if kind in {"symlink", "dangling"}:
        target = tmp_path / "external.yaml"
        if kind == "symlink":
            target.write_text("organs_present: [II]\n")
        manifest.symlink_to(target)
    elif kind == "directory":
        manifest.mkdir()
    else:
        manifest.write_text("organs_present: null\n")
    with pytest.raises((StableReadError, ValueError)):
        discover_seeds(tmp_path)


def test_explicit_empty_manifest_discovers_no_organs(tmp_path):
    repo = tmp_path / "organvm-i-theoria/private-repo"
    repo.mkdir(parents=True)
    (repo / "seed.yaml").write_text("repo: private-repo\n")
    (tmp_path / "workspace-manifest.yaml").write_text("organs_present: []\n")
    assert discover_seeds(tmp_path) == []
