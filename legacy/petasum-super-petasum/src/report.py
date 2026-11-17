"""Generate reports from governance data."""

from __future__ import annotations

from .governance import GovernanceReport
from .tracker import ObligationTracker


def generate_system_report(
    tracker: ObligationTracker,
    governance: GovernanceReport,
) -> str:
    """Generate a full system health report as markdown."""
    lines = ["# System Governance Report", ""]

    # Obligation summary
    summary = tracker.summary()
    lines.append("## Promotion Obligations")
    lines.append(f"- Total: {summary['total']}")
    lines.append(f"- Pending: {summary['pending']}")
    lines.append(f"- Discharged: {summary['discharged']}")
    lines.append(f"- Overdue: {summary['overdue']}")
    lines.append("")

    # Pending obligations
    if tracker.pending:
        lines.append("### Pending Obligations")
        for ob in tracker.pending:
            lines.append(
                f"- [{ob.obligation_type}] {ob.source_organ} \u2192 {ob.target_organ}: {ob.description}"
            )
        lines.append("")

    # Governance health
    lines.append("## Governance Health")
    lines.append(governance.summary())
    lines.append("")

    if governance.fail_count > 0:
        lines.append("### Failing Checks")
        for check in governance.checks:
            if not check.passed:
                lines.append(f"- {check.name}: {check.message}")
        lines.append("")

    return "\n".join(lines)


def generate_organ_report(
    organ: str,
    tracker: ObligationTracker,
    governance: GovernanceReport,
) -> str:
    """Generate a report for a specific organ."""
    lines = [f"# ORGAN-{organ} Report", ""]

    organ_obligations = tracker.by_organ(organ)
    lines.append(f"## Obligations ({len(organ_obligations)})")
    for ob in organ_obligations:
        lines.append(f"- [{ob.status.value}] {ob.description}")
    lines.append("")

    organ_checks = governance.by_organ(organ)
    passed = sum(1 for c in organ_checks if c.passed)
    lines.append(f"## Health Checks ({passed}/{len(organ_checks)} passing)")
    for check in organ_checks:
        mark = "\u2713" if check.passed else "\u2717"
        lines.append(f"- {mark} {check.message}")

    return "\n".join(lines)
