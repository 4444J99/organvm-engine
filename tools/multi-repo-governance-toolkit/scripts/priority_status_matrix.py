#!/usr/bin/env python3
"""priority_status_matrix.py — Cross-reference task-priorities and prompt-atoms.

Builds priority x status matrices for both stores, identifies priority inversions,
domain burndown, recency analysis, agent analysis, and writes actionable output
to priority-status-matrix.jsonl alongside a printed report.

stdlib only.
"""

import json
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE = Path(__file__).resolve().parent.parent
ATOMS_DIR = BASE / "data" / "atoms"
TASK_FILE = ATOMS_DIR / "task-priorities.jsonl"
PROMPT_FILE = ATOMS_DIR / "prompt-atoms.jsonl"
OUTPUT_FILE = ATOMS_DIR / "priority-status-matrix.jsonl"

PRIORITY_ORDER = ["P0", "P1", "P2", "P3"]
PROMPT_STATUSES = ["OPEN", "PARTIAL", "DEFERRED", "FAILED", "ANSWERED"]
TASK_STATUSES = ["pending", "completed"]


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------
def load_jsonl(path: Path) -> list[dict]:
    records = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


# ---------------------------------------------------------------------------
# 1. Priority x Status matrix
# ---------------------------------------------------------------------------
def build_matrix(records: list[dict], statuses: list[str]) -> dict[str, dict[str, int]]:
    matrix: dict[str, dict[str, int]] = {
        p: {s: 0 for s in statuses} for p in PRIORITY_ORDER
    }
    for r in records:
        p = r.get("priority", "P3")
        s = r.get("status", "unknown")
        if p in matrix and s in matrix[p]:
            matrix[p][s] += 1
    return matrix


def print_matrix(label: str, matrix: dict, statuses: list[str]) -> None:
    col_w = max(len(s) for s in statuses) + 2
    header = f"{'':>6}" + "".join(f"{s:>{col_w}}" for s in statuses) + f"{'TOTAL':>{col_w}}"
    print(f"\n{'=' * len(header)}")
    print(f"  {label}")
    print(f"{'=' * len(header)}")
    print(header)
    print("-" * len(header))
    for p in PRIORITY_ORDER:
        row = matrix.get(p, {})
        total = sum(row.values())
        cells = "".join(f"{row.get(s, 0):>{col_w}}" for s in statuses)
        print(f"{p:>6}{cells}{total:>{col_w}}")
    # column totals
    col_totals = {s: sum(matrix[p].get(s, 0) for p in PRIORITY_ORDER) for s in statuses}
    grand = sum(col_totals.values())
    totals_row = "".join(f"{col_totals[s]:>{col_w}}" for s in statuses)
    print("-" * len(header))
    print(f"{'TOTAL':>6}{totals_row}{grand:>{col_w}}")


# ---------------------------------------------------------------------------
# 2. Priority inversions (P3 ANSWERED while P0/P1 OPEN/PARTIAL/DEFERRED)
# ---------------------------------------------------------------------------
def detect_inversions(prompt_matrix: dict) -> list[dict]:
    inversions = []
    # For each lower-priority tier that has resolved work, check if higher tiers have unresolved
    unresolved = {"OPEN", "PARTIAL", "DEFERRED", "FAILED"}
    resolved = {"ANSWERED"}

    for hi_idx, hi_p in enumerate(PRIORITY_ORDER):
        hi_unresolved = sum(prompt_matrix[hi_p].get(s, 0) for s in unresolved)
        if hi_unresolved == 0:
            continue
        for lo_p in PRIORITY_ORDER[hi_idx + 1:]:
            lo_resolved = sum(prompt_matrix[lo_p].get(s, 0) for s in resolved)
            if lo_resolved > 0 and hi_unresolved > 0:
                inversions.append({
                    "high_priority": hi_p,
                    "high_unresolved": hi_unresolved,
                    "low_priority": lo_p,
                    "low_resolved": lo_resolved,
                    "severity": f"{hi_p} has {hi_unresolved} unresolved while {lo_p} has {lo_resolved} resolved",
                })
    return inversions


