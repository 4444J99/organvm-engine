"""Counterexamples for the September 9 exact-head acceptance review."""

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

from organvm_engine.contextmd.receipt import generator_git_identity
from organvm_engine.contextmd.sync import sync_all
from organvm_engine.documentation.audit import audit_repository
from organvm_engine.documentation.privacy import (
    private_only_repository_slugs,
    redact_private_references,
    repository_reference_pattern,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _isolate(monkeypatch) -> None:
    monkeypatch.setattr("organvm_engine.contextmd.sync.precompute_ammoi", lambda: None)
    monkeypatch.setattr(
        "organvm_engine.contextmd.receipt.generator_git_identity",
        lambda *args, **kwargs: {"commit": "a" * 40, "tree": "b" * 40},
    )
    monkeypatch.setattr(
        "organvm_engine.pulse.emitter.emit_engine_event", lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "organvm_engine.ledger.emit.testament_emit", lambda *args, **kwargs: None,
    )


@pytest.mark.parametrize("object_format", ["sha1", "sha256"])
def test_generator_identity_binds_real_git_object_formats(tmp_path, object_format) -> None:
    subprocess.run(
        ["git", "init", "-q", f"--object-format={object_format}", str(tmp_path)], check=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "-c", "user.name=Fixture", "-c",
         "user.email=fixture@example.invalid", "commit", "-q", "--allow-empty", "-m", "Fixture"],
        check=True,
    )
    identity = generator_git_identity(tmp_path)
    expected_length = 40 if object_format == "sha1" else 64
    assert len(identity["commit"]) == expected_length
    assert len(identity["tree"]) == expected_length
    assert identity["tree"] == subprocess.check_output(
        ["git", "-C", str(tmp_path), "rev-parse", f"{identity['commit']}^{{tree}}"], text=True,
    ).strip()


def test_generator_identity_rejects_mixed_object_formats(tmp_path, monkeypatch) -> None:
    from organvm_engine.contextmd.receipt import _validated_generator_identity

    monkeypatch.setattr("organvm_engine.contextmd.receipt._git_status_entries", lambda _root: [])
    monkeypatch.setattr(
        "organvm_engine.contextmd.receipt._git",
        lambda _root, *args: "a" * (40 if args[-1] == "HEAD" else 64),
    )
    with pytest.raises(RuntimeError, match="identity is malformed"):
        generator_git_identity(tmp_path)
    with pytest.raises(RuntimeError, match="exact commit and tree"):
        _validated_generator_identity({"commit": "a" * 40, "tree": "b" * 64})


@pytest.mark.parametrize("private_slug", ["foo", "bar", "baz"])
@pytest.mark.parametrize("public_slug", ["foo.bar", "Foo.BAR", "foo.bar.baz"])
def test_longer_public_bare_slug_remains_public_without_exempting_private_slug(
    public_slug, private_slug,
) -> None:
    private = {f"private/{private_slug}"}
    public = {f"public/{public_slug}"}
    pattern = repository_reference_pattern(
        private, private_only_repository_slugs(private, public), public,
    )
    text = f"{public_slug} and public/{public_slug}; {private_slug}; private/{private_slug}; {private_slug}.json"
    assert redact_private_references(text, pattern) == (
        f"{public_slug} and public/{public_slug}; [private repository]; "
        "[private repository]; [private repository].json"
    )
    assert not [
        match for match in pattern.finditer(public_slug)
        if match.lastgroup in {"private_full", "private_slug"}
    ]


def test_longer_private_slug_wins_over_shorter_public_slug() -> None:
    private = {"private/foo.bar"}
    public = {"public/foo"}
    pattern = repository_reference_pattern(
        private, private_only_repository_slugs(private, public), public,
    )
    assert redact_private_references("foo.bar; foo; public/foo", pattern) == (
        "[private repository]; foo; public/foo"
    )


