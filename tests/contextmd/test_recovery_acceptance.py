"""Public recovery must precede attestation and retain post-install effects."""

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from organvm_engine.contextmd import AUTO_END, AUTO_START
from organvm_engine.contextmd import receipt as receipt_mod
from organvm_engine.contextmd import sync as sync_mod


def test_wal_retirement_failure_keeps_exact_public_binding(tmp_path, monkeypatch) -> None:
    target = tmp_path / "AGENTS.md"
    target.write_text("Manual context.\n", encoding="utf-8")

    def fail_retire(*args):
        raise OSError("injected WAL retirement failure")

    monkeypatch.setattr(sync_mod, "_retire_custody_recovery_record", fail_retire)
    with pytest.raises(sync_mod.ContextCustodyPublicationError) as raised:
        sync_mod._inject_section_result(
            target, f"{AUTO_START}\nGenerated context.\n{AUTO_END}", custody_root=tmp_path,
        )
    payload = target.read_bytes()
    assert b"Generated context." in payload
    assert raised.value.output_binding["path"] == "AGENTS.md"
    assert raised.value.output_binding["sha256"] == "sha256:" + hashlib.sha256(payload).hexdigest()


def test_interrupted_tracked_context_recovers_before_generator_attestation(tmp_path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "AGENTS.md"
    original = b"Manual context survives the interrupted rename.\n"
    target.write_bytes(original)
    for args in (["init", "-q"], ["add", "AGENTS.md"], [
        "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "commit", "-qm", "Fixture",
    ]):
        subprocess.run(["git", "-C", str(workspace), *args], check=True)
    program = r'''
import os
import sys
from pathlib import Path
from organvm_engine.contextmd import AUTO_START, AUTO_END
from organvm_engine.contextmd.sync import _inject_section_result
real_rename = os.rename
def crash_after_capture(src, dst, *args, **kwargs):
    result = real_rename(src, dst, *args, **kwargs)
    if src == "AGENTS.md":
        os._exit(73)
    return result
os.rename = crash_after_capture
workspace = Path(sys.argv[1])
_inject_section_result(workspace / "AGENTS.md", f"{AUTO_START}\nnew\n{AUTO_END}", custody_root=workspace)
'''
    source = Path(__file__).resolve().parents[2] / "src"
    child = subprocess.run(
        [sys.executable, "-c", program, str(workspace)],
        env={**os.environ, "PYTHONPATH": str(source)},
        capture_output=True, text=True, timeout=20, check=False,
    )
    assert child.returncode == 73, child.stderr
    assert not target.exists()
    real_identity = receipt_mod.generator_git_identity
    with pytest.raises(receipt_mod.ContextSyncReceiptError, match="checkout"):
        real_identity(workspace)
    observed = []

    def identity(*args, **kwargs):
        if not observed:
            assert target.read_bytes() == original
        observed.append(real_identity(workspace, **kwargs))
        return observed[-1]

    monkeypatch.setattr(receipt_mod, "generator_git_identity", identity)
    monkeypatch.setattr("organvm_engine.pulse.emitter.emit_engine_event", lambda *a, **kw: None)
    monkeypatch.setattr("organvm_engine.ledger.emit.testament_emit", lambda *a, **kw: None)
    result = sync_mod.sync_all(
        workspace=workspace,
        registry_path=str(Path(__file__).resolve().parents[1] / "fixtures" / "registry-minimal.json"),
        additional_workspace_roots=[], receipt_path=tmp_path / "receipt.json",
    )
    assert not result["errors"]
    assert len(observed) == 2
    assert observed[0] == observed[1]
    assert target.read_bytes().startswith(original)
