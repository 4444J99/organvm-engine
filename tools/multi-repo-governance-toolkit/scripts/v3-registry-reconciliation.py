#!/usr/bin/env python3
"""V3: Registry-to-GitHub Reconciliation

Verifies:
1. Every repo in registry with documentation_status containing DEPLOYED actually exists on GitHub with a README
2. GitHub repo descriptions match registry descriptions
3. No repos on GitHub are missing from registry

For a transfer-aware identity audit, use --identity-snapshot with authenticated
installation catalogue/page receipts and old-path repository GET resolutions.
Use --output outside the repository for private detail, or --aggregate-only for
counts without repository identifiers. Exit 1 means valid evidence with open
reconciliation work; exit 2 means invalid evidence. Neither mode certifies
activation, and this script never changes promotion or validation dates.
"""

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
import subprocess
import sys
import os

REGISTRY_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "repo-registry.json")

SYSTEM_ORGS = [
    'organvm-i-theoria', 'organvm-ii-poiesis', 'organvm-iii-ergon',
    'organvm-iv-taxis', 'organvm-v-logos', 'organvm-vi-koinonia',
    'organvm-vii-kerygma', 'meta-organvm'
]


# ISOTOPE DISSOLUTION: Gate memory--remember G2 (CORPUS_SCRIPTS_DISSOLVED)
try:
    from organvm_engine.registry.loader import load_registry as _engine_load
except ImportError:
    _engine_load = None


def load_registry():
    if _engine_load is not None:
        return _engine_load(REGISTRY_PATH)
    with open(REGISTRY_PATH) as f:
        return json.load(f)


def gh_list_repos(org):
    """List all repos in an org via gh api."""
    repos = []
    page = 1
    while True:
        try:
            result = subprocess.run(
                ["gh", "api", f"orgs/{org}/repos?per_page=100&page={page}",
                 "--jq", '.[].name'],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                print(f"  Error listing {org}: {result.stderr.strip()}")
                break
            names = [n.strip() for n in result.stdout.strip().split('\n') if n.strip()]
            if not names:
                break
            repos.extend(names)
            if len(names) < 100:
                break
            page += 1
        except subprocess.TimeoutExpired:
            print(f"  Timeout listing {org}")
            break
    return repos


def gh_get_repo_info(org, repo):
    """Get repo description and has_readme status."""
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{org}/{repo}",
             "--jq", '{description: .description, has_wiki: .has_wiki, default_branch: .default_branch}'],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout.strip())
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        return None


def gh_has_readme(org, repo):
    """Check if repo has a README."""
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{org}/{repo}/readme",
             "--jq", ".name"],
            capture_output=True, text=True, timeout=15
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return None


def gh_get_description(org, repo):
    """Get repo description from GitHub."""
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{org}/{repo}",
             "--jq", ".description"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            desc = result.stdout.strip()
            return desc if desc and desc != "null" else ""
        return None
    except subprocess.TimeoutExpired:
        return None


def _canonical_repository_id(value):
    """GitHub numeric IDs have one decimal spelling; aliases are not identities."""
    return (isinstance(value, str) and value.isascii() and value.isdecimal()
            and not value.startswith("0"))


def _page_ids(pages, label):
    """Validate complete connector page-index receipts; never accept a capped list."""
    if not isinstance(pages, list) or not pages:
        raise ValueError(f"{label}: missing pagination receipts")
    ids = []
    terminal = False
    for index, page in enumerate(pages):
        if not isinstance(page, dict):
            raise ValueError(f"{label}: pagination receipt must be an object")
        if type(page.get("page_index")) is not int or page["page_index"] != index:
            raise ValueError(f"{label}: page indexes must be contiguous from zero")
        page_size = page.get("requested_page_size")
        if type(page_size) is not int or not 1 <= page_size <= 100:
            raise ValueError(f"{label}: missing or invalid requested page size")
        values = page.get("repositories")
        if not isinstance(values, list) or len(values) > page_size:
            raise ValueError(f"{label}: invalid page size")
        if terminal and values:
            raise ValueError(f"{label}: repositories after terminal page")
        if any(not _canonical_repository_id(value) for value in values):
            raise ValueError(f"{label}: invalid repository ID")
        ids.extend(values)
        terminal = len(values) < page_size
    if not terminal:
        raise ValueError(f"{label}: pagination not exhausted")
    if len(ids) != len(set(ids)):
        raise ValueError(f"{label}: duplicate repository ID across pages")
    return set(ids)


