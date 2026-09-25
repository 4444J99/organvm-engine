"""Tests for multi-agent session discovery and parsing."""

import json
from datetime import datetime, timezone
from pathlib import Path

from organvm_engine.session.agents import (
    AgentSession,
    UnreadableSession,
    _human_size,
    _parse_iso,
    codex_archived_dir,
    codex_home_dir,
    codex_sessions_dir,
    discover_all_sessions,
    discover_claude_sessions,
    discover_codex_sessions,
    discover_gemini_sessions,
)
from organvm_engine.session.parser import (
    detect_agent,
    parse_any_session,
    parse_codex_session,
    parse_gemini_session,
    render_any_transcript,
    render_codex_transcript,
    render_gemini_prompts,
    render_gemini_transcript,
)

# ── Fixtures ───────────────────────────────────────────────────────


def _claude_jsonl(tmp_path: Path, name: str = "abc123.jsonl") -> Path:
    """Create a minimal Claude session JSONL."""
    f = tmp_path / name
    entries = [
        {"type": "user", "sessionId": "abc123", "slug": "test", "cwd": "/test",
         "gitBranch": "main", "timestamp": "2026-03-06T10:00:00Z",
         "message": {"role": "user", "content": "hello"}},
        {"type": "assistant", "sessionId": "abc123", "slug": "test", "cwd": "/test",
         "gitBranch": "main", "timestamp": "2026-03-06T10:05:00Z",
         "message": {"role": "assistant", "content": [{"type": "text", "text": "hi"}]}},
    ]
    with f.open("w") as fh:
        for e in entries:
            fh.write(json.dumps(e) + "\n")
    return f


def _gemini_json(tmp_path: Path, name: str = "session-2026-03-06T10-00-abc123.json") -> Path:
    """Create a minimal Gemini session JSON."""
    chats_dir = tmp_path / "chats"
    chats_dir.mkdir(parents=True, exist_ok=True)
    f = chats_dir / name
    data = {
        "sessionId": "abc123-gemini",
        "projectHash": "deadbeef",
        "startTime": "2026-03-06T10:00:00.000Z",
        "lastUpdated": "2026-03-06T11:00:00.000Z",
        "messages": [
            {"id": "m1", "timestamp": "2026-03-06T10:00:05Z", "type": "user",
             "content": "Build me a thing"},
            {"id": "m2", "timestamp": "2026-03-06T10:00:10Z", "type": "gemini",
             "content": "I will build it.",
             "thoughts": [{"subject": "Planning", "description": "Analyzing the request",
                           "timestamp": "2026-03-06T10:00:08Z"}],
             "toolCalls": [{"id": "read_1", "name": "read_file",
                            "args": {"path": "/foo.py"},
                            "result": [{"functionResponse": {"id": "read_1", "name": "read_file",
                                        "response": {"output": "file contents here"}}}]}],
             "tokens": {"input": 1000, "output": 50, "cached": 0, "thoughts": 100, "tool": 0, "total": 1150}},
            {"id": "m3", "timestamp": "2026-03-06T10:05:00Z", "type": "user",
             "content": "Now fix the bug"},
            {"id": "m4", "timestamp": "2026-03-06T10:05:30Z", "type": "gemini",
             "content": "Bug fixed."},
        ],
        "kind": "chat",
    }
    f.write_text(json.dumps(data), encoding="utf-8")
    return f


def _codex_jsonl(tmp_path: Path, name: str = "rollout-2026-03-06T10-00-00-abc123.jsonl") -> Path:
    """Create a minimal Codex session JSONL."""
    f = tmp_path / name
    entries = [
        {"timestamp": "2026-03-06T10:00:00Z", "type": "session_meta",
         "payload": {"id": "abc123-codex", "cwd": "/Users/test/project",
                     "timestamp": "2026-03-06T10:00:00Z", "cli_version": "0.111.0",
                     "originator": "codex_cli_rs", "source": "cli", "model_provider": "openai",
                     "base_instructions": {"text": "You are Codex."}}},
        {"timestamp": "2026-03-06T10:01:00Z", "type": "response_item",
         "payload": {"role": "user", "type": "message",
                     "content": [{"type": "input_text", "text": "Search for the timeline concept"}]}},
        {"timestamp": "2026-03-06T10:01:30Z", "type": "response_item",
         "payload": {"role": "assistant", "type": "message",
                     "content": [{"type": "output_text", "text": "I found the timeline."}]}},
        {"timestamp": "2026-03-06T10:02:00Z", "type": "response_item",
         "payload": {"type": "function_call", "name": "exec_command",
                     "arguments": '{"cmd":"rg timeline"}', "call_id": "call_123"}},
        {"timestamp": "2026-03-06T10:02:05Z", "type": "response_item",
         "payload": {"type": "function_call_output", "output": "match on line 42",
                     "call_id": "call_123"}},
        {"timestamp": "2026-03-06T10:03:00Z", "type": "response_item",
         "payload": {"type": "reasoning", "content": None,
                     "encrypted_content": "encrypted-data-here", "summary": []}},
    ]
    with f.open("w") as fh:
        for e in entries:
            fh.write(json.dumps(e) + "\n")
    return f


