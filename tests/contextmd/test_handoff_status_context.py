"""Positive tests: context sync flags stale handoffs in the generated context.

Covers organvm-engine #74 item 4. The handoff staleness flag lives in
``_build_handoff_status_context`` (``contextmd/generator.py``): a stale or
expired ``.conductor/active-handoff.md`` must render its status plus the
"verify constraints before relying" warning into the generated context
section, and a fresh handoff must render ACTIVE with no warning. Before this
file, no test pinned that behaviour — the only reference was a negative
monkeypatch test proving the sync path does *not* call the live-context
builders — so a refactor could silently drop the flag and nothing would fail.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from organvm_engine.contextmd.generator import _build_handoff_status_context

WARNING = "verify constraints before relying on this handoff"


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _write_handoff(
    repo: Path,
    *,
    created_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> Path:
    """Mirror of tests/test_handoff.py::_write_handoff (front-matter form)."""
    handoff = repo / ".conductor" / "active-handoff.md"
    handoff.parent.mkdir(parents=True)
    lines = ["---"]
    if created_at is not None:
        lines.append(f"created_at: {_iso(created_at)}")
    if expires_at is not None:
        lines.append(f"expires_at: {_iso(expires_at)}")
    lines.extend(["---", "# Active handoff", "Continue the task."])
    handoff.write_text("\n".join(lines) + "\n")
    return handoff


def test_stale_handoff_renders_stale_and_warning(tmp_path):
    now = datetime.now(timezone.utc)
    repo = tmp_path / "repo"
    _write_handoff(
        repo,
        created_at=now - timedelta(hours=60),
        expires_at=now + timedelta(hours=12),
    )

    section = _build_handoff_status_context(str(repo))

    assert "**STALE**" in section
    assert WARNING in section


def test_fresh_handoff_renders_active_without_warning(tmp_path):
    now = datetime.now(timezone.utc)
    repo = tmp_path / "repo"
    _write_handoff(
        repo,
        created_at=now - timedelta(hours=2),
        expires_at=now + timedelta(hours=12),
    )

    section = _build_handoff_status_context(str(repo))

    assert "**ACTIVE**" in section
    assert WARNING not in section


def test_expired_handoff_renders_expired_and_warning(tmp_path):
    now = datetime.now(timezone.utc)
    repo = tmp_path / "repo"
    _write_handoff(
        repo,
        created_at=now - timedelta(hours=2),
        expires_at=now - timedelta(minutes=1),
    )

    section = _build_handoff_status_context(str(repo))

    assert "**EXPIRED**" in section
    assert WARNING in section


def test_no_handoff_renders_empty(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    assert _build_handoff_status_context(str(repo)) == ""
