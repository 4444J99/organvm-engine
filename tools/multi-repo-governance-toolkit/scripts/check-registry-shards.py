#!/usr/bin/env python3
"""Read-only, counts-only comparison of canonical registry and organ shards.

Exit 0 means exact parity; 1 means measured drift; 77 means malformed or missing
coverage. Repository names and values never appear in the report.
"""

import json
from pathlib import Path


def rows_by_name(organ):
    if not isinstance(organ, dict) or not isinstance(organ.get("repositories"), list):
        raise ValueError("malformed organ")
    rows = {}
    for row in organ["repositories"]:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str) or not row["name"]:
            raise ValueError("malformed repository")
        if row["name"] in rows:
            raise ValueError("duplicate repository")
        rows[row["name"]] = row
    return rows


def compare(canonical, shards):
    if not isinstance(canonical, dict) or not isinstance(canonical.get("organs"), dict):
        raise ValueError("malformed registry")
    result = {"canonical_organs": len(canonical["organs"]), "shard_organs": len(shards),
              "missing_shards": 0, "extra_shards": 0, "drifted_organs": 0,
              "canonical_only_repositories": 0, "shard_only_repositories": 0,
              "changed_repositories": 0, "changed_organ_metadata": 0}
    organs = canonical["organs"]
    # Validate all inputs, including unmatched organs, before reporting measurements.
    left = {key: rows_by_name(value) for key, value in organs.items()}
    right = {key: rows_by_name(value) for key, value in shards.items()}
    result["missing_shards"] = len(organs.keys() - shards.keys())
    result["extra_shards"] = len(shards.keys() - organs.keys())
    for key in organs.keys() & shards.keys():
        a, b = left[key], right[key]
        result["canonical_only_repositories"] += len(a.keys() - b.keys())
        result["shard_only_repositories"] += len(b.keys() - a.keys())
        result["changed_repositories"] += sum(a[name] != b[name] for name in a.keys() & b.keys())
        result["changed_organ_metadata"] += (
            {k: v for k, v in organs[key].items() if k != "repositories"} !=
            {k: v for k, v in shards[key].items() if k != "repositories"}
        )
        result["drifted_organs"] += organs[key] != shards[key]
    status = "unmeasured" if result["missing_shards"] or result["extra_shards"] else (
        "drift" if result["drifted_organs"] else "pass")
    return {"status": status, **result}


def compare_projection(canonical, shards, metadata):
    report = compare(canonical, shards)
    if not isinstance(metadata, dict) or "organs" in metadata:
        raise ValueError("malformed projection metadata")
    report["metadata_matches"] = metadata == {k: v for k, v in canonical.items() if k != "organs"}
    if not report["metadata_matches"] and report["status"] == "pass":
        report["status"] = "drift"
    return report


def main():
    root = Path(__file__).resolve().parents[1]
    try:
        canonical = json.loads((root / "repo-registry.json").read_text())
        shards = {p.stem: json.loads(p.read_text()) for p in (root / "registry").glob("*.json")
                  if p.name != "_meta.json"}
        metadata = json.loads((root / "registry/_meta.json").read_text())
        report = compare_projection(canonical, shards, metadata)
    except (OSError, ValueError, TypeError):
        print(json.dumps({"status": "unmeasured", "reason": "registry inputs unavailable or malformed"}))
        return 77
    print(json.dumps(report, sort_keys=True))
    return {"pass": 0, "drift": 1, "unmeasured": 77}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
