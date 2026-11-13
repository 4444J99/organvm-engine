#!/usr/bin/env python3
"""System Pulse Generator — weekly automated status report.

Generates a structured markdown document from automated data sources:
- system-metrics.json (repo counts, sprint count, essay count)
- data/soak-test/daily-*.json (validation health, CI stability, engagement)
- repo-registry.json (implementation status distribution)
- GitHub API (recent commits, stars/forks delta)

Output: data/pulse/weekly-YYYY-MM-DD.md

Usage:
    python3 scripts/system-pulse-generator.py
    python3 scripts/system-pulse-generator.py --output data/pulse/weekly-2026-02-17.md
    python3 scripts/system-pulse-generator.py --skip-api  # offline mode
"""

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
METRICS_PATH = ROOT / "system-metrics.json"
REGISTRY_PATH = ROOT / "repo-registry.json"
SOAK_DIR = ROOT / "data" / "soak-test"
PULSE_DIR = ROOT / "data" / "pulse"

ORGS = [
    "organvm-i-theoria",
    "organvm-ii-poiesis",
    "organvm-iii-ergon",
    "organvm-iv-taxis",
    "organvm-v-logos",
    "organvm-vi-koinonia",
    "organvm-vii-kerygma",
    "meta-organvm",
]


def gh_api(endpoint, jq_filter=None):
    """Call gh api and return (returncode, output)."""
    cmd = ["gh", "api", endpoint]
    if jq_filter:
        cmd.extend(["--jq", jq_filter])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return result.returncode, result.stdout.strip()


def load_json(path):
    """Load a JSON file, return None on failure."""
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def load_soak_snapshots(days=7):
    """Load the last N days of soak test snapshots."""
    snapshots = sorted(SOAK_DIR.glob("daily-*.json"))
    data = []
    for path in snapshots[-days:]:
        snap = load_json(path)
        if snap and not snap.get("dry_run"):
            data.append(snap)
    return data


def fetch_recent_commits(skip_api=False):
    """Fetch recent commits across all orgs (last 7 days)."""
    if skip_api:
        return []

    commits = []
    for org in ORGS:
        rc, out = gh_api(
            f"search/commits?q=org:{org}+committer-date:>={_week_ago()}&sort=committer-date&per_page=5",
            ".items[] | {repo: .repository.full_name, message: .commit.message, date: .commit.committer.date, sha: .sha}"
        )
        if rc == 0 and out:
            for line in out.strip().split("\n"):
                if line.startswith("{"):
                    try:
                        commits.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    return commits


def fetch_engagement_delta(snapshots):
    """Compute engagement delta from soak test snapshots."""
    if len(snapshots) < 2:
        return None

    first = snapshots[0].get("engagement", {})
    last = snapshots[-1].get("engagement", {})

    return {
        "stars_delta": last.get("total_stars", 0) - first.get("total_stars", 0),
        "forks_delta": last.get("total_forks", 0) - first.get("total_forks", 0),
        "stars_current": last.get("total_stars", 0),
        "forks_current": last.get("total_forks", 0),
        "period_days": len(snapshots),
    }


