"""Tests for the fail-safe testament chain emission helper."""

from __future__ import annotations

import json
from unittest.mock import patch

from organvm_engine.ledger.emit import testament_emit as _testament_emit


class TestTestamentEmitHelper:
    """_testament_emit() is fail-safe and returns event_id or None."""

    def test_emit_returns_event_id(self, tmp_path):
        chain_path = tmp_path / "chain.jsonl"
        with patch("organvm_engine.ledger.emit._CHAIN_PATH", chain_path):
            event_id = _testament_emit(
                event_type="registry.update",
                entity_uid="ent_repo_test",
                source_organ="META-ORGANVM",
                source_repo="test-repo",
                actor="test",
                payload={"field": "status", "new": "GRADUATED"},
            )
        assert event_id is not None
        assert isinstance(event_id, str)
        assert len(event_id) > 0

    def test_emit_writes_to_chain(self, tmp_path):
        chain_path = tmp_path / "chain.jsonl"
        with patch("organvm_engine.ledger.emit._CHAIN_PATH", chain_path):
            _testament_emit(
                event_type="governance.audit",
                entity_uid="",
                actor="test",
            )
        assert chain_path.is_file()
        data = json.loads(chain_path.read_text().strip())
        assert data["event_type"] == "governance.audit"
        assert data["hash"].startswith("sha256:")

    def test_emit_never_raises_on_error(self, tmp_path):
        """A file used as the parent is invalid even for a privileged process."""
        blocked_parent = tmp_path / "not-a-directory"
        blocked_parent.write_text("occupied", encoding="utf-8")
        with patch(
            "organvm_engine.ledger.emit._CHAIN_PATH",
            blocked_parent / "chain.jsonl",
        ):
            result = _testament_emit(event_type="test", entity_uid="e")
        assert result is None  # Should return None, not raise

    def test_emit_chains_events(self, tmp_path):
        chain_path = tmp_path / "chain.jsonl"
        with patch("organvm_engine.ledger.emit._CHAIN_PATH", chain_path):
            id1 = _testament_emit(event_type="test.a", entity_uid="e")
            id2 = _testament_emit(event_type="test.b", entity_uid="e")

        assert id1 is not None
        assert id2 is not None
        assert id1 != id2

        # Verify chain linking
        lines = chain_path.read_text().strip().splitlines()
        assert len(lines) == 2
        e1 = json.loads(lines[0])
        e2 = json.loads(lines[1])
        assert e2["prev_hash"] == e1["hash"]
        assert e2["sequence"] == 1

    def test_emit_with_causal_predecessor(self, tmp_path):
        chain_path = tmp_path / "chain.jsonl"
        with patch("organvm_engine.ledger.emit._CHAIN_PATH", chain_path):
            id1 = _testament_emit(event_type="cause", entity_uid="e")
            _testament_emit(
                event_type="effect",
                entity_uid="e",
                causal_predecessor=id1,
            )

        lines = chain_path.read_text().strip().splitlines()
        e2 = json.loads(lines[1])
        assert e2["causal_predecessor"] == id1

    def test_emit_default_payload_is_empty_dict(self, tmp_path):
        chain_path = tmp_path / "chain.jsonl"
        with patch("organvm_engine.ledger.emit._CHAIN_PATH", chain_path):
            _testament_emit(event_type="test", entity_uid="e")

        data = json.loads(chain_path.read_text().strip())
        assert data["payload"] == {}