# ── Agent detection ────────────────────────────────────────────────


class TestDetectAgent:
    def test_claude_path(self, tmp_path):
        p = Path("/Users/x/.claude/projects/proj/abc.jsonl")
        assert detect_agent(p) == "claude"

    def test_gemini_path(self, tmp_path):
        p = Path("/Users/x/.gemini/tmp/proj/chats/session-abc.json")
        assert detect_agent(p) == "gemini"

    def test_codex_path(self, tmp_path):
        p = Path("/Users/x/.codex/sessions/2026/03/rollout-abc.jsonl")
        assert detect_agent(p) == "codex"

    def test_json_fallback(self, tmp_path):
        p = tmp_path / "unknown.json"
        assert detect_agent(p) == "gemini"

    def test_jsonl_fallback(self, tmp_path):
        p = tmp_path / "unknown.jsonl"
        assert detect_agent(p) == "claude"


# ── Gemini parsing ─────────────────────────────────────────────────


class TestGeminiParsing:
    def test_parse_session(self, tmp_path):
        f = _gemini_json(tmp_path)
        meta = parse_gemini_session(f)
        assert meta is not None
        assert meta.session_id == "abc123-gemini"
        assert meta.human_messages == 2
        assert meta.assistant_messages == 2
        assert "read_file" in meta.tools_used
        assert meta.first_human_message == "Build me a thing"

    def test_transcript_summary(self, tmp_path):
        f = _gemini_json(tmp_path)
        content = render_gemini_transcript(f, unabridged=False)
        assert "Gemini" in content
        assert "Build me a thing" in content
        assert "Bug fixed." in content
        # Summary mode: no thinking, no tool results
        assert "### Thinking" not in content

    def test_transcript_unabridged(self, tmp_path):
        f = _gemini_json(tmp_path)
        content = render_gemini_transcript(f, unabridged=True)
        assert "### Thinking" in content
        assert "Planning" in content
        assert "file contents here" in content
        assert "Tokens:" in content

    def test_prompts(self, tmp_path):
        f = _gemini_json(tmp_path)
        content = render_gemini_prompts(f)
        assert "### P1" in content
        assert "### P2" in content
        assert "Build me a thing" in content
        assert "Now fix the bug" in content

    def test_nonexistent(self, tmp_path):
        assert parse_gemini_session(tmp_path / "nope.json") is None
        assert render_gemini_transcript(tmp_path / "nope.json") == ""

    def test_empty_messages(self, tmp_path):
        f = tmp_path / "empty.json"
        f.write_text('{"messages": []}')
        assert parse_gemini_session(f) is None


# ── Codex parsing ──────────────────────────────────────────────────


class TestCodexParsing:
    def test_parse_session(self, tmp_path):
        f = _codex_jsonl(tmp_path)
        meta = parse_codex_session(f)
        assert meta is not None
        assert meta.session_id == "abc123-codex"
        assert meta.cwd == "/Users/test/project"
        assert meta.human_messages == 1
        assert meta.assistant_messages == 1
        assert "exec_command" in meta.tools_used

    def test_transcript_summary(self, tmp_path):
        f = _codex_jsonl(tmp_path)
        content = render_codex_transcript(f, unabridged=False)
        assert "Codex" in content
        assert "Search for the timeline concept" in content
        assert "I found the timeline." in content

    def test_transcript_unabridged(self, tmp_path):
        f = _codex_jsonl(tmp_path)
        content = render_codex_transcript(f, unabridged=True)
        assert "Tool Call" in content
        assert "exec_command" in content
        assert "match on line 42" in content
        assert "Reasoning" in content
        assert "encrypted" in content

    def test_nonexistent(self, tmp_path):
        assert parse_codex_session(tmp_path / "nope.jsonl") is None


# ── Multi-agent dispatch ───────────────────────────────────────────


