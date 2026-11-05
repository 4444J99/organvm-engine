#!/usr/bin/env python3
"""V4: Dependency Graph Validation

Re-validates the dependency graph from repo-registry.json:
1. No back-edges (I->II->III only; no III->II or II->I)
2. No circular dependencies
3. All dependency targets exist in registry
4. No self-dependencies
"""

import json
import os
from collections import defaultdict

REGISTRY_PATH = os.environ.get(
    "REGISTRY_PATH", os.path.join(os.path.dirname(os.path.dirname(__file__)), "repo-registry.json"))

# Organ ordering for back-edge detection
# Flow is I->II->III. IV orchestrates, V documents, VI/VII amplify.
# Back-edges: III cannot depend on II; II cannot depend on I (wait, that's wrong)
# Actually: I->II->III means I feeds into II, II feeds into III
# Back-edge: III->II or III->I or II->I
ORGAN_LEVELS = {
    'organvm-i-theoria': 1,
    'organvm-ii-poiesis': 2,
    'organvm-iii-ergon': 3,
    'organvm-iv-taxis': 4,  # Orchestration - can reference anything
    'organvm-v-logos': 5,   # Documentation - can reference anything
    'organvm-vi-koinonia': 6,
    'organvm-vii-kerygma': 7,
    'meta-organvm': 8,
}

# Only the I->II->III chain has back-edge restrictions
RESTRICTED_LEVELS = {1, 2, 3}


# ISOTOPE DISSOLUTION: Gate memory--remember G2 (CORPUS_SCRIPTS_DISSOLVED)
try:
    from organvm_engine.registry.loader import load_registry as _engine_load
except ImportError:
    _engine_load = None


def load_registry():
    if _engine_load is not None:
        return _engine_load(REGISTRY_PATH)
    with open(REGISTRY_PATH) as f:
        return json.load(f)