# ---------------------------------------------------------------------------
# 3. Domain burndown
# ---------------------------------------------------------------------------
def domain_burndown(records: list[dict], unresolved_statuses: set[str]) -> list[dict]:
    domain_counts: dict[str, dict] = defaultdict(lambda: {"total": 0, "unresolved": 0, "p0_open": 0, "p1_open": 0})
    for r in records:
        d = r.get("domain", "unknown")
        domain_counts[d]["total"] += 1
        if r.get("status") in unresolved_statuses:
            domain_counts[d]["unresolved"] += 1
            if r.get("priority") == "P0":
                domain_counts[d]["p0_open"] += 1
            elif r.get("priority") == "P1":
                domain_counts[d]["p1_open"] += 1

    result = []
    for domain, counts in sorted(domain_counts.items(), key=lambda x: -x[1]["unresolved"]):
        pct = (counts["unresolved"] / counts["total"] * 100) if counts["total"] else 0
        result.append({
            "domain": domain,
            "total": counts["total"],
            "unresolved": counts["unresolved"],
            "unresolved_pct": round(pct, 1),
            "p0_open": counts["p0_open"],
            "p1_open": counts["p1_open"],
        })
    return result


# ---------------------------------------------------------------------------
# 4. Recency analysis — bucket by year
# ---------------------------------------------------------------------------
def recency_analysis(prompt_records: list[dict]) -> list[dict]:
    year_buckets: dict[str, dict] = defaultdict(lambda: {"total": 0, "open": 0, "answered": 0, "other": 0})
    for r in prompt_records:
        ts = r.get("source", {}).get("timestamp")
        if not ts:
            year = "unknown"
        else:
            try:
                year = str(datetime.fromisoformat(ts.replace("Z", "+00:00")).year)
            except (ValueError, TypeError):
                year = "unknown"
        status = r.get("status", "unknown")
        year_buckets[year]["total"] += 1
        if status == "OPEN":
            year_buckets[year]["open"] += 1
        elif status == "ANSWERED":
            year_buckets[year]["answered"] += 1
        else:
            year_buckets[year]["other"] += 1

    result = []
    for year in sorted(year_buckets.keys()):
        b = year_buckets[year]
        open_pct = (b["open"] / b["total"] * 100) if b["total"] else 0
        result.append({
            "year": year,
            "total": b["total"],
            "open": b["open"],
            "answered": b["answered"],
            "other_unresolved": b["other"],
            "open_pct": round(open_pct, 1),
        })
    return result


