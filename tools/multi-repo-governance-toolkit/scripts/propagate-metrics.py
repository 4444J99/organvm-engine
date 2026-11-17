#!/usr/bin/env python3
"""Propagate metrics from system-metrics.json into whitelisted documentation files.

Thin wrapper around organvm_engine.metrics.propagator — delegates core pattern
matching and propagation to the engine while adding standalone-specific features
(verbose per-line output, whitelist glob resolution, single-file mode).

Usage:
    python3 scripts/propagate-metrics.py                    # corpus-only (default)
    python3 scripts/propagate-metrics.py --dry-run          # preview only
    python3 scripts/propagate-metrics.py --verbose          # show every match
    python3 scripts/propagate-metrics.py --file X.md        # single file only
    python3 scripts/propagate-metrics.py --cross-repo       # all targets from manifest
    python3 scripts/propagate-metrics.py --cross-repo --dry-run  # preview cross-repo
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from organvm_engine.metrics.propagator import (
    SKIP_MARKERS,
    build_patterns,
    copy_json_targets,
    load_manifest,
    propagate_metrics,
    resolve_manifest_files,
)

# ISOTOPE DISSOLUTION: Gate memory--remember G2 (CORPUS_SCRIPTS_DISSOLVED)
from organvm_engine.registry.loader import load_registry as _engine_load

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_METRICS = ROOT / "system-metrics.json"
DEFAULT_TARGETS = ROOT / "metrics-targets.yaml"

# Corpus-only whitelist (used when not in --cross-repo mode)
WHITELIST_GLOBS = [
    "README.md",
    "CLAUDE.md",
    "applications/*.md",
    "applications/shared/*.md",
    "docs/applications/*.md",
    "docs/applications/cover-letters/*.md",
    "docs/essays/09-ai-conductor-methodology.md",
    "docs/operations/*.md",
]


def resolve_whitelist(root: Path) -> list[Path]:
    """Expand whitelist globs into concrete file paths."""
    files: list[Path] = []
    for pattern in WHITELIST_GLOBS:
        files.extend(sorted(root.glob(pattern)))
    seen: set[Path] = set()
    result: list[Path] = []
    for f in files:
        if f not in seen:
            seen.add(f)
            result.append(f)
    return result


@dataclass
class VerboseReplacement:
    """A single line replacement with description, for verbose output."""
    file: Path
    line_num: int
    old_text: str
    new_text: str
    metric: str
    pattern_desc: str


def update_file_verbose(
    filepath: Path,
    patterns: list[tuple[str, re.Pattern, str, str]],
    dry_run: bool,
) -> list[VerboseReplacement]:
    """Apply patterns with verbose tracking. Uses 4-tuple patterns (with desc)."""
    replacements: list[VerboseReplacement] = []
    lines = filepath.read_text().splitlines(keepends=True)
    new_lines: list[str] = []
    changed = False

    for i, line in enumerate(lines, 1):
        if any(marker in line for marker in SKIP_MARKERS):
            new_lines.append(line)
            continue

        new_line = line
        for metric_name, pattern, replacement, desc in patterns:
            match = pattern.search(new_line)
            if match:
                candidate = pattern.sub(replacement, new_line)
                if candidate != new_line:
                    replacements.append(VerboseReplacement(
                        file=filepath,
                        line_num=i,
                        old_text=new_line.rstrip("\n"),
                        new_text=candidate.rstrip("\n"),
                        metric=metric_name,
                        pattern_desc=desc,
                    ))
                    new_line = candidate
                    changed = True

        new_lines.append(new_line)

    if changed and not dry_run:
        filepath.write_text("".join(new_lines))

    return replacements


def _wrap_patterns_with_desc(
    engine_patterns: list[tuple[str, re.Pattern, str]],
) -> list[tuple[str, re.Pattern, str, str]]:
    """Wrap engine 3-tuples into 4-tuples by using metric name as description."""
    return [(name, pat, repl, name) for name, pat, repl in engine_patterns]


def _display_path(filepath: Path) -> str:
    """Show a file path relative to ROOT if inside it, else relative to home."""
    try:
        return str(filepath.relative_to(ROOT))
    except ValueError:
        try:
            return "~/" + str(filepath.relative_to(Path.home()))
        except ValueError:
            return str(filepath)


def print_verbose_summary(
    all_replacements: list[VerboseReplacement], verbose: bool,
) -> None:
    """Print grouped-by-file change report."""
    if not all_replacements:
        print("\nNo changes needed — all files are current.")
        return

    by_file: dict[Path, list[VerboseReplacement]] = {}
    for r in all_replacements:
        by_file.setdefault(r.file, []).append(r)

    by_metric: dict[str, int] = {}
    for r in all_replacements:
        by_metric[r.metric] = by_metric.get(r.metric, 0) + 1

    print(f"\n{'─' * 60}")
    print(f"  {len(all_replacements)} replacement(s) across {len(by_file)} file(s)")
    print(f"{'─' * 60}")

    for filepath, reps in sorted(by_file.items()):
        rel = _display_path(filepath)
        print(f"\n  {rel} ({len(reps)} change{'s' if len(reps) != 1 else ''})")
        for r in reps:
            if verbose:
                print(f"    L{r.line_num} [{r.metric}] {r.pattern_desc}")
                print(f"      - {r.old_text.strip()[:100]}")
                print(f"      + {r.new_text.strip()[:100]}")
            else:
                print(f"    L{r.line_num}: {r.metric} ({r.pattern_desc})")

    print("\n  By metric:")
    for metric, count in sorted(by_metric.items()):
        print(f"    {metric}: {count}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Propagate metrics to documentation",
    )
    parser.add_argument("--metrics", default=str(DEFAULT_METRICS),
                        help="Path to system-metrics.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview changes without writing")
    parser.add_argument("--verbose", action="store_true",
                        help="Show old/new text for every match")
    parser.add_argument("--file", type=str, default=None,
                        help="Process only this file (relative to repo root)")
    parser.add_argument("--cross-repo", action="store_true",
                        help="Read metrics-targets.yaml and propagate")
    parser.add_argument("--targets", default=None,
                        help="Path to metrics-targets.yaml (default: repo root)")
    args = parser.parse_args()

    # Load metrics
    metrics_path = Path(args.metrics)
    if not metrics_path.exists():
        print(
            f"ERROR: {metrics_path} not found. Run calculate-metrics.py first.",
            file=sys.stderr,
        )
        sys.exit(1)

    with open(metrics_path) as f:
        metrics = json.load(f)

    if "computed" not in metrics:
        print(
            f"ERROR: {metrics_path} missing 'computed' section. Wrong schema?",
            file=sys.stderr,
        )
        sys.exit(1)

    # Build patterns from engine (3-tuples) and wrap for verbose mode (4-tuples)
    engine_patterns = build_patterns(metrics)
    verbose_patterns = _wrap_patterns_with_desc(engine_patterns)

    # Cross-repo mode
    if args.cross_repo:
        manifest_path = Path(args.targets) if args.targets else DEFAULT_TARGETS
        if not manifest_path.exists():
            print(f"ERROR: {manifest_path} not found.", file=sys.stderr)
            sys.exit(1)

        manifest = load_manifest(manifest_path)
        mode = "DRY RUN (cross-repo)" if args.dry_run else "PROPAGATING (cross-repo)"

        # Load registry for landing.json transform
        registry_path = ROOT / "repo-registry.json"
        registry = None
        if registry_path.exists():
            registry = _engine_load(registry_path)

        # JSON copies
        json_count = copy_json_targets(
            manifest, metrics, args.dry_run, registry=registry,
        )
        print(f"[{mode}] {json_count} JSON copy target(s)")

        # Markdown targets from manifest
        files = resolve_manifest_files(manifest, ROOT)
        print(f"[{mode}] {len(files)} markdown file(s), {len(engine_patterns)} patterns")

        if args.verbose:
            all_replacements: list[VerboseReplacement] = []
            for filepath in files:
                reps = update_file_verbose(filepath, verbose_patterns, args.dry_run)
                all_replacements.extend(reps)
            print_verbose_summary(all_replacements, args.verbose)
        else:
            result = propagate_metrics(metrics, files, dry_run=args.dry_run)
            print(
                f"  {result.replacements} replacement(s) "
                f"across {result.files_changed} file(s)"
            )

        if args.dry_run:
            print("\n  Run without --dry-run to apply these changes.")
        return

    # Single-file or corpus-only mode
    if args.file:
        target = ROOT / args.file
        if not target.exists():
            print(f"ERROR: {target} not found.", file=sys.stderr)
            sys.exit(1)
        files = [target]
    else:
        files = resolve_whitelist(ROOT)

    if not files:
        print("No target files found.")
        return

    mode = "DRY RUN" if args.dry_run else "PROPAGATING"
    print(f"[{mode}] {len(files)} file(s), {len(engine_patterns)} patterns")

    if args.verbose:
        all_replacements = []
        for filepath in files:
            reps = update_file_verbose(filepath, verbose_patterns, args.dry_run)
            all_replacements.extend(reps)
        print_verbose_summary(all_replacements, args.verbose)
    else:
        result = propagate_metrics(metrics, files, dry_run=args.dry_run)
        print(
            f"  {result.replacements} replacement(s) "
            f"across {result.files_changed} file(s)"
        )

    if args.dry_run:
        print("\n  Run without --dry-run to apply these changes.")


if __name__ == "__main__":
    main()
