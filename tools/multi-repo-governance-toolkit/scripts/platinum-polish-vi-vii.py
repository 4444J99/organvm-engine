#!/usr/bin/env python3
"""Preview or deploy badge polish + CHANGELOG with an explicit CI template."""

import argparse
import subprocess
import base64
import time
import json
from pathlib import Path

DEFAULT_CI_TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "ci-workflows" / "ci-minimal.yml"

REPOS = [
    ("organvm-vi-koinonia", "salon-archive",           "Markdown", "VI",  "Koinonia", "6366F1"),
    ("organvm-vi-koinonia", "reading-group-curriculum", "Markdown", "VI",  "Koinonia", "6366F1"),
    ("organvm-vii-kerygma", "announcement-templates",   "Markdown", "VII", "Kerygma",  "EF4444"),
    ("organvm-vii-kerygma", "social-automation",        "Markdown", "VII", "Kerygma",  "EF4444"),
    ("organvm-vii-kerygma", "distribution-strategy",    "Markdown", "VII", "Kerygma",  "EF4444"),
]


def get_default_branch(org, repo):
    try:
        result = subprocess.run(
            ["gh", "api", f"/repos/{org}/{repo}"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
    except (OSError, json.JSONDecodeError):
        return None
    branch = data.get("default_branch") if isinstance(data, dict) else None
    return branch if isinstance(branch, str) and branch.strip() else None


def get_file_sha(org, repo, path):
    result = subprocess.run(
        ["gh", "api", f"/repos/{org}/{repo}/contents/{path}"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        data = json.loads(result.stdout)
        if isinstance(data, dict) and "sha" in data:
            return data["sha"]
    return None


def put_file(org, repo, path, content, message, branch=None):
    sha = get_file_sha(org, repo, path)
    b64 = base64.b64encode(content.encode()).decode()
    cmd = [
        "gh", "api", "-X", "PUT",
        f"/repos/{org}/{repo}/contents/{path}",
        "-f", f"message={message}",
        "-f", f"content={b64}",
    ]
    if sha:
        cmd.extend(["-f", f"sha={sha}"])
    if branch:
        cmd.extend(["-f", f"branch={branch}"])
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def generate_badge_row(org, repo, lang, organ_num, organ_name, color):
    return f"""[![CI](https://github.com/{org}/{repo}/actions/workflows/ci.yml/badge.svg)](https://github.com/{org}/{repo}/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/{org}/{repo}/blob/main/LICENSE)
[![Organ {organ_num}](https://img.shields.io/badge/Organ-{organ_num}%20{organ_name}-{color})](https://github.com/{org})
[![Status](https://img.shields.io/badge/status-active-brightgreen)](https://github.com/{org}/{repo})
[![{lang}](https://img.shields.io/badge/lang-{lang}-informational)](https://github.com/{org}/{repo})"""


def generate_changelog(org, repo):
    return f"""# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Platinum Sprint: standardized badge row, CHANGELOG
- Initial CHANGELOG following Keep a Changelog format

## [0.1.0] - 2026-02-11

### Added

- Initial public release as part of the organvm eight-organ system
- Core project structure and documentation

[Unreleased]: https://github.com/{org}/{repo}/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/{org}/{repo}/releases/tag/v0.1.0
"""


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ci-template", type=Path, default=DEFAULT_CI_TEMPLATE,
                        help="Path to the owning CI workflow template")
    parser.add_argument("--write", action="store_true",
                        help="Apply changes to the listed repositories (default: preview)")
    args = parser.parse_args(argv)
    try:
        ci_minimal = args.ci_template.expanduser().read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        parser.error(f"--ci-template must name an existing readable workflow: {exc}")
    if not ci_minimal.strip():
        parser.error("--ci-template must not be empty")

    if not args.write:
        print("DRY RUN: CI, CHANGELOG, and badge targets (use --write to apply):")
        for org, repo, *_ in REPOS:
            print(f"  {org}/{repo}")
        return 0

    failures = 0
    for org, repo, lang, num, name, color in REPOS:
        print(f"\nDeploying: {org}/{repo}")
        branch = get_default_branch(org, repo)
        if not branch:
            print("  FAIL: could not resolve the default branch; no writes attempted")
            failures += 1
            continue

        # CI workflow
        print("  CI (ci-minimal)...", end=" ", flush=True)
        if put_file(org, repo, ".github/workflows/ci.yml", ci_minimal,
                    "ci: add minimal CI workflow (Platinum Sprint)", branch):
            print("OK")
        else:
            print("FAIL")
            failures += 1
        time.sleep(1)

        # CHANGELOG
        print("  CHANGELOG...", end=" ", flush=True)
        if put_file(org, repo, "CHANGELOG.md", generate_changelog(org, repo),
                    "docs: add CHANGELOG (Platinum Sprint)", branch):
            print("OK")
        else:
            print("FAIL")
            failures += 1
        time.sleep(1)

        # Badge row injection
        print("  Badge row...", end=" ", flush=True)
        result = subprocess.run(
            ["gh", "api", f"/repos/{org}/{repo}/contents/README.md",
             "-H", "Accept: application/vnd.github.raw+json"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            readme = result.stdout
            badge_row = generate_badge_row(org, repo, lang, num, name, color)
            if "img.shields.io" in readme or "actions/workflows" in readme:
                print("(badges exist, skipping)")
            else:
                lines = readme.split("\n")
                insert_at = 0
                for i, line in enumerate(lines):
                    if line.startswith("# "):
                        insert_at = i + 1
                        break
                new_lines = lines[:insert_at] + [""] + badge_row.split("\n") + [""] + lines[insert_at:]
                readme = "\n".join(new_lines)
                if put_file(org, repo, "README.md", readme,
                            "chore: add badge row (Platinum Sprint)", branch):
                    print("OK")
                else:
                    print("FAIL")
                    failures += 1
        else:
            print("(README unavailable)")
            failures += 1
        time.sleep(1)

    print(f"\nDone: {failures} failed operation(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
