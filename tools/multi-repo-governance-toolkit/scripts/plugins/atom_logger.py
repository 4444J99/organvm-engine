#!/usr/bin/env python3
"""atom-logger — append a structured work-atom record to the prompt registry.

Appends one JSON line to `data/atoms/atomized-tasks.jsonl` describing a
work unit just performed. The format mirrors the existing atom shape:

    {
      "atom_id": "<sha1[:12]>",
      "irf_id": "...",
      "session_id": "...",
      "title": "...",
      "kind": "<created|modified|closed|...>",
      "tags": ["..."],
      "created_at": "YYYY-MM-DDTHH:MM:SSZ"
    }

Usage:
    organ-cli plugin atom-logger \\
        --irf IRF-SYS-184 --session S-2026-05-19-pick-abc \\
        --title "Implement 4 meta-plugins" --kind closed \\
        --tags python skills plugins
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ATOMS_FILE = ROOT / "data" / "atoms" / "atomized-tasks.jsonl"


def _atom_id(payload: dict) -> str:
    canonical = json.dumps(
        {k: payload[k] for k in sorted(payload) if k != "atom_id"},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:12]


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="organ-cli plugin atom-logger")
    parser.add_argument("--irf", required=True, help="IRF ID this atom is anchored to")
    parser.add_argument("--session", required=True, help="originating session ID")
    parser.add_argument("--title", required=True, help="one-line title")
    parser.add_argument("--kind", default="modified",
                        choices=["created", "modified", "closed", "discovered", "deferred"],
                        help="atom kind")
    parser.add_argument("--tags", nargs="*", default=[], help="freeform tags")
    parser.add_argument("--target", default=str(ATOMS_FILE),
                        help="atomized-tasks.jsonl path (default: %(default)s)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the atom to stdout but do not append")
    args = parser.parse_args(argv)

    payload = {
        "irf_id": args.irf,
        "session_id": args.session,
        "title": args.title,
        "kind": args.kind,
        "tags": args.tags,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    payload["atom_id"] = _atom_id(payload)

    target = Path(args.target)
    line = json.dumps(payload, separators=(",", ":"))

    if args.dry_run:
        print(line)
        return 0

    if not target.parent.exists():
        print(f"ERROR: parent directory {target.parent} does not exist", file=sys.stderr)
        return 1

    with target.open("a") as f:
        f.write(line + "\n")
    print(f"appended atom {payload['atom_id']} → {target}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
