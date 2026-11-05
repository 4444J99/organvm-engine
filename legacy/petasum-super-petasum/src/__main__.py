"""CLI entry point for petasum-super-petasum.

Usage:
    python -m src evaluate --registry registry.json
    python -m src audit --registry registry.json [--organ I]
    python -m src report --registry registry.json [--organ I]
"""

from __future__ import annotations

import argparse
import json
import sys

from .governance import (
    GovernanceReport,
    check_ci_health,
    check_documentation_coverage,
)
from .report import generate_organ_report, generate_system_report
from .tracker import ObligationTracker


def load_registry(path: str) -> list[dict]:
    """Load repository data from a registry JSON file."""
    with open(path) as f:
        data = json.load(f)
    repos = data.get("repositories", data) if isinstance(data, dict) else data
    if isinstance(repos, dict):
        return list(repos.values())
    return repos


def cmd_evaluate(args: argparse.Namespace) -> int:
    """Run governance evaluation and print pass/fail summary."""
    repos = load_registry(args.registry)
    report = GovernanceReport()
    for check in check_ci_health(repos):
        report.add_check(check)
    for check in check_documentation_coverage(repos):
        report.add_check(check)

    print(report.summary())
    return 0 if report.passed else 1


def cmd_audit(args: argparse.Namespace) -> int:
    """Run compliance audit across organs."""
    repos = load_registry(args.registry)
    report = GovernanceReport()
    for check in check_ci_health(repos):
        report.add_check(check)
    for check in check_documentation_coverage(repos):
        report.add_check(check)

    if args.organ:
        organ_checks = report.by_organ(args.organ)
        failures = [c for c in organ_checks if not c.passed]
    else:
        failures = [c for c in report.checks if not c.passed]

    if failures:
        print(f"AUDIT FAIL: {len(failures)} issue(s) found")
        for f in failures:
            print(f"  - [{f.organ or 'global'}] {f.name}: {f.message}")
        return 1

    scope = f"ORGAN-{args.organ}" if args.organ else "system-wide"
    print(f"AUDIT PASS: {scope} — all checks passing")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    """Generate a governance report as markdown."""
    repos = load_registry(args.registry)
    report = GovernanceReport()
    for check in check_ci_health(repos):
        report.add_check(check)
    for check in check_documentation_coverage(repos):
        report.add_check(check)

    tracker = ObligationTracker()

    if args.organ:
        output = generate_organ_report(args.organ, tracker, report)
    else:
        output = generate_system_report(tracker, report)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        print(f"Report written to {args.output}")
    else:
        print(output)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch to the appropriate subcommand."""
    parser = argparse.ArgumentParser(
        prog="petasum-super-petasum",
        description="Cross-organ governance tracking and reporting",
    )
    sub = parser.add_subparsers(dest="command")

    # evaluate
    p_eval = sub.add_parser("evaluate", help="Run governance evaluation")
    p_eval.add_argument("--registry", required=True, help="Path to registry JSON")

    # audit
    p_audit = sub.add_parser("audit", help="Run compliance audit")
    p_audit.add_argument("--registry", required=True, help="Path to registry JSON")
    p_audit.add_argument("--organ", help="Filter to specific organ (e.g. I, II)")

    # report
    p_report = sub.add_parser("report", help="Generate governance report")
    p_report.add_argument("--registry", required=True, help="Path to registry JSON")
    p_report.add_argument("--organ", help="Report for specific organ")
    p_report.add_argument("--output", "-o", help="Output file path")

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 2

    dispatch = {
        "evaluate": cmd_evaluate,
        "audit": cmd_audit,
        "report": cmd_report,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
