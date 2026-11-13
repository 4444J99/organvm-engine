#!/usr/bin/env python3
"""PR Status Checker — query all tracked contribution PRs via gh CLI.

Reads the backflow manifest, checks each PR's current state via `gh pr view`,
and outputs a categorized summary table.

Usage:
    python scripts/pr-status-checker.py                    # summary table
    python scripts/pr-status-checker.py --update           # also update manifest
    python scripts/pr-status-checker.py --category stale   # filter by category
    python scripts/pr-status-checker.py --json             # JSON output
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

MANIFEST_PATH = Path(__file__).resolve().parent.parent / "data" / "atoms" / "backflow-manifest.yaml"
STALE_DAYS = 14
VERY_STALE_DAYS = 21


def parse_manifest(path: Path) -> list[dict[str, str]]:
    """Extract PR URLs from the ORGAN-VII section of the backflow manifest."""
    if yaml is not None:
        with open(path) as f:
            data = yaml.safe_load(f)
        prs = []
        for signal in data.get("organs", {}).get("ORGAN-VII", []):
            url = signal.get("metadata", {}).get("pr_url", "")
            if url:
                prs.append({"url": url, "source": signal.get("source", "")})
        return prs

    # Fallback: regex parse if pyyaml not available
    import re
    prs = []
    current_source = ""
    with open(path) as f:
        for line in f:
            source_match = re.match(r"\s*-\s*source:\s*(.+)", line)
            if source_match:
                current_source = source_match.group(1).strip()
            url_match = re.match(r"\s*pr_url:\s*(.+)", line)
            if url_match:
                prs.append({"url": url_match.group(1).strip(), "source": current_source})
    return prs


def parse_pr_url(url: str) -> tuple[str, str, int]:
    """Extract owner, repo, number from a GitHub PR URL."""
    # https://github.com/owner/repo/pull/123
    parts = url.rstrip("/").split("/")
    return parts[-4], parts[-3], int(parts[-1])


def fetch_pr_status(url: str) -> dict[str, Any]:
    """Fetch PR status via gh CLI."""
    owner, repo, number = parse_pr_url(url)
    try:
        result = subprocess.run(
            [
                "gh", "pr", "view", str(number),
                "--repo", f"{owner}/{repo}",
                "--json", "state,title,updatedAt,labels,isDraft,mergedAt,closedAt,mergeable,reviewDecision",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return {"error": result.stderr.strip(), "url": url}
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        return {"error": str(e), "url": url}


def categorize(pr: dict[str, Any]) -> str:
    """Categorize a PR based on its current state."""
    state = pr.get("state", "").upper()

    if state == "MERGED":
        return "merged"
    if state == "CLOSED":
        return "closed"
    if pr.get("isDraft"):
        return "draft"

    updated = pr.get("updatedAt", "")
    if updated:
        try:
            updated_dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - updated_dt).days
        except ValueError:
            age_days = 0
    else:
        age_days = 0

    review = pr.get("reviewDecision", "")
    if review == "APPROVED":
        return "close-to-merge"
    if review == "CHANGES_REQUESTED":
        return "needs-response"

    if age_days >= VERY_STALE_DAYS:
        return "stale"
    if age_days >= STALE_DAYS:
        return "waiting-on-maintainer"

    mergeable = pr.get("mergeable", "")
    if mergeable == "CONFLICTING":
        return "blocked"

    return "waiting-on-maintainer"


def format_table(results: list[dict[str, Any]]) -> str:
    """Format results as a readable table."""
    lines = []
    lines.append(f"{'Category':<22} {'PR':<45} {'Updated':<12} {'State':<8}")
    lines.append("-" * 90)

    sorted_results = sorted(results, key=lambda r: (
        {"merged": 0, "close-to-merge": 1, "needs-response": 2, "blocked": 3,
         "waiting-on-maintainer": 4, "stale": 5, "draft": 6, "closed": 7, "error": 8}.get(r["category"], 9),
        r.get("title", ""),
    ))

    for r in sorted_results:
        if "error" in r and "title" not in r:
            lines.append(f"{'error':<22} {r['url']:<45} {'N/A':<12} {'ERR':<8}")
            continue

        owner, repo, num = parse_pr_url(r["url"])
        pr_id = f"{owner}/{repo}#{num}"
        if len(pr_id) > 43:
            pr_id = pr_id[:40] + "..."

        updated = r.get("updatedAt", "")[:10] if r.get("updatedAt") else "N/A"
        state = r.get("state", "?")[:7]

        lines.append(f"{r['category']:<22} {pr_id:<45} {updated:<12} {state:<8}")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Check status of tracked contribution PRs")
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH, help="Path to backflow manifest")
    parser.add_argument("--update", action="store_true", help="Update manifest with current states")
    parser.add_argument("--category", help="Filter by category")
    parser.add_argument("--json", action="store_true", dest="json_output", help="JSON output")
    args = parser.parse_args()

    if not args.manifest.exists():
        print(f"Manifest not found: {args.manifest}", file=sys.stderr)
        sys.exit(1)

    prs = parse_manifest(args.manifest)
    print(f"Checking {len(prs)} PRs...", file=sys.stderr)

    results = []
    for pr_info in prs:
        status = fetch_pr_status(pr_info["url"])
        status["url"] = pr_info["url"]
        status["source"] = pr_info["source"]
        status["category"] = categorize(status) if "error" not in status or "title" in status else "error"
        results.append(status)

    if args.category:
        results = [r for r in results if r.get("category") == args.category]

    if args.json_output:
        print(json.dumps(results, indent=2, default=str))
    else:
        print(format_table(results))

        # Summary counts
        from collections import Counter
        counts = Counter(r["category"] for r in results)
        print(f"\nTotal: {len(results)} | " + " | ".join(f"{k}: {v}" for k, v in sorted(counts.items())))

    if args.update and yaml is not None:
        with open(args.manifest) as f:
            data = yaml.safe_load(f)

        state_map = {}
        for r in results:
            state = r.get("state", "").lower()
            if state in ("merged", "closed", "open"):
                state_map[r["url"]] = state

        updated = False
        for organ_signals in data.get("organs", {}).values():
            for signal in organ_signals:
                url = signal.get("metadata", {}).get("pr_url", "")
                if url in state_map:
                    old_state = signal.get("metadata", {}).get("pr_state", "")
                    new_state = state_map[url]
                    if old_state != new_state:
                        signal["metadata"]["pr_state"] = new_state
                        updated = True

        if updated:
            data["last_verified"] = datetime.now(timezone.utc).isoformat()
            with open(args.manifest, "w") as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
            print(f"\nManifest updated: {args.manifest}", file=sys.stderr)
        else:
            print("\nNo state changes to update.", file=sys.stderr)


if __name__ == "__main__":
    main()
