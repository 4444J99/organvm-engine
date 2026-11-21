"""Tests for the testament feed export (organvm-engine #246).

The export projects the engine's hash chain into the stakeholder portal's
``TestamentEvent`` shape. The portal's ``verifyEventChain`` /
``verifyCheckpoint`` are the acceptance authority for the feed, so the
tests below re-derive their rules independently (canonical JSON + SHA-256
recomputed inline with hashlib, Merkle roots over all preceding feed
events, anchor digests via the engine's ``compute_anchor_hash``) rather
than trusting the export's own helpers. The run also cross-checks an
exported feed against the portal's actual ``testament-chain.ts`` in Node
(see the PR body) — the Python tests pin the rules; the Node run proves
the real consumer accepts the file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from unittest.mock import patch

import pytest

from organvm_engine.cli import main as cli_main
from organvm_engine.cli.ledger import (
    cmd_ledger_checkpoint,
    cmd_ledger_export_feed,
    cmd_ledger_genesis,
)
from organvm_engine.events.spine import EventSpine
from organvm_engine.ledger.anchor import compute_anchor_hash
from organvm_engine.ledger.chain import GENESIS_PREV_HASH
from organvm_engine.ledger.feed import (
    FeedExportError,
    export_feed,
    write_feed,
)
from organvm_engine.ledger.merkle import compute_merkle_root


def _args(**kwargs):
    """Create a mock argparse.Namespace with ledger defaults."""
    defaults = {
        "chain_path": None,
        "out": None,
        "json": False,
        "event": None,
        "full": False,
        "type": None,
        "tier": None,
        "limit": 20,
        "write": False,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _build_chain(tmp_path, *, checkpoints: int = 1):
    """Build a synthetic chain: genesis + events across tiers + checkpoints.

    Returns the chain path. Each checkpoint closes the events since the
    previous checkpoint (the engine's own checkpoint semantics).
    """
    chain_path = tmp_path / "chain.jsonl"
    assert cmd_ledger_genesis(_args(chain_path=str(chain_path))) == 0
    spine = EventSpine(chain_path)
    kinds = [
        ("governance.promotion", "gov-1", {"label": "Promotion decided"}),
        ("content.published", "pub-1", {"message": "Self-portrait published"}),
        ("registry.update", "reg-1", {}),
        ("git.sync", "git-1", {}),
    ]
    for event_type, uid, payload in kinds:
        spine.emit(
            event_type=event_type,
            entity_uid=uid,
            payload=payload,
            source_organ="META-ORGANVM",
            source_repo="organvm-engine",
            actor="test",
        )
    for _ in range(checkpoints):
        assert cmd_ledger_checkpoint(
            _args(chain_path=str(chain_path), write=True),
        ) == 0
        spine.emit(
            event_type="metrics.update",
            entity_uid="m-1",
            payload={"summary": "Metrics recomputed"},
            source_organ="META-ORGANVM",
            source_repo="organvm-engine",
            actor="test",
        )
    return chain_path


def _canonical(value) -> str:
    """Canonical JSON — the portal's rule, recomputed independently."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _feed_hash(event: dict) -> str:
    """Recompute an event's anchor_hash without the export's helpers."""
    rest = {k: v for k, v in event.items() if k != "anchor_hash"}
    digest = hashlib.sha256(_canonical(rest).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _verify_portal_rules(events: list[dict]) -> None:
    """Re-derive the portal's verifyEventChain + verifyCheckpoint rules."""
    prev_hash = GENESIS_PREV_HASH
    prev_seq = -1
    for event in events:
        assert _feed_hash(event) == event["anchor_hash"], event["sequence"]
        assert event["prev_hash"] == prev_hash, event["sequence"]
        assert event["sequence"] == prev_seq + 1, event["sequence"]
        prev_hash = event["anchor_hash"]
        prev_seq = event["sequence"]
    for event in events:
        if not event["checkpoint"]:
            continue
        batch = [e for e in events if e["sequence"] < event["sequence"]]
        assert batch, "checkpoint covers an empty batch"
        root = compute_merkle_root([e["anchor_hash"] for e in batch])
        assert event["merkle_root"] == root
        anchor = event["anchor"]
        assert anchor is not None
        tip = batch[-1]
        assert anchor["merkle_root"] == root
        assert anchor["chain_tip_hash"] == tip["anchor_hash"]
        assert anchor["sequence_start"] == batch[0]["sequence"]
        assert anchor["sequence_end"] == tip["sequence"]
        assert anchor["event_count"] == len(batch)
        assert anchor["timestamp"] == event["timestamp"]
        assert anchor["anchor_hash"] == compute_anchor_hash(
            merkle_root=root,
            chain_tip_hash=tip["anchor_hash"],
            sequence_start=batch[0]["sequence"],
            sequence_end=tip["sequence"],
            event_count=len(batch),
            timestamp=event["timestamp"],
        )


class TestExportFeed:

    def test_exports_testament_event_shape(self, tmp_path):
        chain_path = _build_chain(tmp_path)
        events = export_feed(chain_path)
        # genesis + 4 events + checkpoint + 1 trailing event
        assert len(events) == 7
        expected_keys = {
            "id", "sequence", "timestamp", "tier", "kind", "label",
            "summary", "prev_hash", "anchor_hash", "merkle_root",
            "checkpoint", "anchor", "source", "provenance",
        }
        for event in events:
            assert set(event) == expected_keys
            assert event["source"] == "engine-chain"
            assert event["anchor_hash"].startswith("sha256:")
        assert events[0]["sequence"] == 0
        assert events[0]["kind"] == "testament.genesis"
        assert events[0]["prev_hash"] == GENESIS_PREV_HASH
        # tiers come from the engine's own map
        assert events[1]["tier"] == "governance"  # governance.promotion
        assert events[2]["tier"] == "milestone"  # content.published
        assert events[3]["tier"] == "operational"  # registry.update
        assert events[4]["tier"] == "infrastructure"  # git.sync

    def test_label_summary_provenance_from_record(self, tmp_path):
        chain_path = _build_chain(tmp_path)
        events = export_feed(chain_path)
        assert events[1]["label"] == "Promotion decided"
        assert events[2]["summary"] == "Self-portrait published"
        # no commit SHA is stored in a chain record — provenance names the
        # chain position + source fields, never a fabricated SHA
        for event in events:
            assert event["provenance"].startswith("organvm-engine chain seq ")
            assert "META-ORGANVM" in event["provenance"]

    def test_feed_passes_portal_rules(self, tmp_path):
        chain_path = _build_chain(tmp_path)
        _verify_portal_rules(export_feed(chain_path))

    def test_two_checkpoints_use_portal_batch_rule(self, tmp_path):
        chain_path = _build_chain(tmp_path, checkpoints=2)
        events = export_feed(chain_path)
        _verify_portal_rules(events)
        checkpoints = [e for e in events if e["checkpoint"]]
        assert len(checkpoints) == 2
        # The second checkpoint's root covers ALL preceding events (the
        # portal's rule), not just the batch since the previous checkpoint
        # (the engine's stored payload root). The two rules agree only on
        # the first checkpoint.
        second = checkpoints[1]
        batch_since_last = [
            e for e in events
            if checkpoints[0]["sequence"] < e["sequence"] < second["sequence"]
        ]
        narrow_root = compute_merkle_root(
            [e["anchor_hash"] for e in batch_since_last],
        )
        assert second["merkle_root"] != narrow_root
        assert second["anchor"]["event_count"] == len(
            [e for e in events if e["sequence"] < second["sequence"]],
        )

    def test_missing_chain_refuses(self, tmp_path):
        with pytest.raises(FeedExportError, match="no chain found"):
            export_feed(tmp_path / "missing.jsonl")

    def test_empty_chain_refuses(self, tmp_path):
        chain_path = tmp_path / "empty.jsonl"
        chain_path.touch()
        with pytest.raises(FeedExportError, match="empty"):
            export_feed(chain_path)

    def test_tampered_chain_refuses(self, tmp_path):
        chain_path = _build_chain(tmp_path)
        lines = chain_path.read_text().splitlines()
        tampered = json.loads(lines[1])
        tampered["payload"] = {"message": "forged"}
        lines[1] = json.dumps(tampered)
        chain_path.write_text("\n".join(lines) + "\n")
        with pytest.raises(FeedExportError, match="failed verification"):
            export_feed(chain_path)

    def test_write_feed_is_deterministic(self, tmp_path):
        chain_path = _build_chain(tmp_path)
        out_a = tmp_path / "a" / "feed.json"
        out_b = tmp_path / "b" / "feed.json"
        write_feed(chain_path, out_a)
        write_feed(chain_path, out_b)
        assert out_a.read_text() == out_b.read_text()
        parsed = json.loads(out_a.read_text())
        assert isinstance(parsed, list) and len(parsed) == 7


class TestExportFeedCli:

    def test_cli_exports_and_reports(self, tmp_path, capsys):
        chain_path = _build_chain(tmp_path)
        out_path = tmp_path / "feed.json"
        result = cmd_ledger_export_feed(
            _args(chain_path=str(chain_path), out=str(out_path)),
        )
        assert result == 0
        assert out_path.is_file()
        assert json.loads(out_path.read_text())[0]["kind"] == "testament.genesis"
        assert "exported" in capsys.readouterr().out

    def test_cli_missing_chain_fails_closed(self, tmp_path, capsys):
        out_path = tmp_path / "feed.json"
        result = cmd_ledger_export_feed(
            _args(chain_path=str(tmp_path / "missing.jsonl"), out=str(out_path)),
        )
        assert result == 1
        assert "no chain found" in capsys.readouterr().out.lower()
        assert not out_path.exists()

    def test_cli_tampered_chain_writes_nothing(self, tmp_path, capsys):
        chain_path = _build_chain(tmp_path)
        lines = chain_path.read_text().splitlines()
        tampered = json.loads(lines[0])
        tampered["hash"] = "sha256:" + "0" * 64
        lines[0] = json.dumps(tampered)
        chain_path.write_text("\n".join(lines) + "\n")
        out_path = tmp_path / "feed.json"
        result = cmd_ledger_export_feed(
            _args(chain_path=str(chain_path), out=str(out_path)),
        )
        assert result == 1
        assert not out_path.exists()

    def test_cli_requires_out(self, tmp_path, capsys):
        chain_path = _build_chain(tmp_path)
        result = cmd_ledger_export_feed(_args(chain_path=str(chain_path)))
        assert result == 1
        assert "--out is required" in capsys.readouterr().out

    def test_main_dispatch(self, tmp_path, capsys):
        chain_path = _build_chain(tmp_path)
        out_path = tmp_path / "feed.json"
        argv = [
            "organvm", "ledger", "export-feed",
            "--chain-path", str(chain_path), "--out", str(out_path),
        ]
        with patch("sys.argv", argv):
            assert cli_main() == 0
        assert out_path.is_file()
        assert json.loads(out_path.read_text())[0]["kind"] == "testament.genesis"
