"""Regression tests for flat workspace context sync."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from organvm_engine.contextmd import AUTO_END, AUTO_START
from organvm_engine.contextmd.sync import sync_all

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_sync_all_updates_repo_in_additional_flat_workspace_root(tmp_path, monkeypatch):
    import organvm_engine.contextmd.sync as sync_mod
    import organvm_engine.ledger.emit as ledger_emit
    import organvm_engine.pulse.emitter as pulse_emitter

    workspace = tmp_path / "workspace"
    flat_root = tmp_path / "flat"
    repo = flat_root / "recursive-engine"
    workspace.mkdir()
    repo.mkdir(parents=True)

    claude_md = repo / "CLAUDE.md"
    # Only a file that already carries both AUTO markers receives the pointer.
    claude_md.write_text(f"# Recursive Engine\n\n{AUTO_START}\nold block\n{AUTO_END}\n")
    (repo / "seed.yaml").write_text(
        "repo: recursive-engine\n"
        "org: organvm-i-theoria\n"
        "produces:\n"
        "  - type: context-files\n"
        "    consumers: [META-ORGANVM]\n",
    )

    monkeypatch.setattr(sync_mod, "precompute_ammoi", lambda: None)
    monkeypatch.setattr(pulse_emitter, "emit_engine_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(ledger_emit, "testament_emit", lambda *args, **kwargs: None)

    result = sync_all(
        workspace=workspace,
        registry_path=str(FIXTURES / "registry-minimal.json"),
        additional_workspace_roots=[flat_root],
    )

    content = claude_md.read_text()
    synced_line = next(line for line in content.splitlines() if "Last synced:" in line)
    synced_at = synced_line.split("Last synced: ", 1)[1].rstrip("*")

    document_path = repo / "docs" / "organvm-context.md"
    document = document_path.read_text()

    assert result["errors"] == []
    assert str(claude_md) in result["updated"]
    assert str(document_path) in result["created"]
    assert any(change["path"] == str(claude_md) for change in result["changelog"])
    assert any(change["path"] == str(document_path) for change in result["changelog"])
    # The instruction file carries the identity pointer: the repo's identity
    # lines stay in the file, and the full generated text is in the document.
    assert AUTO_START in content
    assert "docs/organvm-context.md" in content
    assert "**Org:** `organvm-i-theoria` | **Repo:** `recursive-engine`" in content
    assert "- **Produces** → `META-ORGANVM`: context-files" in content
    assert "## Directives" not in content
    assert not (repo / "GEMINI.md").exists()
    assert not (repo / "AGENTS.md").exists()
    assert "recursive-engine" in document
    assert "**Produces**" in document
    assert "`META-ORGANVM`" in document
    synced_dt = datetime.strptime(synced_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    assert datetime.now(timezone.utc) - synced_dt < timedelta(minutes=1)