class TestMultiAgentDispatch:
    def test_parse_any_claude(self, tmp_path):
        proj = tmp_path / ".claude" / "projects" / "proj"
        proj.mkdir(parents=True)
        f = _claude_jsonl(proj)
        meta = parse_any_session(f)
        assert meta is not None
        assert meta.session_id == "abc123"

    def test_parse_any_gemini(self, tmp_path):
        proj = tmp_path / ".gemini" / "tmp" / "proj"
        proj.mkdir(parents=True)
        f = _gemini_json(proj)
        meta = parse_any_session(f)
        assert meta is not None
        assert meta.session_id == "abc123-gemini"

    def test_parse_any_codex(self, tmp_path):
        proj = tmp_path / ".codex" / "sessions"
        proj.mkdir(parents=True)
        f = _codex_jsonl(proj)
        meta = parse_any_session(f)
        assert meta is not None
        assert meta.session_id == "abc123-codex"

    def test_render_any_claude(self, tmp_path):
        proj = tmp_path / ".claude" / "projects" / "proj"
        proj.mkdir(parents=True)
        f = _claude_jsonl(proj)
        content = render_any_transcript(f)
        assert "Human" in content

    def test_render_any_gemini(self, tmp_path):
        proj = tmp_path / ".gemini" / "tmp" / "proj"
        proj.mkdir(parents=True)
        f = _gemini_json(proj)
        content = render_any_transcript(f)
        assert "Gemini" in content

    def test_render_any_codex(self, tmp_path):
        proj = tmp_path / ".codex" / "sessions"
        proj.mkdir(parents=True)
        f = _codex_jsonl(proj)
        content = render_any_transcript(f)
        assert "Codex" in content


# ── Discovery ──────────────────────────────────────────────────────


