"""Variable binding system for metrics propagation.

Replaces fragile regex-based propagation with explicit HTML comment markers:

    <!-- v:total_repos -->103<!-- /v -->

Files declare which variables they reference. `organvm refresh` resolves
all bindings from a single generated manifest (system-vars.json).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

# Matches <!-- v:KEY -->VALUE<!-- /v --> (VALUE can span lines)
VAR_PATTERN = re.compile(r"(<!-- v:([a-zA-Z0-9_.:-]+) -->).*?(<!-- /v -->)", re.DOTALL)


@dataclass
class Replacement:
    """A single variable binding replacement."""

    key: str
    old_value: str
    new_value: str
    line: int  # approximate line number


@dataclass
class ResolutionResult:
    """Aggregate result of resolving bindings across files."""

    total_replacements: int = 0
    files_changed: int = 0
    files_scanned: int = 0
    unknown_keys: list[str] = field(default_factory=list)
    details: list[str] = field(default_factory=list)


def build_vars(metrics: dict, registry: dict) -> dict[str, str]:
    """Build flat variable manifest from system-metrics.json + registry.

    All values are strings since they're injected into markdown.
    """
    c = metrics.get("computed", {})
    m = metrics.get("manual", {})

    variables: dict[str, str] = {}

    # Core counts
    variables["total_repos"] = str(c.get("total_repos", 0))
    variables["active_repos"] = str(c.get("active_repos", 0))
    variables["archived_repos"] = str(c.get("archived_repos", 0))
    variables["total_organs"] = str(c.get("total_organs", 0))
    variables["operational_organs"] = str(c.get("operational_organs", 0))

    # Word counts — try computed first, fall back to manual
    total_words_numeric = c.get("total_words_numeric") or m.get("total_words_numeric", 0)
    variables["total_words_numeric"] = str(total_words_numeric)
    variables["total_words_formatted"] = f"{int(total_words_numeric):,}"
    variables["total_words_short"] = str(
        c.get("total_words_short") or m.get("total_words_short", "0K+"),
    )

    # CI, deps, essays, sprints
    variables["ci_workflows"] = str(c.get("ci_workflows", 0))
    variables["dependency_edges"] = str(c.get("dependency_edges", 0))
    variables["published_essays"] = str(c.get("published_essays", 0))
    variables["sprints_completed"] = str(c.get("sprints_completed", 0))

    # Code metrics
    variables["code_files"] = str(c.get("code_files") or m.get("code_files", 0))
    variables["test_files"] = str(c.get("test_files") or m.get("test_files", 0))
    variables["repos_with_tests"] = str(
        c.get("repos_with_tests") or m.get("repos_with_tests", 0),
    )

    # Per-organ counts from registry
    organs = registry.get("organs", {})
    for organ_key, organ_data in organs.items():
        repo_count = len(organ_data.get("repositories", []))
        variables[f"organ_repos.{organ_key}"] = str(repo_count)
        variables[f"organ_name.{organ_key}"] = organ_data.get("name", organ_key)

    return variables


def write_vars(variables: dict[str, str], output: Path) -> None:
    """Write system-vars.json."""
    with output.open("w") as f:
        json.dump(variables, f, indent=2, sort_keys=True)
        f.write("\n")


def load_vars(path: Path) -> dict[str, str]:
    """Load system-vars.json."""
    with path.open() as f:
        return json.load(f)


def resolve_file(
    path: Path,
    variables: dict[str, str],
    dry_run: bool = False,
) -> list[Replacement]:
    """Scan a file for <!-- v:KEY --> markers and replace values.

    Unknown keys are preserved with a warning (returned in the replacement
    list with old_value == new_value).
    """
    content = path.read_text()
    replacements: list[Replacement] = []

    def _replace(match: re.Match) -> str:
        open_tag = match.group(1)
        key = match.group(2)
        close_tag = match.group(3)
        old_value = content[match.start() + len(open_tag) : match.end() - len(close_tag)]

        if key not in variables:
            replacements.append(Replacement(
                key=key,
                old_value=old_value,
                new_value=old_value,
                line=content[: match.start()].count("\n") + 1,
            ))
            return match.group(0)  # preserve unknown

        new_value = variables[key]
        replacements.append(Replacement(
            key=key,
            old_value=old_value,
            new_value=new_value,
            line=content[: match.start()].count("\n") + 1,
        ))
        return f"{open_tag}{new_value}{close_tag}"

    new_content = VAR_PATTERN.sub(_replace, content)

    if new_content != content and not dry_run:
        path.write_text(new_content)

    return replacements


def resolve_targets(
    variables: dict[str, str],
    targets: list[Path],
    dry_run: bool = False,
) -> ResolutionResult:
    """Resolve variable bindings across a list of target files."""
    result = ResolutionResult()

    for path in targets:
        if not path.exists() or not path.is_file():
            continue

        result.files_scanned += 1
        replacements = resolve_file(path, variables, dry_run=dry_run)

        if not replacements:
            continue

        changed = any(r.old_value != r.new_value for r in replacements)
        if changed:
            result.files_changed += 1

        for r in replacements:
            if r.old_value != r.new_value:
                result.total_replacements += 1
                result.details.append(
                    f"{path.name}:{r.line} {r.key}: {r.old_value!r} -> {r.new_value!r}",
                )
            elif r.key not in variables and r.key not in result.unknown_keys:
                result.unknown_keys.append(r.key)

    return result


def resolve_targets_from_manifest(
    variables: dict[str, str],
    manifest_path: Path,
    dry_run: bool = False,
) -> ResolutionResult:
    """Load vars-targets.yaml and resolve all bindings."""
    import yaml

    with manifest_path.open() as f:
        manifest = yaml.safe_load(f)

    targets = _collect_targets(manifest)
    return resolve_targets(variables, targets, dry_run=dry_run)


def _collect_targets(manifest: dict) -> list[Path]:
    """Collect concrete file paths from a vars-targets.yaml manifest."""
    all_files: list[Path] = []

    for target in manifest.get("targets", []):
        raw_root = target.get("root", ".")
        root = Path(raw_root).expanduser().resolve()

        # Explicit file list
        for rel in target.get("files", []):
            path = root / rel
            if path.exists():
                all_files.append(path)

        # Glob patterns
        for pattern in target.get("globs", []):
            all_files.extend(sorted(root.glob(pattern)))

    # Deduplicate preserving order
    seen: set[Path] = set()
    result: list[Path] = []
    for f in all_files:
        resolved = f.resolve()
        if resolved not in seen:
            seen.add(resolved)
            result.append(resolved)
    return result
