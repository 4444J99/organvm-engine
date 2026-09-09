"""Private audit runtime residue must not masquerade as generator source."""

import shutil
import subprocess
from pathlib import Path

import pytest

from organvm_engine.contextmd.receipt import ContextSyncReceiptError, generator_git_identity

REPOSITORY = Path(__file__).resolve().parents[1]
ARTIFACTS = (
    "2026-08-31-reader-mode-estate-audit.ipynb",
    "reader-mode-estate-summary.json",
    "reader-mode-public-rollout.json",
    "reader-mode-estate-audit.md",
)


def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


@pytest.fixture
def checkout(tmp_path):
    _git(tmp_path, "init", "-q")
    shutil.copyfile(REPOSITORY / ".gitignore", tmp_path / ".gitignore")
    audit = tmp_path / "docs/audits"
    audit.mkdir(parents=True)
    for name in ARTIFACTS:
        (audit / name).write_text("tracked public artifact\n")
    _git(tmp_path, "add", ".gitignore", "docs/audits")
    _git(
        tmp_path, "-c", "user.name=Audit test", "-c", "user.email=audit@example.invalid",
        "-c", "commit.gpgsign=false", "commit", "-qm", "fixture",
    )
    return tmp_path


def test_private_audit_runtime_residue_is_not_generator_source(checkout):
    expected = generator_git_identity(checkout)
    audit = checkout / "docs/audits"
    for artifact in ARTIFACTS:
        for suffix in ("tmp", "rollback", "displaced", "failed"):
            (audit / f".{artifact}.owned-nonce.{suffix}").write_bytes(b"runtime custody")
    stage = audit / ".reader-mode-audit-build.owned-nonce"
    stage.mkdir(mode=0o700)
    (stage / "private-input.json").write_bytes(b"private runtime snapshot")
    (audit / ".reader-mode-recovery.owned-nonce.pending").write_bytes(b"incomplete WAL")
    (audit / ".reader-mode-publication.recovery").write_bytes(b"active WAL")

    assert generator_git_identity(checkout) == expected
    _git(checkout, "add", "-A")
    assert not _git(checkout, "status", "--porcelain")
    assert not _git(checkout, "diff", "--cached", "--name-only")


@pytest.mark.parametrize("operation", ["modify", "delete"])
@pytest.mark.parametrize("artifact", ARTIFACTS)
def test_tracked_public_audit_changes_still_fail_attestation(checkout, artifact, operation):
    target = checkout / "docs/audits" / artifact
    if operation == "modify":
        target.write_bytes(b"changed public bytes")
    else:
        target.unlink()
    with pytest.raises(ContextSyncReceiptError, match="tracked or untracked changes"):
        generator_git_identity(checkout)


@pytest.mark.parametrize("name", [
    "docs/audits/untracked.py",
    "docs/audits/.other.tmp",
    "docs/audits/.reader-mode-estate-audit.md.nonce.py",
    "elsewhere/.reader-mode-estate-audit.md.nonce.tmp",
])
def test_runtime_custody_ignores_do_not_hide_unrelated_sources(checkout, name):
    path = checkout / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"untracked source")
    with pytest.raises(ContextSyncReceiptError, match="tracked or untracked changes"):
        generator_git_identity(checkout)
