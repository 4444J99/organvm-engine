#!/usr/bin/env python3
"""Normalize mechanical registry spellings without changing evidence claims.

Dry-run by default. Only --write updates the canonical repo-registry.json.
Counts-only output avoids disclosing inventory identities.
"""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import re


def normalize(data: dict) -> tuple[dict, dict[str, int]]:
    result = deepcopy(data)
    counts = {"empty_workflow": 0, "workflow_prefix": 0, "class_case": 0,
              "visibility_caption": 0}
    captions = {
        "MIXED (4 private, 18 public)": "MIXED",
        "SEMI-PUBLIC (Governance visible, implementation details private)": "SEMI-PUBLIC",
        "SEMI-PUBLIC (invitations, participation)": "SEMI-PUBLIC",
    }
    for organ in result["organs"].values():
        caption = organ.get("public_visibility")
        if isinstance(caption, str) and caption in captions:
            if "public_visibility_note" in organ and organ["public_visibility_note"] != caption:
                raise ValueError("visibility note conflicts with historical caption")
            organ["public_visibility"] = captions[caption]
            organ["public_visibility_note"] = caption
            counts["visibility_caption"] += 1
        for repo in organ["repositories"]:
            value = repo.get("ci_workflow")
            if value == "":
                repo["ci_workflow"] = None
                counts["empty_workflow"] += 1
            elif isinstance(value, str) and value.startswith(".github/workflows/"):
                name = value.removeprefix(".github/workflows/")
                if re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*\.ya?ml", name):
                    repo["ci_workflow"] = name
                    counts["workflow_prefix"] += 1
            if repo.get("functional_class") == "infrastructure":
                repo["functional_class"] = "INFRASTRUCTURE"
                counts["class_case"] += 1
    return result, counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    path = Path(__file__).resolve().parents[1] / "repo-registry.json"
    original = path.read_text()
    result, counts = normalize(json.loads(original))
    if args.write and any(counts.values()):
        # Refuse a concurrent change instead of overwriting another writer.
        if path.read_text() != original:
            raise RuntimeError("registry changed during normalization")
        path.write_text(json.dumps(result, indent=2, ensure_ascii=True) + "\n")
    print(json.dumps({"written": args.write and any(counts.values()), "changes": counts}))


if __name__ == "__main__":
    main()
