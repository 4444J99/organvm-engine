"""End-to-end broker receipt coverage for context synchronization."""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from organvm_engine.contextmd.sync import sync_all

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
UNCOOPERATIVE_OVERSIZE_BYTES = 16_000_001


def _registry_schema_payload(*, statuses: list[str]) -> bytes:
    schema = {
        "$defs": {
            "repository": {
                "properties": {
                    "implementation_status": {"enum": statuses},
                    "promotion_status": {
                        "enum": [
                            "LOCAL",
                            "CANDIDATE",
                            "PUBLIC_PROCESS",
                            "GRADUATED",
                            "ARCHIVED",
                        ],
                    },
                    "tier": {
                        "enum": [
                            "flagship",
                            "standard",
                            "stub",
                            "archive",
                            "infrastructure",
                            "sovereign",
                        ],
                    },
                    "revenue_model": {
                        "enum": [
                            "subscription",
                            "freemium",
                            "one-time",
                            "advertising",
                            "marketplace",
                            "internal",
                            "none",
                        ],
                    },
                    "revenue_status": {
                        "enum": ["pre-launch", "beta", "live", "deprecated", "n/a"],
                    },
                },
            },
        },
    }
    return (json.dumps(schema, sort_keys=True) + "\n").encode("utf-8")


def test_sync_all_exposes_an_exact_machine_readable_receipt(tmp_path, monkeypatch) -> None:
    import organvm_engine.contextmd.receipt as receipt_mod
    import organvm_engine.contextmd.sync as sync_mod
    import organvm_engine.ledger.emit as ledger_emit
    import organvm_engine.pulse.emitter as pulse_emitter

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    receipt_path = workspace / "receipts" / "context-sync.json"
    identity = {"commit": "a" * 40, "tree": "b" * 40}

    monkeypatch.setattr(sync_mod, "precompute_ammoi", lambda: None)
    monkeypatch.setattr(
        receipt_mod,
        "generator_git_identity",
        lambda *args, **kwargs: identity,
    )
    monkeypatch.setattr(pulse_emitter, "emit_engine_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(ledger_emit, "testament_emit", lambda *args, **kwargs: None)

    result = sync_all(
        workspace=workspace,
        registry_path=str(FIXTURES / "registry-minimal.json"),
        additional_workspace_roots=[],
        receipt_path=receipt_path,
    )

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert result["receipt_path"] == str(receipt_path)
    assert result["receipt_sha256"].startswith("sha256:")
    assert receipt["status"] == "success"
    assert receipt["generator"] == identity
    assert {item["path"] for item in receipt["outputs"]} == {
        "AGENTS.md",
        "CLAUDE.md",
        "GEMINI.md",
    }
    assert all(
        item["journal_object"] == item["sha256"]
        for item in receipt["outputs"]
    )


def test_receipted_sync_binds_the_exact_external_validation_policy(
    tmp_path,
    monkeypatch,
) -> None:
    import organvm_engine.registry.validator as validator_mod

    _isolate_emitters(monkeypatch)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    schema_path = tmp_path / "registry-v2.schema.json"
    schema_payload = _registry_schema_payload(statuses=["ACTIVE", "PROTOTYPE"])
    schema_path.write_bytes(schema_payload)
    monkeypatch.setattr(validator_mod, "_schema_candidates", lambda: (schema_path,))
    monkeypatch.setattr(validator_mod, "VALID_STATUSES", frozenset({"BOGUS"}))

    sync_all(
        workspace=workspace,
        registry_path=str(FIXTURES / "registry-minimal.json"),
        additional_workspace_roots=[],
        receipt_path=workspace / "receipt.json",
    )

    receipt = json.loads((workspace / "receipt.json").read_text())
    evidence = receipt["inputs"]["registry_validation_policy"]
    assert evidence["policy_version"] == "organvm.registry-validation-policy.v1"
    assert evidence["source_kind"] == "external-schema"
    assert evidence["source_sha256"] == (
        "sha256:" + hashlib.sha256(schema_payload).hexdigest()
    )
    assert evidence["statuses"] == ["ACTIVE", "PROTOTYPE"]
    assert str(schema_path) not in json.dumps(receipt)


def test_receipted_sync_retains_captured_policy_after_external_schema_change(
    tmp_path,
    monkeypatch,
) -> None:
    import organvm_engine.registry.validator as validator_mod

    _isolate_emitters(monkeypatch)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    receipt_path = workspace / "receipt.json"
    schema_path = tmp_path / "registry-v2.schema.json"
    schema_path.write_bytes(_registry_schema_payload(statuses=["ACTIVE"]))
    monkeypatch.setattr(validator_mod, "_schema_candidates", lambda: (schema_path,))
    real_validate = validator_mod.validate_registry

    def validate_then_replace_schema(registry, *, policy=None):
        result = real_validate(registry, policy=policy)
        schema_path.write_bytes(_registry_schema_payload(statuses=["PROTOTYPE"]))
        return result

    monkeypatch.setattr(validator_mod, "validate_registry", validate_then_replace_schema)

    sync_all(
        workspace=workspace,
        registry_path=str(FIXTURES / "registry-minimal.json"),
        additional_workspace_roots=[],
        receipt_path=receipt_path,
    )

    receipt = json.loads(receipt_path.read_text())
    evidence = receipt["inputs"]["registry_validation_policy"]
    assert evidence["statuses"] == ["ACTIVE"]
    assert evidence["source_sha256"] == (
        "sha256:"
        + hashlib.sha256(_registry_schema_payload(statuses=["ACTIVE"])).hexdigest()
    )


def test_receipted_sync_does_not_bootstrap_a_phantom_corpus_between_runs(
    tmp_path,
    monkeypatch,
) -> None:
    _isolate_emitters(monkeypatch)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    first = sync_all(
        workspace=workspace,
        registry_path=str(FIXTURES / "registry-minimal.json"),
        additional_workspace_roots=[],
        receipt_path=workspace / "receipt-1.json",
    )
    second = sync_all(
        workspace=workspace,
        registry_path=str(FIXTURES / "registry-minimal.json"),
        additional_workspace_roots=[],
        receipt_path=workspace / "receipt-2.json",
    )

    first_receipt = json.loads((workspace / "receipt-1.json").read_text())
    second_receipt = json.loads((workspace / "receipt-2.json").read_text())
    assert len(first["created"]) == 3
    assert second["created"] == []
    assert len(second["skipped"]) == 3
    for key in ("registry", "seeds", "seeds_manifest_sha256", "sops"):
        assert first_receipt["inputs"][key] == second_receipt["inputs"][key]
    assert [
        {"path": binding["path"], "state": binding["state"]}
        for binding in first_receipt["inputs"]["target_preimages"]
    ] == [
        {"path": "AGENTS.md", "state": "absent"},
        {"path": "CLAUDE.md", "state": "absent"},
        {"path": "GEMINI.md", "state": "absent"},
    ]
    assert all(
        set(binding["parent_identity"]) == {"device", "inode"}
        for binding in first_receipt["inputs"]["target_preimages"]
    )
    assert all(
        binding["state"] == "present"
        for binding in second_receipt["inputs"]["target_preimages"]
    )
    assert first_receipt["outputs"] == second_receipt["outputs"]
    assert not (workspace / "meta-organvm").exists()


def test_first_receipted_run_cas_binds_preexisting_unchanged_outputs(
    tmp_path,
    monkeypatch,
) -> None:
    import organvm_engine.contextmd.sync as sync_mod

    _isolate_emitters(monkeypatch)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fixed = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)

    class Clock:
        @classmethod
        def now(cls, _zone):
            return fixed

    monkeypatch.setattr(sync_mod, "datetime", Clock)
    registry = json.loads((FIXTURES / "registry-minimal.json").read_text())
    section = sync_mod.generate_workspace_section(
        registry,
        [],
        timestamp="2026-09-01T12:00:00Z",
        include_live_context=False,
    )
    for filename in ("CLAUDE.md", "GEMINI.md", "AGENTS.md"):
        (workspace / filename).write_text(section + "\n", encoding="utf-8")
    journal = workspace / ".organvm-context-cas"
    assert not journal.exists()

    result = sync_all(
        workspace=workspace,
        registry_path=str(FIXTURES / "registry-minimal.json"),
        additional_workspace_roots=[],
        receipt_path=workspace / "receipt.json",
    )

    receipt = json.loads((workspace / "receipt.json").read_text())
    assert len(result["skipped"]) == 3
    assert result["errors"] == []
    assert receipt["status"] == "success"
    assert {item["path"] for item in receipt["outputs"]} == {
        "AGENTS.md",
        "CLAUDE.md",
        "GEMINI.md",
    }
    assert len(list(journal.glob("sha256-*.object"))) == 1
    assert not list(journal.glob("transaction-*"))