def reconcile_identity_snapshot(registry, snapshot, registry_bytes):
    """Reconcile supplied authenticated reads without treating names as identity.

    This extends the existing V3 audit; it does not mutate the registry or
    promote lifecycle/activation status. The detailed result is private when
    the input includes private repositories. GitHub repository GET redirects
    are binding evidence; an equal name elsewhere is only a candidate.
    """
    if not isinstance(registry, dict) or not isinstance(snapshot, dict):
        raise ValueError("registry and identity snapshot must be objects")
    if snapshot.get("snapshot_version") != "organvm.registry-identity-snapshot.v1":
        raise ValueError("unsupported identity snapshot version")
    blob = hashlib.sha1(
        b"blob " + str(len(registry_bytes)).encode() + b"\0" + registry_bytes,
    ).hexdigest()
    if snapshot.get("registry_blob_sha") != blob:
        raise ValueError("registry bytes do not match snapshot Git blob SHA")
    if json.loads(registry_bytes) != registry:
        raise ValueError("registry object differs from bound source bytes")
    organs = registry.get("organs")
    if not isinstance(organs, dict) or not organs:
        raise ValueError("registry must contain nonempty organ mapping")
    for organ in organs.values():
        if not isinstance(organ, dict) or not isinstance(organ.get("repositories"), list):
            raise ValueError("registry organ must contain repository array")
        for entry in organ["repositories"]:
            if not isinstance(entry, dict) or any(
                not isinstance(entry.get(field), str) or not entry[field]
                for field in ("org", "name", "implementation_status")
            ) or type(entry.get("public")) is not bool:
                raise ValueError("registry identity/status/public fields are malformed")
            if "archived" in entry and type(entry["archived"]) is not bool:
                raise ValueError("registry archived override must be boolean")
            if "note" in entry and not isinstance(entry["note"], str):
                raise ValueError("registry note must be a string")
    if not any(organ["repositories"] for organ in organs.values()):
        raise ValueError("registry must contain repository rows")
    summary = registry.get("summary", {})
    if not isinstance(summary, dict):
        raise ValueError("registry summary must be an object")
    timestamp = snapshot.get("observed_at")
    if not isinstance(timestamp, str):
        raise ValueError("snapshot observation timestamp must be a string")
    observed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if observed.tzinfo is None:
        raise ValueError("snapshot observation timestamp must include timezone")

    installations = snapshot.get("installation_pages")
    if not isinstance(installations, list) or not installations:
        raise ValueError("missing installation inventory")
    catalogue = snapshot.get("installation_catalogue")
    if not isinstance(catalogue, list) or not catalogue:
        raise ValueError("missing installation catalogue")
    if any(not isinstance(installation, dict) for installation in catalogue):
        raise ValueError("installation catalogue entries must be objects")
    catalogue_ids = [installation.get("id") for installation in catalogue]
    if any(type(value) is not int or value <= 0 for value in catalogue_ids) or len(catalogue_ids) != len(set(catalogue_ids)):
        raise ValueError("invalid or duplicate installation catalogue ID")
    installed = {}
    installation_ids = set()
    for installation in installations:
        if not isinstance(installation, dict):
            raise ValueError("installation receipt must be an object")
        installation_id = installation.get("installation_id")
        if type(installation_id) is not int or installation_id <= 0 or installation_id in installation_ids:
            raise ValueError("invalid or duplicate installation ID")
        installation_ids.add(installation_id)
        for repo_id in _page_ids(installation.get("pages"), str(installation_id)):
            if repo_id in installed:
                raise ValueError("repository ID appears in multiple installations")
            installed[repo_id] = installation_id
    if installation_ids != set(catalogue_ids):
        raise ValueError("installation page receipts do not cover complete catalogue")
    collaborators = _page_ids(snapshot.get("collaborator_pages"), "collaborators")

    repos = snapshot.get("repositories")
    if not isinstance(repos, list):
        raise ValueError("missing repository inventory")
    by_id = {}
    for repo in repos:
        if not isinstance(repo, dict):
            raise ValueError("repository inventory entries must be objects")
        repo_id = repo.get("id")
        if not _canonical_repository_id(repo_id) or repo_id in by_id:
            raise ValueError("invalid or duplicate stable repository ID")
        if repo.get("visibility") not in {"public", "private", "internal"}:
            raise ValueError("invalid live visibility")
        if type(repo.get("archived")) is not bool:
            raise ValueError("invalid live archive value")
        if repo.get("installation_id") != installed.get(repo_id):
            raise ValueError("repository installation does not match page receipts")
        full_name = repo.get("full_name")
        if not isinstance(full_name, str) or len(full_name.split("/")) != 2:
            raise ValueError("invalid canonical repository path")
        if repo.get("name") != full_name.split("/")[1]:
            raise ValueError("repository name differs from canonical path")
        by_id[repo_id] = repo
    if set(by_id) != set(installed) | collaborators:
        raise ValueError("repository inventory differs from paginated ID union")
    paths = [repo["full_name"].lower() for repo in repos]
    if len(paths) != len(set(paths)):
        raise ValueError("canonical path maps to multiple IDs")

    resolutions = snapshot.get("resolutions")
    if not isinstance(resolutions, list):
        raise ValueError("missing old-path resolutions")
    by_row = {}
    for resolution in resolutions:
        if not isinstance(resolution, dict):
            raise ValueError("old-path resolutions must be objects")
        key = resolution.get("row_key")
        if not isinstance(key, str) or key in by_row:
            raise ValueError("invalid or duplicate resolution row")
        by_row[key] = resolution

    rows = []
    used = {repo_id: [] for repo_id in by_id}
    for organ_key, organ in registry.get("organs", {}).items():
        for index, entry in enumerate(organ.get("repositories", [])):
            key = f"{organ_key}:{index}"
            requested = f"{entry['org']}/{entry['name']}"
            resolution = by_row.pop(key, None)
            if resolution is None or resolution.get("requested_full_name") != requested:
                raise ValueError(f"{key}: missing or wrong old-path resolution")
            row = {
                "row_key": key, "registry_path": requested,
                "promotion_status": entry.get("promotion_status"),
                "last_validated": entry.get("last_validated"),
                "repository_id": None, "canonical_path": None,
                "metadata_mismatches": [], "same_name_candidates": [],
            }
            if resolution.get("status") == "resolved":
                repo_id = resolution.get("repository_id")
                repo = by_id.get(repo_id)
                if repo is None or repo["full_name"] != resolution.get("full_name"):
                    raise ValueError(f"{key}: resolution disagrees with stable-ID inventory")
                row.update({
                    "repository_id": repo_id,
                    "canonical_path": repo["full_name"],
                    "binding": "literal" if requested == repo["full_name"] else "redirect",
                    "live_visibility": repo["visibility"],
                    "live_archived": repo["archived"],
                })
                used[repo_id].append(key)
                if entry.get("public") != (repo["visibility"] == "public"):
                    row["metadata_mismatches"].append("visibility")
                registry_archived = entry.get(
                    "archived", entry.get("implementation_status") == "ARCHIVED",
                )
                if registry_archived != repo["archived"]:
                    row["metadata_mismatches"].append("archive")
            elif resolution.get("status") == "unavailable":
                if resolution.get("repository_id") is not None or resolution.get("full_name") is not None:
                    raise ValueError(f"{key}: unavailable resolution carries a binding")
                explicit_local = entry.get("org") == "local" and (
                    "local-only" in entry.get("note", "").lower()
                    or "no remote" in entry.get("note", "").lower()
                )
                row["binding"] = "explicit-local" if explicit_local else "unavailable"
                row["error_code"] = resolution.get("error_code")
                row["same_name_candidates"] = [
                    {"repository_id": repo["id"], "canonical_path": repo["full_name"]}
                    for repo in repos if repo["name"].lower() == entry["name"].lower()
                ]
            else:
                raise ValueError(f"{key}: unknown resolution outcome")
            rows.append(row)
    if by_row:
        raise ValueError("snapshot has resolutions absent from this registry")
    declared = summary.get("total_repos")
    if declared is not None and (type(declared) is not int or declared != len(rows)):
        raise ValueError("registry declared total differs from row count")

    duplicates = [
        {"repository_id": repo_id, "canonical_path": by_id[repo_id]["full_name"],
         "registry_rows": keys, "disposition": "alias-or-merge-decision-required"}
        for repo_id, keys in used.items() if len(keys) > 1
    ]
    inventory_map = [
        {"repository_id": repo_id, "canonical_path": repo["full_name"],
         "visibility": repo["visibility"], "archived": repo["archived"],
         "registry_rows": used[repo_id],
         "registration_disposition": "registered" if used[repo_id] else "unregistered-or-exclusion-required",
         "activation_status": "unknown", "activation_evidence": []}
        for repo_id, repo in sorted(by_id.items(), key=lambda item: item[1]["full_name"].lower())
    ]
    summary = {
        "installations": len(installations), "visible_repositories": len(by_id),
        "installed_repositories": len(installed),
        "collaborator_only_repositories": len(collaborators - set(installed)),
        "public_repositories": sum(r["visibility"] == "public" for r in repos),
        "private_repositories": sum(r["visibility"] == "private" for r in repos),
        "archived_repositories": sum(r["archived"] for r in repos),
        "registry_rows": len(rows),
        "literal_rows": sum(r["binding"] == "literal" for r in rows),
        "redirect_rows": sum(r["binding"] == "redirect" for r in rows),
        "bound_rows": sum(r["repository_id"] is not None for r in rows),
        "bound_unique_ids": sum(bool(keys) for keys in used.values()),
        "explicit_local_rows": sum(r["binding"] == "explicit-local" for r in rows),
        "unavailable_rows": sum(r["binding"] == "unavailable" for r in rows),
        "same_name_candidate_rows": sum(bool(r["same_name_candidates"]) for r in rows),
        "duplicate_identity_groups": len(duplicates),
        "metadata_discrepancy_rows": sum(bool(r["metadata_mismatches"]) for r in rows),
        "visibility_discrepancy_rows": sum("visibility" in r["metadata_mismatches"] for r in rows),
        "archive_discrepancy_rows": sum("archive" in r["metadata_mismatches"] for r in rows),
        "unregistered_inventory_ids": sum(not keys for keys in used.values()),
    }
    blockers = [key for key in (
        "redirect_rows", "unavailable_rows", "duplicate_identity_groups", "metadata_discrepancy_rows",
        "unregistered_inventory_ids",
    ) if summary[key]]
    return {
        "report_version": "organvm.v3-identity-reconciliation.v1",
        "observed_at": snapshot["observed_at"], "registry_blob_sha": blob,
        "snapshot_valid": True, "reconciled": not blockers,
        "activation_verified": False, "blockers": blockers,
        "summary": summary, "registry_rows": rows,
        "duplicate_identities": duplicates, "inventory_map": inventory_map,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", default=REGISTRY_PATH)
    parser.add_argument("--identity-snapshot", help="Authenticated, paginated identity evidence JSON")
    parser.add_argument("--output", help="Explicit private output path for identity reconciliation")
    parser.add_argument("--aggregate-only", action="store_true", help="Omit names and IDs from output")
    args = parser.parse_args(argv)
    if args.identity_snapshot:
        if not args.output:
            parser.error("--identity-snapshot requires --output; detailed output may be private")
        output_path = Path(args.output).resolve()
        inputs = {Path(args.registry).resolve(), Path(args.identity_snapshot).resolve()}
        if output_path in inputs:
            parser.error("output must not overwrite either input")
        raw = Path(args.registry).read_bytes()
        try:
            report = reconcile_identity_snapshot(
                json.loads(raw), json.loads(Path(args.identity_snapshot).read_text()), raw,
            )
        except (ValueError, TypeError, KeyError) as error:
            print(f"V3 IDENTITY INPUT INVALID: {error}", file=sys.stderr)
            return 2
        if args.aggregate_only:
            report = {key: value for key, value in report.items()
                      if key not in {"registry_rows", "inventory_map", "duplicate_identities"}}
            report["report_version"] = "organvm.v3-identity-reconciliation.aggregate.v1"
        descriptor = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
            stream.write("\n")
        print(json.dumps(report["summary"], sort_keys=True))
        print(f"V3 IDENTITY RESULT: {'PASS' if report['reconciled'] else 'RECONCILIATION REQUIRED'}")
        return 0 if report["reconciled"] else 1
    if args.output or args.aggregate_only or args.registry != REGISTRY_PATH:
        parser.error("--output, --aggregate-only and --registry require --identity-snapshot")
    registry = load_registry()

    print("=" * 80)
    print("V3: REGISTRY-TO-GITHUB RECONCILIATION")
    print("=" * 80)

    # Build registry map: {(org, name): repo_data}
    registry_repos = {}
    for organ_key, organ_data in registry.get("organs", {}).items():
        for repo in organ_data.get("repositories", []):
            key = (repo["org"], repo["name"])
            registry_repos[key] = repo

    print(f"\nRegistry contains {len(registry_repos)} total repo entries")

    # ── Step 1: List all repos on GitHub ────────────────────────────
    print("\n── Listing repos on GitHub ──")
    github_repos = {}  # org -> [repo_names]

    for org in SYSTEM_ORGS:
        sys.stdout.write(f"\r  Listing {org}...")
        sys.stdout.flush()
        repos = gh_list_repos(org)
        github_repos[org] = repos
        print(f"\r  {org}: {len(repos)} repos")

    total_gh = sum(len(v) for v in github_repos.values())
    print(f"\n  Total repos on GitHub: {total_gh}")

    # ── Step 2: Check registry DEPLOYED repos exist on GitHub ──────
    print("\n── Checking DEPLOYED repos exist on GitHub ──")
    deployed_missing = []
    deployed_no_readme = []
    deployed_ok = []

    for (org, name), repo_data in registry_repos.items():
        doc_status = repo_data.get("documentation_status", "")
        note = repo_data.get("note", "")

        # Only check repos that should be DEPLOYED and not NOT_CREATED
        if "NOT_CREATED" in note:
            continue
        if "DEPLOYED" not in doc_status and doc_status != "INFRASTRUCTURE":
            continue

        if name not in github_repos.get(org, []):
            deployed_missing.append((org, name, doc_status))
        else:
            has_rm = gh_has_readme(org, name)
            if has_rm:
                deployed_ok.append((org, name))
            elif has_rm is False:
                deployed_no_readme.append((org, name, doc_status))
            # None means timeout — treat as ok for now

    print(f"  DEPLOYED repos on GitHub with README: {len(deployed_ok)}")
    print(f"  DEPLOYED repos missing from GitHub: {len(deployed_missing)}")
    print(f"  DEPLOYED repos on GitHub WITHOUT README: {len(deployed_no_readme)}")

    if deployed_missing:
        print("\n  MISSING FROM GITHUB:")
        for org, name, status in deployed_missing:
            print(f"    - {org}/{name} (registry says: {status})")

    if deployed_no_readme:
        print("\n  NO README ON GITHUB:")
        for org, name, status in deployed_no_readme:
            print(f"    - {org}/{name} (registry says: {status})")

    # ── Step 3: Check for GitHub repos missing from registry ────────
    print("\n── Checking for GitHub repos not in registry ──")
    github_not_in_registry = []

    for org, repo_names in github_repos.items():
        for name in repo_names:
            if (org, name) not in registry_repos:
                github_not_in_registry.append((org, name))

    if github_not_in_registry:
        print(f"  {len(github_not_in_registry)} repos on GitHub not in registry:")
        for org, name in github_not_in_registry:
            print(f"    - {org}/{name}")
    else:
        print("  All GitHub repos accounted for in registry")

    # ── Step 4: Description comparison ──────────────────────────────
    print("\n── Checking description matches ──")
    desc_mismatches = []

    # Only check repos that had descriptions set during Gold Sprint
    for (org, name), repo_data in registry_repos.items():
        note = repo_data.get("note", "")
        if "NOT_CREATED" in note:
            continue
        if name not in github_repos.get(org, []):
            continue

        registry_desc = repo_data.get("description", "")
        # Only compare if registry has a substantial description
        if not registry_desc or len(registry_desc) < 20:
            continue

        gh_desc = gh_get_description(org, name)
        if gh_desc is not None and gh_desc and gh_desc != registry_desc:
            # Only flag if they're very different (not just minor wording changes)
            if len(gh_desc) > 0 and registry_desc.lower()[:50] != gh_desc.lower()[:50]:
                desc_mismatches.append((org, name, registry_desc[:80], gh_desc[:80]))

    if desc_mismatches:
        print(f"  {len(desc_mismatches)} description mismatches:")
        for org, name, reg_desc, gh_desc in desc_mismatches[:10]:
            print(f"    {org}/{name}:")
            print(f"      Registry: {reg_desc}...")
            print(f"      GitHub:   {gh_desc}...")
    else:
        print("  No significant description mismatches found")

    # ── Summary ──────────────────────────────────────────────────────
    print(f"\n{'=' * 80}")
    print("V3 SUMMARY")
    print(f"{'=' * 80}")
    print(f"  Registry repos: {len(registry_repos)}")
    print(f"  GitHub repos: {total_gh}")
    print(f"  DEPLOYED + on GitHub + has README: {len(deployed_ok)}")
    print(f"  DEPLOYED but missing from GitHub: {len(deployed_missing)}")
    print(f"  DEPLOYED but no README: {len(deployed_no_readme)}")
    print(f"  On GitHub but not in registry: {len(github_not_in_registry)}")
    print(f"  Description mismatches: {len(desc_mismatches)}")

    v3_pass = len(deployed_missing) == 0 and len(deployed_no_readme) == 0
    print(f"\n  V3 RESULT: {'PASS' if v3_pass else 'ISSUES FOUND'}")

    # Write report
    report = {
        "registry_count": len(registry_repos),
        "github_count": total_gh,
        "deployed_ok": len(deployed_ok),
        "deployed_missing": [{"org": o, "repo": r, "status": s} for o, r, s in deployed_missing],
        "deployed_no_readme": [{"org": o, "repo": r, "status": s} for o, r, s in deployed_no_readme],
        "github_not_in_registry": [{"org": o, "repo": r} for o, r in github_not_in_registry],
        "description_mismatches": [{"org": o, "repo": r, "registry": rd, "github": gd} for o, r, rd, gd in desc_mismatches],
        "pass": v3_pass
    }

    report_path = os.path.join(os.path.dirname(__file__), "v3-report.json")
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"\n  Report written to {report_path}")


if __name__ == "__main__":
    sys.exit(main())
