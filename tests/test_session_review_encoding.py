"""Session review must not silently promote lossy parser output."""

from unittest.mock import patch

from test_session_review import _FakeArgs, _make_test_session

from organvm_engine.cli.session import cmd_session_review
from organvm_engine.session.parser import parse_any_session


def test_review_rejects_corruption_after_valid_messages(tmp_path, capsys):
    path = _make_test_session(tmp_path)
    original = path.read_bytes()
    prefix = original + b"{}\n" * 30_000
    path.write_bytes(prefix + b"\x8d\n")
    # Recovery parsing stays deliberately tolerant; only review is strict.
    assert parse_any_session(path) is not None
    with patch("organvm_engine.cli.session.find_session", return_value=path):
        assert cmd_session_review(_FakeArgs(session_id="test-abc")) == 1
    output = capsys.readouterr().out
    assert '"status": "unreadable-session"' in output
    assert f'"reason": "non-UTF-8 input at byte {len(prefix)}"' in output
    assert "Session Review:" not in output


def test_review_accepts_valid_unicode_replacement_character(tmp_path, capsys):
    path = _make_test_session(tmp_path)
    path.write_text(path.read_text().replace("Implement the feature", "Implement \ufffd café"))
    with (
        patch("organvm_engine.cli.session.find_session", return_value=path),
        patch("organvm_engine.cli.session.discover_plans", return_value=[]),
    ):
        assert cmd_session_review(_FakeArgs(session_id="test-abc")) == 0
    assert "unreadable-session" not in capsys.readouterr().out