def _isolate_emitters(monkeypatch) -> None:
    import organvm_engine.contextmd.receipt as receipt_mod
    import organvm_engine.contextmd.sync as sync_mod
    import organvm_engine.ledger.emit as ledger_emit
    import organvm_engine.pulse.emitter as pulse_emitter

    identity = {"commit": "a" * 40, "tree": "b" * 40}
    monkeypatch.setattr(sync_mod, "precompute_ammoi", lambda: None)
    monkeypatch.setattr(
        receipt_mod,
        "generator_git_identity",
        lambda *args, **kwargs: identity,
    )
    monkeypatch.setattr(pulse_emitter, "emit_engine_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(ledger_emit, "testament_emit", lambda *args, **kwargs: None)


def _replace_with_uncooperative_target(target: Path, root: Path, kind: str) -> None:
    """Install a final-syscall replacement outside the cooperative lease."""
    target.unlink()
    if kind == "symlink":
        outside = root / "outside.txt"
        outside.write_text("foreign\n", encoding="utf-8")
        target.symlink_to(outside)
    elif kind == "directory":
        target.mkdir()
    elif kind == "fifo":
        os.mkfifo(target)
    else:
        assert kind == "oversize"
        target.write_bytes(b"x" * UNCOOPERATIVE_OVERSIZE_BYTES)


def test_receipt_only_lists_urls_rendered_into_selected_outputs(tmp_path, monkeypatch) -> None:
    _isolate_emitters(monkeypatch)
    workspace = tmp_path / "workspace"
    flat = workspace / "flat"
    selected = flat / "recursive-engine"
    filtered = flat / "metasystem-master"
    selected.mkdir(parents=True)
    filtered.mkdir()
    (selected / "seed.yaml").write_text(
        "repo: recursive-engine\n"
        "org: organvm-i-theoria\n"
        "consumes:\n"
        "  - type: context\n"
        "    source: external/selected\n",
        encoding="utf-8",
    )
    (filtered / "seed.yaml").write_text(
        "repo: metasystem-master\n"
        "org: organvm-ii-poiesis\n"
        "consumes:\n"
        "  - type: context\n"
        "    source: external/filtered\n",
        encoding="utf-8",
    )
    receipt_path = workspace / "receipt.json"

    sync_all(
        workspace=workspace,
        registry_path=str(FIXTURES / "registry-minimal.json"),
        additional_workspace_roots=[flat],
        organs=["ORGAN-I"],
        receipt_path=receipt_path,
    )

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["resolved_remote_references"] == [
        {
            "direction": "consumes",
            "output_path": "flat/recursive-engine/AGENTS.md",
            "path": "CLAUDE.md",
            "ref": "main",
            "ref_source": "fallback.main",
            "repository": "external/selected",
            "url": "https://github.com/external/selected/blob/main/CLAUDE.md",
        },
    ]
    assert "external/filtered" not in receipt_path.read_text(encoding="utf-8")


def test_receipted_sync_preflights_symlinked_repo_before_any_write(
    tmp_path,
    monkeypatch,
) -> None:
    _isolate_emitters(monkeypatch)
    workspace = tmp_path / "workspace"
    flat = workspace / "flat"
    outside = tmp_path / "outside"
    flat.mkdir(parents=True)
    outside.mkdir()
    (flat / "recursive-engine").symlink_to(outside, target_is_directory=True)
    receipt_path = workspace / "receipt.json"

    with pytest.raises(RuntimeError, match="real in-workspace directory"):
        sync_all(
            workspace=workspace,
            registry_path=str(FIXTURES / "registry-minimal.json"),
            additional_workspace_roots=[flat],
            organs=["ORGAN-I"],
            receipt_path=receipt_path,
        )

    assert list(outside.iterdir()) == []
    assert not receipt_path.exists()
    assert not (workspace / "AGENTS.md").exists()


def test_custody_preflight_rejects_a_fifo_without_blocking(tmp_path) -> None:
    import organvm_engine.contextmd.sync as sync_mod
    from organvm_engine.contextmd import AUTO_END, AUTO_START

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "AGENTS.md"
    os.mkfifo(target)

    with pytest.raises(RuntimeError, match="not a regular file"):
        sync_mod._inject_section_result(
            target,
            f"{AUTO_START}\nnew\n{AUTO_END}",
            custody_root=workspace,
        )

    assert target.exists()
    assert not (workspace / ".organvm-context-cas").exists()


def test_custody_read_rejects_in_place_edit_at_final_path_stat(
    tmp_path,
    monkeypatch,
) -> None:
    import organvm_engine.contextmd.sync as sync_mod

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "CLAUDE.md"
    target.write_text("ORIGINAL\n", encoding="utf-8")
    parent_fd = sync_mod.os.open(
        workspace,
        sync_mod.os.O_RDONLY | getattr(sync_mod.os, "O_DIRECTORY", 0),
    )
    real_stat = sync_mod.os.stat
    raced = False

    def edit_at_final_stat(name, *args, dir_fd=None, **kwargs):
        nonlocal raced
        if name == target.name and dir_fd == parent_fd and not raced:
            target.write_text("CONCURRENT LONGER CONTENT\n", encoding="utf-8")
            raced = True
        return real_stat(name, *args, dir_fd=dir_fd, **kwargs)

    monkeypatch.setattr(sync_mod.os, "stat", edit_at_final_stat)
    try:
        with pytest.raises(RuntimeError, match="changed while reading"):
            sync_mod._read_custody_payload(parent_fd, target.name)
    finally:
        sync_mod.os.close(parent_fd)

    assert raced is True


def test_receipt_fails_if_input_changes_after_it_was_parsed(tmp_path, monkeypatch) -> None:
    import organvm_engine.contextmd.sync as sync_mod

    _isolate_emitters(monkeypatch)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry = workspace / "registry.json"
    registry.write_bytes((FIXTURES / "registry-minimal.json").read_bytes())
    receipt_path = workspace / "receipt.json"
    original_generate = sync_mod.generate_workspace_section
    mutated = False

    def mutate_after_parse(*args, **kwargs):
        nonlocal mutated
        if not mutated:
            registry.write_text('{"version": "changed"}\n', encoding="utf-8")
            mutated = True
        return original_generate(*args, **kwargs)

    monkeypatch.setattr(sync_mod, "generate_workspace_section", mutate_after_parse)

    with pytest.raises(RuntimeError, match="context sync input evidence changed"):
        sync_all(
            workspace=workspace,
            registry_path=str(registry),
            additional_workspace_roots=[],
            receipt_path=receipt_path,
        )
    assert not receipt_path.exists()


def test_receipt_fails_if_generated_output_changes_before_binding(
    tmp_path,
    monkeypatch,
) -> None:
    import organvm_engine.contextmd.receipt as receipt_mod

    _isolate_emitters(monkeypatch)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    receipt_path = workspace / "receipt.json"
    original_build = receipt_mod.build_context_sync_receipt

    def mutate_before_binding(**kwargs):
        (workspace / "AGENTS.md").write_text("tampered\n", encoding="utf-8")
        return original_build(**kwargs)

    monkeypatch.setattr(receipt_mod, "build_context_sync_receipt", mutate_before_binding)

    with pytest.raises(RuntimeError, match="generated output changed"):
        sync_all(
            workspace=workspace,
            registry_path=str(FIXTURES / "registry-minimal.json"),
            additional_workspace_roots=[],
            receipt_path=receipt_path,
        )
    assert not receipt_path.exists()


def test_preflight_race_preserves_a_new_manual_target(tmp_path, monkeypatch) -> None:
    import organvm_engine.contextmd.sync as sync_mod

    _isolate_emitters(monkeypatch)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "AGENTS.md"
    original_generate = sync_mod.generate_workspace_section
    calls = 0

    def create_manual_target(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 3:
            target.write_text("CONCURRENT USER EDIT\n", encoding="utf-8")
        return original_generate(*args, **kwargs)

    monkeypatch.setattr(sync_mod, "generate_workspace_section", create_manual_target)
    result = sync_all(
        workspace=workspace,
        registry_path=str(FIXTURES / "registry-minimal.json"),
        additional_workspace_roots=[],
        receipt_path=workspace / "receipt.json",
    )
    receipt = json.loads((workspace / "receipt.json").read_text())

    assert target.read_text(encoding="utf-8") == "CONCURRENT USER EDIT\n"
    assert receipt["status"] == "failed"
    assert "AGENTS.md" not in {item["path"] for item in receipt["outputs"]}
    assert any("changed after receipted preflight" in error["error"] for error in result["errors"])


def test_receipt_fails_if_generator_identity_changes_during_sync(
    tmp_path,
    monkeypatch,
) -> None:
    import organvm_engine.contextmd.receipt as receipt_mod

    _isolate_emitters(monkeypatch)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    receipt_path = workspace / "receipt.json"
    identities = iter(
        [
            {"commit": "a" * 40, "tree": "b" * 40},
            {"commit": "c" * 40, "tree": "d" * 40},
        ],
    )
    monkeypatch.setattr(
        receipt_mod,
        "generator_git_identity",
        lambda *args, **kwargs: next(identities),
    )

    with pytest.raises(RuntimeError, match="generator Git identity changed"):
        sync_all(
            workspace=workspace,
            registry_path=str(FIXTURES / "registry-minimal.json"),
            additional_workspace_roots=[],
            receipt_path=receipt_path,
        )
    assert not receipt_path.exists()
    assert not (workspace / "AGENTS.md").exists()
    assert not (workspace / "CLAUDE.md").exists()
    assert not (workspace / "GEMINI.md").exists()


def test_receipt_write_failure_restores_every_generated_output(
    tmp_path,
    monkeypatch,
) -> None:
    import organvm_engine.contextmd.receipt as receipt_mod

    _isolate_emitters(monkeypatch)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    receipt_path = workspace / "receipt.json"
    agents = workspace / "AGENTS.md"
    original = b"manual context\n"
    agents.write_bytes(original)

    def fail_receipt_write(*_args, **_kwargs):
        raise OSError("simulated receipt fsync failure")

    monkeypatch.setattr(receipt_mod, "write_context_sync_receipt", fail_receipt_write)

    with pytest.raises(RuntimeError, match="context sync receipt creation failed"):
        sync_all(
            workspace=workspace,
            registry_path=str(FIXTURES / "registry-minimal.json"),
            additional_workspace_roots=[],
            receipt_path=receipt_path,
        )

    assert agents.read_bytes() == original
    assert not (workspace / "CLAUDE.md").exists()
    assert not (workspace / "GEMINI.md").exists()
    assert not receipt_path.exists()


def test_custodied_unchanged_context_binds_exact_trailing_newline(tmp_path) -> None:
    from organvm_engine.contextmd import AUTO_END, AUTO_START
    from organvm_engine.contextmd.sync import _inject_section_result

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "AGENTS.md"
    section = f"{AUTO_START}\nhello\n{AUTO_END}"
    target.write_text(section + "\n", encoding="utf-8")

    result = _inject_section_result(target, section, custody_root=workspace)

    assert result["action"] == "unchanged"
    assert target.read_text(encoding="utf-8") == section + "\n"
    assert result["output_binding"]["bytes"] == len((section + "\n").encode())


def test_custodied_update_preserves_private_file_mode(tmp_path) -> None:
    from organvm_engine.contextmd import AUTO_END, AUTO_START
    from organvm_engine.contextmd.sync import _inject_section_result

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "AGENTS.md"
    target.write_text(f"{AUTO_START}\nold\n{AUTO_END}\n", encoding="utf-8")
    target.chmod(0o600)

    _inject_section_result(
        target,
        f"{AUTO_START}\nnew\n{AUTO_END}",
        custody_root=workspace,
    )

    assert target.stat().st_mode & 0o777 == 0o600


def test_custodied_update_rejects_a_concurrent_manual_edit(
    tmp_path,
    monkeypatch,
) -> None:
    import organvm_engine.contextmd.sync as sync_mod
    from organvm_engine.contextmd import AUTO_END, AUTO_START

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "AGENTS.md"
    original = f"manual before\n{AUTO_START}\nold\n{AUTO_END}\n"
    concurrent = f"concurrent manual edit\n{AUTO_START}\nold\n{AUTO_END}\n"
    target.write_text(original, encoding="utf-8")
    original_write = sync_mod._write_custody_payload

    def raced_write(*args, **kwargs):
        target.write_text(concurrent, encoding="utf-8")
        return original_write(*args, **kwargs)

    monkeypatch.setattr(sync_mod, "_write_custody_payload", raced_write)

    with pytest.raises(RuntimeError, match="changed after rendering"):
        sync_mod._inject_section_result(
            target,
            f"{AUTO_START}\nnew\n{AUTO_END}",
            custody_root=workspace,
        )
    assert target.read_text(encoding="utf-8") == concurrent


def test_custodied_update_rejects_a_parent_moved_outside_workspace(
    tmp_path,
    monkeypatch,
) -> None:
    import organvm_engine.contextmd.sync as sync_mod
    from organvm_engine.contextmd import AUTO_END, AUTO_START

    workspace = tmp_path / "workspace"
    parent = workspace / "a"
    parent.mkdir(parents=True)
    target = parent / "AGENTS.md"
    original = f"manual\n{AUTO_START}\nold\n{AUTO_END}\n"
    target.write_text(original, encoding="utf-8")
    escaped = tmp_path / "escaped"
    original_write = sync_mod._write_custody_payload

    def raced_write(*args, **kwargs):
        parent.rename(escaped)
        parent.mkdir()
        return original_write(*args, **kwargs)

    monkeypatch.setattr(sync_mod, "_write_custody_payload", raced_write)

    with pytest.raises(RuntimeError, match="parent moved outside custody"):
        sync_mod._inject_section_result(
            target,
            f"{AUTO_START}\nnew\n{AUTO_END}",
            custody_root=workspace,
        )
    assert (escaped / "AGENTS.md").read_text(encoding="utf-8") == original
    assert not target.exists()


def test_custody_target_rejects_parent_traversal(tmp_path) -> None:
    from organvm_engine.contextmd.sync import _open_custody_parent

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / ".." / "outside" / "AGENTS.md"

    with pytest.raises(RuntimeError, match="parent traversal"):
        _open_custody_parent(target, workspace)


def test_custody_openat_rejects_intermediate_symlink_swap(tmp_path, monkeypatch) -> None:
    import organvm_engine.contextmd.sync as sync_mod

    workspace = tmp_path / "workspace"
    inside = workspace / "a" / "b"
    outside = tmp_path / "outside" / "b"
    inside.mkdir(parents=True)
    outside.mkdir(parents=True)
    target = inside / "AGENTS.md"
    original_open = sync_mod.os.open
    swapped = False

    def raced_open(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal swapped
        if path == "a" and dir_fd is not None and not swapped:
            (workspace / "a").rename(workspace / "a-original")
            (workspace / "a").symlink_to(tmp_path / "outside", target_is_directory=True)
            swapped = True
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(sync_mod.os, "open", raced_open)

    with pytest.raises(RuntimeError, match="real in-workspace directory"):
        sync_mod._open_custody_parent(target, workspace)
    assert swapped is True
    assert list(outside.iterdir()) == []


def test_receipted_sync_binds_sop_sources_and_resolved_semantics(
    tmp_path,
    monkeypatch,
) -> None:
    _isolate_emitters(monkeypatch)
    workspace = tmp_path / "workspace"
    repo = workspace / "organvm-i-theoria" / "recursive-engine"
    directive = repo / ".sops" / "SOP--directive.md"
    directive.parent.mkdir(parents=True)

    def write_directive(title: str) -> None:
        directive.write_text(
            "---\n"
            "name: directive\n"
            "scope: repo\n"
            "phase: graduation\n"
            "---\n"
            f"# {title}\n",
            encoding="utf-8",
        )

    write_directive("First")
    sync_all(
        workspace=workspace,
        registry_path=str(FIXTURES / "registry-minimal.json"),
        additional_workspace_roots=[],
        organs=["ORGAN-I"],
        receipt_path=workspace / "receipt-1.json",
    )
    first = json.loads((workspace / "receipt-1.json").read_text())

    write_directive("Second")
    sync_all(
        workspace=workspace,
        registry_path=str(FIXTURES / "registry-minimal.json"),
        additional_workspace_roots=[],
        organs=["ORGAN-I"],
        receipt_path=workspace / "receipt-2.json",
    )
    second = json.loads((workspace / "receipt-2.json").read_text())

    assert first["inputs"]["sops"]["manifest_sha256"] != (
        second["inputs"]["sops"]["manifest_sha256"]
    )
    assert first["inputs"]["sops"]["entries"][0]["title"] == "First"
    assert second["inputs"]["sops"]["entries"][0]["title"] == "Second"
    assert "| repo | graduation | directive | Second |" in (
        repo / "CLAUDE.md"
    ).read_text(encoding="utf-8")


def test_receipted_sync_never_calls_unbound_live_context_helpers(
    tmp_path,
    monkeypatch,
) -> None:
    import builtins

    import organvm_engine.contextmd.generator as generator_mod
    import organvm_engine.organ_config as organ_config_mod

    _isolate_emitters(monkeypatch)
    workspace = tmp_path / "workspace"
    (workspace / "organvm-i-theoria" / "recursive-engine").mkdir(parents=True)

    def unexpected(*_args, **_kwargs):
        raise AssertionError("unbound live helper was called")

    for name in (
        "_build_system_library_context",
        "_build_plan_context",
        "_build_atoms_context",
        "_build_prompting_hint",
        "_build_ecosystem_context",
        "_build_network_context",
        "_build_ontologia_context",
        "_build_handoff_status_context",
        "_build_variable_context",
        "_build_ammoi_context",
        "_build_trivium_context",
        "_build_logos_context",
        "_read_omega_counts",
    ):
        monkeypatch.setattr(generator_mod, name, unexpected)
    monkeypatch.setattr(generator_mod, "resolve_entity", unexpected)
    monkeypatch.setattr(organ_config_mod, "dir_to_registry_key", unexpected)
    monkeypatch.setattr(organ_config_mod, "load_organ_topology", unexpected)
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "organvm_engine.git.superproject":
            raise AssertionError("receipted sync imported unbound superproject state")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    result = sync_all(
        workspace=workspace,
        registry_path=str(FIXTURES / "registry-minimal.json"),
        additional_workspace_roots=[],
        organs=["ORGAN-I"],
        receipt_path=workspace / "receipt.json",
    )

    assert result["errors"] == []
    receipt = json.loads((workspace / "receipt.json").read_text())
    assert receipt["inputs"]["render_profile"] == "receipted-core-v1"
    assert receipt["inputs"]["invocation"]["organ_directory_map"] == {
        "ORGAN-I": "organvm-i-theoria",
    }


def test_receipted_sync_rejects_replacement_of_the_workspace_root(
    tmp_path,
    monkeypatch,
) -> None:
    import organvm_engine.contextmd.receipt as receipt_mod

    _isolate_emitters(monkeypatch)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    moved_workspace = tmp_path / "workspace-original"
    real_capture = receipt_mod.capture_context_sync_inputs
    swapped = False

    def capture_then_swap(*args, **kwargs):
        nonlocal swapped
        result = real_capture(*args, **kwargs)
        workspace.rename(moved_workspace)
        workspace.mkdir()
        swapped = True
        return result

    monkeypatch.setattr(receipt_mod, "capture_context_sync_inputs", capture_then_swap)

    with pytest.raises(RuntimeError, match="workspace root changed"):
        sync_all(
            workspace=workspace,
            registry_path=str(FIXTURES / "registry-minimal.json"),
            additional_workspace_roots=[],
            receipt_path=workspace / "receipt.json",
        )

    assert swapped is True
    assert list(workspace.iterdir()) == []
    assert not (moved_workspace / "receipt.json").exists()


@pytest.mark.parametrize("targets_present", [False, True])
def test_receipted_sync_rejects_repo_parent_replacement_after_preflight(
    tmp_path,
    monkeypatch,
    targets_present,
) -> None:
    import organvm_engine.contextmd.sync as sync_mod

    _isolate_emitters(monkeypatch)
    workspace = tmp_path / "workspace"
    repo = workspace / "organvm-i-theoria" / "recursive-engine"
    repo.mkdir(parents=True)
    replacement = tmp_path / "replacement-repo"
    replacement.mkdir()
    moved_repo = tmp_path / "original-repo"
    original_payload = "manual context\n"
    if targets_present:
        for name in ("CLAUDE.md", "GEMINI.md", "AGENTS.md"):
            (repo / name).write_text(original_payload, encoding="utf-8")
            (replacement / name).write_text(original_payload, encoding="utf-8")
    real_preflight = sync_mod._preflight_context_outputs
    swapped = False

    def preflight_then_swap(*args, **kwargs):
        nonlocal swapped
        bindings = real_preflight(*args, **kwargs)
        repo.rename(moved_repo)
        replacement.rename(repo)
        swapped = True
        return bindings

    monkeypatch.setattr(sync_mod, "_preflight_context_outputs", preflight_then_swap)

    result = sync_all(
        workspace=workspace,
        registry_path=str(FIXTURES / "registry-minimal.json"),
        additional_workspace_roots=[],
        organs=["ORGAN-I"],
        receipt_path=workspace / "receipt.json",
    )
    receipt = json.loads((workspace / "receipt.json").read_text())

    assert swapped is True
    assert receipt["status"] == "failed"
    assert sum(
        "target changed after receipted preflight" in error["error"]
        for error in result["errors"]
    ) == 3
    expected_names = {"CLAUDE.md", "GEMINI.md", "AGENTS.md"} if targets_present else set()
    assert {path.name for path in repo.iterdir()} == expected_names
    assert {path.name for path in moved_repo.iterdir()} == expected_names
    if targets_present:
        assert all(path.read_text() == original_payload for path in repo.iterdir())
        assert all(path.read_text() == original_payload for path in moved_repo.iterdir())


def test_receipted_sync_rejects_oversize_render_before_install(
    tmp_path,
    monkeypatch,
) -> None:
    _isolate_emitters(monkeypatch)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "CLAUDE.md"
    original = b"x" * 15_999_900
    target.write_bytes(original)

    result = sync_all(
        workspace=workspace,
        registry_path=str(FIXTURES / "registry-minimal.json"),
        additional_workspace_roots=[],
        receipt_path=workspace / "receipt.json",
    )
    receipt = json.loads((workspace / "receipt.json").read_text())

    assert target.read_bytes() == original
    assert receipt["status"] == "failed"
    assert "CLAUDE.md" not in {binding["path"] for binding in receipt["outputs"]}
    assert any("exceeds receipted size limit" in error["error"] for error in result["errors"])


def test_receipted_sync_preserves_outputs_across_distinct_run_times(
    tmp_path,
    monkeypatch,
) -> None:
    import organvm_engine.contextmd.sync as sync_mod

    _isolate_emitters(monkeypatch)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    moments = iter(
        [
            datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc),
            datetime(2026, 9, 1, 12, 0, 2, tzinfo=timezone.utc),
        ],
    )

    class Clock:
        @classmethod
        def now(cls, _zone):
            return next(moments)

    monkeypatch.setattr(sync_mod, "datetime", Clock)
    first = sync_all(
        workspace=workspace,
        registry_path=str(FIXTURES / "registry-minimal.json"),
        additional_workspace_roots=[],
        receipt_path=workspace / "receipt-1.json",
    )
    second = sync_all(
        workspace=workspace,
        registry_path=str(FIXTURES / "registry-minimal.json"),
        additional_workspace_roots=[],
        receipt_path=workspace / "receipt-2.json",
    )
    first_receipt = json.loads((workspace / "receipt-1.json").read_text())
    second_receipt = json.loads((workspace / "receipt-2.json").read_text())

    assert len(first["created"]) == 3
    assert second["updated"] == []
    assert len(second["skipped"]) == 3
    assert first_receipt["outputs"] == second_receipt["outputs"]
    assert first_receipt["generated_at"] == "2026-09-01T12:00:00Z"
    assert second_receipt["generated_at"] == "2026-09-01T12:00:02Z"


def test_custody_commit_boundary_does_not_clobber_a_concurrent_edit(
    tmp_path,
    monkeypatch,
) -> None:
    import organvm_engine.contextmd.sync as sync_mod
    from organvm_engine.contextmd import AUTO_END, AUTO_START

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "AGENTS.md"
    original = f"manual before\n{AUTO_START}\nold\n{AUTO_END}\n"
    concurrent = f"CONCURRENT USER EDIT\n{AUTO_START}\nold\n{AUTO_END}\n"
    target.write_text(original, encoding="utf-8")
    real_rename = sync_mod.os.rename
    raced = False

    def raced_rename(src, dst, *args, **kwargs):
        nonlocal raced
        if src == "AGENTS.md" and not raced:
            target.write_text(concurrent, encoding="utf-8")
            raced = True
        return real_rename(src, dst, *args, **kwargs)

    monkeypatch.setattr(sync_mod.os, "rename", raced_rename)
    with pytest.raises(RuntimeError, match="changed at commit boundary"):
        sync_mod._inject_section_result(
            target,
            f"{AUTO_START}\nnew\n{AUTO_END}",
            custody_root=workspace,
        )

    assert raced is True
    assert target.read_text(encoding="utf-8") == concurrent
    assert not list(workspace.glob(".AGENTS.md.*"))


@pytest.mark.parametrize(
    "replacement_kind",
    ["symlink", "directory", "fifo", "oversize"],
)
def test_custody_retains_an_uncooperative_commit_boundary_replacement_privately(
    tmp_path,
    monkeypatch,
    replacement_kind,
) -> None:
    import organvm_engine.contextmd.sync as sync_mod
    from organvm_engine.contextmd import AUTO_END, AUTO_START

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".git").mkdir()
    target = workspace / "AGENTS.md"
    target.write_text(
        f"manual before\n{AUTO_START}\nold\n{AUTO_END}\n",
        encoding="utf-8",
    )
    real_rename = sync_mod.os.rename
    raced = False

    def raced_rename(src, dst, *args, **kwargs):
        nonlocal raced
        if src == "AGENTS.md" and not raced:
            _replace_with_uncooperative_target(target, tmp_path, replacement_kind)
            raced = True
        return real_rename(src, dst, *args, **kwargs)

    monkeypatch.setattr(sync_mod.os, "rename", raced_rename)
    with pytest.raises(RuntimeError, match="retained in the private custody journal"):
        sync_mod._inject_section_result(
            target,
            f"{AUTO_START}\nnew\n{AUTO_END}",
            custody_root=workspace,
        )

    journal = workspace / ".git" / "organvm-context-cas"
    retained = list(journal.glob("transaction-*.preimage"))
    assert raced is True
    assert not target.exists()
    assert len(retained) == 1
    if replacement_kind == "symlink":
        assert retained[0].is_symlink()
    elif replacement_kind == "directory":
        assert retained[0].is_dir()
    elif replacement_kind == "fifo":
        import stat

        assert stat.S_ISFIFO(retained[0].stat().st_mode)
    else:
        assert retained[0].stat().st_size == UNCOOPERATIVE_OVERSIZE_BYTES
    assert not list(journal.glob("transaction-*.generated"))


def test_custody_leaves_a_cas_bound_output_when_post_install_fsync_fails(
    tmp_path,
    monkeypatch,
) -> None:
    import stat

    import organvm_engine.contextmd.sync as sync_mod
    from organvm_engine.contextmd import AUTO_END, AUTO_START

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "CLAUDE.md"
    original = f"manual\n{AUTO_START}\nold\n{AUTO_END}\n"
    target.write_text(original, encoding="utf-8")
    real_fsync = sync_mod.os.fsync
    failed = False

    def failing_directory_fsync(descriptor):
        nonlocal failed
        if (
            stat.S_ISDIR(sync_mod.os.fstat(descriptor).st_mode)
            and target.exists()
            and "new" in target.read_text(encoding="utf-8")
            and not failed
        ):
            failed = True
            raise OSError("simulated directory fsync failure")
        return real_fsync(descriptor)

    monkeypatch.setattr(sync_mod.os, "fsync", failing_directory_fsync)
    with pytest.raises(
        sync_mod.ContextCustodyPublicationError,
        match="CAS-bound output became public",
    ):
        sync_mod._inject_section_result(
            target,
            f"{AUTO_START}\nnew\n{AUTO_END}",
            custody_root=workspace,
    )

    assert failed is True
    assert "new" in target.read_text(encoding="utf-8")
    objects = list((workspace / ".organvm-context-cas").glob("sha256-*.object"))
    assert original.encode() in {path.read_bytes() for path in objects}
    assert target.read_bytes() in {path.read_bytes() for path in objects}
    assert not list((workspace / ".organvm-context-cas").glob("transaction-*"))
    assert not list(workspace.glob(".CLAUDE.md.*"))


@pytest.mark.parametrize(
    "replacement_kind",
    ["symlink", "directory", "fifo", "oversize"],
)
def test_custody_never_cleans_up_an_uncooperative_post_install_replacement(
    tmp_path,
    monkeypatch,
    replacement_kind,
) -> None:
    import stat

    import organvm_engine.contextmd.sync as sync_mod
    from organvm_engine.contextmd import AUTO_END, AUTO_START

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".git").mkdir()
    target = workspace / "CLAUDE.md"
    target.write_text(
        f"manual\n{AUTO_START}\nold\n{AUTO_END}\n",
        encoding="utf-8",
    )
    real_fsync = sync_mod.os.fsync
    raced = False

    def replace_then_fail(descriptor):
        nonlocal raced
        if (
            stat.S_ISDIR(sync_mod.os.fstat(descriptor).st_mode)
            and target.is_file()
            and not target.is_symlink()
            and "new" in target.read_text(encoding="utf-8")
            and not raced
        ):
            _replace_with_uncooperative_target(target, tmp_path, replacement_kind)
            raced = True
            raise OSError("simulated post-install boundary failure")
        return real_fsync(descriptor)

    monkeypatch.setattr(sync_mod.os, "fsync", replace_then_fail)
    with pytest.raises(RuntimeError, match="remains at the public path"):
        sync_mod._inject_section_result(
            target,
            f"{AUTO_START}\nnew\n{AUTO_END}",
            custody_root=workspace,
        )

    assert raced is True
    if replacement_kind == "symlink":
        assert target.is_symlink()
    elif replacement_kind == "directory":
        assert target.is_dir()
    elif replacement_kind == "fifo":
        assert stat.S_ISFIFO(target.stat().st_mode)
    else:
        assert target.stat().st_size == UNCOOPERATIVE_OVERSIZE_BYTES
    journal = workspace / ".git" / "organvm-context-cas"
    assert not list(journal.glob("transaction-*"))