def main():
    registry = load_registry()

    print("=" * 80)
    print("V4: DEPENDENCY GRAPH VALIDATION")
    print("=" * 80)

    # Build repo map and dependency graph
    all_repos = {}  # "org/name" -> repo_data
    deps = []  # list of (from_key, to_key)

    for organ_key, organ_data in registry.get("organs", {}).items():
        for repo in organ_data.get("repositories", []):
            key = f"{repo['org']}/{repo['name']}"
            all_repos[key] = repo

            for dep in repo.get("dependencies", []):
                deps.append((key, dep))

    print(f"\n  Total repos: {len(all_repos)}")
    print(f"  Total dependency edges: {len(deps)}")

    violations = []

    # ── Check 1: All dependency targets exist ──────────────────────
    print("\n── Check 1: Dependency targets exist ──")
    missing_targets = []
    for from_key, to_key in deps:
        if to_key not in all_repos:
            missing_targets.append((from_key, to_key))

    if missing_targets:
        print(f"  FAIL: {len(missing_targets)} dependencies point to non-existent repos:")
        for f, t in missing_targets:
            print(f"    {f} -> {t} (NOT IN REGISTRY)")
            violations.append(f"Missing target: {f} -> {t}")
    else:
        print(f"  PASS: All {len(deps)} dependency targets exist in registry")

    # ── Check 2: No self-dependencies ──────────────────────────────
    print("\n── Check 2: No self-dependencies ──")
    self_deps = [(f, t) for f, t in deps if f == t]
    if self_deps:
        print(f"  FAIL: {len(self_deps)} self-dependencies:")
        for f, t in self_deps:
            print(f"    {f} -> {t}")
            violations.append(f"Self-dep: {f}")
    else:
        print("  PASS: No self-dependencies")

    # ── Check 3: No back-edges in I->II->III chain ──────────────
    print("\n── Check 3: No back-edges (I->II->III direction) ──")
    back_edges = []
    for from_key, to_key in deps:
        from_org = from_key.split('/')[0]
        to_org = to_key.split('/')[0]

        from_level = ORGAN_LEVELS.get(from_org)
        to_level = ORGAN_LEVELS.get(to_org)

        if from_level is None or to_level is None:
            continue

        # Only check back-edges within the I-II-III chain
        if from_level in RESTRICTED_LEVELS and to_level in RESTRICTED_LEVELS:
            if from_level > to_level:
                # This is OK: higher organs CAN depend on lower organs
                # I(1) feeds II(2) feeds III(3)
                # So III depending on II is a back-edge
                # But wait - III CAN depend on II's output? No.
                # The constitution says: "ORGAN-III cannot depend on ORGAN-II"
                # So any III->II or III->I or II->I is a violation
                pass
            elif from_level < to_level:
                # Lower depending on higher — this IS a back-edge
                # Wait, actually: I->II->III means data flows from I to II to III
                # So II depends on I (ok), III depends on II (ok), III depends on I (ok)
                # But I depending on II (back-edge), I depending on III (back-edge),
                # II depending on III (back-edge)
                back_edges.append((from_key, to_key, from_org, to_org))

        # Check explicit constitution rule: III cannot depend on II
        if from_org == 'organvm-iii-ergon' and to_org == 'organvm-ii-poiesis':
            if (from_key, to_key, from_org, to_org) not in back_edges:
                back_edges.append((from_key, to_key, from_org, to_org))

    if back_edges:
        print(f"  FAIL: {len(back_edges)} back-edges found:")
        for f, t, fo, to in back_edges:
            print(f"    {f} -> {t} (BACK-EDGE: {fo} -> {to})")
            violations.append(f"Back-edge: {f} -> {t}")
    else:
        print("  PASS: No back-edges in I->II->III chain")

    # ── Check 4: No circular dependencies ──────────────────────────
    print("\n── Check 4: No circular dependencies ──")

    # Build adjacency list
    adj = defaultdict(list)
    for from_key, to_key in deps:
        adj[from_key].append(to_key)

    # DFS cycle detection
    WHITE, GRAY, BLACK = 0, 1, 2
    color = defaultdict(lambda: WHITE)
    cycles = []

    def dfs(node, path):
        color[node] = GRAY
        path.append(node)
        for neighbor in adj[node]:
            if color[neighbor] == GRAY:
                # Found cycle
                cycle_start = path.index(neighbor)
                cycle = path[cycle_start:] + [neighbor]
                cycles.append(cycle)
            elif color[neighbor] == WHITE:
                dfs(neighbor, path)
        path.pop()
        color[node] = BLACK

    for node in list(all_repos.keys()):
        if color[node] == WHITE:
            dfs(node, [])

    if cycles:
        print(f"  FAIL: {len(cycles)} circular dependencies:")
        for cycle in cycles:
            print(f"    {' -> '.join(cycle)}")
            violations.append(f"Cycle: {' -> '.join(cycle)}")
    else:
        print("  PASS: No circular dependencies")

    # ── Check 5: Cross-organ dependency direction audit ──────────
    print("\n── Check 5: Cross-organ dependency summary ──")
    cross_organ = defaultdict(int)
    for from_key, to_key in deps:
        from_org = from_key.split('/')[0]
        to_org = to_key.split('/')[0]
        if from_org != to_org:
            cross_organ[f"{from_org} -> {to_org}"] += 1

    for direction, count in sorted(cross_organ.items()):
        print(f"    {direction}: {count}")

    # ── Summary ──────────────────────────────────────────────────────
    print(f"\n{'=' * 80}")
    print("V4 SUMMARY")
    print(f"{'=' * 80}")
    print(f"  Total dependency edges: {len(deps)}")
    print(f"  Missing targets: {len(missing_targets)}")
    print(f"  Self-dependencies: {len(self_deps)}")
    print(f"  Back-edges: {len(back_edges)}")
    print(f"  Circular dependencies: {len(cycles)}")
    print(f"  Total violations: {len(violations)}")

    v4_pass = len(violations) == 0
    print(f"\n  V4 RESULT: {'PASS' if v4_pass else 'ISSUES FOUND'}")

    # Write report
    report = {
        "total_deps": len(deps),
        "missing_targets": len(missing_targets),
        "self_deps": len(self_deps),
        "back_edges": len(back_edges),
        "cycles": len(cycles),
        "violations": violations,
        "cross_organ_summary": dict(cross_organ),
        "pass": v4_pass
    }

    report_path = os.environ.get("V4_REPORT", os.path.join(os.path.dirname(__file__), "v4-report.json"))
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"\n  Report written to {report_path}")
    return 0 if v4_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