@pytest.mark.parametrize("grow_during_read", [False, True])
def test_oversized_nested_markdown_is_an_explicit_audit_limit(
    tmp_path, monkeypatch, grow_during_read,
) -> None:
    import organvm_engine._stable_io as stable_io
    import organvm_engine.documentation.audit as audit_mod

    monkeypatch.setattr(audit_mod, "MAX_MARKDOWN_FILE_BYTES", 128)
    (tmp_path / "README.md").write_text("# Overview\n", encoding="utf-8")
    docs = tmp_path / "docs"
    docs.mkdir()
    target = docs / "LARGE.md"
    target.write_bytes(b"x" * (32 if grow_during_read else 129))
    real_read = stable_io.os.read
    grew = False

    def grow_then_read(descriptor, count):
        nonlocal grew
        if grow_during_read and not grew and os.fstat(descriptor).st_ino == target.stat().st_ino:
            grew = True
            with target.open("ab") as stream:
                stream.write(b"x" * 129)
        return real_read(descriptor, count)

    monkeypatch.setattr(stable_io.os, "read", grow_then_read)
    result = audit_repository(tmp_path)
    assert result["markdown_input_limit_exceeded"] is True
    assert any(
        finding["code"] == "markdown-input-limit" and finding["severity"] == "error"
        for finding in result["findings"]
    )
    assert grew is grow_during_read


def test_duplicate_resolved_roots_publish_each_output_once(tmp_path, monkeypatch) -> None:
    _isolate(monkeypatch)
    workspace = tmp_path / "workspace"
    flat = workspace / "flat"
    repo = flat / "recursive-engine"
    repo.mkdir(parents=True)
    (repo / "AGENTS.md").write_text("# Manual introduction\n", encoding="utf-8")
    alias = workspace / "alias"
    alias.symlink_to(flat, target_is_directory=True)
    receipt_path = workspace / "receipt.json"
    result = sync_all(
        workspace=workspace,
        registry_path=str(FIXTURES / "registry-minimal.json"),
        additional_workspace_roots=[flat, flat / ".", alias],
        organs=["ORGAN-I"],
        receipt_path=receipt_path,
    )
    receipt = json.loads(receipt_path.read_text())
    assert result["errors"] == []
    assert receipt["status"] == "success"
    assert receipt["inputs"]["invocation"]["additional_workspace_roots"] == ["flat"]
    outputs = [entry["path"] for entry in receipt["outputs"]]
    assert len(outputs) == len(set(outputs))
    assert "Manual introduction" in (repo / "AGENTS.md").read_text()


@pytest.mark.parametrize("explicit_directory", [None, "local-theory"])
def test_owner_identity_does_not_change_organ_output_directory(
    tmp_path, monkeypatch, explicit_directory,
) -> None:
    _isolate(monkeypatch)
    registry = json.loads((FIXTURES / "registry-minimal.json").read_text())
    organ = registry["organs"]["ORGAN-I"]
    organ["github_org"] = "remote-owner"
    organ["org"] = "another-owner"
    for entry in organ["repositories"]:
        entry["org"] = "remote-owner"
    if explicit_directory:
        organ["directory"] = explicit_directory
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps(registry))
    workspace = tmp_path / "workspace"
    local_directory = explicit_directory or "organvm-i-theoria"
    repo = workspace / local_directory / "recursive-engine"
    repo.mkdir(parents=True)
    result = sync_all(
        workspace=workspace, registry_path=str(registry_path),
        additional_workspace_roots=[], organs=["ORGAN-I"],
        receipt_path=workspace / "receipt.json",
    )
    receipt = json.loads((workspace / "receipt.json").read_text())
    assert result["errors"] == []
    assert receipt["inputs"]["invocation"]["organ_directory_map"] == {
        "ORGAN-I": local_directory,
    }
    assert (repo / "AGENTS.md").exists()
    assert not (workspace / "remote-owner").exists()


@pytest.mark.parametrize("directory", ["../outside", "", None, 42, "parent/child"])
def test_malformed_explicit_organ_directory_never_falls_back(directory) -> None:
    from organvm_engine.contextmd.sync import _registry_organ_directory_map

    with pytest.raises(RuntimeError, match="invalid explicit organ directory"):
        _registry_organ_directory_map({"organs": {"ORGAN-I": {
            "directory": directory, "org": "remote-owner",
            "repositories": [{"org": "remote-owner"}],
        }}})


