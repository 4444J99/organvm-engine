#!/usr/bin/env python3
"""session-orchestrator — master sequencer for Phase 0→3 chain.

Reads the active handoff envelope and reports the current phase plus the next
unblocked actions. Designed to be the first plugin a new session invokes.

Phase model (per `docs/operations/operational-cadence.md`):
    Phase 0 — Substrate / Domain Scaffolding (DIWS)
    Phase 1 — Documentation / Specification
    Phase 2 — Validation / Micro-validation
    Phase 3 — Integration / Release

Usage:
    organ-cli plugin session-orchestrator                # print phase + actions
    organ-cli plugin session-orchestrator --handoff PATH # use a different envelope
    organ-cli plugin session-orchestrator --json         # machine-readable
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HANDOFF = ROOT / ".conductor" / "active-handoff.md"


@dataclass
class Action:
    priority: str
    title: str
    irf_id: str | None
    body: str


@dataclass
class OrchestratorReport:
    handoff_path: str
    handoff_session: str | None
    handoff_phase: str | None
    completed_count: int
    open_actions: list[Action]
    next_action: Action | None
    warnings: list[str]


def _parse_handoff(text: str) -> OrchestratorReport:
    session_match = re.search(r"\*\*From:\*\*\s*([^|]+)", text)
    phase_match = re.search(r"\*\*Phase:\*\*\s*([^\n]+)", text)
    session = session_match.group(1).strip() if session_match else None
    phase = phase_match.group(1).strip() if phase_match else None

    completed = re.findall(r"^- \[x\]\s+", text, flags=re.MULTILINE)

    actions: list[Action] = []
    blocks = re.split(r"^###\s+", text, flags=re.MULTILINE)
    for block in blocks:
        header_match = re.match(r"(P[0-3])\s+—\s+([^\n]+)", block)
        if not header_match:
            continue
        priority = header_match.group(1)
        items = re.findall(r"^\d+\.\s+\*\*(IRF-[A-Z]+-\d+)?:?\*?\*?\s*([^\n]+)\n", block, flags=re.MULTILINE)
        for irf_id, title in items:
            body_match = re.search(
                rf"^\d+\.\s+\*\*{re.escape(irf_id) if irf_id else ''}[^\n]+\n((?:\s{{2,}}[^\n]+\n)+)",
                block,
                flags=re.MULTILINE,
            )
            body = body_match.group(1).strip() if body_match else ""
            actions.append(Action(priority=priority, title=title.strip().rstrip(":"), irf_id=irf_id or None, body=body))

    warnings: list[str] = []
    if not actions:
        warnings.append("no parseable actions in handoff — check envelope format")
    if session is None:
        warnings.append("no session ID found in handoff")
    if phase is None:
        warnings.append("no phase declaration found in handoff")

    next_action = actions[0] if actions else None

    return OrchestratorReport(
        handoff_path=str(DEFAULT_HANDOFF),
        handoff_session=session,
        handoff_phase=phase,
        completed_count=len(completed),
        open_actions=actions,
        next_action=next_action,
        warnings=warnings,
    )


def _emit_markdown(report: OrchestratorReport) -> str:
    lines = [
        "# Session Orchestrator Report",
        "",
        f"- **Handoff envelope:** `{report.handoff_path}`",
        f"- **Originating session:** {report.handoff_session or '(unknown)'}",
        f"- **Phase per envelope:** {report.handoff_phase or '(unknown)'}",
        f"- **Completed items in envelope:** {report.completed_count}",
        "",
        "## Open actions (in declared order)",
        "",
    ]
    if not report.open_actions:
        lines.append("_(none parsed)_")
    else:
        for i, a in enumerate(report.open_actions, 1):
            tag = f" [{a.irf_id}]" if a.irf_id else ""
            lines.append(f"{i}. **{a.priority}**{tag} — {a.title}")
    lines.append("")
    if report.next_action:
        n = report.next_action
        lines.extend([
            "## Recommended next action",
            "",
            f"**{n.priority}** {n.irf_id or ''} — {n.title}",
            "",
        ])
    if report.warnings:
        lines.extend(["## Warnings", ""])
        for w in report.warnings:
            lines.append(f"- ⚠ {w}")
        lines.append("")
    return "\n".join(lines)


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="organ-cli plugin session-orchestrator")
    parser.add_argument("--handoff", default=str(DEFAULT_HANDOFF),
                        help="path to active-handoff.md (default: %(default)s)")
    parser.add_argument("--json", action="store_true",
                        help="emit machine-readable JSON instead of markdown")
    args = parser.parse_args(argv)

    handoff = Path(args.handoff)
    if not handoff.exists():
        print(f"ERROR: handoff envelope not found at {handoff}", file=sys.stderr)
        return 1

    report = _parse_handoff(handoff.read_text())
    if args.json:
        print(json.dumps({
            **{k: v for k, v in asdict(report).items() if k != "open_actions" and k != "next_action"},
            "open_actions": [asdict(a) for a in report.open_actions],
            "next_action": asdict(report.next_action) if report.next_action else None,
        }, indent=2))
    else:
        print(_emit_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(run())
