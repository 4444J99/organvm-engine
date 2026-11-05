#!/usr/bin/env python3
"""Quality filter for vacuum-atoms JSONL files.

Separates signal from noise in N/A-detection atom files. Noise categories:
  - Code artifacts: type hints (str | None), null checks, undefined guards
  - Markup artifacts: HTML tags, CSS properties with 'none' values
  - Job posting boilerplate: supervisory responsibilities, EEO, duties
  - Shell artifacts: /dev/null redirects, 2>/dev/null patterns
  - Too short: context under 30 chars with no actionable content
  - Near-duplicates: context strings that match within edit distance

Outputs two JSONL files: *-signal.jsonl and *-noise.jsonl, plus a stats report.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path


# ---------------------------------------------------------------------------
# Noise pattern definitions
# ---------------------------------------------------------------------------

# File extensions that are almost always code artifacts, not user content
CODE_ARTIFACT_EXTENSIONS: set[str] = {
    "pyi", "pyc", "pyo",  # Python stubs / bytecode
    "d.ts", "d.mts",       # TypeScript declaration files
    "map",                  # Source maps
    "min.js", "min.css",   # Minified bundles
    "wasm",                 # WebAssembly
    "lock",                 # Lock files
}

# Patterns matched against the full source_file path
SOURCE_FILE_NOISE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"typeshed-fallback/", re.I),
    re.compile(r"node_modules/", re.I),
    re.compile(r"\.vscode/extensions/", re.I),
    re.compile(r"vscode-pylance", re.I),
    re.compile(r"dist/typeshed", re.I),
    re.compile(r"/site-packages/", re.I),
    re.compile(r"__pycache__/", re.I),
    # VSCode/IDE extension bundles (JS, TS, etc.)
    re.compile(r"/extensions/[^/]+/(?:dist|out|node_modules)/", re.I),
    re.compile(r"Wires/extensions/", re.I),
    # Git internal files
    re.compile(r"\.git/(?:logs|objects|refs|hooks)/", re.I),
    # Scoop/Homebrew package internals
    re.compile(r"scoop/(?:buckets|apps)/", re.I),
    # Bundled/compiled artifacts
    re.compile(r"/dist/[^/]+\.(?:js|cjs|mjs)$", re.I),
]

# Context-level regex patterns -> noise category name
CONTEXT_NOISE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # Python type hints with None
    ("python_type_hint", re.compile(
        r"\b(?:str|int|float|bool|bytes|list|dict|tuple|set|"
        r"Callable|Optional|Sequence|Mapping|Iterator|Iterable|"
        r"Any|Type|Union)\s*\|\s*None\b"
    )),
    ("python_type_hint", re.compile(
        r"Optional\[(?:str|int|float|bool|bytes|list|dict)\]"
    )),
    ("python_type_hint", re.compile(
        r"def\s+__init__\s*\([^)]*None[^)]*\)\s*->\s*None"
    )),
    ("python_type_hint", re.compile(
        r"->\s*(?:str|int|float|bool|None)\s*\|\s*None"
    )),

    # TypeScript/JS type annotations with null/undefined
    ("ts_type_annotation", re.compile(
        r":\s*(?:string|number|boolean|any|void)\s*\|\s*(?:null|undefined)"
    )),

    # JS/TS undefined checks (code logic, not content)
    ("js_undefined_check", re.compile(
        r"(?:===?\s*undefined|!==?\s*undefined|typeof\s+\w+\s*===?\s*['\"]undefined['\"])"
    )),

    # Code null checks
    ("code_null_check", re.compile(
        r"(?:!==?\s*null|===?\s*null|\?\.\w+|!\.\w+|if\s*\(\s*\w+\s*(?:!=|==)\s*null)"
    )),

    # Python None assignments/checks in code
    ("python_none_code", re.compile(
        r"(?:=\s*None\s*[,)\]#]|\bis\s+None\b|\bis\s+not\s+None\b)"
    )),

    # CSS properties with none value
    ("css_none_value", re.compile(
        r"(?:appearance|display|visibility|background(?:-image)?|"
        r"border(?:-style)?|outline|text-decoration|list-style(?:-type)?|"
        r"box-shadow|pointer-events|resize|float|clear)\s*:\s*none"
    )),

    # HTML/XML markup
    ("html_markup", re.compile(
        r"<(?:div|span|td|tr|th|ul|ol|li|select|option|input|form|"
        r"table|button|label|textarea|img|a\s|p\s|h[1-6]|br|hr|"
        r"script|style|link|meta|head|body|html)[>\s/]",
        re.I,
    )),

    # Shell /dev/null redirects
    ("shell_devnull", re.compile(r"(?:2?>|&>)\s*/dev/null")),

    # Job posting boilerplate
    ("job_boilerplate", re.compile(
        r"(?:Supervisory\s+Responsibilit|Equal\s+Opportunity\s+Employer|"
        r"EOE|ADA\s+Accommodation|Affirmative\s+Action|"
        r"Other\s+duties\s+as\s+assigned|"
        r"(?:Bachelor|Master)(?:'s)?\s+degree\s+(?:preferred|required)\b)",
        re.I,
    )),

    # JSON schema / config noise with null
    ("json_schema_null", re.compile(
        r'"(?:type|default|value|result)"\s*:\s*null'
    )),

    # Source map / minified code
    ("minified_code", re.compile(
        r"(?:sourceMapping(?:URL)?|/\*#\s*sourceMappingURL|"
        r"[a-zA-Z_$]\.[a-zA-Z_$]\.[a-zA-Z_$]\.[a-zA-Z_$]\.[a-zA-Z_$]"
        r"(?:\.[a-zA-Z_$]){3,})"
    )),

    # TODO/FIXME in code (the TODO label itself is the signal; the code context is noise)
    ("todo_in_code", re.compile(
        r"(?://|#|/\*)\s*(?:TODO|FIXME|HACK|XXX|UNDONE)\b"
    )),
]

# Labels that indicate the vacuum detector found a literal programming keyword,
# not a genuine gap in user content
PROGRAMMING_KEYWORD_LABELS: set[str] = {
    "None",       # Python's None
    "null",       # JS/JSON null
    "undefined",  # JS undefined
}


@dataclass
class NoiseClassification:
    """Result of classifying a single atom."""
    is_noise: bool
    reasons: list[str] = field(default_factory=list)


@dataclass
class FilterStats:
    """Aggregate statistics from a filter run."""
    total: int = 0
    signal: int = 0
    noise: int = 0
    noise_by_reason: Counter = field(default_factory=Counter)
    noise_by_label: Counter = field(default_factory=Counter)
    signal_by_label: Counter = field(default_factory=Counter)
    duplicate_count: int = 0


def extract_extension(source_file: str) -> str:
    """Extract file extension from a source_file path, ignoring anchors."""
    clean = source_file.split("#")[0]
    path = Path(clean)
    return path.suffix.lstrip(".").lower() if path.suffix else ""


def is_code_artifact_by_source(source_file: str) -> str | None:
    """Check if the source file path indicates a code artifact.

    Returns the reason string if noise, None if not.
    """
    ext = extract_extension(source_file)
    if ext in CODE_ARTIFACT_EXTENSIONS:
        return f"code_extension:{ext}"

    for pattern in SOURCE_FILE_NOISE_PATTERNS:
        if pattern.search(source_file):
            return f"source_path:{pattern.pattern[:30]}"

    return None


def classify_atom(atom: dict[str, object], seen_hashes: dict[str, str]) -> NoiseClassification:
    """Classify a single atom as SIGNAL or NOISE.

    The classification is conservative: an atom is noise only if it matches
    at least one definitive noise pattern. Ambiguous cases are kept as signal.
    """
    reasons: list[str] = []
    context: str = str(atom.get("context", ""))
    label: str = str(atom.get("label", ""))
    source_file: str = str(atom.get("source_file", ""))
    atom_id: str = str(atom.get("id", ""))

    # ---- Source file check ----
    source_reason = is_code_artifact_by_source(source_file)
    if source_reason:
        reasons.append(source_reason)

    # ---- Extension-based code artifact detection ----
    ext = extract_extension(source_file)
    if ext in ("pyi", "d.ts") and label in PROGRAMMING_KEYWORD_LABELS:
        reasons.append(f"typestub_{label}")

    # ---- Programming keyword labels from code files ----
    if label in PROGRAMMING_KEYWORD_LABELS and ext in (
        "py", "pyi", "js", "ts", "mjs", "cjs", "jsx", "tsx",
        "go", "rs", "java", "c", "cpp", "h", "hpp", "cs",
        "rb", "swift", "kt", "scala", "sh", "bash", "zsh",
        "map",
    ):
        # Check if context looks like code rather than prose
        code_indicators = sum([
            bool(re.search(r"def\s+\w+\(", context)),
            bool(re.search(r"class\s+\w+[:(]", context)),
            bool(re.search(r"function\s+\w+\(", context)),
            bool(re.search(r"(?:const|let|var)\s+\w+\s*=", context)),
            bool(re.search(r"import\s+\{", context)),
            bool(re.search(r"(?:if|else|while|for)\s*\(", context)),
            bool(re.search(r"return\s+", context)),
            bool(re.search(r"(?:public|private|protected|static)\s+", context)),
            bool(re.search(r"\b(?:self|this)\.\w+", context)),
            bool(re.search(r"=>\s*\{", context)),
            bool(re.search(r";\s*$", context)),
        ])
        if code_indicators >= 2:
            reasons.append(f"code_context_{label}")

    # ---- Context pattern matching ----
    for category, pattern in CONTEXT_NOISE_PATTERNS:
        if pattern.search(context):
            reasons.append(category)
            break  # one context pattern is sufficient

    # ---- Very short context with no semantic content ----
    stripped = re.sub(r"[^a-zA-Z\s]", "", context).strip()
    word_count = len(stripped.split()) if stripped else 0
    if word_count < 5 and len(context) < 40:
        reasons.append("too_short")

    # ---- Near-duplicate detection (exact context hash) ----
    context_hash = sha256(context.encode("utf-8")).hexdigest()[:16]
    if context_hash in seen_hashes:
        reasons.append(f"duplicate_of:{seen_hashes[context_hash]}")
    else:
        seen_hashes[context_hash] = atom_id

    is_noise = len(reasons) > 0
    return NoiseClassification(is_noise=is_noise, reasons=reasons)


def run_filter(
    input_path: Path,
    output_dir: Path | None = None,
    dry_run: bool = False,
) -> FilterStats:
    """Run the quality filter on a JSONL file.

    Args:
        input_path: Path to the input JSONL file.
        output_dir: Directory for output files. Defaults to input file's directory.
        dry_run: If True, compute stats without writing output files.

    Returns:
        FilterStats with aggregate results.
    """
    if output_dir is None:
        output_dir = input_path.parent

    stem = input_path.stem  # e.g. "vacuum-atoms"
    signal_path = output_dir / f"{stem}-signal.jsonl"
    noise_path = output_dir / f"{stem}-noise.jsonl"

    stats = FilterStats()
    seen_hashes: dict[str, str] = {}

    signal_fh = None
    noise_fh = None

    try:
        if not dry_run:
            signal_fh = open(signal_path, "w", encoding="utf-8")
            noise_fh = open(noise_path, "w", encoding="utf-8")

        with open(input_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue

                try:
                    atom = json.loads(line)
                except json.JSONDecodeError:
                    sys.stderr.write(f"WARN: invalid JSON at line {line_num}, skipping\n")
                    continue

                stats.total += 1
                result = classify_atom(atom, seen_hashes)
                label = str(atom.get("label", "UNKNOWN"))

                if result.is_noise:
                    stats.noise += 1
                    stats.noise_by_label[label] += 1
                    for reason in result.reasons:
                        # Normalize reason to category
                        category = reason.split(":")[0] if ":" in reason else reason
                        stats.noise_by_reason[category] += 1
                    if noise_fh:
                        atom["_noise_reasons"] = result.reasons
                        noise_fh.write(json.dumps(atom, ensure_ascii=False) + "\n")
                else:
                    stats.signal += 1
                    stats.signal_by_label[label] += 1
                    if signal_fh:
                        signal_fh.write(json.dumps(atom, ensure_ascii=False) + "\n")

                if stats.total % 25000 == 0:
                    sys.stderr.write(
                        f"  processed {stats.total:,} atoms "
                        f"({stats.signal:,} signal / {stats.noise:,} noise)\n"
                    )

    finally:
        if signal_fh:
            signal_fh.close()
        if noise_fh:
            noise_fh.close()

    # Count duplicates specifically
    stats.duplicate_count = stats.noise_by_reason.get("duplicate_of", 0)

    return stats


def print_report(stats: FilterStats, input_path: Path) -> None:
    """Print a human-readable summary report."""
    print(f"\n{'=' * 60}")
    print(f"QUALITY FILTER REPORT: {input_path.name}")
    print(f"{'=' * 60}")
    print(f"  Total atoms:    {stats.total:>10,}")
    print(f"  Signal:         {stats.signal:>10,}  ({100*stats.signal/max(stats.total,1):.1f}%)")
    print(f"  Noise:          {stats.noise:>10,}  ({100*stats.noise/max(stats.total,1):.1f}%)")
    print(f"  Duplicates:     {stats.duplicate_count:>10,}")

    print("\n--- Top 15 noise reasons ---")
    for reason, count in stats.noise_by_reason.most_common(15):
        pct = 100 * count / max(stats.noise, 1)
        print(f"  {reason:<30s}  {count:>8,}  ({pct:.1f}%)")

    print("\n--- Noise by label ---")
    for label, count in stats.noise_by_label.most_common(10):
        pct = 100 * count / max(stats.noise, 1)
        print(f"  {label:<20s}  {count:>8,}  ({pct:.1f}%)")

    print("\n--- Signal by label ---")
    for label, count in stats.signal_by_label.most_common(10):
        pct = 100 * count / max(stats.signal, 1)
        print(f"  {label:<20s}  {count:>8,}  ({pct:.1f}%)")

    print(f"{'=' * 60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Quality filter for vacuum-atoms JSONL files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Path to the input JSONL file",
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=Path,
        default=None,
        help="Directory for output files (default: same as input)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute stats without writing output files",
    )
    args = parser.parse_args()

    input_path: Path = args.input.resolve()
    if not input_path.exists():
        sys.exit(f"ERROR: input file not found: {input_path}")

    output_dir: Path | None = args.output_dir.resolve() if args.output_dir else None
    if output_dir and not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Processing: {input_path}")
    print(f"Output to:  {output_dir or input_path.parent}")
    if args.dry_run:
        print("(dry run -- no files will be written)")

    stats = run_filter(input_path, output_dir, dry_run=args.dry_run)
    print_report(stats, input_path)

    if not args.dry_run:
        stem = input_path.stem
        out = output_dir or input_path.parent
        print(f"Signal: {out / f'{stem}-signal.jsonl'}")
        print(f"Noise:  {out / f'{stem}-noise.jsonl'}")


if __name__ == "__main__":
    main()
