"""Subprocess interruption proofs for the audit artifact-set publication WAL."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

BUILDER = Path(__file__).resolve().parents[1] / "docs/audits/build_reader_mode_estate_audit.py"
NAMES = ("report.md", "summary.json", "third.md")


def _builder(root):
    spec = importlib.util.spec_from_file_location("audit_recovery_test", BUILDER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.HERE = root
    return module


def _originals(root, absent=False):
    originals = {}
    for name in NAMES:
        if absent and name == NAMES[0]:
            continue
        payload = f"original:{name}\n".encode()
        (root / name).write_bytes(payload)
        originals[name] = payload
    return originals


def _interrupt(root, boundary, *, recover=False):
    program = r'''
import importlib.util
import os
import sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("audit_recovery_child", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.HERE = Path(sys.argv[2])
boundary = sys.argv[3]
names = ("report.md", "summary.json", "third.md")
real_rename, real_link, real_unlink = Path.rename, module.os.link, Path.unlink
real_wal = getattr(module, "_write_artifact_recovery", None)
committed = False

def interrupted_rename(source, target):
    result = real_rename(source, target)
    if boundary == "after-displace-first" and source.name == names[0] and target.suffix == ".displaced":
        os._exit(73)
    if boundary == "after-displace-second" and source.name == names[1] and target.suffix == ".displaced":
        os._exit(73)
    if boundary in {"after-rollback-displace", "after-recovery-displace"} and source.name == names[0] and target.suffix == ".failed":
        os._exit(73)
    return result

def interrupted_link(source, target, **kwargs):
    if boundary == "after-rollback-displace" and source.suffix == ".tmp" and target.name == names[1]:
        raise OSError("force whole-set rollback")
    result = real_link(source, target, **kwargs)
    if boundary == "after-link-first" and source.suffix == ".tmp" and target.name == names[0]:
        os._exit(73)
    return result

def interrupted_wal(record):
    global committed
    if record["state"] == "committed" and boundary == "before-commit":
        os._exit(73)
    result = real_wal(record)
    if record["state"] == "committed":
        committed = True
        if boundary == "after-commit":
            os._exit(73)
    return result

def interrupted_unlink(path, **kwargs):
    result = real_unlink(path, **kwargs)
    if committed and boundary == "during-committed-cleanup" and path.suffix == ".rollback":
        os._exit(73)
    return result

Path.rename, Path.unlink, module.os.link = interrupted_rename, interrupted_unlink, interrupted_link
if real_wal is not None:
    module._write_artifact_recovery = interrupted_wal
if sys.argv[4] == "recover":
    module.recover_artifact_publication()
else:
    module.publish_exact_candidate_bytes({module.HERE / name: f"candidate:{name}\n".encode() for name in names})
raise AssertionError("requested crash boundary was not reached")
'''
    result = subprocess.run(
        [sys.executable, "-c", program, str(BUILDER), str(root), boundary,
         "recover" if recover else "publish"],
        env={**os.environ, "PYTHONPATH": str(BUILDER.parents[2] / "src")},
        text=True, capture_output=True, timeout=30, check=False,
    )
    assert result.returncode == 73, result.stderr


@pytest.mark.parametrize("boundary", [
    "after-displace-first", "after-displace-second", "after-link-first",
    "after-rollback-displace", "before-commit",
])
def test_pending_publication_restores_complete_original_set(tmp_path, boundary):
    originals = _originals(tmp_path)
    _interrupt(tmp_path, boundary)
    module = _builder(tmp_path)
    module.recover_artifact_publication()
    assert {name: (tmp_path / name).read_bytes() for name in NAMES} == originals
    assert set(path.name for path in tmp_path.iterdir()) == set(NAMES)
    module.recover_artifact_publication()


@pytest.mark.parametrize("boundary", ["after-commit", "during-committed-cleanup"])
def test_committed_publication_is_not_reverted_on_restart(tmp_path, boundary):
    _originals(tmp_path)
    _interrupt(tmp_path, boundary)
    module = _builder(tmp_path)
    module.recover_artifact_publication()
    assert all((tmp_path / name).read_bytes() == f"candidate:{name}\n".encode() for name in NAMES)
    assert set(path.name for path in tmp_path.iterdir()) == set(NAMES)


def test_recovery_can_itself_restart_after_rollback_displacement(tmp_path):
    originals = _originals(tmp_path)
    _interrupt(tmp_path, "after-displace-second")
    _interrupt(tmp_path, "after-recovery-displace", recover=True)
    module = _builder(tmp_path)
    module.recover_artifact_publication()
    assert {name: (tmp_path / name).read_bytes() for name in NAMES} == originals
    assert set(path.name for path in tmp_path.iterdir()) == set(NAMES)


def test_recovery_retires_a_created_candidate_without_creating_an_original(tmp_path):
    originals = _originals(tmp_path, absent=True)
    _interrupt(tmp_path, "after-link-first")
    _builder(tmp_path).recover_artifact_publication()
    assert not (tmp_path / NAMES[0]).exists()
    assert {name: (tmp_path / name).read_bytes() for name in originals} == originals
    assert set(path.name for path in tmp_path.iterdir()) == set(originals)


def test_main_recovers_before_missing_private_inputs_are_consulted(tmp_path, monkeypatch):
    originals = _originals(tmp_path)
    _interrupt(tmp_path, "after-displace-first")
    module = _builder(tmp_path)

    def missing_inputs():
        assert {name: (tmp_path / name).read_bytes() for name in NAMES} == originals
        raise RuntimeError("private exports unavailable")

    monkeypatch.setattr(module, "verify_live_inputs_against_manifest", missing_inputs)
    with pytest.raises(RuntimeError, match="private exports unavailable"):
        module.main()
    assert set(path.name for path in tmp_path.iterdir()) == set(NAMES)


def test_recovery_preserves_concurrent_public_replacement_and_preimage(tmp_path):
    originals = _originals(tmp_path)
    _interrupt(tmp_path, "after-displace-first")
    target = tmp_path / NAMES[0]
    target.write_bytes(b"concurrent replacement")
    with pytest.raises(RuntimeError, match="concurrent public artifact preserved"):
        _builder(tmp_path).recover_artifact_publication()
    assert target.read_bytes() == b"concurrent replacement"
    assert originals[NAMES[0]] in [path.read_bytes() for path in tmp_path.glob(".*.displaced")]


@pytest.mark.parametrize("corruption", ["target-path", "alias-path", "root", "digest", "missing-key"])
def test_recovery_rejects_forged_paths_or_changed_custody(tmp_path, corruption):
    _originals(tmp_path)
    _interrupt(tmp_path, "after-displace-first")
    module = _builder(tmp_path)
    wal = tmp_path / module.ARTIFACT_RECOVERY_NAME
    record = json.loads(wal.read_bytes())
    if corruption == "target-path":
        record["artifacts"][0]["target"] = "../outside.md"
    elif corruption == "alias-path":
        record["artifacts"][0]["displaced"] = "../outside.md"
    elif corruption == "root":
        record["root"]["inode"] += 1
    elif corruption == "digest":
        record["artifacts"][0]["original_binding"]["sha256"] = "0" * 64
    else:
        del record["artifacts"][0]["original_binding"]
    wal.write_text(json.dumps(record))
    with pytest.raises(RuntimeError):
        module.recover_artifact_publication()
    assert not (tmp_path / NAMES[0]).exists()
    assert wal.exists()
    assert list(tmp_path.glob(".*.displaced"))


@pytest.mark.parametrize("kind", ["symlink", "fifo", "nonprivate", "malformed"])
def test_recovery_rejects_unsafe_journal_files(tmp_path, kind):
    module = _builder(tmp_path)
    wal = tmp_path / module.ARTIFACT_RECOVERY_NAME
    if kind == "symlink":
        peer = tmp_path / "peer"
        peer.write_text("{}")
        wal.symlink_to(peer)
    elif kind == "fifo":
        os.mkfifo(wal, mode=0o600)
    else:
        wal.write_text("{}" if kind == "nonprivate" else "{broken")
        wal.chmod(0o644 if kind == "nonprivate" else 0o600)
    with pytest.raises(RuntimeError):
        module.recover_artifact_publication()


def test_commit_marker_fsync_failure_never_starts_rollback(tmp_path, monkeypatch):
    _originals(tmp_path)
    module = _builder(tmp_path)
    real_fsync = module._fsync_artifact_directory
    failed = False

    def fail_after_committed_marker():
        nonlocal failed
        wal = tmp_path / module.ARTIFACT_RECOVERY_NAME
        if wal.exists() and json.loads(wal.read_bytes())["state"] == "committed" and not failed:
            failed = True
            raise OSError("commit durability acknowledgement failed")
        real_fsync()

    with monkeypatch.context() as patch:
        patch.setattr(module, "_fsync_artifact_directory", fail_after_committed_marker)
        with pytest.raises(OSError, match="commit durability"):
            module.publish_exact_candidate_bytes({
                tmp_path / name: f"candidate:{name}\n".encode() for name in NAMES
            })
    assert failed
    assert all((tmp_path / name).read_bytes() == f"candidate:{name}\n".encode() for name in NAMES)
    module.recover_artifact_publication()
    assert set(path.name for path in tmp_path.iterdir()) == set(NAMES)


def test_empty_publication_does_not_create_a_recovery_record(tmp_path):
    _builder(tmp_path).publish_exact_candidate_bytes({})
    assert not list(tmp_path.iterdir())


def test_recovery_rejects_journal_replacement_between_stat_and_read(tmp_path, monkeypatch):
    _originals(tmp_path)
    _interrupt(tmp_path, "after-displace-first")
    module = _builder(tmp_path)
    wal = tmp_path / module.ARTIFACT_RECOVERY_NAME
    payload = wal.read_bytes()
    real_read = module._read_regular_bytes_once

    def replace_journal_then_read(path):
        if path == wal:
            replacement = tmp_path / "replacement"
            replacement.write_bytes(payload)
            replacement.chmod(0o600)
            replacement.replace(wal)
        return real_read(path)

    monkeypatch.setattr(module, "_read_regular_bytes_once", replace_journal_then_read)
    with pytest.raises(RuntimeError, match="metadata changed while reading"):
        module.recover_artifact_publication()
    assert not (tmp_path / NAMES[0]).exists()


def test_recovery_rejects_replaced_root_before_mutation(tmp_path, monkeypatch):
    root = tmp_path / "artifacts"
    root.mkdir()
    _originals(root)
    _interrupt(root, "after-displace-first")
    module = _builder(root)
    real_read = module._read_artifact_recovery
    moved = tmp_path / "original-artifacts"

    def swap_after_read():
        record = real_read()
        root.rename(moved)
        root.mkdir()
        (root / NAMES[0]).write_bytes(b"independent replacement root")
        return record

    monkeypatch.setattr(module, "_read_artifact_recovery", swap_after_read)
    with pytest.raises(RuntimeError, match="recovery directory changed"):
        module.recover_artifact_publication()
    assert (root / NAMES[0]).read_bytes() == b"independent replacement root"
    assert not (moved / NAMES[0]).exists()
    assert list(moved.glob(".*.displaced"))
