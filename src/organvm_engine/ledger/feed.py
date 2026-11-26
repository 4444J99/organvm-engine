"""Export the Testament Chain as a portal-ingestible JSON event feed.

Implements organvm-engine #246 (follow-up to #54): a read-only projection
of the engine's own hash chain into the stakeholder portal's
``TestamentEvent`` shape (``src/data/testament-events.ts``), so the portal
can ingest live chain data at build time and flip ``source`` from
``"seed"`` to ``"engine-chain"``.

Feed-level hashes vs engine hashes (read this before assuming the feed
re-states the chain): the portal's ``verifyEventChain`` recomputes each
event's hash over the *exported* ``TestamentEvent`` fields (everything
except ``anchor_hash`` itself), and the seed feed's hashes are computed
that way too. The engine record's own ``hash`` covers a different field
set (``event_id``/``event_type``/``payload``/...), so it cannot be copied
verbatim — the export recomputes ``anchor_hash`` over the exported fields
with the same canonical-JSON + SHA-256 rule (reusing
``ledger.chain.compute_event_hash``). The feed is therefore a re-hashed
projection: internally verifiable by the portal, in the same event order
as the engine chain, but its hashes are feed hashes, not the engine's
chain hashes. The engine chain itself is never modified by an export.

Checkpoint roots follow the portal's ``verifyCheckpoint`` rule: a
checkpoint's ``merkle_root`` covers *all preceding events* in the feed,
and its ``anchor`` is the engine's ``AnchorRecord`` digest over that
root (sequence range from the first feed event, timestamp = the
checkpoint event's own timestamp). This matches the engine's stored
checkpoint payload root only for the first checkpoint — the engine's
``ledger checkpoint`` command roots each batch since the *previous*
checkpoint, while the portal recomputes over everything before the
checkpoint. The portal rule wins here because it is the acceptance
authority for the feed.

Delivery: the chain lives on the operator machine (``~/.organvm/testament/
chain.jsonl``), so CI cannot produce the live feed. The operator runs
``organvm ledger export-feed --out <path>`` where the chain lives and
carries the JSON into the portal repo as a checked-in feed file — the
same way ``organvm testament render --write`` already carries rendered
artifacts (it writes to an output dir and CI uploads them as
``testament-artifacts-<sha>``; nothing copies into the portal repo
automatically). There is no live-fetch path from CI artifacts.

Fail-closed: a missing chain, an empty chain, or a chain that fails
``verify_chain`` refuses to export (non-zero exit, no file written).
"""

from __future__ import annotations

import json as _json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from organvm_engine.events.spine import EventRecord
from organvm_engine.ledger.anchor import AnchorRecord
from organvm_engine.ledger.chain import (
    GENESIS_PREV_HASH,
    compute_event_hash,
    verify_chain,
)
from organvm_engine.ledger.merkle import compute_merkle_root
from organvm_engine.ledger.tiers import classify_event_tier

#: Value carried in every exported event's ``source`` field.
FEED_SOURCE = "engine-chain"


class FeedExportError(Exception):
    """The chain cannot be exported as a feed (missing/empty/corrupt)."""


