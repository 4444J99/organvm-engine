#!/usr/bin/env python3
"""Fix README links broken by the #26 declutter (docs moved root -> docs/).

For a repo, finds the files my "Declutter root per #26" commit moved into docs/,
then rewrites README.md links `](FILE.md)` / `](./FILE.md)` -> `](./docs/FILE.md)`.
Build-safe (markdown). Idempotent. Prints whether it changed anything.

Usage: fix-readme-doc-links.py REPO   (writes in place; caller commits)
"""
import re
import subprocess
import sys
from pathlib import Path


def main(repo: Path) -> int:
    readme = repo / "README.md"
    if not readme.exists():
        print(f"{repo.name}: no README"); return 0
    sha = subprocess.run(["git", "log", "--grep=Declutter root per #26", "--pretty=%H", "-1"],
                         cwd=repo, capture_output=True, text=True).stdout.strip()
    if not sha:
        print(f"{repo.name}: no declutter commit"); return 0
    ns = subprocess.run(["git", "show", sha, "--name-status"], cwd=repo,
                        capture_output=True, text=True).stdout
    moved = [Path(line.split("\t")[2]).name for line in ns.splitlines()
             if line.startswith("R") and "\tdocs/" in line]
    txt = readme.read_text(); orig = txt
    for f in moved:
        # ](FILE.md) or ](./FILE.md)  ->  ](./docs/FILE.md)   (skip if already docs/)
        txt = re.sub(r"\]\((\./)?" + re.escape(f) + r"\)", f"](./docs/{f})", txt)
    if txt != orig:
        readme.write_text(txt)
        print(f"{repo.name}: FIXED README links -> docs/")
        return 1
    print(f"{repo.name}: no broken links")
    return 0


if __name__ == "__main__":
    raise SystemExit(0 if main(Path(sys.argv[1]).expanduser()) >= 0 else 1)
