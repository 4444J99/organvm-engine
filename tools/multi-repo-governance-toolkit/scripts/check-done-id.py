#!/usr/bin/env python3
"""Pre-commit hook: validate DONE-ID assignments against counter.

Prevents the 5th collision incident by enforcing:
1. No DONE-NNN in staged IRF changes where NNN >= counter next_id
2. No duplicate DONE-NNN assignments (same ID, different content)
3. Counter must be incremented BEFORE IRF additions

Usage: python3 scripts/check-done-id.py [--repo-root /path/to/corpus] [--staged]
  --repo-root: checkout containing the counter and IRF (default: current directory)
  --staged: only check git staged changes (for pre-commit hook)
  (no flag): check entire IRF file (for manual audit)
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# Match counter-sequenced numeric IDs (DONE-566) but NOT date-form IDs
# (DONE-2026-04-30, a separate scheme used e.g. by IRF-OPS-019). The trailing
# negative lookahead (?![\d-]) rejects any DONE-number followed by another digit
# or a hyphen, so "DONE-2026-04-30" yields no match instead of a spurious 2026.
DONE_PATTERN = re.compile(r"DONE-(\d{1,4})(?![\d-])")


def load_counter(counter_file: Path) -> dict:
    with counter_file.open() as f:
        return json.load(f)


def get_staged_irf_additions(repo_root: Path, irf_file: Path) -> list[str]:
    """Get only the added lines in the staged IRF diff."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--unified=0", "--", str(irf_file)],
        capture_output=True, text=True, cwd=repo_root, check=True,
    )
    return [
        line[1:]  # strip leading +
        for line in result.stdout.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]


def get_all_done_ids(text: str) -> list[int]:
    return [int(m) for m in DONE_PATTERN.findall(text)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(),
                        help="Corpus checkout containing data/done-id-counter.json and the IRF")
    parser.add_argument("--staged", action="store_true", help="Check staged IRF additions")
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    irf_file = repo_root / "INST-INDEX-RERUM-FACIENDARUM.md"
    staged_only = args.staged

    try:
        counter = load_counter(repo_root / "data" / "done-id-counter.json")
        next_id = counter["next_id"]
        if staged_only:
            lines = get_staged_irf_additions(repo_root, irf_file)
            if not lines:
                sys.exit(0)  # no IRF changes staged
            text = "\n".join(lines)
            source = "staged changes"
        else:
            text = irf_file.read_text()
            source = "full IRF file"
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print(f"DONE-ID inputs unavailable: {exc}. Select the corpus checkout with --repo-root.",
              file=sys.stderr)
        sys.exit(2)

    done_ids = get_all_done_ids(text)
    if not done_ids:
        sys.exit(0)  # no DONE-IDs found

    errors = []

    # Check 1: No DONE-ID >= next_id (counter not incremented)
    over_counter = [d for d in done_ids if d >= next_id]
    if over_counter:
        errors.append(
            f"DONE-ID(s) {over_counter} >= counter next_id ({next_id}). "
            f"You must increment data/done-id-counter.json BEFORE assigning IDs."
        )

    # Check 2: No duplicate DONE-IDs in assignment rows only
    # Cross-references (e.g. "advances DONE-408") are allowed — only flag
    # rows starting with | DONE-NNN | (actual assignment table entries)
    if staged_only:
        assign_re = re.compile(r"^\|\s*DONE-(\d+)\s*\|")
        assign_ids = [int(assign_re.match(l).group(1)) for l in lines if assign_re.match(l)]
        seen = set()
        dupes = set()
        for d in assign_ids:
            if d in seen:
                dupes.add(d)
            seen.add(d)
        if dupes:
            errors.append(
                f"Duplicate DONE-ID assignment(s) in {source}: {sorted(dupes)}"
            )

    if errors:
        print("=" * 60, file=sys.stderr)
        print("DONE-ID VALIDATION FAILED", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        for e in errors:
            print(f"  ✗ {e}", file=sys.stderr)
        print(f"\nCounter state: next_id={next_id}, "
              f"last_claimed_by={counter.get('last_claimed_by', 'unknown')}",
              file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        sys.exit(1)

    max_id = max(done_ids)
    print(f"✓ DONE-ID check passed ({source}): "
          f"{len(done_ids)} IDs found, max=DONE-{max_id}, "
          f"counter next_id={next_id}")
    sys.exit(0)


if __name__ == "__main__":
    main()