def test_custody_in_place_oversize_edit_cannot_poison_generated_staging_cleanup(
    tmp_path,
    monkeypatch,
) -> None:
    import organvm_engine.contextmd.sync as sync_mod
    from organvm_engine.contextmd import AUTO_END, AUTO_START

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".git").mkdir()
    target = workspace / "CLAUDE.md"
    target.write_text(
        f"manual\n{AUTO_START}\nold\n{AUTO_END}\n",
        encoding="utf-8",
    )
    real_remove = sync_mod._remove_private_journal_alias
    raced = False

    def edit_before_private_remove(
        journal_fd,
        name,
        expected_identity,
        expected_payload,
    ):
        nonlocal raced
        if name.endswith(".generated") and not raced:
            target.write_bytes(b"x" * UNCOOPERATIVE_OVERSIZE_BYTES)
            raced = True
        return real_remove(
            journal_fd,
            name,
            expected_identity,
            expected_payload,
        )

    monkeypatch.setattr(
        sync_mod,
        "_remove_private_journal_alias",
        edit_before_private_remove,
    )
    with pytest.raises(RuntimeError, match="remains at the public path"):
        sync_mod._inject_section_result(
            target,
            f"{AUTO_START}\nnew\n{AUTO_END}",
            custody_root=workspace,
        )

    journal = workspace / ".git" / "organvm-context-cas"
    assert raced is True
    assert target.stat().st_size == UNCOOPERATIVE_OVERSIZE_BYTES
    assert not list(journal.glob("transaction-*"))
    assert len(list(journal.glob("sha256-*.object"))) == 2