def _week_ago():
    return (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")


def _present(value, default="n/a"):
    """Return value if meaningfully present, else a clean placeholder."""
    return value if value not in (None, "", "?") else default


def _resolve_total_words(computed, manual):
    """Prefer engine-computed word_counts, fall back to manual, else n/a."""
    wc = computed.get("word_counts") or {}
    total = wc.get("total")
    if total is None:
        total = manual.get("total_words")
    if isinstance(total, (int, float)):
        return f"{int(total):,}"
    return _present(total)


def generate_pulse(metrics, registry, snapshots, commits, skip_api=False):
    """Generate the pulse markdown document."""
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")

    computed = metrics.get("computed", {})
    manual = metrics.get("manual", {})

    # Section 1: System Health
    health_lines = []
    if snapshots:
        latest = snapshots[-1]
        val = latest.get("validation", {})
        reg_pass = val.get("registry_pass", False)
        dep_pass = val.get("dependency_pass", False)
        health_lines.append(f"- Registry integrity: {'PASS' if reg_pass else 'FAIL'}")
        health_lines.append(f"- Dependency graph: {'PASS' if dep_pass else 'FAIL'}")
        health_lines.append(f"- Stale repos: {len(val.get('stale_repos', []))}")
        health_lines.append(f"- Data points: {len(snapshots)} snapshots this period")

        validation_passes = sum(
            1 for s in snapshots
            if s.get("validation", {}).get("registry_pass")
            and s.get("validation", {}).get("dependency_pass")
        )
        health_lines.append(f"- Validation pass rate: {validation_passes}/{len(snapshots)} days")
    else:
        health_lines.append("- No soak test data available yet")

    # Section 2: This Week's Numbers
    numbers_lines = [
        f"- Total repos: {computed.get('total_repos', '?')}",
        f"- Active repos: {computed.get('active_repos', '?')}",
        f"- Archived repos: {computed.get('archived_repos', '?')}",
        f"- Prototype repos: {computed.get('implementation_status', {}).get('PROTOTYPE', 0)}",
        f"- Published essays: {computed.get('published_essays', '?')}",
        f"- Sprints completed: {computed.get('sprints_completed', '?')}",
        f"- Organs operational: {computed.get('operational_organs', '?')}/{computed.get('total_organs', 8)}",
        f"- Total words: {_resolve_total_words(computed, manual)}",
        f"- Code files: {_present(manual.get('code_files'))}",
        f"- Test files: {_present(manual.get('test_files'))}",
    ]

    # Section 3: Engagement Delta
    engagement_lines = []
    delta = fetch_engagement_delta(snapshots)
    if delta:
        def sign(n):
            return f"+{n}" if n > 0 else str(n)
        engagement_lines.append(f"- Stars: {delta['stars_current']} ({sign(delta['stars_delta'])} this period)")
        engagement_lines.append(f"- Forks: {delta['forks_current']} ({sign(delta['forks_delta'])} this period)")
        engagement_lines.append(f"- Period: {delta['period_days']} days of data")
    else:
        engagement_lines.append("- Insufficient data for delta calculation (need 2+ snapshots)")

    # Section 4: CI Stability
    ci_lines = []
    if snapshots:
        latest_ci = snapshots[-1].get("ci", {})
        ci_lines.append(f"- Repos checked: {latest_ci.get('total_checked', 0)}")
        ci_lines.append(f"- Passing: {latest_ci.get('passing', 0)}")
        ci_lines.append(f"- Failing: {latest_ci.get('failing', 0)}")
        ci_lines.append(f"- Unknown: {latest_ci.get('unknown', 0)}")
        ci_lines.append(f"- Billing-locked: {latest_ci.get('billing_locked', 0)}")
        failures = latest_ci.get("failures", [])
        if failures:
            ci_lines.append(f"- Failures: {', '.join(failures[:5])}")
    else:
        ci_lines.append("- No CI data available yet")

    # Section 5: Notable Events
    events_lines = []
    if commits:
        events_lines.append(f"- {len(commits)} commits across orgs this week")
        # Group by repo
        by_repo = defaultdict(int)
        for c in commits:
            by_repo[c.get("repo", "unknown")] += 1
        for repo, count in sorted(by_repo.items(), key=lambda x: -x[1])[:5]:
            events_lines.append(f"  - {repo}: {count} commits")
    elif not skip_api:
        events_lines.append("- No recent commits detected")
    else:
        events_lines.append("- Commit data skipped (--skip-api mode)")

    # Implementation status breakdown
    impl = computed.get("implementation_status", {})
    status_line = ", ".join(f"{k}: {v}" for k, v in impl.items())

    # Assemble document
    lines = [
        f"# System Pulse — Week of {date_str}",
        "",
        f"*Auto-generated by system-pulse-generator.py at {now.strftime('%Y-%m-%d %H:%M UTC')}*",
        "",
        "---",
        "",
        "## 1. System Health",
        "",
        *health_lines,
        "",
        "## 2. This Week's Numbers",
        "",
        *numbers_lines,
        "",
        f"Implementation status: {status_line}",
        "",
        "## 3. Engagement Delta",
        "",
        *engagement_lines,
        "",
        "## 4. CI Stability",
        "",
        *ci_lines,
        "",
        "## 5. Notable Events",
        "",
        *events_lines,
        "",
        "---",
        "",
        "*This report is generated automatically every Sunday at 12:00 UTC*",
        "*by the System Pulse Weekly workflow (.github/workflows/system-pulse-weekly.yml).*",
        "",
    ]

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate weekly system pulse report")
    parser.add_argument("--output", type=Path, help="Output file path")
    parser.add_argument("--skip-api", action="store_true", help="Skip GitHub API calls")
    parser.add_argument("--days", type=int, default=7, help="Days of soak data to analyze")
    args = parser.parse_args()

    print("System Pulse Generator")
    print("=" * 40)

    # Load data sources
    metrics = load_json(METRICS_PATH)
    if not metrics:
        print("ERROR: Could not load system-metrics.json")
        sys.exit(1)

    registry = load_json(REGISTRY_PATH)
    if not registry:
        print("WARNING: Could not load repo-registry.json")
        registry = {}

    snapshots = load_soak_snapshots(days=args.days)
    print(f"Loaded {len(snapshots)} soak test snapshots")

    commits = fetch_recent_commits(skip_api=args.skip_api)
    print(f"Found {len(commits)} recent commits")

    # Generate report
    report = generate_pulse(metrics, registry, snapshots, commits, skip_api=args.skip_api)

    # Write output
    PULSE_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    output_path = args.output or (PULSE_DIR / f"weekly-{today}.md")

    with open(output_path, "w") as f:
        f.write(report)

    print(f"\nPulse report written: {output_path}")
    print(f"Length: {len(report)} chars, {len(report.splitlines())} lines")

    return 0


if __name__ == "__main__":
    sys.exit(main())
