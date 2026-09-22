"""Interrupted CAS creation must not publish a partial canonical object."""

import hashlib
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from organvm_engine.contextmd import AUTO_END, AUTO_START
from organvm_engine.contextmd.sync import _inject_section_result


@pytest.mark.parametrize(
    "boundary",
    ["partial-write", "before-chmod", "after-chmod", "after-fsync", "before-publish", "after-publish"],
)
def test_custody_object_crash_retries_without_poisoning_canonical_digest(tmp_path, boundary) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "AGENTS.md"
    original = b"manual context survives a CAS interruption\n"
    target.write_bytes(original)
    source = Path(__file__).resolve().parents[2] / "src"
    program = r'''
import hashlib
import os
import sys
from pathlib import Path
from organvm_engine.contextmd.sync import _inject_section_result

workspace = Path(sys.argv[1])
boundary = sys.argv[2]
payload = (workspace / "AGENTS.md").read_bytes()
canonical = "sha256-" + hashlib.sha256(payload).hexdigest() + ".object"
real_write, real_chmod, real_fsync, real_rename = os.write, os.fchmod, os.fsync, os.rename
object_fd = None

def interrupted_write(descriptor, value):
    global object_fd
    if value == payload:
        object_fd = descriptor
        if boundary == "partial-write":
            real_write(descriptor, value[:4])
            os._exit(73)
    return real_write(descriptor, value)

def interrupted_chmod(descriptor, mode):
    if descriptor == object_fd and boundary == "before-chmod":
        os._exit(73)
    result = real_chmod(descriptor, mode)
    if descriptor == object_fd and boundary == "after-chmod":
        os._exit(73)
    return result

def interrupted_fsync(descriptor):
    result = real_fsync(descriptor)
    if descriptor == object_fd and boundary == "after-fsync":
        os._exit(73)
    return result

def interrupted_rename(src, dst, *args, **kwargs):
    if dst == canonical and boundary == "before-publish":
        os._exit(73)
    result = real_rename(src, dst, *args, **kwargs)
    if dst == canonical and boundary == "after-publish":
        os._exit(73)
    return result

os.write, os.fchmod, os.fsync, os.rename = (
    interrupted_write, interrupted_chmod, interrupted_fsync, interrupted_rename,
)
_inject_section_result(workspace / "AGENTS.md", "first section", custody_root=workspace)
raise AssertionError("writer did not reach the requested crash boundary")
'''
    completed = subprocess.run(
        [sys.executable, "-c", program, str(workspace), boundary],
        env={**os.environ, "PYTHONPATH": str(source)}, capture_output=True,
        text=True, timeout=20, check=False,
    )
    assert completed.returncode == 73, completed.stderr
    assert target.read_bytes() == original
    journal = workspace / ".organvm-context-cas"
    canonical = journal / f"sha256-{hashlib.sha256(original).hexdigest()}.object"
    if boundary == "after-publish":
        assert canonical.read_bytes() == original
        assert canonical.stat().st_nlink == 1
        assert stat.S_IMODE(canonical.stat().st_mode) == 0o400
    else:
        assert not canonical.exists()
        assert list(journal.glob("transaction-*.generated"))

    result = _inject_section_result(
        target, f"{AUTO_START}\nretried section\n{AUTO_END}", custody_root=workspace,
    )
    assert result["action"] == "updated"
    assert target.read_bytes().startswith(original)
    assert canonical.read_bytes() == original
    assert canonical.stat().st_nlink == 1
    assert stat.S_IMODE(canonical.stat().st_mode) == 0o400
    assert not list(journal.glob("transaction-*"))
    assert not list(journal.glob("recovery-*"))


@pytest.mark.parametrize("failure", ["write", "chmod", "file-fsync", "directory-fsync"])
def test_custody_object_publication_failure_can_retry(tmp_path, monkeypatch, failure) -> None:
    import organvm_engine.contextmd.sync as sync_mod

    journal = tmp_path / "journal"
    journal.mkdir(mode=0o700)
    journal_fd = os.open(journal, os.O_RDONLY | os.O_DIRECTORY)
    payload = b"complete object bytes\n"
    canonical = journal / sync_mod._custody_object_name(payload)
    real_write, real_chmod, real_fsync = os.write, os.fchmod, os.fsync
    failed = False

    def fail_write(descriptor, value):
        nonlocal failed
        if failure == "write" and not failed:
            failed = True
            real_write(descriptor, value[:4])
            raise OSError("injected object write failure")
        return real_write(descriptor, value)

    def fail_chmod(descriptor, mode):
        nonlocal failed
        if failure == "chmod" and not failed:
            failed = True
            raise OSError("injected object chmod failure")
        return real_chmod(descriptor, mode)

    def fail_fsync(descriptor):
        nonlocal failed
        is_directory = stat.S_ISDIR(os.fstat(descriptor).st_mode)
        matching = (failure == "file-fsync" and not is_directory) or (
            failure == "directory-fsync" and is_directory
        )
        if matching and not failed:
            failed = True
            raise OSError("injected object fsync failure")
        return real_fsync(descriptor)

    monkeypatch.setattr(sync_mod.os, "write", fail_write)
    monkeypatch.setattr(sync_mod.os, "fchmod", fail_chmod)
    monkeypatch.setattr(sync_mod.os, "fsync", fail_fsync)
    try:
        sync_mod._lock_custody_journal(journal_fd)
        with pytest.raises(OSError, match="injected object"):
            sync_mod._ensure_custody_object(journal_fd, payload)
        assert failed
        assert not list(journal.glob("transaction-*"))
        assert canonical.exists() == (failure == "directory-fsync")
        sync_mod._ensure_custody_object(journal_fd, payload)
        assert canonical.read_bytes() == payload
        assert canonical.stat().st_nlink == 1
        assert stat.S_IMODE(canonical.stat().st_mode) == 0o400
    finally:
        os.close(journal_fd)


def test_custody_object_refuses_a_canonical_winner_before_publication(tmp_path, monkeypatch) -> None:
    import organvm_engine.contextmd.sync as sync_mod

    journal = tmp_path / "journal"
    journal.mkdir(mode=0o700)
    journal_fd = os.open(journal, os.O_RDONLY | os.O_DIRECTORY)
    payload = b"generated bytes\n"
    canonical = journal / sync_mod._custody_object_name(payload)
    winner = b"preexisting canonical evidence must not be replaced\n"
    real_fsync = os.fsync
    appeared = False

    def introduce_winner(descriptor):
        nonlocal appeared
        result = real_fsync(descriptor)
        if not appeared and stat.S_ISREG(os.fstat(descriptor).st_mode):
            appeared = True
            canonical.write_bytes(winner)
            canonical.chmod(0o400)
        return result

    monkeypatch.setattr(sync_mod.os, "fsync", introduce_winner)
    try:
        sync_mod._lock_custody_journal(journal_fd)
        with pytest.raises(RuntimeError, match="object appeared before publication"):
            sync_mod._ensure_custody_object(journal_fd, payload)
        assert appeared
        assert canonical.read_bytes() == winner
        assert not list(journal.glob("transaction-*"))
        with pytest.raises(RuntimeError, match="digest collision or corruption"):
            sync_mod._ensure_custody_object(journal_fd, payload)
        assert canonical.read_bytes() == winner
    finally:
        os.close(journal_fd)