def test_custody_failure_preserves_and_binds_an_in_place_concurrent_edit(
    tmp_path,
    monkeypatch,
) -> None:
    import stat

    import organvm_engine.contextmd.sync as sync_mod
    from organvm_engine.contextmd import AUTO_END, AUTO_START

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "CLAUDE.md"
    original = f"manual\n{AUTO_START}\nold\n{AUTO_END}\n"
    concurrent = "CONCURRENT IN-PLACE EDIT\n"
    target.write_text(original, encoding="utf-8")
    real_fsync = sync_mod.os.fsync
    raced = False

    def edit_then_fail(descriptor):
        nonlocal raced
        if (
            stat.S_ISDIR(sync_mod.os.fstat(descriptor).st_mode)
            and target.exists()
            and "new" in target.read_text(encoding="utf-8")
            and not raced
        ):
            target.write_text(concurrent, encoding="utf-8")
            raced = True
            raise OSError("simulated durability failure after concurrent edit")
        return real_fsync(descriptor)

    monkeypatch.setattr(sync_mod.os, "fsync", edit_then_fail)
    with pytest.raises(
        sync_mod.ContextCustodyPublicationError,
        match="CAS-bound output became public",
    ):
        sync_mod._inject_section_result(
            target,
            f"{AUTO_START}\nnew\n{AUTO_END}",
            custody_root=workspace,
        )

    assert raced is True
    assert target.read_text(encoding="utf-8") == concurrent
    objects = list((workspace / ".organvm-context-cas").glob("sha256-*.object"))
    assert original.encode() in {path.read_bytes() for path in objects}
    assert concurrent.encode() in {path.read_bytes() for path in objects}


