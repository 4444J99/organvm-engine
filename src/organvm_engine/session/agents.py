"""Multi-agent session discovery and parsing.

Supports Claude Code, Gemini CLI, Codex, and OpenCode session formats.
All four are normalized to a common SessionMeta + rendering pipeline.
"""

from __future__ import annotations

import codecs
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# ── Storage locations ──────────────────────────────────────────────

CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
GEMINI_TMP_DIR = Path.home() / ".gemini" / "tmp"
GEMINI_PROJECTS_JSON = Path.home() / ".local" / "share" / "gemini" / "projects.json"
CODEX_SESSIONS_DIR = Path.home() / ".codex" / "sessions"
CODEX_ARCHIVED_DIR = Path.home() / ".codex" / "archived_sessions"
OPENCODE_DB = Path.home() / ".local" / "share" / "opencode" / "opencode.db"


def codex_home_dir() -> Path:
    """Return resolved Codex root directory, honoring CODEX_HOME if set."""
    val = os.environ.get("CODEX_HOME", "").strip()
    if val:
        return Path(val).expanduser()
    return Path.home() / ".codex"


def codex_sessions_dir() -> Path:
    """Return active Codex sessions directory."""
    val = os.environ.get("CODEX_HOME", "").strip()
    if val:
        return Path(val).expanduser() / "sessions"
    return CODEX_SESSIONS_DIR


def codex_archived_dir() -> Path:
    """Return archived Codex sessions directory."""
    val = os.environ.get("CODEX_HOME", "").strip()
    if val:
        return Path(val).expanduser() / "archived_sessions"
    return CODEX_ARCHIVED_DIR

_UTF8_SCAN_CHUNK_BYTES = 64 * 1024
_CODEX_META_LINE_LIMIT_BYTES = 1024 * 1024


# ── Agent enum ─────────────────────────────────────────────────────

AGENTS = ("claude", "gemini", "codex", "opencode")


@dataclass
class AgentSession:
    """Unified session descriptor across all agents."""

    agent: str  # claude | gemini | codex
    session_id: str
    file_path: Path
    project_dir: str  # decoded project path or best guess
    started: datetime | None
    ended: datetime | None
    size_bytes: int

    @property
    def date_str(self) -> str:
        if self.started:
            return self.started.strftime("%Y-%m-%d")
        return "unknown"

    @property
    def duration_minutes(self) -> int | None:
        if self.started and self.ended:
            delta = self.ended - self.started
            return int(delta.total_seconds() / 60)
        return None

    @property
    def size_human(self) -> str:
        if self.size_bytes >= 1_048_576:
            return f"{self.size_bytes / 1_048_576:.1f}MB"
        if self.size_bytes >= 1024:
            return f"{self.size_bytes / 1024:.0f}KB"
        return f"{self.size_bytes}B"


@dataclass(frozen=True)
class UnreadableSession:
    """Actionable diagnostic for a session file that is not valid UTF-8."""

    agent: str
    file_path: Path
    byte_offset: int

    @classmethod
    def from_decode_error(
        cls,
        agent: str,
        file_path: Path,
        exc: UnicodeDecodeError,
    ) -> UnreadableSession:
        """Build a diagnostic with an absolute byte offset."""
        return cls(agent, file_path, _absolute_utf8_error_offset(file_path, exc.start))

    def to_dict(self) -> dict[str, str | int]:
        """Return a stable CLI-facing representation of the diagnostic."""
        return {
            "status": "unreadable-session",
            "agent": self.agent,
            "file": str(self.file_path),
            "reason": f"non-UTF-8 input at byte {self.byte_offset}",
            "action": "Re-encode the file as UTF-8 or remove it from the session corpus.",
        }


