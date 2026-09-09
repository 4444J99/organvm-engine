"""CLI handlers for reader-mode documentation validation and auditing."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

from organvm_engine.documentation.audit import (
    DIMENSIONS,
    audit_repository,
    discover_repositories,
    load_schema,
)
from organvm_engine.documentation.record import load_project_record, validate_project_record


def cmd_docs_validate(args) -> int:
    """Validate a canonical project record and its declared local routes."""
    record_path = Path(args.record).absolute()
    root = Path(args.root).resolve() if args.root else record_path.parent
    try:
        record = load_project_record(record_path)
        schema_path = Path(args.schema).resolve() if args.schema else None
        schema = load_schema(schema_path) if schema_path else None
        assertion_path = (
            Path(args.assertion_schema).resolve()
            if getattr(args, "assertion_schema", None)
            else None
        )
        if assertion_path is None and schema_path is not None:
            sibling = schema_path.with_name("assertion-evidence.v1.schema.json")
            assertion_path = sibling if sibling.is_file() else None
        assertion_schema = load_schema(assertion_path) if assertion_path else None
        errors = validate_project_record(
            record,
            root=root,
            schema=schema,
            assertion_schema=assertion_schema,
            require_git_tracked_evidence=getattr(
                args,
                "require_git_tracked_evidence",
                False,
            ),
            actual_repository=getattr(args, "actual_repository", None),
        )
    except (OSError, ValueError, yaml.YAMLError) as exc:
        errors = [str(exc)]

    if getattr(args, "json", False):
        json.dump(
            {"record": str(record_path), "valid": not errors, "errors": errors},
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
    elif errors:
        print(f"Invalid project record: {record_path}")
        for error in errors:
            print(f"  - {error}")
    else:
        print(f"Valid project record: {record_path}")
    return 1 if errors else 0


def cmd_docs_audit(args) -> int:
    """Audit one or more repository documentation surfaces."""
    paths = []
    for raw_path in args.paths:
        try:
            if not raw_path:
                raise ValueError("path is empty")
            path = Path(raw_path).resolve(strict=True)
            if not path.is_dir():
                raise ValueError("path is not a directory")
        except (OSError, RuntimeError, ValueError) as exc:
            print(f"Error: invalid explicit audit path {raw_path!r}: {exc}", file=sys.stderr)
            return 1
        paths.append(path)
    workspace = getattr(args, "workspace", None)
    if workspace is not None:
        repositories = (
            discover_repositories(workspace)
            if not isinstance(workspace, str) or workspace.strip()
            else []
        )
        if not repositories:
            rendered_workspace = (
                str(Path(workspace).resolve())
                if not isinstance(workspace, str) or workspace.strip()
                else "<empty>"
            )
            print(
                "Error: no Git repositories discovered under explicit workspace: "
                f"{rendered_workspace}",
                file=sys.stderr,
            )
            return 1
        paths.extend(repositories)
    if not paths:
        paths = [Path.cwd().resolve()]
    unique_paths = sorted(set(paths))
    results = [audit_repository(path) for path in unique_paths]

    output_format = "json" if getattr(args, "json", False) else args.format
    if output_format == "json":
        rendered = json.dumps({"repositories": results}, indent=2) + "\n"
    elif output_format == "markdown":
        rendered = _render_markdown(results)
    else:
        rendered = _render_table(results)

    if args.output:
        try:
            Path(args.output).write_text(rendered, encoding="utf-8")
        except OSError as exc:
            print(
                f"Error: cannot write documentation audit to {args.output}: {exc}",
                file=sys.stderr,
            )
            return 1
        print(f"Documentation audit written to {args.output}")
    else:
        sys.stdout.write(rendered)

    has_errors = any(
        finding["severity"] == "error"
        for result in results
        for finding in result["findings"]
    )
    return 1 if args.strict and has_errors else 0


def _render_table(results: list[dict]) -> str:
    header = (
        f"{'Repository':<36} {'Class':<5} "
        + " ".join(f"{name[:4].upper():>4}" for name in DIMENSIONS)
        + "\n"
    )
    separator = "─" * (len(header.rstrip())) + "\n"
    rows = []
    for result in results:
        signals = result["signals"]
        row = (
            f"{result['repository'][:36]:<36} {result['documentation_class']:<5} "
            + " ".join(f"{signals[name]:>4}" for name in DIMENSIONS)
            + "\n"
        )
        rows.append(row)
    return header + separator + "".join(rows)


def _render_markdown(results: list[dict]) -> str:
    lines = [
        "# Reader-mode documentation audit",
        "",
        "> Counts below are structural markers, not quality scores.",
        "",
        "| Repository | Class | Orientation | Technical | Conceptual | Commercial | Evidence | SEO | Links |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for result in results:
        signal = result["signals"]
        lines.append(
            f"| {result['repository']} | {result['documentation_class']} | "
            f"{signal['orientation']} | {signal['technical_depth']} | "
            f"{signal['conceptual_depth']} | {signal['commercial_relevance']} | "
            f"{signal['evidence']} | {signal['seo_surface']} | {signal['cross_linking']} |",
        )
    lines.extend(["", "## Findings", ""])
    for result in results:
        lines.append(f"### {result['repository']}")
        lines.append("")
        if not result["findings"]:
            lines.append("No structural findings.")
        else:
            for finding in result["findings"]:
                lines.append(
                    f"- **{finding['severity'].upper()} · {finding['code']}** — {finding['message']}",
                )
        lines.append("")
    return "\n".join(lines)