def test_custody_only_deletes_private_journal_aliases(tmp_path, monkeypatch) -> None:
    import organvm_engine.contextmd.sync as sync_mod
    from organvm_engine.contextmd import AUTO_END, AUTO_START

    if not Path("/proc/self/fd").is_dir():
        pytest.skip("procfs file descriptors are required for this race simulation")

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "AGENTS.md"
    target.write_text(
        f"manual\n{AUTO_START}\nold\n{AUTO_END}\n",
        encoding="utf-8",
    )

    real_unlink = sync_mod.os.unlink
    deletions = []

    def recorded_unlink(path, *args, **kwargs):
        directory_fd = kwargs.get("dir_fd")
        deletions.append(
            (path, sync_mod.os.readlink(f"/proc/self/fd/{directory_fd}")),
        )
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(sync_mod.os, "unlink", recorded_unlink)
    result = sync_mod._inject_section_result(
        target,
        f"{AUTO_START}\nnew\n{AUTO_END}",
        custody_root=workspace,
    )

    assert result["action"] == "updated"
    assert "new" in target.read_text(encoding="utf-8")
    assert deletions
    assert all(str(path).startswith("transaction-") for path, _fd in deletions)
    assert all(".organvm-context-cas" in directory for _path, directory in deletions)
    assert not list(workspace.glob(".organvm-context-transaction.*"))