def _absolute_utf8_error_offset(file_path: Path, fallback: int) -> int:
    """Locate the first invalid UTF-8 byte with bounded memory use."""
    decoder = codecs.getincrementaldecoder("utf-8")()
    consumed = 0
    try:
        with file_path.open("rb") as stream:
            while chunk := stream.read(_UTF8_SCAN_CHUNK_BYTES):
                buffered = len(decoder.getstate()[0])
                try:
                    decoder.decode(chunk, final=False)
                except UnicodeDecodeError as exc:
                    return consumed - buffered + exc.start
                consumed += len(chunk)

            buffered = len(decoder.getstate()[0])
            try:
                decoder.decode(b"", final=True)
            except UnicodeDecodeError as exc:
                return consumed - buffered + exc.start
    except OSError:
        pass
    return fallback


def _record_decode_error(
    diagnostics: list[UnreadableSession] | None,
    agent: str,
    file_path: Path,
    exc: UnicodeDecodeError,
) -> None:
    """Record a decode failure when the caller requested discovery diagnostics."""
    if diagnostics is not None:
        diagnostics.append(UnreadableSession.from_decode_error(agent, file_path, exc))


# ── Discovery ──────────────────────────────────────────────────────


def discover_claude_sessions(
    project_filter: str | None = None,
    directory_filter: str | None = None,
    *,
    diagnostics: list[UnreadableSession] | None = None,
) -> list[AgentSession]:
    """Find all Claude Code sessions.

    ``directory_filter`` matches the decoded cwd exactly (not a substring of
    project-dir name), so paths like ``/Users/4jp/Code/_agent`` do not
    false-positive against scopes whose name contains ``agent``.
    """
    if not CLAUDE_PROJECTS_DIR.exists():
        return []

    results = []
    for proj_dir in CLAUDE_PROJECTS_DIR.iterdir():
        if not proj_dir.is_dir():
            continue
        if project_filter and project_filter not in proj_dir.name:
            continue

        # Read actual cwd from first session file
        decoded_path = _read_cwd_from_claude_project(proj_dir)

        if directory_filter and decoded_path != directory_filter:
            continue

        for jsonl in proj_dir.glob("*.jsonl"):
            meta = _quick_parse_claude(jsonl, decoded_path, diagnostics=diagnostics)
            if meta:
                results.append(meta)

    return results


def discover_gemini_sessions(
    project_filter: str | None = None,
    directory_filter: str | None = None,
    *,
    diagnostics: list[UnreadableSession] | None = None,
) -> list[AgentSession]:
    """Find all Gemini CLI sessions.

    Gemini's per-project slug is a hash of the working directory; to filter
    by exact directory we reverse-lookup the slug via ``projects.json``.
    Globs both ``session-*.json`` (older format) and ``session-*.jsonl``
    (current format) — both extensions are present in active chats dirs.
    """
    if not GEMINI_TMP_DIR.exists():
        return []

    target_slug: str | None = None
    if directory_filter:
        target_slug = _gemini_slug_for_directory(directory_filter)
        if target_slug is None:
            return []

    results = []
    for proj_dir in GEMINI_TMP_DIR.iterdir():
        if not proj_dir.is_dir():
            continue
        chats_dir = proj_dir / "chats"
        if not chats_dir.is_dir():
            continue
        if project_filter and project_filter not in proj_dir.name:
            continue
        if target_slug is not None and proj_dir.name != target_slug:
            continue

        for pattern in ("session-*.json", "session-*.jsonl"):
            for session_file in chats_dir.glob(pattern):
                meta = _quick_parse_gemini(
                    session_file,
                    proj_dir.name,
                    diagnostics=diagnostics,
                )
                if meta:
                    results.append(meta)

    return results


def _gemini_slug_for_directory(directory: str) -> str | None:
    """Reverse-lookup the Gemini slug for an absolute working directory."""
    if not GEMINI_PROJECTS_JSON.exists():
        return None
    try:
        with GEMINI_PROJECTS_JSON.open(encoding="utf-8") as f:
            mapping = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    projects = mapping.get("projects", mapping)
    return projects.get(directory)


