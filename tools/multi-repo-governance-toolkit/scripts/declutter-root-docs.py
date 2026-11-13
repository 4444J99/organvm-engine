#!/usr/bin/env python3
"""Root-declutter helper for standard #26 §8 — relocate loose docs into docs/.

Moves non-canonical root *.md files into docs/ via `git mv`. Markdown docs are
not imported by code, so this is build-safe (worst case: a relative link inside
a moved doc needs fixing — cosmetic, not breaking).

KEEPS at root: README, CHANGELOG, and GitHub-recognized community-health /
identity files (CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, SUPPORT, MAINTAINERS,
GOVERNANCE, CODEOWNERS) + agent context files (CLAUDE/AGENTS/GEMINI).

Usage:
    declutter-root-docs.py REPO [REPO ...]            # dry-run
    declutter-root-docs.py --apply REPO [REPO ...]
"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

KEEP = {
    "readme.md", "changelog.md", "contributing.md", "code_of_conduct.md",
    "security.md", "support.md", "maintainers.md", "governance.md",
    "codeowners.md", "claude.md", "agents.md", "gemini.md", "history.md",
}


def run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def loose_docs(repo: Path) -> list[Path]:
    out = []
    for e in repo.iterdir():
        if e.is_file() and e.suffix.lower() == ".md" and e.name.lower() not in KEEP:
            out.append(e)
    return sorted(out)


def main() -> int:
    args = sys.argv[1:]
    apply = "--apply" in args
    repos = [Path(a).expanduser() for a in args if a != "--apply"]
    grand = 0
    for repo in repos:
        if not (repo / ".git").exists():
            print(f"skip (not a repo): {repo}")
            continue
        docs = loose_docs(repo)
        if not docs:
            print(f"{repo.name}: nothing to move")
            continue
        print(f"{repo.name}: {'MOVING' if apply else 'would move'} {len(docs)} loose docs -> docs/")
        if not apply:
            for d in docs:
                print(f"    · {d.name}")
            continue
        (repo / "docs").mkdir(exist_ok=True)
        moved = []
        for d in docs:
            dest = repo / "docs" / d.name
            if dest.exists():
                continue  # never overwrite
            rc, out = run(["git", "mv", d.name, f"docs/{d.name}"], repo)
            if rc == 0:
                moved.append(d.name)
            else:
                print(f"    ! {d.name}: {out[:80]}")
        if moved:
            msg = (f"Declutter root per #26 §8: move {len(moved)} docs to docs/\n\n"
                   f"Relocate non-canonical root markdown into docs/ (build-safe; "
                   f"markdown is not imported). Reduces root file count toward <20.\n\n"
                   f"Co-Authored-By: Claude Opus 4.8 (1M context) <[email redacted]>")
            rc, out = run(["git", "commit", "-q", "-m", msg], repo)
            print(f"    {'committed' if rc == 0 else 'COMMIT FAILED: ' + out[:80]} ({len(moved)} files)")
            grand += len(moved) if rc == 0 else 0
    if apply:
        print(f"\nTotal moved+committed: {grand} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