def test_custody_uses_linked_worktree_git_admin_for_bounded_cas(tmp_path) -> None:
    import organvm_engine.contextmd.sync as sync_mod
    from organvm_engine.contextmd import AUTO_END, AUTO_START

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    git_admin = tmp_path / "git-admin"
    git_admin.mkdir()
    (workspace / ".git").write_text(f"gitdir: {git_admin}\n", encoding="utf-8")
    target = workspace / "CLAUDE.md"
    original = f"manual\n{AUTO_START}\nold\n{AUTO_END}\n"
    target.write_text(original, encoding="utf-8")

    result = sync_mod._inject_section_result(
        target,
        f"{AUTO_START}\nnew\n{AUTO_END}",
        custody_root=workspace,
    )

    journal = git_admin / "organvm-context-cas"
    assert result["action"] == "updated"
    assert not (workspace / ".organvm-context-cas").exists()
    objects = list(journal.glob("sha256-*.object"))
    assert len(objects) == 2
    assert all(path.stat().st_mode & 0o777 == 0o400 for path in objects)
    assert all(path.stat().st_nlink == 1 for path in objects)
    assert not list(journal.glob("transaction-*"))

    target.write_text(original, encoding="utf-8")
    sync_mod._inject_section_result(
        target,
        f"{AUTO_START}\nnew\n{AUTO_END}",
        custody_root=workspace,
    )
    assert len(list(journal.glob("sha256-*.object"))) == 2
    assert not list(journal.glob("transaction-*"))