# ---------------------------------------------------------------------------
# 5. Agent analysis — unresolved P0/P1 by provider
# ---------------------------------------------------------------------------
def agent_analysis(prompt_records: list[dict]) -> list[dict]:
    agent_data: dict[str, dict] = defaultdict(
        lambda: {"total": 0, "p0_unresolved": 0, "p1_unresolved": 0, "total_unresolved": 0}
    )
    unresolved = {"OPEN", "PARTIAL", "DEFERRED", "FAILED"}
    for r in prompt_records:
        agent = r.get("agent", "unknown")
        agent_data[agent]["total"] += 1
        if r.get("status") in unresolved:
            agent_data[agent]["total_unresolved"] += 1
            if r.get("priority") == "P0":
                agent_data[agent]["p0_unresolved"] += 1
            elif r.get("priority") == "P1":
                agent_data[agent]["p1_unresolved"] += 1

    result = []
    for agent, d in sorted(agent_data.items(), key=lambda x: -(x[1]["p0_unresolved"] + x[1]["p1_unresolved"])):
        result.append({
            "agent": agent,
            "total_prompts": d["total"],
            "total_unresolved": d["total_unresolved"],
            "p0_unresolved": d["p0_unresolved"],
            "p1_unresolved": d["p1_unresolved"],
            "critical_load": d["p0_unresolved"] + d["p1_unresolved"],
        })
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    print("Loading task-priorities.jsonl ...")
    tasks = load_jsonl(TASK_FILE)
    print(f"  {len(tasks):,} records")

    print("Loading prompt-atoms.jsonl ...")
    prompts = load_jsonl(PROMPT_FILE)
    print(f"  {len(prompts):,} records")

    # --- 1. Matrices ---
    task_matrix = build_matrix(tasks, TASK_STATUSES)
    prompt_matrix = build_matrix(prompts, PROMPT_STATUSES)

    print_matrix("TASK-PRIORITIES: Priority x Status", task_matrix, TASK_STATUSES)
    print_matrix("PROMPT-ATOMS: Priority x Status", prompt_matrix, PROMPT_STATUSES)

    # --- 2. Priority inversions ---
    inversions = detect_inversions(prompt_matrix)
    print(f"\n{'=' * 60}")
    print("  PRIORITY INVERSIONS (prompt-atoms)")
    print(f"{'=' * 60}")
    if inversions:
        for inv in inversions:
            print(f"  ! {inv['severity']}")
    else:
        print("  None detected.")

    # --- 3. Domain burndown ---
    # Merge both stores by shared key for combined view
    prompt_unresolved = {"OPEN", "PARTIAL", "DEFERRED", "FAILED"}
    task_unresolved = {"pending"}

    prompt_burndown = domain_burndown(prompts, prompt_unresolved)
    task_burndown = domain_burndown(tasks, task_unresolved)

    print(f"\n{'=' * 80}")
    print("  DOMAIN BURNDOWN — PROMPT-ATOMS (top 15 by unresolved)")
    print(f"{'=' * 80}")
    print(f"  {'Domain':<20} {'Total':>8} {'Unresolved':>12} {'%':>7} {'P0':>6} {'P1':>6}")
    print(f"  {'-'*60}")
    for row in prompt_burndown[:15]:
        print(f"  {row['domain']:<20} {row['total']:>8} {row['unresolved']:>12} {row['unresolved_pct']:>6.1f}% {row['p0_open']:>6} {row['p1_open']:>6}")

    print(f"\n{'=' * 80}")
    print("  DOMAIN BURNDOWN — TASK-PRIORITIES (top 15 by unresolved)")
    print(f"{'=' * 80}")
    print(f"  {'Domain':<20} {'Total':>8} {'Unresolved':>12} {'%':>7} {'P0':>6} {'P1':>6}")
    print(f"  {'-'*60}")
    for row in task_burndown[:15]:
        print(f"  {row['domain']:<20} {row['total']:>8} {row['unresolved']:>12} {row['unresolved_pct']:>6.1f}% {row['p0_open']:>6} {row['p1_open']:>6}")

    # --- 4. Recency analysis ---
    recency = recency_analysis(prompts)
    print(f"\n{'=' * 70}")
    print("  RECENCY ANALYSIS — Prompt-atoms by year")
    print(f"{'=' * 70}")
    print(f"  {'Year':<10} {'Total':>8} {'OPEN':>8} {'ANSWERED':>10} {'Other':>8} {'Open%':>8}")
    print(f"  {'-'*52}")
    for row in recency:
        print(f"  {row['year']:<10} {row['total']:>8} {row['open']:>8} {row['answered']:>10} {row['other_unresolved']:>8} {row['open_pct']:>7.1f}%")

    # --- 5. Agent analysis ---
    agents = agent_analysis(prompts)
    print(f"\n{'=' * 80}")
    print("  AGENT ANALYSIS — Unresolved P0/P1 by provider")
    print(f"{'=' * 80}")
    print(f"  {'Agent':<12} {'Total':>8} {'Unresolved':>12} {'P0':>6} {'P1':>6} {'Critical':>10}")
    print(f"  {'-'*56}")
    for row in agents:
        print(f"  {row['agent']:<12} {row['total_prompts']:>8} {row['total_unresolved']:>12} {row['p0_unresolved']:>6} {row['p1_unresolved']:>6} {row['critical_load']:>10}")

    # --- 6. Actionable insights ---
    # Compute key metrics for the summary
    total_prompt_unresolved = sum(1 for p in prompts if p.get("status") in prompt_unresolved)
    total_task_pending = sum(1 for t in tasks if t.get("status") in task_unresolved)
    prompt_matrix["P0"].get("OPEN", 0) + prompt_matrix["P0"].get("PARTIAL", 0)
    task_p0_pending = task_matrix["P0"].get("pending", 0)

    # Worst domain by combined critical mass
    combined_domains: dict[str, int] = defaultdict(int)
    for row in prompt_burndown:
        combined_domains[row["domain"]] += row["p0_open"] + row["p1_open"]
    for row in task_burndown:
        combined_domains[row["domain"]] += row["p0_open"] + row["p1_open"]
    worst_domains = sorted(combined_domains.items(), key=lambda x: -x[1])[:5]

    # Worst agent
    worst_agent = agents[0] if agents else None

    print(f"\n{'=' * 70}")
    print("  ACTIONABLE INSIGHTS")
    print(f"{'=' * 70}")

    prompt_pct = total_prompt_unresolved / len(prompts) * 100
    task_pct = total_task_pending / len(tasks) * 100
    p0_prompt_unresolved = sum(prompt_matrix["P0"].get(s, 0) for s in prompt_unresolved)
    combined = total_prompt_unresolved + total_task_pending

    print("\n  1. SCALE OF UNRESOLVED WORK")
    print(f"     - Prompt-atoms: {total_prompt_unresolved:,} / {len(prompts):,} unresolved ({prompt_pct:.1f}%)")
    print(f"     - Task-priorities: {total_task_pending:,} / {len(tasks):,} pending ({task_pct:.1f}%)")
    print(f"     - Combined open backlog: {combined:,} items")

    print("\n  2. CRITICAL P0 EXPOSURE")
    print(f"     - Prompt-atoms P0 unresolved: {p0_prompt_unresolved}")
    print(f"     - Task-priorities P0 pending: {task_p0_pending}")
    print("     - These must be triaged before any P2/P3 work proceeds.")

    print(f"\n  3. PRIORITY INVERSIONS: {len(inversions)} detected")
    if inversions:
        for inv in inversions:
            print(f"     - {inv['severity']}")
    else:
        print("     None detected -- but this is mechanical, not strategic.")
        print("     P3 ANSWERED items are old conversational prompts, not proof")
        print("     that low-priority work was deliberately chosen over critical work.")

    print("\n  4. WORST DOMAINS (combined P0+P1 critical mass)")
    for dom, count in worst_domains:
        if count > 0:
            print(f"     - {dom}: {count} critical items")

    if worst_agent:
        wa = worst_agent
        print("\n  5. AGENT HOTSPOT")
        print(f"     - {wa['agent']}: {wa['critical_load']} unresolved P0/P1 items")
        print(f"       ({wa['p0_unresolved']} P0, {wa['p1_unresolved']} P1)")
        print(f"       out of {wa['total_prompts']:,} total prompts")

    max_open_year = max(recency, key=lambda r: r["open_pct"]) if recency else None
    if max_open_year and max_open_year["open_pct"] > 0:
        bias = "more" if max_open_year["year"] >= "2025" else "NOT more"
        print("\n  6. RECENCY BIAS")
        print(f"     - Year {max_open_year['year']} has highest OPEN rate: {max_open_year['open_pct']:.1f}%")
        print(f"       ({max_open_year['open']} OPEN out of {max_open_year['total']} total)")
        print(f"     - Newer items are {bias} likely to be OPEN.")

    # --- 7. Write output ---
    output_records = []
    output_records.append({"section": "task_matrix", "data": task_matrix})
    output_records.append({"section": "prompt_matrix", "data": prompt_matrix})
    output_records.append({"section": "priority_inversions", "data": inversions})
    output_records.append({"section": "domain_burndown_prompts", "data": prompt_burndown})
    output_records.append({"section": "domain_burndown_tasks", "data": task_burndown})
    output_records.append({"section": "recency_analysis", "data": recency})
    output_records.append({"section": "agent_analysis", "data": agents})
    output_records.append({
        "section": "summary",
        "data": {
            "total_prompts": len(prompts),
            "total_tasks": len(tasks),
            "prompt_unresolved": total_prompt_unresolved,
            "task_pending": total_task_pending,
            "combined_backlog": total_prompt_unresolved + total_task_pending,
            "inversions_detected": len(inversions),
            "worst_domains": worst_domains[:5],
            "worst_agent": worst_agent["agent"] if worst_agent else None,
            "generated_at": datetime.now().isoformat(),
        },
    })

    with open(OUTPUT_FILE, "w", encoding="utf-8") as fh:
        for rec in output_records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"\n  Output written to {OUTPUT_FILE}")
    print(f"  {len(output_records)} sections, {os.path.getsize(OUTPUT_FILE):,} bytes")


if __name__ == "__main__":
    main()