class TestDiscovery:
    def test_claude_discovery(self, tmp_path, monkeypatch):
        monkeypatch.setattr("organvm_engine.session.agents.CLAUDE_PROJECTS_DIR", tmp_path)
        proj = tmp_path / "proj"
        proj.mkdir()
        _claude_jsonl(proj)

        sessions = discover_claude_sessions()
        assert len(sessions) == 1
        assert sessions[0].agent == "claude"

    def test_gemini_discovery(self, tmp_path, monkeypatch):
        monkeypatch.setattr("organvm_engine.session.agents.GEMINI_TMP_DIR", tmp_path)
        proj = tmp_path / "portfolio"
        proj.mkdir()
        _gemini_json(proj)

        sessions = discover_gemini_sessions()
        assert len(sessions) == 1
        assert sessions[0].agent == "gemini"

    def test_gemini_discovery_validates_entire_jsonl(self, tmp_path, monkeypatch):
        monkeypatch.setattr("organvm_engine.session.agents.GEMINI_TMP_DIR", tmp_path)
        chats_dir = tmp_path / "portfolio" / "chats"
        chats_dir.mkdir(parents=True)
        session_file = chats_dir / "session-corrupt.jsonl"
        header = (
            b'{"sessionId":"gemini-corrupt",'
            b'"startTime":"2026-03-06T10:00:00Z"}\n'
        )
        valid_events = b"{}\n" * 7_000
        invalid_offset = len(header) + len(valid_events)
        session_file.write_bytes(header + valid_events + b"\x8d\n")
        diagnostics = []

        sessions = discover_gemini_sessions(diagnostics=diagnostics)

        assert sessions == []
        assert len(diagnostics) == 1
        assert diagnostics[0].agent == "gemini"
        assert diagnostics[0].byte_offset == invalid_offset

    def test_codex_discovery(self, tmp_path, monkeypatch):
        monkeypatch.setattr("organvm_engine.session.agents.CODEX_SESSIONS_DIR", tmp_path)
        monkeypatch.setattr("organvm_engine.session.agents.CODEX_ARCHIVED_DIR", tmp_path / "archived")
        _codex_jsonl(tmp_path)

        sessions = discover_codex_sessions()
        assert len(sessions) == 1
        assert sessions[0].agent == "codex"

    def test_codex_filters_before_recording_decode_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr("organvm_engine.session.agents.CODEX_SESSIONS_DIR", tmp_path)
        monkeypatch.setattr(
            "organvm_engine.session.agents.CODEX_ARCHIVED_DIR",
            tmp_path / "archived",
        )
        session_file = tmp_path / "rollout-corrupt.jsonl"
        meta = {
            "timestamp": "2026-03-06T10:00:00Z",
            "type": "session_meta",
            "payload": {
                "id": "codex-corrupt",
                "cwd": "/Users/test/other",
                "timestamp": "2026-03-06T10:00:00Z",
            },
        }
        header = (json.dumps(meta) + "\n").encode()
        valid_events = b"{}\n" * 7_000
        invalid_offset = len(header) + len(valid_events)
        session_file.write_bytes(header + valid_events + b"\x8d\n")
        unrelated_diagnostics = []

        sessions = discover_codex_sessions(
            project_filter="target",
            diagnostics=unrelated_diagnostics,
        )

        assert sessions == []
        assert unrelated_diagnostics == []

        matching_diagnostics = []
        sessions = discover_codex_sessions(
            project_filter="other",
            diagnostics=matching_diagnostics,
        )

        assert sessions == []
        assert len(matching_diagnostics) == 1
        assert matching_diagnostics[0].byte_offset == invalid_offset

    def test_codex_recovers_cwd_when_following_bytes_are_invalid(
        self,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.setattr("organvm_engine.session.agents.CODEX_SESSIONS_DIR", tmp_path)
        monkeypatch.setattr(
            "organvm_engine.session.agents.CODEX_ARCHIVED_DIR",
            tmp_path / "archived",
        )
        session_file = tmp_path / "rollout-corrupt.jsonl"
        meta = {
            "timestamp": "2026-03-06T10:00:00Z",
            "type": "session_meta",
            "payload": {
                "id": "codex-corrupt",
                "cwd": "/Users/test/other",
                "timestamp": "2026-03-06T10:00:00Z",
            },
        }
        header = (json.dumps(meta) + "\n").encode()
        session_file.write_bytes(header + b"\x8d\n")

        unrelated_diagnostics = []
        sessions = discover_codex_sessions(
            project_filter="target",
            diagnostics=unrelated_diagnostics,
        )

        assert sessions == []
        assert unrelated_diagnostics == []

        matching_diagnostics = []
        sessions = discover_codex_sessions(
            project_filter="other",
            diagnostics=matching_diagnostics,
        )

        assert sessions == []
        assert len(matching_diagnostics) == 1
        assert matching_diagnostics[0].byte_offset == len(header)

    def test_unreadable_offset_scan_does_not_load_entire_file(
        self,
        tmp_path,
        monkeypatch,
    ):
        session_file = tmp_path / "corrupt.jsonl"
        valid_prefix = b"{}\n" * 50_000
        session_file.write_bytes(valid_prefix + b"\x8d\n")
        try:
            session_file.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            decode_error = exc
        else:  # pragma: no cover - the fixture is deliberately invalid
            raise AssertionError("fixture unexpectedly decoded")

        def fail_read_bytes(_self):
            raise AssertionError("offset scan must not call Path.read_bytes")

        monkeypatch.setattr(Path, "read_bytes", fail_read_bytes)

        diagnostic = UnreadableSession.from_decode_error(
            "codex",
            session_file,
            decode_error,
        )

        assert diagnostic.byte_offset == len(valid_prefix)

    def test_discover_all(self, tmp_path, monkeypatch):
        # Claude
        claude_dir = tmp_path / "claude"
        claude_dir.mkdir()
        claude_proj = claude_dir / "proj"
        claude_proj.mkdir()
        _claude_jsonl(claude_proj)
        monkeypatch.setattr("organvm_engine.session.agents.CLAUDE_PROJECTS_DIR", claude_dir)

        # Gemini
        gemini_dir = tmp_path / "gemini"
        gemini_dir.mkdir()
        gemini_proj = gemini_dir / "portfolio"
        gemini_proj.mkdir()
        _gemini_json(gemini_proj)
        monkeypatch.setattr("organvm_engine.session.agents.GEMINI_TMP_DIR", gemini_dir)

        # Codex
        codex_dir = tmp_path / "codex"
        codex_dir.mkdir()
        _codex_jsonl(codex_dir)
        monkeypatch.setattr("organvm_engine.session.agents.CODEX_SESSIONS_DIR", codex_dir)
        monkeypatch.setattr("organvm_engine.session.agents.CODEX_ARCHIVED_DIR", tmp_path / "archived")

        # OpenCode (stub a missing DB so the adapter returns []).
        monkeypatch.setattr(
            "organvm_engine.session.agents.OPENCODE_DB", tmp_path / "opencode.db",
        )

        sessions = discover_all_sessions()
        assert len(sessions) == 3
        agents = {s.agent for s in sessions}
        assert agents == {"claude", "gemini", "codex"}

    def test_discover_with_agent_filter(self, tmp_path, monkeypatch):
        claude_dir = tmp_path / "claude"
        claude_dir.mkdir()
        proj = claude_dir / "proj"
        proj.mkdir()
        _claude_jsonl(proj)
        monkeypatch.setattr("organvm_engine.session.agents.CLAUDE_PROJECTS_DIR", claude_dir)
        monkeypatch.setattr("organvm_engine.session.agents.GEMINI_TMP_DIR", tmp_path / "no-gemini")
        monkeypatch.setattr("organvm_engine.session.agents.CODEX_SESSIONS_DIR", tmp_path / "no-codex")
        monkeypatch.setattr("organvm_engine.session.agents.CODEX_ARCHIVED_DIR", tmp_path / "no-archive")

        sessions = discover_all_sessions(agent="claude")
        assert len(sessions) == 1
        assert sessions[0].agent == "claude"

        sessions = discover_all_sessions(agent="gemini")
        assert len(sessions) == 0

    def test_nonexistent_dirs(self, tmp_path, monkeypatch):
        monkeypatch.setattr("organvm_engine.session.agents.CLAUDE_PROJECTS_DIR", tmp_path / "nope")
        monkeypatch.setattr("organvm_engine.session.agents.GEMINI_TMP_DIR", tmp_path / "nope2")
        monkeypatch.setattr("organvm_engine.session.agents.CODEX_SESSIONS_DIR", tmp_path / "nope3")
        monkeypatch.setattr("organvm_engine.session.agents.CODEX_ARCHIVED_DIR", tmp_path / "nope4")
        monkeypatch.setattr("organvm_engine.session.agents.OPENCODE_DB", tmp_path / "nope5.db")

        assert discover_all_sessions() == []


# ── Relocated CODEX_HOME ───────────────────────────────────────────


class TestCodexRelocatedHome:
    def test_relocated_codex_home_discovery(self, tmp_path, monkeypatch):
        relocated = tmp_path / "custom_codex"
        active_dir = relocated / "sessions" / "2026" / "09" / "16"
        archived_dir = relocated / "archived_sessions"
        active_dir.mkdir(parents=True)
        archived_dir.mkdir(parents=True)

        _codex_jsonl(active_dir, "rollout-2026-09-16T10-00-00-active.jsonl")
        _codex_jsonl(archived_dir, "rollout-2026-09-15T10-00-00-archived.jsonl")

        monkeypatch.setenv("CODEX_HOME", str(relocated))

        assert codex_home_dir() == relocated
        assert codex_sessions_dir() == relocated / "sessions"
        assert codex_archived_dir() == relocated / "archived_sessions"

        sessions = discover_codex_sessions()
        assert len(sessions) == 2
        ids = {s.session_id for s in sessions}
        assert "abc123-codex" in ids

        active_file = next(active_dir.glob("*.jsonl"))
        assert detect_agent(active_file) == "codex"

    def test_codex_home_fallback_when_unset_or_empty(self, monkeypatch):
        monkeypatch.delenv("CODEX_HOME", raising=False)
        assert codex_home_dir() == Path.home() / ".codex"
        assert codex_sessions_dir() == Path.home() / ".codex" / "sessions"
        assert codex_archived_dir() == Path.home() / ".codex" / "archived_sessions"

        monkeypatch.setenv("CODEX_HOME", "   ")
        assert codex_home_dir() == Path.home() / ".codex"
        assert codex_sessions_dir() == Path.home() / ".codex" / "sessions"
        assert codex_archived_dir() == Path.home() / ".codex" / "archived_sessions"


# ── Helpers ────────────────────────────────────────────────────────


class TestHelpers:
    def test_parse_iso(self):
        ts = _parse_iso("2026-03-06T10:00:00Z")
        assert ts == datetime(2026, 3, 6, 10, 0, tzinfo=timezone.utc)

    def test_parse_iso_none(self):
        assert _parse_iso(None) is None
        assert _parse_iso("") is None

    def test_human_size(self):
        assert _human_size(500) == "500B"
        assert _human_size(2048) == "2KB"
        assert _human_size(1_500_000) == "1.4MB"
        assert _human_size(2_000_000_000) == "1.9GB"

    def test_agent_session_properties(self):
        s = AgentSession(
            agent="claude", session_id="abc", file_path=Path("/test"),
            project_dir="/proj", started=datetime(2026, 3, 6, 10, 0, tzinfo=timezone.utc),
            ended=datetime(2026, 3, 6, 11, 30, tzinfo=timezone.utc), size_bytes=1_500_000,
        )
        assert s.date_str == "2026-03-06"
        assert s.duration_minutes == 90
        assert s.size_human == "1.4MB"

    def test_agent_session_no_times(self):
        s = AgentSession(
            agent="gemini", session_id="x", file_path=Path("/test"),
            project_dir="/proj", started=None, ended=None, size_bytes=500,
        )
        assert s.date_str == "unknown"
        assert s.duration_minutes is None
        assert s.size_human == "500B"