def discover_codex_sessions(
    project_filter: str | None = None,
    directory_filter: str | None = None,
    *,
    diagnostics: list[UnreadableSession] | None = None,
) -> list[AgentSession]:
    """Find all Codex sessions (active + archived)."""
    results = []

    sessions_dir = codex_sessions_dir()
    archived_dir = codex_archived_dir()

    # Active sessions: <CODEX_HOME>/sessions/YYYY/MM/DD/rollout-*.jsonl
    if sessions_dir.exists():
        for jsonl in sessions_dir.rglob("rollout-*.jsonl"):
            meta = _quick_parse_codex(
                jsonl,
                project_filter,
                directory_filter,
                diagnostics=diagnostics,
            )
            if meta:
                results.append(meta)

    # Archived: <CODEX_HOME>/archived_sessions/rollout-*.jsonl
    if archived_dir.exists():
        for jsonl in archived_dir.rglob("rollout-*.jsonl"):
            meta = _quick_parse_codex(
                jsonl,
                project_filter,
                directory_filter,
                diagnostics=diagnostics,
            )
            if meta:
                results.append(meta)

    return results


def discover_opencode_sessions(
    project_filter: str | None = None,
    directory_filter: str | None = None,
) -> list[AgentSession]:
    """Find all OpenCode sessions via the local SQLite store.

    OpenCode is keyed by ``session.directory`` (the worktree absolute path),
    so ``directory_filter`` is an exact match. ``project_filter`` is treated
    as a substring against ``directory``.
    """
    if not OPENCODE_DB.exists():
        return []

    where = []
    params: list[str] = []
    if directory_filter:
        where.append("directory = ?")
        params.append(directory_filter)
    elif project_filter:
        where.append("directory LIKE ?")
        params.append(f"%{project_filter}%")
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    query = (
        "SELECT id, COALESCE(title, ''), directory, "
        "time_created, time_updated "
        f"FROM session {clause} ORDER BY time_updated DESC"
    )

    results: list[AgentSession] = []
    try:
        # Read-only connection — OpenCode may have the DB open in WAL mode.
        uri = f"file:{OPENCODE_DB}?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=1.0) as con:
            cur = con.execute(query, params)
            rows = cur.fetchall()
    except sqlite3.Error:
        return []

    for sid, _title, directory, t_created, t_updated in rows:
        started = _epoch_ms_to_dt(t_created)
        ended = _epoch_ms_to_dt(t_updated)
        # OpenCode does not expose per-session file paths; the DB itself is
        # the canonical location.
        results.append(
            AgentSession(
                agent="opencode",
                session_id=sid,
                file_path=OPENCODE_DB,
                project_dir=directory,
                started=started,
                ended=ended,
                size_bytes=0,
            ),
        )
    return results


def _epoch_ms_to_dt(value: int | float | None) -> datetime | None:
    """Convert an OpenCode millisecond epoch to a tz-aware datetime."""
    if not value:
        return None
    try:
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    except (OSError, ValueError, TypeError):
        return None