def test_custody_rejects_gitfile_edit_at_final_live_stat(
    tmp_path,
    monkeypatch,
) -> None:
    import organvm_engine.contextmd.sync as sync_mod
    from organvm_engine.contextmd import AUTO_END, AUTO_START

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    first_admin = tmp_path / "git-admin-first"
    second_admin = tmp_path / "git-admin-second-longer"
    first_admin.mkdir()
    second_admin.mkdir()
    gitfile = workspace / ".git"
    gitfile.write_text(f"gitdir: {first_admin}\n", encoding="utf-8")
    target = workspace / "CLAUDE.md"
    target.write_text(
        f"manual\n{AUTO_START}\nold\n{AUTO_END}\n",
        encoding="utf-8",
    )
    real_lstat = Path.lstat
    gitfile_stats = 0
    raced = False

    def edit_at_final_lstat(path):
        nonlocal gitfile_stats, raced
        if path == gitfile:
            gitfile_stats += 1
            if gitfile_stats == 2 and not raced:
                gitfile.write_text(f"gitdir: {second_admin}\n", encoding="utf-8")
                raced = True
        return real_lstat(path)

    monkeypatch.setattr(Path, "lstat", edit_at_final_lstat)

    with pytest.raises(RuntimeError, match="gitfile changed"):
        sync_mod._inject_section_result(
            target,
            f"{AUTO_START}\nnew\n{AUTO_END}",
            custody_root=workspace,
        )

    assert raced is True
    assert not (first_admin / "organvm-context-cas").exists()
    assert not (second_admin / "organvm-context-cas").exists()


def test_custody_rejects_a_cas_object_with_an_extra_hardlink(tmp_path) -> None:
    import organvm_engine.contextmd.sync as sync_mod
    from organvm_engine.contextmd import AUTO_END, AUTO_START

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "CLAUDE.md"
    original = f"manual\n{AUTO_START}\nold\n{AUTO_END}\n"
    target.write_text(original, encoding="utf-8")
    section = f"{AUTO_START}\nnew\n{AUTO_END}"
    sync_mod._inject_section_result(target, section, custody_root=workspace)

    journal = workspace / ".organvm-context-cas"
    objects = list(journal.glob("sha256-*.object"))
    assert len(objects) == 2
    (journal / "foreign-hardlink").hardlink_to(objects[0])
    target.write_text(original, encoding="utf-8")

    with pytest.raises(RuntimeError, match="custody object mode is not immutable"):
        sync_mod._inject_section_result(target, section, custody_root=workspace)

    assert target.read_text(encoding="utf-8") == original


def test_custody_rejects_a_nonprivate_existing_journal(tmp_path) -> None:
    import organvm_engine.contextmd.sync as sync_mod
    from organvm_engine.contextmd import AUTO_END, AUTO_START

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    journal = workspace / ".organvm-context-cas"
    journal.mkdir(mode=0o700)
    journal.chmod(0o755)
    target = workspace / "AGENTS.md"

    with pytest.raises(RuntimeError, match="journal is not private"):
        sync_mod._inject_section_result(
            target,
            f"{AUTO_START}\nnew\n{AUTO_END}",
            custody_root=workspace,
        )

    assert not target.exists()
    assert journal.stat().st_mode & 0o777 == 0o755


def test_custody_reaps_only_private_transactions_into_the_cas(tmp_path) -> None:
    import hashlib

    import organvm_engine.contextmd.sync as sync_mod
    from organvm_engine.contextmd import AUTO_END, AUTO_START

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    journal = workspace / ".organvm-context-cas"
    journal.mkdir(mode=0o700)
    interrupted_payload = b"interrupted preimage\n"
    transaction = journal / ("transaction-" + "a" * 48 + ".preimage")
    transaction.write_bytes(interrupted_payload)
    unrelated = journal / "operator-note"
    unrelated.write_text("keep", encoding="utf-8")

    target = workspace / "AGENTS.md"
    result = sync_mod._inject_section_result(
        target,
        f"{AUTO_START}\nnew\n{AUTO_END}",
        custody_root=workspace,
    )

    digest = hashlib.sha256(interrupted_payload).hexdigest()
    assert result["action"] == "created"
    assert not transaction.exists()
    assert (journal / f"sha256-{digest}.object").read_bytes() == interrupted_payload
    assert unrelated.read_text(encoding="utf-8") == "keep"
    assert not list(journal.glob("transaction-*"))


def test_custody_fails_closed_when_the_private_journal_cannot_be_locked(
    tmp_path,
    monkeypatch,
) -> None:
    import fcntl

    import organvm_engine.contextmd.sync as sync_mod
    from organvm_engine.contextmd import AUTO_END, AUTO_START

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "AGENTS.md"

    def fail_lock(*_args, **_kwargs):
        raise OSError("lock unavailable")

    monkeypatch.setattr(fcntl, "flock", fail_lock)
    with pytest.raises(RuntimeError, match="cannot lock context custody journal"):
        sync_mod._inject_section_result(
            target,
            f"{AUTO_START}\nnew\n{AUTO_END}",
            custody_root=workspace,
        )

    assert not target.exists()


def test_failed_sync_receipt_has_no_unbound_post_install_effect(
    tmp_path,
    monkeypatch,
) -> None:
    import stat

    import organvm_engine.contextmd.sync as sync_mod

    _isolate_emitters(monkeypatch)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "CLAUDE.md"
    real_fsync = sync_mod.os.fsync
    failed = False

    def fail_after_claude_install(descriptor):
        nonlocal failed
        if (
            stat.S_ISDIR(sync_mod.os.fstat(descriptor).st_mode)
            and target.exists()
            and "ORGANVM:AUTO:START" in target.read_text(encoding="utf-8")
            and not failed
        ):
            failed = True
            raise OSError("simulated post-install durability failure")
        return real_fsync(descriptor)

    monkeypatch.setattr(sync_mod.os, "fsync", fail_after_claude_install)
    result = sync_all(
        workspace=workspace,
        registry_path=str(FIXTURES / "registry-minimal.json"),
        additional_workspace_roots=[],
        receipt_path=workspace / "receipt.json",
    )
    receipt = json.loads((workspace / "receipt.json").read_text())

    assert failed is True
    assert receipt["status"] == "failed"
    assert any(error["path"] == "CLAUDE.md" for error in receipt["errors"])
    assert target.exists()
    output = next(item for item in receipt["outputs"] if item["path"] == "CLAUDE.md")
    assert output["bytes"] == len(target.read_bytes())
    assert output["sha256"] == output["journal_object"]
    assert result["errors"]
    assert not list(workspace.glob(".CLAUDE.md.*"))


def test_render_existing_context_preserves_legacy_healing_when_only_timestamp_matches() -> None:
    import re

    import organvm_engine.contextmd.sync as sync_mod
    from organvm_engine.contextmd import AUTO_END, AUTO_START

    section = (
        f"{AUTO_START}\nbody\n"
        "*Last synced: 2026-09-01T10:00:00Z*\n"
        f"{AUTO_END}"
    )
    original = (
        section
        + "\n\n<!-- ERROR: Repo 'stale' not found -->"
        + "\n\n## Active Handoff Protocol\nobsolete\n"
    )

    action, rendered, change = sync_mod._render_existing_context(
        Path("AGENTS.md"),
        original,
        section,
        re,
    )

    assert action == "updated"
    assert change is not None
    assert "<!-- ERROR:" not in rendered
    assert "obsolete" not in rendered


def test_receipted_directory_mapping_ignores_unselected_ambiguous_organs() -> None:
    import organvm_engine.contextmd.sync as sync_mod

    registry = {
        "organs": {
            "SELECTED": {
                "directory": "selected-organ",
                "repositories": [{"org": "selected-organ"}],
            },
            "UNRELATED": {
                "directory": "first-directory",
                "repositories": [{"org": "second-directory"}],
            },
        },
    }

    assert sync_mod._registry_organ_directory_map(registry, ["SELECTED"]) == {
        "SELECTED": "selected-organ",
    }