@dataclass
class FeedEvent:
    """One exported event, in the portal's ``TestamentEvent`` shape."""

    event: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return the plain dict (the JSON-serializable form)."""
        return self.event


def _chain_files(chain_path: Path) -> list[Path]:
    """Return the chain files to read, in order — same set ``verify_chain``
    walks (rotated segments first, active file last; single-file fallback
    when the path is not the standard ``chain.jsonl``)."""
    from organvm_engine.ledger.rotation import all_chain_files

    files = all_chain_files(chain_path.parent)
    if not files and chain_path.is_file():
        files = [chain_path]
    return files


def read_chain_records(chain_path: Path | str) -> list[EventRecord]:
    """Read every record of the chain at *chain_path*, oldest first.

    Raises:
        FeedExportError: If a line is not valid JSON or not an object.
    """
    path = Path(chain_path)
    records: list[EventRecord] = []
    for fp in _chain_files(path):
        for lineno, line in enumerate(fp.read_text().splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                data = _json.loads(line)
            except _json.JSONDecodeError as exc:
                raise FeedExportError(
                    f"{fp.name} line {lineno}: invalid JSON ({exc})",
                ) from exc
            if not isinstance(data, dict):
                raise FeedExportError(
                    f"{fp.name} line {lineno}: expected a JSON object",
                )
            records.append(EventRecord.from_dict(data))
    return records


def _label(record: EventRecord) -> str:
    """Short label for the event.

    Uses the payload's own label/title when the emitter provided one;
    otherwise the event type — never invented.
    """
    payload = record.payload or {}
    for key in ("label", "title"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return record.event_type


def _summary(record: EventRecord) -> str:
    """One-line summary for the event.

    Uses the payload's own summary/message/description when present. A
    checkpoint with no message gets a factual restatement of its payload
    (event count + sequence range); anything else falls back to the event
    type rather than inventing prose.
    """
    payload = record.payload or {}
    for key in ("summary", "message", "description"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if record.event_type == "testament.checkpoint":
        event_range = payload.get("event_range")
        event_count = payload.get("event_count")
        if (
            isinstance(event_range, list)
            and len(event_range) == 2
            and isinstance(event_count, int)
        ):
            return (
                f"Merkle checkpoint closing {event_count} events "
                f"(sequences {event_range[0]}–{event_range[1]})."
            )
    return record.event_type


def _provenance(record: EventRecord) -> str:
    """Provenance naming where the event comes from.

    Chain records carry no commit SHA, so provenance names the chain
    position plus the record's own source repo/organ fields — never a
    fabricated SHA.
    """
    repo = record.source_repo or "organvm-engine"
    base = f"{repo} chain seq {record.sequence}"
    if record.source_organ:
        base += f" ({record.source_organ})"
    return base


def _checkpoint_anchor(
    record: EventRecord,
    preceding: list[dict[str, Any]],
) -> tuple[str, dict[str, Any]]:
    """Build a checkpoint's Merkle root + AnchorRecord digest.

    The root covers *all preceding events* in the feed (the portal's
    ``verifyCheckpoint`` rule), and the anchor digest is the engine's
    ``AnchorRecord`` computation over that root, the feed tip hash, the
    full preceding range, and the checkpoint event's own timestamp.

    Returns:
        (merkle_root, anchor_dict) with exactly the portal's
        ``TestamentAnchor`` fields.
    """
    if not preceding:
        raise FeedExportError(
            f"checkpoint at sequence {record.sequence} covers an empty batch",
        )
    leaves = [event["anchor_hash"] for event in preceding]
    root = compute_merkle_root(leaves)
    tip = preceding[-1]
    anchor = AnchorRecord(
        merkle_root=root,
        chain_tip_hash=tip["anchor_hash"],
        sequence_start=preceding[0]["sequence"],
        sequence_end=tip["sequence"],
        event_count=len(preceding),
        timestamp=record.timestamp,
    )
    anchor_dict = {
        "merkle_root": anchor.merkle_root,
        "chain_tip_hash": anchor.chain_tip_hash,
        "sequence_start": anchor.sequence_start,
        "sequence_end": anchor.sequence_end,
        "event_count": anchor.event_count,
        "timestamp": anchor.timestamp,
        "anchor_hash": anchor.anchor_hash,
    }
    return root, anchor_dict


def build_feed_event(
    record: EventRecord,
    prev_feed_hash: str,
    preceding: list[dict[str, Any]],
) -> dict[str, Any]:
    """Project one chain record into a ``TestamentEvent`` dict.

    Args:
        record: The chain record to project.
        prev_feed_hash: The previous feed event's ``anchor_hash``
            (``GENESIS_PREV_HASH`` for the first event).
        preceding: The feed events already built, oldest first — used
            only for checkpoint root/anchor computation.

    The event's ``anchor_hash`` is computed over the exported fields
    (everything except ``anchor_hash`` itself) with the engine's
    canonical-JSON + SHA-256 rule — see the module docstring for why
    this is a feed hash, not a copy of the record's chain hash.
    """
    is_checkpoint = record.event_type == "testament.checkpoint"
    if is_checkpoint:
        merkle_root, anchor = _checkpoint_anchor(record, preceding)
    else:
        merkle_root, anchor = None, None

    event: dict[str, Any] = {
        "id": record.event_id,
        "sequence": record.sequence,
        "timestamp": record.timestamp,
        "tier": classify_event_tier(record.event_type).value,
        "kind": record.event_type,
        "label": _label(record),
        "summary": _summary(record),
        "prev_hash": prev_feed_hash,
        "merkle_root": merkle_root,
        "checkpoint": is_checkpoint,
        "anchor": anchor,
        "source": FEED_SOURCE,
        "provenance": _provenance(record),
    }
    # Feed hash: canonical JSON over the exported fields (no "hash" key
    # present, so compute_event_hash covers exactly these fields).
    event["anchor_hash"] = compute_event_hash(event)
    return event


def export_feed(chain_path: Path | str) -> list[dict[str, Any]]:
    """Export the chain at *chain_path* as a list of ``TestamentEvent``
    dicts, in chain order.

    The chain is verified with ``verify_chain`` first; a corrupt chain
    refuses to export. A missing or empty chain raises
    :class:`FeedExportError` instead of writing an empty feed.

    Raises:
        FeedExportError: Missing/empty/corrupt chain.
    """
    path = Path(chain_path)
    if not path.is_file():
        raise FeedExportError(f"no chain found at {path}")
    result = verify_chain(path)
    if not result.valid:
        raise FeedExportError(
            "chain failed verification: " + "; ".join(result.errors[:5]),
        )
    records = read_chain_records(path)
    if not records:
        raise FeedExportError(
            f"chain is empty — run `organvm ledger genesis` first ({path})",
        )
    events: list[dict[str, Any]] = []
    prev_hash = GENESIS_PREV_HASH
    for record in records:
        event = build_feed_event(record, prev_hash, events)
        events.append(event)
        prev_hash = event["anchor_hash"]
    return events


def write_feed(
    chain_path: Path | str,
    out_path: Path | str,
) -> list[dict[str, Any]]:
    """Export the chain and write deterministic JSON to *out_path*.

    Deterministic: sorted keys, 2-space indent, no wall-clock timestamps
    except the events' own. Parent directories are created as needed.
    Returns the exported event list.
    """
    events = export_feed(chain_path)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_json.dumps(events, indent=2, sort_keys=True) + "\n")
    return events
