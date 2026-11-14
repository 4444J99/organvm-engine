"""Public CLI surface inventory and compatibility classification.

The ``organvm`` command line is a promise to consumers (scripts, CI, agents).
This module extracts that promise from the live argparse tree into a plain,
deterministic mapping, compares it with a committed baseline, and classifies
every difference as ``breaking`` (something a consumer could rely on is gone or
changed shape) or ``compatible`` (purely additive).

It deliberately reads the parser the CLI itself builds, so the inventory cannot
drift from the implementation, and it inspects no repositories, network or
registry state.

Usage::

    python -m organvm_engine.api_surface show          # print current surface
    python -m organvm_engine.api_surface check         # compare with baseline
    python -m organvm_engine.api_surface write         # rewrite the baseline

``check`` exits 1 when the change is breaking. Intentional breaks are recorded
by running ``write`` in the same reviewed change as a CHANGELOG entry (see
``docs/api/VERSIONING.md``).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

# Positional arguments are keyed by dest; options by their longest flag string.
_BASELINE_RELATIVE = Path("docs") / "api" / "cli-surface.json"


def _argument_entry(action: argparse.Action) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "required": bool(action.required) if action.option_strings else action.nargs
        not in ("?", "*"),
    }
    if action.option_strings:
        entry["flags"] = sorted(action.option_strings)
    if action.choices is not None:
        entry["choices"] = sorted(str(c) for c in action.choices)
    entry["takes_value"] = action.nargs != 0
    return entry


def _argument_key(action: argparse.Action) -> str:
    if action.option_strings:
        return max(action.option_strings, key=len)
    return action.dest


def _walk(parser: argparse.ArgumentParser, path: tuple[str, ...], out: dict[str, Any]) -> None:
    arguments: dict[str, Any] = {}
    children: list[tuple[str, argparse.ArgumentParser]] = []
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            children.extend(action.choices.items())
            continue
        if isinstance(action, argparse._HelpAction):
            continue
        arguments[_argument_key(action)] = _argument_entry(action)
    if path:
        out[" ".join(path)] = {"arguments": dict(sorted(arguments.items()))}
    for name, child in children:
        _walk(child, (*path, name), out)


def extract_surface(parser: argparse.ArgumentParser) -> dict[str, Any]:
    """Return a deterministic description of every command the parser accepts."""
    commands: dict[str, Any] = {}
    _walk(parser, (), commands)
    return {
        "schema_version": SCHEMA_VERSION,
        "commands": dict(sorted(commands.items())),
    }


@dataclass
class SurfaceDiff:
    """Classified difference between a baseline surface and the current one."""

    breaking: list[str] = field(default_factory=list)
    compatible: list[str] = field(default_factory=list)

    @property
    def is_breaking(self) -> bool:
        return bool(self.breaking)

    @property
    def is_empty(self) -> bool:
        return not self.breaking and not self.compatible


def diff_surfaces(baseline: dict[str, Any], current: dict[str, Any]) -> SurfaceDiff:
    """Classify differences, treating the baseline as the consumer promise.

    Breaking: a command or argument removed; an argument that became required;
    a value-taking argument that stopped taking a value (or the reverse); a
    previously accepted choice removed. Compatible: new commands, new optional
    arguments, new choices.
    """
    result = SurfaceDiff()
    base_cmds = baseline.get("commands", {})
    cur_cmds = current.get("commands", {})

    for name in sorted(set(base_cmds) - set(cur_cmds)):
        result.breaking.append(f"command removed: {name}")
    for name in sorted(set(cur_cmds) - set(base_cmds)):
        result.compatible.append(f"command added: {name}")

    for name in sorted(set(base_cmds) & set(cur_cmds)):
        base_args = base_cmds[name].get("arguments", {})
        cur_args = cur_cmds[name].get("arguments", {})
        for key in sorted(set(base_args) - set(cur_args)):
            result.breaking.append(f"argument removed: {name} {key}")
        for key in sorted(set(cur_args) - set(base_args)):
            if cur_args[key]["required"]:
                result.breaking.append(f"required argument added: {name} {key}")
            else:
                result.compatible.append(f"argument added: {name} {key}")
        for key in sorted(set(base_args) & set(cur_args)):
            old, new = base_args[key], cur_args[key]
            if new["required"] and not old["required"]:
                result.breaking.append(f"argument became required: {name} {key}")
            if new["takes_value"] != old["takes_value"]:
                result.breaking.append(f"argument value arity changed: {name} {key}")
            old_choices = set(old.get("choices", []))
            new_choices = set(new.get("choices", []))
            if old_choices and new_choices:
                for choice in sorted(old_choices - new_choices):
                    result.breaking.append(f"choice removed: {name} {key}={choice}")
                for choice in sorted(new_choices - old_choices):
                    result.compatible.append(f"choice added: {name} {key}={choice}")
            elif old_choices and not new_choices:
                result.compatible.append(f"choices unrestricted: {name} {key}")
            elif new_choices and not old_choices:
                result.breaking.append(f"choices restricted: {name} {key}")
            old_flags = set(old.get("flags", []))
            new_flags = set(new.get("flags", []))
            for flag in sorted(old_flags - new_flags):
                result.breaking.append(f"flag removed: {name} {flag}")
            for flag in sorted(new_flags - old_flags):
                result.compatible.append(f"flag added: {name} {flag}")

    return result


def baseline_path(root: Path | None = None) -> Path:
    """Locate the committed baseline relative to the repository checkout."""
    base = root if root is not None else Path(__file__).resolve().parents[2]
    return base / _BASELINE_RELATIVE


def load_baseline(path: Path) -> dict[str, Any]:
    """Load a baseline, rejecting an unknown schema rather than guessing."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"{path}: unsupported schema_version {data.get('schema_version')!r}; "
            f"expected {SCHEMA_VERSION}",
        )
    return data


def render_surface(surface: dict[str, Any]) -> str:
    """Serialize a surface exactly as it is committed (stable, newline-terminated)."""
    return json.dumps(surface, indent=2, sort_keys=True) + "\n"


def _current_surface() -> dict[str, Any]:
    from organvm_engine.cli import build_parser

    return extract_surface(build_parser())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m organvm_engine.api_surface")
    ap.add_argument("action", choices=["show", "check", "write"])
    ap.add_argument("--baseline", type=Path, default=None, help="Baseline path override")
    args = ap.parse_args(argv)

    path = args.baseline or baseline_path()
    surface = _current_surface()

    if args.action == "show":
        sys.stdout.write(render_surface(surface))
        return 0
    if args.action == "write":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_surface(surface), encoding="utf-8")
        print(f"wrote {path} ({len(surface['commands'])} commands)")
        return 0

    if not path.is_file():
        print(f"baseline missing: {path}", file=sys.stderr)
        return 2
    diff = diff_surfaces(load_baseline(path), surface)
    for line in diff.breaking:
        print(f"BREAKING   {line}")
    for line in diff.compatible:
        print(f"compatible {line}")
    if diff.is_empty:
        print("CLI surface matches baseline")
    if diff.is_breaking:
        return 1
    if diff.compatible:
        print("additive change: run 'write' to refresh the baseline", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