def test_receipt_destination_cannot_alias_a_generated_context_output(
    tmp_path,
    monkeypatch,
) -> None:
    _isolate_emitters(monkeypatch)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(RuntimeError, match="collides with a generated context output"):
        sync_all(
            workspace=workspace,
            registry_path=str(FIXTURES / "registry-minimal.json"),
            additional_workspace_roots=[],
            receipt_path=workspace / "CLAUDE.md",
        )

    assert not (workspace / "CLAUDE.md").exists()
    assert not (workspace / "GEMINI.md").exists()
    assert not (workspace / "AGENTS.md").exists()


def test_receipt_destination_cannot_alias_the_context_changelog(
    tmp_path,
    monkeypatch,
) -> None:
    from organvm_engine.paths import PathConfig, context_changelog_path

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _isolate_emitters(monkeypatch)
    changelog = context_changelog_path(PathConfig(workspace_dir=workspace))

    with pytest.raises(RuntimeError, match="collides with the context changelog"):
        sync_all(
            workspace=workspace,
            registry_path=str(FIXTURES / "registry-minimal.json"),
            additional_workspace_roots=[],
            receipt_path=changelog,
        )

    assert not changelog.exists()
    assert not (workspace / "CLAUDE.md").exists()
    assert not (workspace / "GEMINI.md").exists()
    assert not (workspace / "AGENTS.md").exists()


def test_receipted_sync_rejects_a_seed_path_added_before_publication(
    tmp_path,
    monkeypatch,
) -> None:
    import organvm_engine.seed.discover as seed_discover

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _isolate_emitters(monkeypatch)
    originals = {
        workspace / name: f"manual {name}\n"
        for name in ("CLAUDE.md", "GEMINI.md", "AGENTS.md")
    }
    for target, content in originals.items():
        target.write_text(content, encoding="utf-8")
    real_discover = seed_discover.discover_seeds
    calls = 0

    def discover_with_late_seed(root):
        nonlocal calls
        calls += 1
        if calls == 2:
            late_seed = (
                Path(root)
                / seed_discover.ORGAN_ORGS[0]
                / "late-repository"
                / "seed.yaml"
            )
            late_seed.parent.mkdir(parents=True)
            late_seed.write_text("repo: late-repository\n", encoding="utf-8")
        return real_discover(root)

    monkeypatch.setattr(seed_discover, "discover_seeds", discover_with_late_seed)

    with pytest.raises(RuntimeError, match="seed evidence path set changed"):
        sync_all(
            workspace=workspace,
            registry_path=str(FIXTURES / "registry-minimal.json"),
            additional_workspace_roots=[],
            receipt_path=workspace / "receipt.json",
        )

    assert calls == 2
    assert not (workspace / "receipt.json").exists()
    assert {target: target.read_text(encoding="utf-8") for target in originals} == originals


def test_receipted_sync_rebinds_sops_at_the_publication_boundary(
    tmp_path,
    monkeypatch,
) -> None:
    import organvm_engine.contextmd.receipt as receipt_mod

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _isolate_emitters(monkeypatch)
    real_bind = receipt_mod.bind_context_sync_sops
    calls = 0

    def change_on_final_binding(entries, root):
        nonlocal calls
        calls += 1
        binding = real_bind(entries, root)
        if calls == 3:
            return {**binding, "manifest_sha256": "sha256:" + "f" * 64}
        return binding

    monkeypatch.setattr(
        receipt_mod,
        "bind_context_sync_sops",
        change_on_final_binding,
    )

    with pytest.raises(RuntimeError, match="SOP evidence path set changed"):
        sync_all(
            workspace=workspace,
            registry_path=str(FIXTURES / "registry-minimal.json"),
            additional_workspace_roots=[],
            receipt_path=workspace / "receipt.json",
        )

    assert calls == 3
    assert not (workspace / "receipt.json").exists()
    assert not (workspace / "CLAUDE.md").exists()
    assert not (workspace / "GEMINI.md").exists()
    assert not (workspace / "AGENTS.md").exists()


@pytest.mark.parametrize("failure", ["seed-discovery", "sop-binding"])
def test_final_input_rebinding_exceptions_restore_context_preimages(
    tmp_path, monkeypatch, failure,
) -> None:
    import organvm_engine.contextmd.receipt as receipt_mod
    import organvm_engine.seed.discover as seed_mod

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _isolate_emitters(monkeypatch)
    originals = {workspace / name: f"manual {name}\n" for name in ("CLAUDE.md", "GEMINI.md", "AGENTS.md")}
    for target, content in originals.items():
        target.write_text(content, encoding="utf-8")
    calls = 0
    if failure == "seed-discovery":
        real = seed_mod.discover_seeds

        def fail_final(root):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise ValueError("workspace manifest cannot be safely loaded")
            return real(root)

        monkeypatch.setattr(seed_mod, "discover_seeds", fail_final)
    else:
        real = receipt_mod.bind_context_sync_sops

        def fail_final(entries, root):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise ValueError("SOP input cannot be safely bound")
            return real(entries, root)

        monkeypatch.setattr(receipt_mod, "bind_context_sync_sops", fail_final)
    with pytest.raises(RuntimeError, match="context sync receipt creation failed"):
        sync_all(
            workspace=workspace,
            registry_path=str(FIXTURES / "registry-minimal.json"),
            additional_workspace_roots=[],
            receipt_path=workspace / "receipt.json",
        )
    assert not (workspace / "receipt.json").exists()
    assert {target: target.read_text(encoding="utf-8") for target in originals} == originals


def test_rendering_exception_restores_preexisting_organ_context(tmp_path, monkeypatch):
    import organvm_engine.sop.resolver as resolver_mod

    workspace = tmp_path / "workspace"
    organ = workspace / "organvm-i-theoria"
    (organ / "recursive-engine").mkdir(parents=True)
    _isolate_emitters(monkeypatch)
    originals = {organ / name: f"manual {name}\n" for name in ("CLAUDE.md", "GEMINI.md", "AGENTS.md")}
    for target, content in originals.items():
        target.write_text(content, encoding="utf-8")

    def fail_resolution(*args, **kwargs):
        assert any(target.read_text() != content for target, content in originals.items())
        raise ValueError("synthetic late SOP resolution failure")

    monkeypatch.setattr(resolver_mod, "resolve_all", fail_resolution)
    with pytest.raises(RuntimeError, match="context sync rendering failed"):
        sync_all(
            workspace=workspace,
            registry_path=str(FIXTURES / "registry-minimal.json"),
            additional_workspace_roots=[],
            receipt_path=workspace / "receipt.json",
        )
    assert not (workspace / "receipt.json").exists()
    assert {target: target.read_text(encoding="utf-8") for target in originals} == originals


def test_malformed_sop_override_rejected_before_context_publication(tmp_path, monkeypatch):
    from organvm_engine.contextmd.receipt import ContextSyncReceiptError

    workspace = tmp_path / "workspace"
    organ = workspace / "organvm-i-theoria"
    sops = organ / "recursive-engine" / ".sops"
    sops.mkdir(parents=True)
    (sops / "bad.md").write_text("---\nname: example\nscope: repo\noverrides: [other]\n---\nDirective.\n")
    _isolate_emitters(monkeypatch)
    originals = {organ / name: f"manual {name}\n" for name in ("CLAUDE.md", "GEMINI.md", "AGENTS.md")}
    for target, content in originals.items():
        target.write_text(content, encoding="utf-8")
    with pytest.raises(ContextSyncReceiptError, match="SOP metadata overrides"):
        sync_all(
            workspace=workspace,
            registry_path=str(FIXTURES / "registry-minimal.json"),
            additional_workspace_roots=[],
            receipt_path=workspace / "receipt.json",
        )
    assert not (workspace / "receipt.json").exists()
    assert {target: target.read_text(encoding="utf-8") for target in originals} == originals
