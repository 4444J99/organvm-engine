"""Custody and fail-closed tests for context synchronization receipts."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from organvm_engine.contextmd.receipt import (
    CONTEXT_SYNC_RECEIPT_SCHEMA,
    ContextSyncReceiptError,
    build_context_sync_receipt,
    write_context_sync_receipt,
)

GENERATOR_IDENTITY = {"commit": "a" * 40, "tree": "b" * 40}


def _fixture(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    registry = workspace / "registry.json"
    registry.write_text('{"version": 1}\n', encoding="utf-8")
    seed = workspace / "repo" / "seed.yaml"
    seed.parent.mkdir()
    seed.write_text("repo: example\n", encoding="utf-8")
    output = seed.parent / "AGENTS.md"
    output.write_text("# Generated\n", encoding="utf-8")
    return workspace, registry, seed, output


def test_context_sync_receipt_binds_inputs_outputs_generator_and_urls(tmp_path) -> None:
    workspace, registry, seed, output = _fixture(tmp_path)
    reference = {
        "output_path": "repo/AGENTS.md",
        "direction": "consumes",
        "repository": "organvm/schema-definitions",
        "ref": "main",
        "ref_source": "fallback.main",
        "path": "CLAUDE.md",
        "url": "https://github.com/organvm/schema-definitions/blob/main/CLAUDE.md",
    }

    receipt = build_context_sync_receipt(
        workspace=workspace,
        registry_path=registry,
        seed_paths=[seed],
        remote_references=[reference],
        output_paths=[output],
        errors=[],
        generator_identity=GENERATOR_IDENTITY,
        generated_at=datetime(2026, 9, 1, 12, 30, tzinfo=timezone.utc),
    )

    assert receipt["schema_version"] == CONTEXT_SYNC_RECEIPT_SCHEMA
    assert receipt["status"] == "success"
    assert receipt["generated_at"] == "2026-09-01T12:30:00Z"
    assert receipt["generator"] == GENERATOR_IDENTITY
    assert receipt["inputs"]["registry"]["sha256"].startswith("sha256:")
    assert receipt["inputs"]["registry_validation_policy"]["policy_version"] == (
        "organvm.registry-validation-policy.v1"
    )
    assert receipt["inputs"]["registry_validation_policy"]["statuses"]
    assert receipt["inputs"]["seeds"][0]["path"] == "repo/seed.yaml"
    assert receipt["outputs"] == [
        {
            "path": "repo/AGENTS.md",
            "bytes": output.stat().st_size,
            "sha256": "sha256:" + hashlib.sha256(output.read_bytes()).hexdigest(),
        },
    ]
    assert receipt["resolved_remote_references"] == [reference]
    assert "does not attest remote availability" in receipt["claim_boundary"]


def test_validation_policy_explicit_empty_candidates_do_not_read_live_defaults(
    monkeypatch,
) -> None:
    import organvm_engine.registry.validator as validator_mod

    def unexpected():
        raise AssertionError("live schema candidates were consulted")

    monkeypatch.setattr(validator_mod, "_schema_candidates", unexpected)

    policy = validator_mod.capture_registry_validation_policy(())

    assert policy.source_kind == "embedded-fallback"
    assert policy.evidence()["policy_version"] == (
        "organvm.registry-validation-policy.v1"
    )


@pytest.mark.parametrize(
    "schema",
    [
        [],
        {"$defs": []},
        {"$defs": {"repository": {"properties": []}}},
        {
            "$defs": {
                "repository": {
                    "properties": {
                        "implementation_status": {"enum": ["ACTIVE", 7]},
                    },
                },
            },
        },
    ],
)
def test_malformed_external_validation_schema_falls_back_cleanly(
    tmp_path,
    schema,
) -> None:
    from organvm_engine.registry.validator import (
        capture_registry_validation_policy,
    )

    schema_path = tmp_path / "registry-v2.schema.json"
    schema_path.write_text(json.dumps(schema), encoding="utf-8")

    with pytest.warns(UserWarning, match="Failed to parse"):
        policy = capture_registry_validation_policy((schema_path,))

    assert policy.source_kind == "embedded-fallback"
    assert "ACTIVE" in policy.statuses


def test_sop_receipt_binding_couples_semantics_to_the_discovered_source_bytes(
    tmp_path,
) -> None:
    from organvm_engine.contextmd.receipt import bind_context_sync_sops
    from organvm_engine.sop.discover import discover_sops

    workspace = tmp_path / "workspace"
    directive = (
        workspace
        / "organvm-i-theoria"
        / "recursive-engine"
        / ".sops"
        / "SOP--directive.md"
    )
    directive.parent.mkdir(parents=True)
    directive.write_text(
        "---\nname: directive\nscope: repo\nphase: foundation\n---\n# First\n",
        encoding="utf-8",
    )
    entries = discover_sops(workspace)
    assert entries[0].title == "First"
    directive.write_text(
        "---\nname: directive\nscope: repo\nphase: graduation\n---\n# Second\n",
        encoding="utf-8",
    )

    with pytest.raises(ContextSyncReceiptError, match="changed after semantic discovery"):
        bind_context_sync_sops(entries, workspace)


def test_failed_sync_is_explicit_in_receipt_without_claiming_success(tmp_path) -> None:
    workspace, registry, seed, output = _fixture(tmp_path)

    receipt = build_context_sync_receipt(
        workspace=workspace,
        registry_path=registry,
        seed_paths=[seed],
        remote_references=[],
        output_paths=[output],
        errors=[{"path": "repo/CLAUDE.md", "error": "generation failed"}],
        generator_identity=GENERATOR_IDENTITY,
    )

    assert receipt["status"] == "failed"
    assert receipt["errors"] == [
        {"path": "repo/CLAUDE.md", "error": "generation failed"},
    ]


def test_receipt_is_atomically_created_and_never_overwritten(tmp_path) -> None:
    target = tmp_path / "receipts" / "context-sync.json"
    receipt = {"schema_version": CONTEXT_SYNC_RECEIPT_SCHEMA, "status": "success"}

    digest = write_context_sync_receipt(target, receipt)

    assert digest == "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()
    assert json.loads(target.read_text(encoding="utf-8")) == receipt
    assert not list(target.parent.glob(f".{target.name}.*.tmp"))
    with pytest.raises(ContextSyncReceiptError, match="already exists"):
        write_context_sync_receipt(target, receipt)


def test_receipt_publication_only_unlinks_private_transaction_aliases(
    tmp_path,
    monkeypatch,
) -> None:
    import organvm_engine.contextmd.receipt as receipt_mod

    target = tmp_path / "context-sync.json"
    real_unlink = receipt_mod.os.unlink
    unlinks: list[tuple[str, int, int]] = []

    def guarded_unlink(name, *args, dir_fd=None, **kwargs):
        assert dir_fd is not None
        assert name != target.name
        assert receipt_mod.RECEIPT_TRANSACTION_ALIAS.fullmatch(name)
        status = receipt_mod.os.fstat(dir_fd)
        unlinks.append((name, status.st_dev, status.st_ino))
        return real_unlink(name, *args, dir_fd=dir_fd, **kwargs)

    monkeypatch.setattr(receipt_mod.os, "unlink", guarded_unlink)
    receipt = {"status": "success"}
    digest = write_context_sync_receipt(target, receipt)

    assert target.exists()
    object_id = digest.removeprefix("sha256:")
    custody_object = (
        tmp_path / ".organvm-receipt-cas" / "sha256" / object_id
    )
    assert custody_object.read_bytes() == target.read_bytes()
    assert custody_object.stat().st_ino != target.stat().st_ino
    custody = custody_object.parent.stat()
    assert len(unlinks) == 1
    assert unlinks[0][0].endswith(".generated")
    assert unlinks[0][1:] == (custody.st_dev, custody.st_ino)
    assert not list(custody_object.parent.glob("transaction-*"))
    assert not list(tmp_path.glob(".organvm-receipt-transaction.*"))


def test_receipt_cas_reuses_one_object_per_unique_payload(tmp_path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    receipt = {"status": "success"}

    first_digest = write_context_sync_receipt(first, receipt)
    second_digest = write_context_sync_receipt(second, receipt)

    assert first_digest == second_digest
    objects = list((tmp_path / ".organvm-receipt-cas" / "sha256").iterdir())
    assert [item.name for item in objects] == [first_digest.removeprefix("sha256:")]
    assert objects[0].read_bytes() == first.read_bytes() == second.read_bytes()
    assert len({first.stat().st_ino, second.stat().st_ino, objects[0].stat().st_ino}) == 3


def test_receipt_cas_uses_real_git_admin_dir_without_dirty_aliases(tmp_path) -> None:
    import subprocess

    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    target = repository / "context-sync.json"

    digest = write_context_sync_receipt(target, {"status": "success"})

    object_id = digest.removeprefix("sha256:")
    custody_object = (
        repository
        / ".git"
        / "organvm-receipt-cas"
        / "sha256"
        / object_id
    )
    assert custody_object.read_bytes() == target.read_bytes()
    assert not (repository / ".organvm-receipt-cas").exists()
    status = subprocess.run(
        ["git", "-C", str(repository), "status", "--short"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert status == ["?? context-sync.json"]


def test_receipt_cas_fails_closed_for_unsafe_git_marker(tmp_path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    outside = tmp_path / "outside-git"
    outside.mkdir()
    (repository / ".git").symlink_to(outside, target_is_directory=True)
    target = repository / "context-sync.json"

    with pytest.raises(ContextSyncReceiptError, match="not safely discoverable"):
        write_context_sync_receipt(target, {"status": "success"})

    assert not target.exists()
    assert not (repository / ".organvm-receipt-cas").exists()


def test_receipt_cas_rejects_cross_device_git_admin(tmp_path, monkeypatch) -> None:
    import organvm_engine.contextmd.receipt as receipt_mod

    if not Path("/proc").is_dir():
        pytest.skip("procfs is required for descriptor replacement simulation")

    target = tmp_path / "context-sync.json"
    proc_fd = receipt_mod.os.open(
        "/proc",
        receipt_mod.os.O_RDONLY | getattr(receipt_mod.os, "O_DIRECTORY", 0),
    )

    def cross_device_git_admin(_start):
        return receipt_mod.os.dup(proc_fd)

    monkeypatch.setattr(
        receipt_mod,
        "_discover_git_admin_fd",
        cross_device_git_admin,
    )
    try:
        with pytest.raises(ContextSyncReceiptError, match="filesystem boundary"):
            write_context_sync_receipt(target, {"status": "success"})
    finally:
        receipt_mod.os.close(proc_fd)

    assert not target.exists()
    assert not (tmp_path / ".organvm-receipt-cas").exists()


def test_receipt_cas_rejects_mutable_object_mode(tmp_path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    receipt = {"status": "success"}
    digest = write_context_sync_receipt(first, receipt)
    custody_object = (
        tmp_path
        / ".organvm-receipt-cas"
        / "sha256"
        / digest.removeprefix("sha256:")
    )
    custody_object.chmod(0o600)

    with pytest.raises(ContextSyncReceiptError, match="CAS object is corrupt"):
        write_context_sync_receipt(second, receipt)

    assert not second.exists()


def test_receipt_cas_rejects_permissive_fallback_directory(tmp_path) -> None:
    cas = tmp_path / ".organvm-receipt-cas"
    cas.mkdir(mode=0o755)
    target = tmp_path / "context-sync.json"

    with pytest.raises(ContextSyncReceiptError, match="owner-private"):
        write_context_sync_receipt(target, {"status": "success"})

    assert not target.exists()


def test_receipt_parent_creation_never_traverses_an_existing_symlink(tmp_path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(outside, target_is_directory=True)
    target = linked / "new-directory" / "context-sync.json"

    with pytest.raises(ContextSyncReceiptError, match="without following links"):
        write_context_sync_receipt(target, {"status": "success"})

    assert not (outside / "new-directory").exists()


def test_receipt_does_not_clobber_a_destination_created_during_write(
    tmp_path,
    monkeypatch,
) -> None:
    import organvm_engine.contextmd.receipt as receipt_mod

    target = tmp_path / "context-sync.json"
    original_link = receipt_mod.os.link

    def raced_link(src, dst, *args, **kwargs):
        if dst == target.name:
            target.write_text("concurrent writer\n", encoding="utf-8")
        return original_link(src, dst, *args, **kwargs)

    monkeypatch.setattr(receipt_mod.os, "link", raced_link)

    with pytest.raises(FileExistsError):
        write_context_sync_receipt(target, {"status": "success"})
    assert target.read_text(encoding="utf-8") == "concurrent writer\n"
    assert not list(tmp_path.glob(f".{target.name}.*.tmp"))


def test_receipt_does_not_clobber_a_fifo_created_before_publication(
    tmp_path,
    monkeypatch,
) -> None:
    import stat

    import organvm_engine.contextmd.receipt as receipt_mod

    if not hasattr(receipt_mod.os, "mkfifo"):
        pytest.skip("FIFO creation is unavailable")
    target = tmp_path / "context-sync.json"
    original_link = receipt_mod.os.link
    raced = False

    def raced_link(src, dst, *args, **kwargs):
        nonlocal raced
        if dst == target.name and not raced:
            receipt_mod.os.mkfifo(dst, mode=0o600, dir_fd=kwargs["dst_dir_fd"])
            raced = True
        return original_link(src, dst, *args, **kwargs)

    monkeypatch.setattr(receipt_mod.os, "link", raced_link)

    with pytest.raises(FileExistsError):
        write_context_sync_receipt(target, {"status": "success"})

    assert raced is True
    assert stat.S_ISFIFO(target.lstat().st_mode)
    cas = tmp_path / ".organvm-receipt-cas" / "sha256"
    assert len(list(cas.iterdir())) == 1
    assert not list(cas.glob("transaction-*"))


def test_receipt_publication_failure_retains_cas_bound_public_bytes(
    tmp_path,
    monkeypatch,
) -> None:
    import organvm_engine.contextmd.receipt as receipt_mod

    target = tmp_path / "context-sync.json"
    real_fsync = receipt_mod.os.fsync
    failed = False

    def failing_parent_fsync(descriptor):
        nonlocal failed
        if (
            (receipt_mod.os.fstat(descriptor).st_dev, receipt_mod.os.fstat(descriptor).st_ino)
            == (target.parent.stat().st_dev, target.parent.stat().st_ino)
            and target.exists()
            and not failed
        ):
            failed = True
            raise OSError("simulated receipt directory fsync failure")
        return real_fsync(descriptor)

    monkeypatch.setattr(receipt_mod.os, "fsync", failing_parent_fsync)
    with pytest.raises(OSError, match="simulated receipt directory fsync failure"):
        write_context_sync_receipt(target, {"status": "success"})

    assert failed is True
    assert json.loads(target.read_text(encoding="utf-8")) == {"status": "success"}
    assert not list(tmp_path.glob(f".{target.name}.*.tmp"))
    objects = list((tmp_path / ".organvm-receipt-cas" / "sha256").iterdir())
    assert len(objects) == 1
    assert objects[0].read_bytes() == (
        json.dumps({"status": "success"}, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    assert not list(objects[0].parent.glob("transaction-*"))


def test_receipt_failure_only_unlinks_private_cas_transactions(
    tmp_path,
    monkeypatch,
) -> None:
    import organvm_engine.contextmd.receipt as receipt_mod

    target = tmp_path / "context-sync.json"
    real_fsync = receipt_mod.os.fsync
    real_unlink = receipt_mod.os.unlink
    unlinks: list[tuple[str, int, int]] = []
    failed = False

    def failing_parent_fsync(descriptor):
        nonlocal failed
        if (
            (receipt_mod.os.fstat(descriptor).st_dev, receipt_mod.os.fstat(descriptor).st_ino)
            == (target.parent.stat().st_dev, target.parent.stat().st_ino)
            and target.exists()
            and not failed
        ):
            failed = True
            raise OSError("simulated receipt directory fsync failure")
        return real_fsync(descriptor)

    def guarded_unlink(name, *args, dir_fd=None, **kwargs):
        assert dir_fd is not None
        assert name != target.name
        assert receipt_mod.RECEIPT_TRANSACTION_ALIAS.fullmatch(name)
        status = receipt_mod.os.fstat(dir_fd)
        unlinks.append((name, status.st_dev, status.st_ino))
        return real_unlink(name, *args, dir_fd=dir_fd, **kwargs)

    monkeypatch.setattr(receipt_mod.os, "fsync", failing_parent_fsync)
    monkeypatch.setattr(receipt_mod.os, "unlink", guarded_unlink)
    with pytest.raises(OSError, match="simulated receipt directory fsync failure"):
        write_context_sync_receipt(target, {"status": "success"})

    cas = tmp_path / ".organvm-receipt-cas" / "sha256"
    custody = cas.stat()
    assert failed is True
    assert target.exists()
    assert len(unlinks) == 1
    assert {name.rsplit(".", 1)[-1] for name, _device, _inode in unlinks} == {
        "generated",
    }
    assert all(
        (device, inode) == (custody.st_dev, custody.st_ino)
        for _name, device, inode in unlinks
    )
    assert not list(cas.glob("transaction-*"))


def test_receipt_failure_never_moves_a_concurrent_symlink(
    tmp_path,
    monkeypatch,
) -> None:
    import organvm_engine.contextmd.receipt as receipt_mod

    target = tmp_path / "context-sync.json"
    generated = {"status": "success"}
    generated_bytes = (
        json.dumps(generated, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    generated_digest = hashlib.sha256(generated_bytes).hexdigest()
    real_fsync = receipt_mod.os.fsync
    outside = tmp_path / "outside-receipt"
    outside.write_text("FOREIGN\n", encoding="utf-8")
    failed = False

    def fail_parent_fsync(descriptor):
        nonlocal failed
        if (
            (receipt_mod.os.fstat(descriptor).st_dev, receipt_mod.os.fstat(descriptor).st_ino)
            == (target.parent.stat().st_dev, target.parent.stat().st_ino)
            and target.exists()
            and not failed
        ):
            failed = True
            target.unlink()
            target.symlink_to(outside)
            raise OSError("simulated receipt directory fsync failure")
        return real_fsync(descriptor)

    def forbid_public_rename(*_args, **_kwargs):
        raise AssertionError("receipt cleanup must never rename a public path")

    monkeypatch.setattr(receipt_mod.os, "fsync", fail_parent_fsync)
    monkeypatch.setattr(receipt_mod.os, "rename", forbid_public_rename)
    with pytest.raises(OSError, match="simulated receipt directory fsync failure"):
        write_context_sync_receipt(target, generated)

    cas = tmp_path / ".organvm-receipt-cas" / "sha256"
    assert failed is True
    assert target.is_symlink()
    assert target.readlink() == outside
    assert (cas / generated_digest).read_bytes() == generated_bytes
    assert not list(cas.glob("transaction-*"))


def test_receipt_failure_never_moves_an_oversized_concurrent_file(
    tmp_path,
    monkeypatch,
) -> None:
    import organvm_engine.contextmd.receipt as receipt_mod

    target = tmp_path / "context-sync.json"
    oversized = tmp_path / "oversized.tmp"
    oversized.write_bytes(b"X" * (receipt_mod.MAX_RECEIPT_INPUT_BYTES + 1))
    real_fsync = receipt_mod.os.fsync
    generated = {"status": "success"}
    generated_bytes = (
        json.dumps(generated, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    generated_digest = hashlib.sha256(generated_bytes).hexdigest()
    failed = False

    def replace_at_parent_fsync(descriptor):
        nonlocal failed
        opened = receipt_mod.os.fstat(descriptor)
        parent = target.parent.stat()
        if (
            (opened.st_dev, opened.st_ino) == (parent.st_dev, parent.st_ino)
            and target.exists()
            and not failed
        ):
            failed = True
            receipt_mod.os.replace(oversized, target)
            raise OSError("simulated receipt directory fsync failure")
        return real_fsync(descriptor)

    monkeypatch.setattr(receipt_mod.os, "fsync", replace_at_parent_fsync)
    with pytest.raises(OSError, match="simulated receipt directory fsync failure"):
        write_context_sync_receipt(target, generated)

    cas = tmp_path / ".organvm-receipt-cas" / "sha256"
    assert failed is True
    assert target.stat().st_size == receipt_mod.MAX_RECEIPT_INPUT_BYTES + 1
    assert target.read_bytes() == b"X" * (receipt_mod.MAX_RECEIPT_INPUT_BYTES + 1)
    assert (cas / generated_digest).read_bytes() == generated_bytes
    assert not list(cas.glob("transaction-*"))


def test_receipt_private_cleanup_does_not_capture_an_oversized_public_edit(
    tmp_path,
    monkeypatch,
) -> None:
    import organvm_engine.contextmd.receipt as receipt_mod

    target = tmp_path / "context-sync.json"
    generated = {"status": "success"}
    generated_bytes = (
        json.dumps(generated, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    generated_digest = hashlib.sha256(generated_bytes).hexdigest()
    oversized = b"Y" * (receipt_mod.MAX_RECEIPT_INPUT_BYTES + 1)
    real_unlink = receipt_mod.os.unlink
    edited = False

    def edit_at_private_unlink(name, *args, dir_fd=None, **kwargs):
        nonlocal edited
        if name.endswith(".generated") and not edited:
            target.write_bytes(oversized)
            edited = True
        return real_unlink(name, *args, dir_fd=dir_fd, **kwargs)

    monkeypatch.setattr(receipt_mod.os, "unlink", edit_at_private_unlink)
    with pytest.raises(ContextSyncReceiptError, match="changed during publication"):
        write_context_sync_receipt(target, generated)

    cas = tmp_path / ".organvm-receipt-cas" / "sha256"
    assert edited is True
    assert target.stat().st_size == len(oversized)
    assert target.read_bytes() == oversized
    assert (cas / generated_digest).read_bytes() == generated_bytes
    assert not list(cas.glob("transaction-*"))


def test_receipt_final_check_fifo_swap_is_nonblocking(
    tmp_path,
    monkeypatch,
) -> None:
    import stat

    import organvm_engine.contextmd.receipt as receipt_mod

    if not hasattr(receipt_mod.os, "mkfifo") or not hasattr(
        receipt_mod.os,
        "O_NONBLOCK",
    ):
        pytest.skip("nonblocking FIFO reads are unavailable")
    target = tmp_path / "context-sync.json"
    generated = {"status": "success"}
    generated_bytes = (
        json.dumps(generated, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    generated_digest = hashlib.sha256(generated_bytes).hexdigest()
    original_open = receipt_mod.os.open
    swapped = False

    def swap_at_public_open(name, flags, *args, dir_fd=None, **kwargs):
        nonlocal swapped
        is_public_read = (
            name == target.name
            and dir_fd is not None
            and flags & receipt_mod.os.O_RDONLY == receipt_mod.os.O_RDONLY
            and not flags & getattr(receipt_mod.os, "O_DIRECTORY", 0)
        )
        if is_public_read and not swapped:
            receipt_mod.os.unlink(name, dir_fd=dir_fd)
            receipt_mod.os.mkfifo(name, mode=0o600, dir_fd=dir_fd)
            swapped = True
            assert flags & receipt_mod.os.O_NONBLOCK
        return original_open(name, flags, *args, dir_fd=dir_fd, **kwargs)

    monkeypatch.setattr(receipt_mod.os, "open", swap_at_public_open)

    with pytest.raises(ContextSyncReceiptError, match="changed during publication"):
        write_context_sync_receipt(target, generated)

    cas = tmp_path / ".organvm-receipt-cas" / "sha256"
    assert swapped is True
    assert stat.S_ISFIFO(target.lstat().st_mode)
    assert (cas / generated_digest).read_bytes() == generated_bytes
    assert not list(cas.glob("transaction-*"))


def test_public_receipt_edit_does_not_mutate_immutable_cas_object(tmp_path) -> None:
    target = tmp_path / "context-sync.json"
    receipt = {"status": "success"}
    digest = write_context_sync_receipt(target, receipt)
    generated = target.read_bytes()
    custody_object = (
        tmp_path
        / ".organvm-receipt-cas"
        / "sha256"
        / digest.removeprefix("sha256:")
    )

    target.write_bytes(b"CONCURRENT IN-PLACE EDIT\n")

    assert target.read_bytes() != generated
    assert custody_object.read_bytes() == generated
    assert custody_object.stat().st_ino != target.stat().st_ino


def test_output_receipt_rejects_mutable_sync_custody_object(tmp_path) -> None:
    import organvm_engine.contextmd.receipt as receipt_mod

    workspace = tmp_path / "workspace"
    output = workspace / "repo" / "AGENTS.md"
    output.parent.mkdir(parents=True)
    output.write_text("# Generated\n", encoding="utf-8")
    payload = output.read_bytes()
    journal = workspace / ".organvm-context-cas"
    journal.mkdir(mode=0o700)
    object_name = f"sha256-{hashlib.sha256(payload).hexdigest()}.object"
    custody_object = journal / object_name
    custody_object.write_bytes(payload)
    custody_object.chmod(0o600)
    workspace_status = workspace.stat()
    parent_status = output.parent.stat()

    with pytest.raises(ContextSyncReceiptError, match="not private and immutable"):
        receipt_mod._output_binding(
            output,
            workspace,
            {
                "device": workspace_status.st_dev,
                "inode": workspace_status.st_ino,
            },
            expected_parent_identity={
                "device": parent_status.st_dev,
                "inode": parent_status.st_ino,
            },
        )


def test_receipt_publication_rejects_parent_swap(tmp_path, monkeypatch) -> None:
    import organvm_engine.contextmd.receipt as receipt_mod

    parent = tmp_path / "receipts"
    parent.mkdir()
    moved_parent = tmp_path / "receipts-original"
    outside = tmp_path / "outside"
    outside.mkdir()
    target = parent / "context-sync.json"
    original_link = receipt_mod.os.link
    swapped = False

    def raced_link(src, dst, *args, **kwargs):
        nonlocal swapped
        if dst == target.name and not swapped:
            parent.rename(moved_parent)
            parent.symlink_to(outside, target_is_directory=True)
            swapped = True
        return original_link(src, dst, *args, **kwargs)

    monkeypatch.setattr(receipt_mod.os, "link", raced_link)
    with pytest.raises(ContextSyncReceiptError, match="parent changed"):
        write_context_sync_receipt(target, {"status": "success"})

    assert swapped is True
    assert json.loads(
        (moved_parent / target.name).read_text(encoding="utf-8"),
    ) == {"status": "success"}
    assert not (outside / target.name).exists()


def test_receipt_publication_preserves_replacement_before_parent_fsync(
    tmp_path,
    monkeypatch,
) -> None:
    import stat

    import organvm_engine.contextmd.receipt as receipt_mod

    target = tmp_path / "context-sync.json"
    real_fsync = receipt_mod.os.fsync
    replaced = False

    def replace_before_parent_fsync(descriptor):
        nonlocal replaced
        if (
            stat.S_ISDIR(receipt_mod.os.fstat(descriptor).st_mode)
            and target.exists()
            and not replaced
        ):
            target.unlink()
            target.write_text("CONCURRENT\n", encoding="utf-8")
            replaced = True
        return real_fsync(descriptor)

    monkeypatch.setattr(receipt_mod.os, "fsync", replace_before_parent_fsync)
    with pytest.raises(ContextSyncReceiptError, match="changed during publication"):
        write_context_sync_receipt(target, {"status": "success"})

    assert replaced is True
    assert target.read_text(encoding="utf-8") == "CONCURRENT\n"
    assert not list(tmp_path.glob(f".{target.name}.*.tmp"))


def test_receipt_fsync_failure_never_unlinks_a_concurrent_replacement(
    tmp_path,
    monkeypatch,
) -> None:
    import stat

    import organvm_engine.contextmd.receipt as receipt_mod

    target = tmp_path / "context-sync.json"
    real_fsync = receipt_mod.os.fsync
    real_rename = receipt_mod.os.rename
    replaced = False
    moved_public_names: list[str] = []

    def replace_then_fail(descriptor):
        nonlocal replaced
        if (
            stat.S_ISDIR(receipt_mod.os.fstat(descriptor).st_mode)
            and target.exists()
            and not replaced
        ):
            target.unlink()
            target.write_text("CONCURRENT\n", encoding="utf-8")
            replaced = True
            raise OSError("simulated parent fsync failure")
        return real_fsync(descriptor)

    def track_public_rename(src, dst, *args, **kwargs):
        if src == target.name:
            moved_public_names.append(dst)
        return real_rename(src, dst, *args, **kwargs)

    monkeypatch.setattr(receipt_mod.os, "fsync", replace_then_fail)
    monkeypatch.setattr(receipt_mod.os, "rename", track_public_rename)
    with pytest.raises(OSError, match="simulated parent fsync failure"):
        write_context_sync_receipt(target, {"status": "success"})

    assert replaced is True
    assert moved_public_names == []
    assert target.read_text(encoding="utf-8") == "CONCURRENT\n"
    assert not list(tmp_path.glob(f".{target.name}.*.tmp"))


def test_receipt_rejects_output_outside_bound_workspace(tmp_path) -> None:
    workspace, registry, seed, _output = _fixture(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text("outside\n", encoding="utf-8")

    with pytest.raises(ContextSyncReceiptError, match="outside the receipted workspace"):
        build_context_sync_receipt(
            workspace=workspace,
            registry_path=registry,
            seed_paths=[seed],
            remote_references=[],
            output_paths=[outside],
            errors=[],
            generator_identity=GENERATOR_IDENTITY,
        )


def test_receipt_rejects_symlinked_input_evidence(tmp_path) -> None:
    workspace, registry, seed, output = _fixture(tmp_path)
    linked_seed = workspace / "linked-seed.yaml"
    linked_seed.symlink_to(seed)

    with pytest.raises(ContextSyncReceiptError, match="not a regular file"):
        build_context_sync_receipt(
            workspace=workspace,
            registry_path=registry,
            seed_paths=[linked_seed],
            remote_references=[],
            output_paths=[output],
            errors=[],
            generator_identity=GENERATOR_IDENTITY,
        )


def test_receipt_input_stat_to_open_fifo_swap_is_nonblocking(
    tmp_path,
    monkeypatch,
) -> None:
    import stat

    import organvm_engine.contextmd.receipt as receipt_mod

    if not hasattr(receipt_mod.os, "mkfifo") or not hasattr(
        receipt_mod.os,
        "O_NONBLOCK",
    ):
        pytest.skip("nonblocking FIFO reads are unavailable")
    evidence = tmp_path / "registry.json"
    evidence.write_text('{"version": 1}\n', encoding="utf-8")
    original_open = receipt_mod.os.open
    swapped = False

    def swap_at_evidence_open(name, flags, *args, dir_fd=None, **kwargs):
        nonlocal swapped
        if (
            name == evidence.name
            and dir_fd is not None
            and not flags & getattr(receipt_mod.os, "O_DIRECTORY", 0)
            and not swapped
        ):
            receipt_mod.os.unlink(name, dir_fd=dir_fd)
            receipt_mod.os.mkfifo(name, mode=0o600, dir_fd=dir_fd)
            swapped = True
            assert flags & receipt_mod.os.O_NONBLOCK
        return original_open(name, flags, *args, dir_fd=dir_fd, **kwargs)

    monkeypatch.setattr(receipt_mod.os, "open", swap_at_evidence_open)

    with pytest.raises(ContextSyncReceiptError, match="not a regular file"):
        receipt_mod._file_binding(evidence, label="registry.json")

    assert swapped is True
    assert stat.S_ISFIFO(evidence.lstat().st_mode)


def test_receipt_input_rejects_in_place_edit_at_final_path_stat(
    tmp_path,
    monkeypatch,
) -> None:
    import organvm_engine.contextmd.receipt as receipt_mod

    evidence = tmp_path / "registry.json"
    evidence.write_text('{"version": 1}\n', encoding="utf-8")
    real_stat = receipt_mod.os.stat
    target_stats = 0
    raced = False

    def edit_at_final_stat(name, *args, dir_fd=None, **kwargs):
        nonlocal raced, target_stats
        if name == evidence.name and dir_fd is not None:
            target_stats += 1
            if target_stats == 2 and not raced:
                evidence.write_text('{"version": 200}\n', encoding="utf-8")
                raced = True
        return real_stat(name, *args, dir_fd=dir_fd, **kwargs)

    monkeypatch.setattr(receipt_mod.os, "stat", edit_at_final_stat)

    with pytest.raises(ContextSyncReceiptError, match="changed while it was being bound"):
        receipt_mod._file_binding(evidence, label="registry.json")

    assert raced is True


def test_receipt_public_match_rejects_in_place_edit_at_final_path_stat(
    tmp_path,
    monkeypatch,
) -> None:
    import organvm_engine.contextmd.receipt as receipt_mod

    target = tmp_path / "receipt.json"
    expected_payload = b'{"status":"success"}\n'
    target.write_bytes(expected_payload)
    expected_status = target.stat()
    parent_fd = receipt_mod.os.open(
        tmp_path,
        receipt_mod.os.O_RDONLY | getattr(receipt_mod.os, "O_DIRECTORY", 0),
    )
    real_stat = receipt_mod.os.stat
    target_stats = 0
    raced = False

    def edit_at_final_stat(name, *args, dir_fd=None, **kwargs):
        nonlocal raced, target_stats
        if name == target.name and dir_fd == parent_fd:
            target_stats += 1
            if target_stats == 2 and not raced:
                target.write_bytes(b"CONCURRENT LONGER RECEIPT\n")
                raced = True
        return real_stat(name, *args, dir_fd=dir_fd, **kwargs)

    monkeypatch.setattr(receipt_mod.os, "stat", edit_at_final_stat)
    try:
        assert not receipt_mod._installed_receipt_matches(
            parent_fd,
            target.name,
            expected_status,
            expected_payload,
        )
    finally:
        receipt_mod.os.close(parent_fd)

    assert raced is True


def test_receipt_rejects_intermediate_symlinked_input_parent(tmp_path) -> None:
    workspace, registry, seed, output = _fixture(tmp_path)
    linked_parent = workspace / "linked-repo"
    linked_parent.symlink_to(seed.parent, target_is_directory=True)

    with pytest.raises(ContextSyncReceiptError, match="cannot open receipt input"):
        build_context_sync_receipt(
            workspace=workspace,
            registry_path=registry,
            seed_paths=[linked_parent / "seed.yaml"],
            remote_references=[],
            output_paths=[output],
            errors=[],
            generator_identity=GENERATOR_IDENTITY,
        )


def test_receipt_rejects_input_parent_swapped_during_binding(
    tmp_path,
    monkeypatch,
) -> None:
    import organvm_engine.contextmd.receipt as receipt_mod

    workspace, registry, seed, output = _fixture(tmp_path)
    original_parent = seed.parent
    moved_parent = workspace / "repo-original"
    outside_parent = tmp_path / "outside-input"
    outside_parent.mkdir()
    (outside_parent / "seed.yaml").write_bytes(seed.read_bytes())
    real_open = receipt_mod.os.open
    swapped = False

    def raced_open(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal swapped
        if path == "seed.yaml" and dir_fd is not None and not swapped:
            original_parent.rename(moved_parent)
            original_parent.symlink_to(outside_parent, target_is_directory=True)
            swapped = True
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(receipt_mod.os, "open", raced_open)
    with pytest.raises(ContextSyncReceiptError, match="path changed while"):
        build_context_sync_receipt(
            workspace=workspace,
            registry_path=registry,
            seed_paths=[seed],
            remote_references=[],
            output_paths=[output],
            errors=[],
            generator_identity=GENERATOR_IDENTITY,
        )

    assert swapped is True


def test_receipt_rejects_output_parent_swapped_to_outside_during_binding(
    tmp_path,
    monkeypatch,
) -> None:
    import organvm_engine.contextmd.receipt as receipt_mod

    workspace, registry, seed, output = _fixture(tmp_path)
    original_parent = output.parent
    moved_parent = workspace / "repo-original"
    outside_parent = tmp_path / "outside"
    outside_parent.mkdir()
    (outside_parent / "AGENTS.md").write_bytes(output.read_bytes())
    real_open = receipt_mod.os.open
    swapped = False

    def raced_open(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal swapped
        if path == "AGENTS.md" and dir_fd is not None and not swapped:
            original_parent.rename(moved_parent)
            original_parent.symlink_to(outside_parent, target_is_directory=True)
            swapped = True
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(receipt_mod.os, "open", raced_open)
    with pytest.raises(ContextSyncReceiptError, match="cannot bind context output"):
        build_context_sync_receipt(
            workspace=workspace,
            registry_path=registry,
            seed_paths=[seed],
            remote_references=[],
            output_paths=[output],
            errors=[],
            generator_identity=GENERATOR_IDENTITY,
        )

    assert swapped is True
    assert (outside_parent / "AGENTS.md").read_bytes() == (moved_parent / "AGENTS.md").read_bytes()


def test_receipt_rejects_final_output_replacement_between_binding_checks(
    tmp_path,
    monkeypatch,
) -> None:
    import organvm_engine.contextmd.sync as sync_mod

    workspace, registry, seed, output = _fixture(tmp_path)
    real_assert = sync_mod._assert_custody_parent_is_live
    swapped = False

    def replace_after_first_read(*args, **kwargs):
        nonlocal swapped
        if not swapped:
            output.unlink()
            output.write_text("CONCURRENT NEW OUTPUT\n", encoding="utf-8")
            swapped = True
        return real_assert(*args, **kwargs)

    monkeypatch.setattr(
        sync_mod,
        "_assert_custody_parent_is_live",
        replace_after_first_read,
    )
    with pytest.raises(ContextSyncReceiptError, match="changed during receipt binding"):
        build_context_sync_receipt(
            workspace=workspace,
            registry_path=registry,
            seed_paths=[seed],
            remote_references=[],
            output_paths=[output],
            errors=[],
            generator_identity=GENERATOR_IDENTITY,
        )

    assert swapped is True


def test_receipt_rejects_input_changed_while_hashing(tmp_path, monkeypatch) -> None:
    import organvm_engine.contextmd.receipt as receipt_mod

    workspace, registry, seed, output = _fixture(tmp_path)
    original_read = receipt_mod.os.read
    calls = 0

    def raced_read(descriptor, size):
        nonlocal calls
        chunk = original_read(descriptor, size)
        calls += 1
        if calls == 1:
            registry.write_text('{"version": 2}\n', encoding="utf-8")
        return chunk

    monkeypatch.setattr(receipt_mod.os, "read", raced_read)

    with pytest.raises(ContextSyncReceiptError, match="changed while it was being bound"):
        build_context_sync_receipt(
            workspace=workspace,
            registry_path=registry,
            seed_paths=[seed],
            remote_references=[],
            output_paths=[output],
            errors=[],
            generator_identity=GENERATOR_IDENTITY,
        )


def test_receipt_rejects_malformed_generator_identity(tmp_path) -> None:
    workspace, registry, seed, output = _fixture(tmp_path)

    with pytest.raises(ContextSyncReceiptError, match="exact commit and tree"):
        build_context_sync_receipt(
            workspace=workspace,
            registry_path=registry,
            seed_paths=[seed],
            remote_references=[],
            output_paths=[output],
            errors=[],
            generator_identity={"commit": "main", "tree": "dirty"},
        )


def test_success_receipt_requires_at_least_one_bound_output(tmp_path) -> None:
    workspace, registry, seed, _output = _fixture(tmp_path)

    with pytest.raises(ContextSyncReceiptError, match="requires output bindings"):
        build_context_sync_receipt(
            workspace=workspace,
            registry_path=registry,
            seed_paths=[seed],
            remote_references=[],
            output_paths=[],
            errors=[],
            generator_identity=GENERATOR_IDENTITY,
        )


def test_total_failure_receipt_is_durable_without_any_outputs(tmp_path) -> None:
    workspace, registry, seed, _output = _fixture(tmp_path)

    receipt = build_context_sync_receipt(
        workspace=workspace,
        registry_path=registry,
        seed_paths=[seed],
        remote_references=[],
        output_paths=[],
        errors=[{"path": "AGENTS.md", "error": "destination is not writable"}],
        generator_identity=GENERATOR_IDENTITY,
    )

    assert receipt["status"] == "failed"
    assert receipt["outputs"] == []
    assert receipt["errors"] == [
        {"path": "AGENTS.md", "error": "destination is not writable"},
    ]


def test_generator_identity_fails_closed_on_untracked_runtime_source(
    tmp_path,
    monkeypatch,
) -> None:
    import organvm_engine.contextmd.receipt as receipt_mod

    monkeypatch.setattr(
        receipt_mod,
        "_git_status_entries",
        lambda _root: [
            ("??", ("src/organvm_engine/contextmd/injected.py",)),
        ],
    )

    with pytest.raises(ContextSyncReceiptError, match="tracked or untracked"):
        receipt_mod.generator_git_identity(tmp_path)


def test_generator_identity_allows_only_bound_context_outputs(
    tmp_path,
    monkeypatch,
) -> None:
    import organvm_engine.contextmd.receipt as receipt_mod

    output = tmp_path / "AGENTS.md"
    output.write_text("generated\n", encoding="utf-8")
    monkeypatch.setattr(
        receipt_mod,
        "_git_status_entries",
        lambda _root: [(" M", (("AGENTS.md"),))],
    )
    monkeypatch.setattr(
        receipt_mod,
        "_git",
        lambda _root, *args: "a" * 40 if args[-1] == "HEAD" else "b" * 40,
    )

    identity = receipt_mod.generator_git_identity(
        tmp_path,
        allowed_dirty_paths=[output],
    )

    assert identity == GENERATOR_IDENTITY


def test_generator_tree_is_derived_from_the_captured_commit(
    tmp_path,
    monkeypatch,
) -> None:
    import organvm_engine.contextmd.receipt as receipt_mod

    commit = "c" * 40
    tree = "d" * 40
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(receipt_mod, "_git_status_entries", lambda _root: [])

    def resolved(_root, *args):
        calls.append(args)
        return commit if args[-1] == "HEAD" else tree

    monkeypatch.setattr(receipt_mod, "_git", resolved)

    identity = receipt_mod.generator_git_identity(tmp_path)

    assert identity == {"commit": commit, "tree": tree}
    assert calls == [
        ("rev-parse", "HEAD"),
        ("rev-parse", f"{commit}^{{tree}}"),
    ]
