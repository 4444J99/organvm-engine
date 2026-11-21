"""Ledger CLI commands — the Testament Protocol's native hash chain."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

_DEFAULT_CHAIN_PATH = Path.home() / ".organvm" / "testament" / "chain.jsonl"


def _chain_path(args: argparse.Namespace) -> Path:
    """Resolve chain path from args or default."""
    raw = getattr(args, "chain_path", None)
    return Path(raw) if raw else _DEFAULT_CHAIN_PATH


def cmd_ledger_genesis(args: argparse.Namespace) -> int:
    """Initialize the Testament Chain with a genesis event."""
    from organvm_engine.events.spine import EventSpine

    path = _chain_path(args)
    if path.is_file() and path.stat().st_size > 0:
        print(f"  Chain already exists at {path}")
        print("  Genesis can only be called once. The chain is immutable.")
        return 1

    spine = EventSpine(path)
    record = spine.emit(
        event_type="testament.genesis",
        entity_uid="",
        source_organ="META-ORGANVM",
        source_repo="organvm-engine",
        actor="human:genesis",
        payload={
            "message": (
                "The Testament Chain begins. Every mutation witnessed. "
                "Every state traceable. The system remembers."
            ),
        },
    )

    print("\n  Testament Chain Genesis")
    print(f"  {'=' * 48}")
    print(f"  Event ID:  {record.event_id}")
    print(f"  Sequence:  {record.sequence}")
    print(f"  Hash:      {record.hash}")
    print(f"  Path:      {path}")
    print("\n  The chain has begun.\n")
    return 0


def cmd_ledger_status(args: argparse.Namespace) -> int:
    """Show Testament Chain status."""
    from organvm_engine.ledger.chain import verify_chain

    path = _chain_path(args)
    as_json = getattr(args, "json", False)

    if not path.is_file():
        if as_json:
            print(json.dumps({"exists": False, "event_count": 0}))
        else:
            print("\n  No chain found. Run `organvm ledger genesis` to begin.\n")
        return 0

    result = verify_chain(path)

    if as_json:
        print(json.dumps({
            "exists": True,
            "valid": result.valid,
            "event_count": result.event_count,
            "last_sequence": result.last_sequence,
            "last_hash": result.last_hash,
            "errors": result.errors,
        }))
    else:
        status = "VALID" if result.valid else "CORRUPTED"
        print(f"\n  Testament Chain — {status}")
        print(f"  {'=' * 48}")
        print(f"  Events:        {result.event_count}")
        print(f"  Last sequence: {result.last_sequence}")
        if result.last_hash:
            print(f"  Last hash:     {result.last_hash[:30]}...")
        print(f"  Path:          {path}")
        if result.errors:
            print(f"\n  Errors ({len(result.errors)}):")
            for e in result.errors[:10]:
                print(f"    - {e}")
        print()

    return 0


def cmd_ledger_verify(args: argparse.Namespace) -> int:
    """Verify Testament Chain integrity."""
    from organvm_engine.ledger.chain import verify_chain

    path = _chain_path(args)
    if not path.is_file():
        print("  No chain found.")
        return 1

    result = verify_chain(path)

    if result.valid:
        print(
            f"\n  Chain VERIFIED — {result.event_count} events, "
            f"integrity intact from genesis to sequence {result.last_sequence}.\n",
        )
        return 0
    print(f"\n  Chain CORRUPTED — {len(result.errors)} error(s):")
    for e in result.errors:
        print(f"    - {e}")
    print()
    return 1


def cmd_ledger_log(args: argparse.Namespace) -> int:
    """Query the Testament Chain."""
    from organvm_engine.events.spine import EventSpine
    from organvm_engine.ledger.tiers import EventTier, classify_event_tier

    path = _chain_path(args)
    spine = EventSpine(path)

    event_type = getattr(args, "type", None)
    limit = getattr(args, "limit", 20)
    tier_filter = getattr(args, "tier", None)
    as_json = getattr(args, "json", False)

    records = spine.query(event_type=event_type, limit=limit)

    if tier_filter:
        target_tier = EventTier(tier_filter)
        records = [
            r for r in records if classify_event_tier(r.event_type) == target_tier
        ]

    if as_json:
        from dataclasses import asdict

        print(json.dumps([asdict(r) for r in records], indent=2, default=str))
    else:
        if not records:
            print("\n  No events found.\n")
            return 0

        print(f"\n  Testament Chain — {len(records)} events")
        print(f"  {'Seq':<6} {'Type':<28} {'Tier':<14} {'Timestamp':<20}")
        print(f"  {'-' * 70}")
        for r in records:
            tier = classify_event_tier(r.event_type).value
            ts = r.timestamp[:19] if r.timestamp else ""
            print(f"  {r.sequence:<6} {r.event_type:<28} {tier:<14} {ts}")
        print()

    return 0


def cmd_ledger_checkpoint(args: argparse.Namespace) -> int:
    """Create a Merkle checkpoint of events since last checkpoint."""
    from organvm_engine.events.spine import EventSpine
    from organvm_engine.ledger.merkle import compute_merkle_root

    path = _chain_path(args)
    dry_run = not getattr(args, "write", False)
    spine = EventSpine(path)

    # Find events since last checkpoint
    all_events = spine.query(limit=100_000)
    last_chk_seq = -1
    for ev in all_events:
        if ev.event_type == "testament.checkpoint":
            last_chk_seq = ev.sequence

    batch = [
        ev
        for ev in all_events
        if ev.sequence > last_chk_seq
        and ev.event_type != "testament.checkpoint"
    ]

    if not batch:
        print("  No events to checkpoint.")
        return 0

    leaves = [ev.hash for ev in batch if ev.hash]
    if not leaves:
        print("  No hashed events to checkpoint.")
        return 0

    root = compute_merkle_root(leaves)
    seq_range = (batch[0].sequence, batch[-1].sequence)

    if dry_run:
        print(
            f"\n  [dry-run] Would checkpoint {len(batch)} events "
            f"(seq {seq_range[0]}-{seq_range[1]})",
        )
        print(f"  Merkle root: {root}")
        print("\n  Run with --write to create checkpoint.\n")
        return 0

    record = spine.emit(
        event_type="testament.checkpoint",
        entity_uid="",
        source_organ="META-ORGANVM",
        source_repo="organvm-engine",
        actor="ledger:checkpoint",
        payload={
            "merkle_root": root,
            "event_range": list(seq_range),
            "event_count": len(batch),
            "prev_checkpoint_seq": last_chk_seq if last_chk_seq >= 0 else None,
        },
    )

    print(f"\n  Checkpoint created — sequence {record.sequence}")
    print(f"  Merkle root: {root}")
    print(f"  Events: {len(batch)} (seq {seq_range[0]}-{seq_range[1]})\n")
    return 0


def cmd_ledger_repair(args: argparse.Namespace) -> int:
    """Repair a corrupted chain by recomputing hashes and fixing sequences."""
    from organvm_engine.ledger.chain import repair_chain, verify_chain

    path = _chain_path(args)
    if not path.is_file():
        print("  No chain found.")
        return 1

    dry_run = not getattr(args, "write", False)

    # Check if repair is needed
    pre = verify_chain(path)
    if pre.valid:
        print(
            f"\n  Chain is already VALID ({pre.event_count} events). "
            "No repair needed.\n",
        )
        return 0

    if dry_run:
        print(
            f"\n  Chain has {len(pre.errors)} error(s) across "
            f"{pre.event_count} events.",
        )
        print("  Run with --write to repair.\n")
        return 0

    result = repair_chain(path)

    # Verify after repair
    post = verify_chain(path)

    print("\n  Chain Repair Complete")
    print(f"  {'=' * 48}")
    print(f"  Events read:    {result['events_read']}")
    print(f"  Events repaired: {result['events_repaired']}")
    if result.get("parse_errors"):
        print(f"  Parse errors:   {result['parse_errors']}")
    print(f"  Backup:         {result['backup']}")
    print(f"  Post-repair:    {'VALID' if post.valid else 'STILL CORRUPTED'}")
    print()

    return 0 if post.valid else 1


def cmd_ledger_export_feed(args: argparse.Namespace) -> int:
    """Export the Testament Chain as a portal-ingestible JSON event feed.

    Reads the chain (verifying it first — a corrupt chain refuses to
    export), projects every record into the stakeholder portal's
    ``TestamentEvent`` shape, and writes deterministic JSON to ``--out``.
    The chain lives on the operator machine, so the operator runs this
    where the chain lives and carries the JSON into the portal repo as a
    checked-in feed file; CI cannot produce the live feed. See
    ``organvm_engine.ledger.feed`` for the feed-hash and checkpoint-root
    rules (feed-level hashes, portal ``verifyCheckpoint`` batch rule).
    """
    from organvm_engine.ledger.feed import FeedExportError, write_feed

    path = _chain_path(args)
    out = getattr(args, "out", None)
    if not out:
        print("  --out is required: where to write the JSON feed.")
        return 1
    if not path.is_file():
        print("  No chain found.")
        return 1

    try:
        events = write_feed(path, out)
    except FeedExportError as exc:
        print(f"  Refusing to export: {exc}")
        return 1

    print(f"\n  Testament feed exported — {len(events)} events")
    print(f"  Chain: {path}")
    print(f"  Wrote: {out}\n")
    return 0
