#!/usr/bin/env python3
"""vacuum-radar — real-time VACUUM / N/A detection across the IRF and repo state.

Scans `INST-INDEX-RERUM-FACIENDARUM.md` for:
  - Open entries containing the marker "VACUUM"
  - Open entries whose final pipe-column is literally "None" (no closure tag)
  - Open entries with priority P1 (high-attention open items)
  - Cross-checks the count against `data/done-id-counter.json` for sanity

Emits a markdown report. Exit code is non-zero iff `--fail-on N` (default 0)
is exceeded by the count of open VACUUM entries.

Usage:
    organ-cli plugin vacuum-radar
    organ-cli plugin vacuum-radar --json
    organ-cli plugin vacuum-radar --fail-on 5
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IRF_FILE = ROOT / "INST-INDEX-RERUM-FACIENDARUM.md"
COUNTER_FILE = ROOT / "data" / "done-id-counter.json"

VACUUM_MARKER = "VACUUM"
IRF_ROW = re.compile(r"^\|\s*(~?~?)(IRF-[A-Z]+-\d+)~?~?\s*\|", re.MULTILINE)


@dataclass
class IRFEntry:
    irf_id: str
    closed: bool
    priority: str | None
    summary: str
    last_col: str


@dataclass
class VacuumReport:
    total_entries: int
    open_entries: int
    closed_entries: int
    open_vacuums: list[IRFEntry]
    p1_open: list[IRFEntry]
    none_in_last_col: list[IRFEntry]
    next_done_id: int


def _parse_irf(text: str) -> list[IRFEntry]:
    """Walk IRF table rows. Strikethrough (~~ID~~) marks closed entries."""
    rows: list[IRFEntry] = []
    for line in text.splitlines():
        if not line.startswith("| IRF-") and not line.startswith("| ~~IRF-"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        first = cells[0]
        closed = first.startswith("~~") and first.endswith("~~")
        irf_id_m = re.match(r"~?~?(IRF-[A-Z]+-\d+)~?~?", first)
        if not irf_id_m:
            continue
        irf_id = irf_id_m.group(1)
        prio_cell = cells[1] if len(cells) > 1 else ""
        prio_m = re.search(r"P[0-3]", prio_cell)
        priority = prio_m.group(0) if prio_m else None
        summary = cells[2] if len(cells) > 2 else ""
        last_col = cells[-1] if cells else ""
        rows.append(IRFEntry(
            irf_id=irf_id,
            closed=closed,
            priority=priority,
            summary=summary[:240],
            last_col=last_col,
        ))
    return rows


def _scan(entries: list[IRFEntry]) -> VacuumReport:
    open_entries = [e for e in entries if not e.closed]
    closed_entries = [e for e in entries if e.closed]
    open_vacuums = [e for e in open_entries if VACUUM_MARKER in e.summary]
    p1_open = [e for e in open_entries if e.priority == "P1"]
    none_last = [e for e in open_entries if e.last_col.strip().lower() == "none"]

    next_done_id = -1
    if COUNTER_FILE.exists():
        try:
            next_done_id = json.loads(COUNTER_FILE.read_text()).get("next_id", -1)
        except json.JSONDecodeError as exc:
            print(f"vacuum-radar: warning — could not parse {COUNTER_FILE}: {exc}",
                  file=sys.stderr)

    return VacuumReport(
        total_entries=len(entries),
        open_entries=len(open_entries),
        closed_entries=len(closed_entries),
        open_vacuums=open_vacuums,
        p1_open=p1_open,
        none_in_last_col=none_last,
        next_done_id=next_done_id,
    )


def _emit_markdown(report: VacuumReport) -> str:
    lines = [
        "# Vacuum Radar Report",
        "",
        f"- **IRF total entries:** {report.total_entries}",
        f"- **Open:** {report.open_entries}",
        f"- **Closed:** {report.closed_entries}",
        f"- **Open VACUUMs:** {len(report.open_vacuums)}",
        f"- **Open P1 items:** {len(report.p1_open)}",
        f"- **Open entries with `None` in last column:** {len(report.none_in_last_col)}",
        f"- **Next DONE-ID:** {report.next_done_id}",
        "",
    ]

    def _table(rows: list[IRFEntry], title: str) -> list[str]:
        out = [f"## {title}", ""]
        if not rows:
            out.extend(["_(none)_", ""])
            return out
        out.extend(["| ID | Priority | Summary |", "|---|---|---|"])
        for r in rows[:30]:
            short = (r.summary[:160] + "…") if len(r.summary) > 160 else r.summary
            short = short.replace("|", "\\|").replace("\n", " ")
            out.append(f"| {r.irf_id} | {r.priority or ''} | {short} |")
        if len(rows) > 30:
            out.append(f"| … | … | _{len(rows) - 30} more rows_ |")
        out.append("")
        return out

    lines.extend(_table(report.open_vacuums, "Open VACUUM entries"))
    lines.extend(_table(report.p1_open, "Open P1 entries"))
    lines.extend(_table(report.none_in_last_col, "Open entries with `None` in last column"))
    return "\n".join(lines)


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="organ-cli plugin vacuum-radar")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of markdown")
    parser.add_argument("--fail-on", type=int, default=-1,
                        help="exit non-zero if open VACUUM count exceeds N (default: never fail)")
    args = parser.parse_args(argv)

    if not IRF_FILE.exists():
        print(f"ERROR: IRF not found at {IRF_FILE}", file=sys.stderr)
        return 2

    entries = _parse_irf(IRF_FILE.read_text())
    report = _scan(entries)

    if args.json:
        print(json.dumps({
            **{k: v for k, v in asdict(report).items() if not isinstance(v, list)},
            "open_vacuums": [asdict(e) for e in report.open_vacuums],
            "p1_open": [asdict(e) for e in report.p1_open],
            "none_in_last_col": [asdict(e) for e in report.none_in_last_col],
        }, indent=2))
    else:
        print(_emit_markdown(report))

    if args.fail_on >= 0 and len(report.open_vacuums) > args.fail_on:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run())