def discover_all_sessions(
    agent: str | None = None,
    project_filter: str | None = None,
    directory_filter: str | None = None,
    *,
    diagnostics: list[UnreadableSession] | None = None,
) -> list[AgentSession]:
    """Discover sessions across all agents, sorted newest first."""
    results: list[AgentSession] = []

    if agent is None or agent == "claude":
        results.extend(
            discover_claude_sessions(
                project_filter,
                directory_filter,
                diagnostics=diagnostics,
            ),
        )
    if agent is None or agent == "gemini":
        results.extend(
            discover_gemini_sessions(
                project_filter,
                directory_filter,
                diagnostics=diagnostics,
            ),
        )
    if agent is None or agent == "codex":
        results.extend(
            discover_codex_sessions(
                project_filter,
                directory_filter,
                diagnostics=diagnostics,
            ),
        )
    if agent is None or agent == "opencode":
        results.extend(discover_opencode_sessions(project_filter, directory_filter))

    results.sort(
        key=lambda s: s.started or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return results


# ── Quick parsers (metadata only, no full content scan) ────────────


def _read_cwd_from_claude_project(proj_dir: Path) -> str:
    """Read actual cwd from the first Claude session file."""
    for jsonl in proj_dir.glob("*.jsonl"):
        try:
            with jsonl.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                        cwd = msg.get("cwd")
                        if cwd:
                            return cwd
                    except json.JSONDecodeError:
                        continue
        except (OSError, UnicodeDecodeError):
            continue
    return proj_dir.name


def _quick_parse_claude(
    jsonl_path: Path,
    project_dir: str,
    *,
    diagnostics: list[UnreadableSession] | None = None,
) -> AgentSession | None:
    """Extract minimal metadata from a Claude JSONL without full parse."""
    try:
        size = jsonl_path.stat().st_size
    except OSError:
        return None

    timestamps: list[datetime] = []
    try:
        with jsonl_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts_str = msg.get("timestamp")
                if ts_str:
                    try:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        timestamps.append(ts)
                    except (ValueError, TypeError):
                        pass
                # Only need first and last — stop scanning after we have a few
                # but we need to reach the end for the last timestamp
    except UnicodeDecodeError as exc:
        _record_decode_error(diagnostics, "claude", jsonl_path, exc)
        return None
    except OSError:
        return None

    if not timestamps:
        return None

    return AgentSession(
        agent="claude",
        session_id=jsonl_path.stem,
        file_path=jsonl_path,
        project_dir=project_dir,
        started=min(timestamps),
        ended=max(timestamps),
        size_bytes=size,
    )


def _quick_parse_gemini(
    session_file: Path,
    project_slug: str,
    *,
    diagnostics: list[UnreadableSession] | None = None,
) -> AgentSession | None:
    """Extract minimal metadata from a Gemini session file.

    Gemini ships two on-disk formats:
      * ``.json`` (older) — a single JSON object per file
      * ``.jsonl`` (current) — first line is the session header object,
        subsequent lines are individual events

    Both have ``sessionId`` / ``startTime`` / ``lastUpdated`` on the
    first JSON object.
    """
    try:
        size = session_file.stat().st_size
    except OSError:
        return None

    try:
        with session_file.open(encoding="utf-8") as f:
            if session_file.suffix == ".jsonl":
                first_line = f.readline().strip()
                if not first_line:
                    return None
                data = json.loads(first_line)
                for _line in f:
                    pass
            else:
                data = json.load(f)
    except UnicodeDecodeError as exc:
        _record_decode_error(diagnostics, "gemini", session_file, exc)
        return None
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(data, dict):
        return None

    session_id = data.get("sessionId", session_file.stem)
    start_str = data.get("startTime")
    end_str = data.get("lastUpdated")

    started = _parse_iso(start_str)
    ended = _parse_iso(end_str)

    return AgentSession(
        agent="gemini",
        session_id=session_id,
        file_path=session_file,
        project_dir=project_slug,
        started=started,
        ended=ended,
        size_bytes=size,
    )


def _quick_parse_codex(
    jsonl_path: Path,
    project_filter: str | None,
    directory_filter: str | None = None,
    *,
    diagnostics: list[UnreadableSession] | None = None,
) -> AgentSession | None:
    """Extract minimal metadata from a Codex rollout JSONL."""
    try:
        size = jsonl_path.stat().st_size
    except OSError:
        return None

    session_id = ""
    cwd = ""
    started: datetime | None = None
    timestamps: list[datetime] = []

    try:
        with jsonl_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                ts_str = entry.get("timestamp")
                if ts_str:
                    ts = _parse_iso(ts_str)
                    if ts:
                        timestamps.append(ts)

                if entry.get("type") == "session_meta":
                    payload = entry.get("payload", {})
                    session_id = payload.get("id", jsonl_path.stem)
                    cwd = payload.get("cwd", "")
                    ts_str2 = payload.get("timestamp")
                    if ts_str2:
                        started = _parse_iso(ts_str2)
    except UnicodeDecodeError as exc:
        if not cwd:
            cwd = _recover_codex_cwd(jsonl_path)
        if cwd and not _codex_cwd_matches_filters(
            cwd,
            project_filter,
            directory_filter,
        ):
            return None
        _record_decode_error(diagnostics, "codex", jsonl_path, exc)
        return None
    except OSError:
        return None

    if not _codex_cwd_matches_filters(cwd, project_filter, directory_filter):
        return None

    if not timestamps and not started:
        return None

    return AgentSession(
        agent="codex",
        session_id=session_id or jsonl_path.stem,
        file_path=jsonl_path,
        project_dir=cwd or jsonl_path.parent.name,
        started=started or (min(timestamps) if timestamps else None),
        ended=max(timestamps) if timestamps else None,
        size_bytes=size,
    )


def _recover_codex_cwd(jsonl_path: Path) -> str:
    """Recover a Codex cwd without text-reader look-ahead across bad bytes.

    Binary, size-limited line reads ensure a valid ``session_meta`` line can be
    decoded even when the following line contains invalid UTF-8 in the same
    buffered text read. Oversized lines are skipped with bounded memory use.
    """
    try:
        with jsonl_path.open("rb") as stream:
            while raw_line := stream.readline(_CODEX_META_LINE_LIMIT_BYTES + 1):
                if (
                    len(raw_line) > _CODEX_META_LINE_LIMIT_BYTES
                    and not raw_line.endswith(b"\n")
                ):
                    while raw_line and not raw_line.endswith(b"\n"):
                        raw_line = stream.readline(_CODEX_META_LINE_LIMIT_BYTES + 1)
                    continue
                try:
                    entry = json.loads(raw_line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if not isinstance(entry, dict):
                    continue
                if entry.get("type") != "session_meta":
                    continue
                payload = entry.get("payload", {})
                if not isinstance(payload, dict):
                    continue
                cwd = payload.get("cwd", "")
                return cwd if isinstance(cwd, str) else ""
    except OSError:
        pass
    return ""


def _codex_cwd_matches_filters(
    cwd: str,
    project_filter: str | None,
    directory_filter: str | None,
) -> bool:
    """Return whether a recovered Codex cwd belongs in the requested scope."""
    if directory_filter and cwd != directory_filter:
        return False
    return not (project_filter and project_filter not in cwd)


def _parse_iso(ts_str: str | None) -> datetime | None:
    """Parse an ISO timestamp string, tolerant of Z suffix."""
    if not ts_str:
        return None
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


# ── Summary statistics ─────────────────────────────────────────────


def agent_summary() -> dict[str, dict]:
    """Return per-agent session counts and total size."""
    summary = {}
    for agent in AGENTS:
        if agent == "claude":
            sessions = discover_claude_sessions()
        elif agent == "gemini":
            sessions = discover_gemini_sessions()
        elif agent == "codex":
            sessions = discover_codex_sessions()
        elif agent == "opencode":
            sessions = discover_opencode_sessions()
        else:
            continue

        # OpenCode AgentSession.size_bytes is 0 (no per-session file); fall
        # back to the SQLite DB size for the total-bytes column so the
        # column stays informative.
        if agent == "opencode" and sessions and OPENCODE_DB.exists():
            try:
                total_size = OPENCODE_DB.stat().st_size
            except OSError:
                total_size = 0
        else:
            total_size = sum(s.size_bytes for s in sessions)
        dates = [s.started for s in sessions if s.started]
        summary[agent] = {
            "count": len(sessions),
            "total_bytes": total_size,
            "total_human": _human_size(total_size),
            "earliest": min(dates).strftime("%Y-%m-%d") if dates else None,
            "latest": max(dates).strftime("%Y-%m-%d") if dates else None,
        }

    return summary


def _human_size(nbytes: int) -> str:
    if nbytes >= 1_073_741_824:
        return f"{nbytes / 1_073_741_824:.1f}GB"
    if nbytes >= 1_048_576:
        return f"{nbytes / 1_048_576:.1f}MB"
    if nbytes >= 1024:
        return f"{nbytes / 1024:.0f}KB"
    return f"{nbytes}B"
