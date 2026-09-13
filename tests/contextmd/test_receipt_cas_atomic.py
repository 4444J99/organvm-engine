"""Real interruption tests for atomic receipt custody publication and recovery."""

import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from organvm_engine.contextmd import receipt as receipt_mod

RECEIPT = {"status": "success", "proof": "exact interrupted receipt bytes"}
PAYLOAD = (json.dumps(RECEIPT, indent=2, sort_keys=True) + "\n").encode()
DIGEST = hashlib.sha256(PAYLOAD).hexdigest()


def _interrupt_receipt_writer(target: Path, boundary: str) -> None:
    """Use process exit so no Python exception/finally cleanup can run."""
    source = Path(__file__).resolve().parents[2] / "src"
    program = r'''
import hashlib
import json
import os
import sys
from pathlib import Path
from organvm_engine.contextmd import receipt

target = Path(sys.argv[1])
boundary = sys.argv[2]
data = json.loads(sys.argv[3])
payload = (json.dumps(data, indent=2, sort_keys=True) + "\n").encode()
digest = hashlib.sha256(payload).hexdigest()
real_write = receipt.os.write
real_rename = receipt.os.rename
real_link = receipt.os.link

def interrupted_write(fd, data):
    if boundary == "partial-cas-write" and data == payload:
        real_write(fd, data[:11])
        os._exit(73)
    return real_write(fd, data)

def interrupted_rename(src, dst, *args, **kwargs):
    if dst == digest and boundary == "before-cas-publication":
        os._exit(73)
    result = real_rename(src, dst, *args, **kwargs)
    if dst == digest and boundary == "after-cas-publication":
        os._exit(73)
    return result

def interrupted_link(src, dst, *args, **kwargs):
    if dst == digest and boundary == "before-cas-publication":
        os._exit(73)
    result = real_link(src, dst, *args, **kwargs)
    if dst == digest and boundary == "after-cas-publication":
        os._exit(73)
    if dst == target.name and boundary == "after-public-link":
        os._exit(73)
    return result

receipt.os.write = interrupted_write
receipt.os.rename = interrupted_rename
receipt.os.link = interrupted_link
receipt.write_context_sync_receipt(target, data)
raise AssertionError("writer never reached requested interruption boundary")
'''
    completed = subprocess.run(
        [sys.executable, "-c", program, str(target), boundary, json.dumps(RECEIPT)],
        env={**os.environ, "PYTHONPATH": str(source)},
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert completed.returncode == 73, completed.stderr


@pytest.mark.parametrize(
    "boundary",
    ["partial-cas-write", "before-cas-publication", "after-cas-publication", "after-public-link"],
)
def test_receipt_restart_never_leaves_a_partial_or_multilink_cas_object(
    tmp_path, boundary,
) -> None:
    target = tmp_path / "receipt.json"
    _interrupt_receipt_writer(target, boundary)
    cas = tmp_path / ".organvm-receipt-cas" / "sha256"
    canonical = cas / DIGEST
    published = boundary in {"after-cas-publication", "after-public-link"}
    assert canonical.exists() is published
    if published:
        assert canonical.read_bytes() == PAYLOAD
        assert stat.S_IMODE(canonical.stat().st_mode) == 0o400
        assert canonical.stat().st_nlink == 1
    if boundary == "after-public-link":
        assert target.read_bytes() == PAYLOAD
        public_inode = target.stat().st_ino
    else:
        assert not target.exists()

    retry = tmp_path / "receipt-retry.json"
    assert receipt_mod.write_context_sync_receipt(retry, RECEIPT) == "sha256:" + DIGEST
    assert retry.read_bytes() == PAYLOAD
    assert canonical.read_bytes() == PAYLOAD
    assert canonical.stat().st_nlink == 1
    assert not list(cas.glob("transaction-*"))
    if boundary == "after-public-link":
        assert target.read_bytes() == PAYLOAD
        assert target.stat().st_ino == public_inode
        assert target.stat().st_nlink == 1
    if boundary == "partial-cas-write":
        partial = PAYLOAD[:11]
        preserved = cas / hashlib.sha256(partial).hexdigest()
        assert preserved.read_bytes() == partial
        assert stat.S_IMODE(preserved.stat().st_mode) == 0o400


def test_receipt_reaps_exact_legacy_two_link_cas_pair(tmp_path) -> None:
    cas = tmp_path / "cas"
    cas.mkdir(mode=0o700)
    canonical = cas / DIGEST
    canonical.write_bytes(PAYLOAD)
    canonical.chmod(0o400)
    alias = cas / ("transaction-" + "a" * 48 + ".rollback")
    alias.hardlink_to(canonical)
    original_inode = canonical.stat().st_ino
    descriptor = os.open(cas, os.O_RDONLY | os.O_DIRECTORY)
    try:
        receipt_mod._lock_receipt_cas(descriptor)
        receipt_mod._reap_receipt_transactions(descriptor)
        receipt_mod._ensure_receipt_cas_object(descriptor, DIGEST, PAYLOAD)
    finally:
        os.close(descriptor)
    assert canonical.read_bytes() == PAYLOAD
    assert canonical.stat().st_ino == original_inode
    assert canonical.stat().st_nlink == 1
    assert not alias.exists()


@pytest.mark.parametrize("recognized_alias", [False, True])
def test_receipt_cas_still_rejects_unknown_or_additional_hardlinks(
    tmp_path, recognized_alias,
) -> None:
    cas = tmp_path / "cas"
    cas.mkdir(mode=0o700)
    canonical = cas / DIGEST
    canonical.write_bytes(PAYLOAD)
    canonical.chmod(0o400)
    foreign = tmp_path / "foreign-link"
    foreign.hardlink_to(canonical)
    alias = cas / ("transaction-" + "b" * 48 + ".rollback")
    if recognized_alias:
        alias.hardlink_to(canonical)
    descriptor = os.open(cas, os.O_RDONLY | os.O_DIRECTORY)
    try:
        receipt_mod._lock_receipt_cas(descriptor)
        with pytest.raises(receipt_mod.ContextSyncReceiptError, match="CAS object is corrupt"):
            if recognized_alias:
                receipt_mod._reap_receipt_transactions(descriptor)
            else:
                receipt_mod._ensure_receipt_cas_object(descriptor, DIGEST, PAYLOAD)
    finally:
        os.close(descriptor)
    assert foreign.read_bytes() == canonical.read_bytes() == PAYLOAD
    assert alias.exists() is recognized_alias


@pytest.mark.parametrize("write_result", [0, -1])
def test_receipt_cas_zero_progress_write_fails_and_cleans_private_alias(
    tmp_path, monkeypatch, write_result,
) -> None:
    cas = tmp_path / "cas"
    cas.mkdir(mode=0o700)
    descriptor = os.open(cas, os.O_RDONLY | os.O_DIRECTORY)
    try:
        receipt_mod._lock_receipt_cas(descriptor)
        with monkeypatch.context() as patch:
            patch.setattr(receipt_mod.os, "write", lambda *_: write_result)
            with pytest.raises(receipt_mod.ContextSyncReceiptError, match="cannot write"):
                receipt_mod._ensure_receipt_cas_object(descriptor, DIGEST, PAYLOAD)
        assert not list(cas.iterdir())
        receipt_mod._ensure_receipt_cas_object(descriptor, DIGEST, PAYLOAD)
        assert (cas / DIGEST).read_bytes() == PAYLOAD
    finally:
        os.close(descriptor)


def test_receipt_cas_refuses_a_canonical_winner_before_rename(tmp_path, monkeypatch) -> None:
    cas = tmp_path / "cas"
    cas.mkdir(mode=0o700)
    canonical = cas / DIGEST
    real_fsync = receipt_mod.os.fsync
    winner = b"independently installed winner"

    def publish_winner_on_file_fsync(descriptor):
        if stat.S_ISREG(os.fstat(descriptor).st_mode):
            canonical.write_bytes(winner)
            canonical.chmod(0o400)
        return real_fsync(descriptor)

    monkeypatch.setattr(receipt_mod.os, "fsync", publish_winner_on_file_fsync)
    descriptor = os.open(cas, os.O_RDONLY | os.O_DIRECTORY)
    try:
        receipt_mod._lock_receipt_cas(descriptor)
        with pytest.raises(receipt_mod.ContextSyncReceiptError, match="appeared before publication"):
            receipt_mod._ensure_receipt_cas_object(descriptor, DIGEST, PAYLOAD)
    finally:
        os.close(descriptor)
    assert canonical.read_bytes() == winner
    assert not list(cas.glob("transaction-*"))


def test_receipt_publication_zero_progress_write_is_recoverable(tmp_path, monkeypatch) -> None:
    target = tmp_path / "receipt.json"
    real_write = receipt_mod.os.write
    writes = 0

    def stop_at_publication_staging(descriptor, payload):
        nonlocal writes
        writes += 1
        if writes == 2:
            return 0
        return real_write(descriptor, payload)

    with monkeypatch.context() as patch:
        patch.setattr(receipt_mod.os, "write", stop_at_publication_staging)
        with pytest.raises(receipt_mod.ContextSyncReceiptError, match="publication staging"):
            receipt_mod.write_context_sync_receipt(target, RECEIPT)
    assert writes == 2
    assert not target.exists()
    receipt_mod.write_context_sync_receipt(target, RECEIPT)
    assert target.read_bytes() == PAYLOAD
    cas = tmp_path / ".organvm-receipt-cas" / "sha256"
    assert not list(cas.glob("transaction-*"))


def test_receipt_cas_short_writes_preserve_complete_payload(tmp_path, monkeypatch) -> None:
    target = tmp_path / "receipt.json"
    real_write = receipt_mod.os.write

    def short_write(descriptor, payload):
        return real_write(descriptor, payload[:7])

    monkeypatch.setattr(receipt_mod.os, "write", short_write)
    receipt_mod.write_context_sync_receipt(target, RECEIPT)
    assert target.read_bytes() == PAYLOAD
    canonical = tmp_path / ".organvm-receipt-cas" / "sha256" / DIGEST
    assert canonical.read_bytes() == PAYLOAD
    assert canonical.stat().st_nlink == 1
