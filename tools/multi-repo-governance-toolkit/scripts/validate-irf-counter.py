#!/usr/bin/env python3
"""Pre-commit hook: validate DONE-ID counter against IRF body.

Reverse-invariant complement to scripts/check-done-id.py. Together they form
forward + reverse coverage of the DONE-ID claim/render lifecycle:

- check-done-id.py (forward): "no staged DONE-NNN above counter / no duplicates"
- validate-irf-counter.py (reverse): "no claimed DONE-NNN missing from IRF body"

The reverse direction catches the "claim-and-disappear" failure mode: a session
increments the counter (claims an ID range) but never renders the row into IRF.
Closes IRF-MON-014.

Exit codes:
  0 = in sync (or all missing IDs covered by an accept condition)
  1 = missing-IDs: un-accepted gap detected (prints list)
  2 = counter-rollback: claimed_max regressed since HEAD~1
  3 = malformed input (counter JSON parse error, IRF unreadable)
"""

import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
COUNTER_FILE = REPO_ROOT / "data" / "done-id-counter.json"
IRF_FILE = REPO_ROOT / "INST-INDEX-RERUM-FACIENDARUM.md"
ARCHIVE_DIRS = [REPO_ROOT / "docs" / "archive", REPO_ROOT / "docs" / "operations" / "archive"]

# "Rendered" = DONE-NNN referenced anywhere in IRF body. This deviates from
# the narrow column-1 regex check-done-id.py:82 uses for *duplicate-assignment*
# detection, because the IRF's actual rendering practice puts DONE-NNN as a
# claim marker (e.g. "**DONE-429**:") inside the description column of an
# IRF-XXX-NNN row, not as the row's primary key. The narrow regex misses
# those — but they ARE rendered.
DONE_ID_RE = re.compile(r"DONE-(\d+)")
GAP_MARKER_RE = re.compile(r"GAP-DOCUMENTED-IN-IRF-MON-\d{3}")

# Grandfathered ghost set: counter-claimed but never rendered, accepted by
# IRF-MON-014 historical scope (see handoff spec; exact set, do not extend
# without a new IRF-MON entry).
GRANDFATHERED: set[int] = (
    set(range(490, 497)) | set(range(504, 522))
)


def load_counter() -> dict:
    try:
        with open(COUNTER_FILE) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"validate-irf-counter: counter unreadable: {e}", file=sys.stderr)
        sys.exit(3)


def claimed_max_from(counter: dict) -> int:
    """claimed_max = max(next_id - 1, claimed_range[1])"""
    next_id = int(counter["next_id"])
    range_upper = int(counter.get("claimed_range", [0, 0])[1])
    return max(next_id - 1, range_upper)


def rendered_set(text: str) -> set[int]:
    return {int(m) for m in DONE_ID_RE.findall(text)}


def archive_rendered_set() -> set[int]:
    """DONE-IDs whose assignment row appears under any archive subtree."""
    ids: set[int] = set()
    for adir in ARCHIVE_DIRS:
        if not adir.exists():
            continue
        for md in adir.rglob("*.md"):
            try:
                ids |= rendered_set(md.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
    return ids


def gap_marker_covered(irf_text: str) -> set[int]:
    """IDs that share a line with a GAP-DOCUMENTED-IN-IRF-MON-\\d{3} marker.

    Interpretation: a marker placed on a line documents the gap for any
    DONE-NNN references appearing on the same line (e.g. a row noting
    'DONE-590..600 GAP-DOCUMENTED-IN-IRF-MON-019').
    """
    covered: set[int] = set()
    for line in irf_text.splitlines():
        if GAP_MARKER_RE.search(line):
            covered |= {int(m) for m in DONE_ID_RE.findall(line)}
    return covered


def head_claimed_max() -> int | None:
    """claimed_max from data/done-id-counter.json at HEAD~1, or None if absent."""
    try:
        result = subprocess.run(
            ["git", "show", f"HEAD~1:{COUNTER_FILE.relative_to(REPO_ROOT)}"],
            capture_output=True, text=True, cwd=REPO_ROOT, check=False,
        )
        if result.returncode != 0:
            return None
        return claimed_max_from(json.loads(result.stdout))
    except (json.JSONDecodeError, ValueError):
        return None


def main() -> int:
    counter = load_counter()
    try:
        claimed_max = claimed_max_from(counter)
    except (KeyError, ValueError, TypeError) as e:
        print(f"validate-irf-counter: counter malformed: {e}", file=sys.stderr)
        return 3

    try:
        irf_text = IRF_FILE.read_text(encoding="utf-8")
    except OSError as e:
        print(f"validate-irf-counter: IRF unreadable: {e}", file=sys.stderr)
        return 3

    prior_max = head_claimed_max()
    if prior_max is not None and claimed_max < prior_max:
        print(
            f"validate-irf-counter: counter rollback detected "
            f"(HEAD~1 claimed_max={prior_max}, current={claimed_max})",
            file=sys.stderr,
        )
        return 2

    claimed = set(range(1, claimed_max + 1))
    rendered = rendered_set(irf_text)
    missing = claimed - rendered

    if missing:
        missing -= archive_rendered_set()
    if missing:
        missing -= gap_marker_covered(irf_text)
    if missing:
        missing -= GRANDFATHERED

    if missing:
        print("=" * 60, file=sys.stderr)
        print("DONE-ID COUNTER/IRF MISMATCH", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        print(
            f"  ✗ {len(missing)} claimed DONE-ID(s) not rendered in IRF "
            f"(and not in archive / gap-marked / grandfathered):",
            file=sys.stderr,
        )
        for d in sorted(missing):
            print(f"      DONE-{d}", file=sys.stderr)
        print(
            "  Remediation: either render the missing row(s) into "
            f"{IRF_FILE.name}, document the gap with a "
            "GAP-DOCUMENTED-IN-IRF-MON-NNN marker on the relevant line, "
            "or archive the row under docs/archive/.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