@pytest.mark.parametrize("concurrent_winner", [False, True])
def test_retained_agents_failure_keeps_rendered_reference_inventory(
    tmp_path, monkeypatch, concurrent_winner,
) -> None:
    import organvm_engine.contextmd.sync as sync_mod

    _isolate(monkeypatch)
    workspace = tmp_path / "workspace"
    repo = workspace / "flat" / "recursive-engine"
    repo.mkdir(parents=True)
    (repo / "seed.yaml").write_text(
        "repo: recursive-engine\norg: organvm-i-theoria\nconsumes:\n"
        "  - type: context\n    source: external/selected\n", encoding="utf-8",
    )
    target = repo / "AGENTS.md"
    real_fsync = sync_mod.os.fsync
    failed = False

    def fail_after_agents_install(descriptor):
        nonlocal failed
        if stat.S_ISDIR(os.fstat(descriptor).st_mode) and target.exists() and not failed:
            failed = True
            if concurrent_winner:
                replacement = repo / "winner.tmp"
                replacement.write_text("Concurrent writer without rendered links.\n")
                replacement.replace(target)
            raise OSError("post-install durability failure")
        return real_fsync(descriptor)

    monkeypatch.setattr(sync_mod.os, "fsync", fail_after_agents_install)
    result = sync_all(
        workspace=workspace, registry_path=str(FIXTURES / "registry-minimal.json"),
        additional_workspace_roots=[repo.parent], organs=["ORGAN-I"],
        receipt_path=workspace / "receipt.json",
    )
    receipt = json.loads((workspace / "receipt.json").read_text())
    assert failed and result["errors"]
    assert receipt["status"] == "failed"
    assert any(output["path"] == "flat/recursive-engine/AGENTS.md" for output in receipt["outputs"])
    expected_references = [{
        "direction": "consumes", "output_path": "flat/recursive-engine/AGENTS.md",
        "path": "CLAUDE.md", "ref": "main", "ref_source": "fallback.main",
        "repository": "external/selected",
        "url": "https://github.com/external/selected/blob/main/CLAUDE.md",
    }]
    assert receipt["resolved_remote_references"] == ([] if concurrent_winner else expected_references)


def test_unknown_requested_organ_is_rejected() -> None:
    from organvm_engine.contextmd.sync import _registry_organ_directory_map

    with pytest.raises(RuntimeError, match="unknown requested organ: ORAGN-I"):
        _registry_organ_directory_map({"organs": {"ORGAN-I": {}}}, ["ORAGN-I"])


def test_git_evidence_reference_accepts_full_sha256_only() -> None:
    from organvm_engine.documentation.record import GIT_EVIDENCE_REFERENCE

    assert GIT_EVIDENCE_REFERENCE.fullmatch(f"git:{'a' * 64}:docs/proof.md")
    assert GIT_EVIDENCE_REFERENCE.fullmatch(f"git:{'b' * 40}")
    assert not GIT_EVIDENCE_REFERENCE.fullmatch(f"git:{'c' * 63}")


def test_organ_edges_resolve_canonical_workspace_directory(monkeypatch) -> None:
    from organvm_engine.contextmd.generator import _build_organ_edges

    monkeypatch.setattr(
        "organvm_engine.organ_config.registry_key_to_dir",
        lambda: {"ORGAN-I": "organvm-i-theoria", "ORGAN-II": "organvm-ii-poiesis"},
    )
    seeds = [{
        "org": "organvm-i-theoria", "repo": "source",
        "produces": [{"target": "organvm-ii-poiesis/target", "type": "artifact"}],
    }]
    registry = {"organs": {"ORGAN-I": {"repositories": []}, "ORGAN-II": {"repositories": []}}}

    rendered = _build_organ_edges("ORGAN-I", seeds, registry)
    assert "ORGAN-I" in rendered and "ORGAN-II" in rendered
