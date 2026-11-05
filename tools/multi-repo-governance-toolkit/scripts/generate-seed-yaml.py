#!/usr/bin/env python3
"""Generate seed.yaml for repos that don't have one yet.

Reads repo-registry.json to enumerate all non-archived repos, checks which
already have seed.yaml, and generates one for each missing repo using
registry metadata and organ-level defaults.

Usage:
    python3 scripts/generate-seed-yaml.py                  # dry-run (default)
    python3 scripts/generate-seed-yaml.py --write          # write locally
    python3 scripts/generate-seed-yaml.py --write --push   # write + git push
    python3 scripts/generate-seed-yaml.py --remote-only    # push via gh api (no local clone needed)
"""

import argparse
import base64
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# ISOTOPE DISSOLUTION: Gate memory--remember G2 (CORPUS_SCRIPTS_DISSOLVED)
try:
    from organvm_engine.registry.loader import load_registry as _engine_load
except ImportError:
    _engine_load = None

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "repo-registry.json"
WORKSPACE = Path(os.environ.get("ORGANVM_WORKSPACE", ".")).expanduser()

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

# ── Organ metadata ──────────────────────────────────────────
# Maps organ key to (number, name, suffix)
ORGAN_MAP = {
    "ORGAN-I":      ("I",    "Theory",        "theoria"),
    "ORGAN-II":     ("II",   "Art",           "poiesis"),
    "ORGAN-III":    ("III",  "Commerce",      "ergon"),
    "ORGAN-IV":     ("IV",   "Orchestration", "taxis"),
    "ORGAN-V":      ("V",    "Public Process","logos"),
    "ORGAN-VI":     ("VI",   "Community",     "koinonia"),
    "ORGAN-VII":    ("VII",  "Marketing",     "kerygma"),
    "META-ORGANVM": ("Meta", "Meta",          "meta-organvm"),
}

# ── Organ-level produces/consumes defaults ──────────────────
ORGAN_PRODUCES = {
    "I":    [{"type": "theory", "description": "Epistemological frameworks, recursive engines, ontological systems"}],
    "II":   [{"type": "creative-artifact", "description": "Generative art, interactive system, or experiential work"}],
    "III":  [{"type": "product", "description": "Software product, API, or service"}],
    "IV":   [{"type": "governance-policy", "description": "Orchestration config and governance rules"}],
    "V":    [{"type": "essay", "description": "Public narrative documenting the building process"}],
    "VI":   [{"type": "session-archive", "description": "Salon sessions, reading group curricula"}],
    "VII":  [{"type": "distribution-record", "description": "POSSE distribution and social posts"}],
    "Meta": [{"type": "registry", "description": "System-wide registry, audit records, classified artifacts"}],
}

ORGAN_CONSUMES = {
    "I":    [],
    "II":   [{"type": "theory-artifact", "source": "ORGAN-I", "description": "Theoretical frameworks inform art creation"}],
    "III":  [],
    "IV":   [{"type": "registry", "source": "META-ORGANVM", "description": "Registry data for orchestration"}],
    "V":    [{"type": "theory", "source": "ORGAN-I", "description": "Theory informs public essays"}],
    "VI":   [],
    "VII":  [{"type": "essay", "source": "ORGAN-V", "description": "Essays for POSSE distribution"}],
    "Meta": [],
}

ORGAN_SUBSCRIPTIONS = {
    "I":    [
        {"event": "governance.updated", "source": "ORGAN-IV", "action": "Check compliance with updated governance rules"},
        {"event": "health-audit.completed", "source": "ORGAN-IV", "action": "Review audit findings for this repo"},
    ],
    "II":   [
        {"event": "governance.updated", "source": "ORGAN-IV", "action": "Check compliance with updated governance rules"},
        {"event": "health-audit.completed", "source": "ORGAN-IV", "action": "Review audit findings for this repo"},
        {"event": "theory.published", "source": "ORGAN-I", "action": "Check for art derivative opportunities"},
    ],
    "III":  [
        {"event": "governance.updated", "source": "ORGAN-IV", "action": "Check compliance with updated governance rules"},
        {"event": "health-audit.completed", "source": "ORGAN-IV", "action": "Review audit findings for this repo"},
    ],
    "IV":   [
        {"event": "registry.updated", "source": "META-ORGANVM", "action": "Re-validate dependency graph"},
    ],
    "V":    [
        {"event": "governance.updated", "source": "ORGAN-IV", "action": "Check compliance with updated governance rules"},
    ],
    "VI":   [
        {"event": "governance.updated", "source": "ORGAN-IV", "action": "Check compliance with updated governance rules"},
    ],
    "VII":  [
        {"event": "essay.published", "source": "ORGAN-V", "action": "Distribute via POSSE channels"},
    ],
    "Meta": [],
}

# ── Language detection ──────────────────────────────────────

LANG_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".rb": "ruby",
    ".swift": "swift",
    ".kt": "kotlin",
    ".c": "c",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".php": "php",
    ".sh": "shell",
    ".zsh": "shell",
    ".bash": "shell",
}

# Directories to skip when detecting language
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".next", "dist", "build"}


def detect_language_local(repo_path: Path) -> str:
    """Detect primary language from file extensions in local repo."""
    counts: dict[str, int] = {}
    try:
        for f in repo_path.rglob("*"):
            if any(part in SKIP_DIRS for part in f.parts):
                continue
            if f.is_file():
                ext = f.suffix.lower()
                if ext in LANG_EXTENSIONS:
                    lang = LANG_EXTENSIONS[ext]
                    counts[lang] = counts.get(lang, 0) + 1
    except (PermissionError, OSError):
        pass

    if not counts:
        return "mixed"
    return max(counts, key=counts.get)


def detect_language_remote(org: str, repo: str) -> str:
    """Detect primary language from GitHub API."""
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{org}/{repo}/languages", "--jq", "keys[0]"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().lower()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return "mixed"


# ── CI workflow mapping ─────────────────────────────────────

def ci_workflow_path(value: object) -> str | None:
    """Preserve registered workflow names; reject malformed paths visibly.

    Empty strings and the exact workflow-directory prefix are legacy registry
    representations. Accept them here while canonical records migrate to null
    and basenames. This describes a workflow, not its execution or health.
    """
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError("ci_workflow must be a workflow basename or null")
    name = value.removeprefix(".github/workflows/")
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*\.ya?ml", name):
        raise ValueError("ci_workflow must be a workflow basename or null")
    return f".github/workflows/{name}"


# ── YAML generation ─────────────────────────────────────────
# Hand-crafted YAML generation to match existing seed.yaml style exactly.
# No external dependency needed.

def yaml_str(value) -> str:
    """Quote a YAML string value if needed."""
    s = str(value)
    if s in ("true", "false", "null", "yes", "no", "on", "off") or s.startswith("{") or s.startswith("["):
        return f'"{s}"'
    if any(c in s for c in ":{}[]&*?|->!%@`#,"):
        return f'"{s}"'
    return s


def generate_seed_yaml(repo_data: dict, organ_key: str, organ_num: str, organ_name: str, language: str) -> str:
    """Generate seed.yaml content for a repo."""
    name = repo_data["name"]
    org = repo_data["org"]
    impl_status = repo_data.get("implementation_status", "ACTIVE")
    tier = repo_data.get("tier", "standard")
    promotion = repo_data.get("promotion_status", "LOCAL")
    ci_workflow = ci_workflow_path(repo_data.get("ci_workflow"))

    lines = [
        f"# seed.yaml — Automation Contract for {org}/{name}",
        "# Schema: seed/v1.0",
        f"# Generated: {TODAY} (SENSORIA Sprint)",
        "",
        'schema_version: "1.0"',
        f"organ: {organ_num}",
        f"organ_name: {organ_name}",
        f"repo: {name}",
        f"org: {org}",
        "",
        "metadata:",
        f"  implementation_status: {impl_status}",
        f"  tier: {tier}",
        f"  promotion_status: {promotion}",
        f'  last_validated: "{repo_data.get("last_validated", TODAY)}"',
        f'  generated: "{TODAY}"',
        '  sprint: "SENSORIA"',
        f"  language: {language}",
    ]

    # Agents
    lines.append("")
    if ci_workflow:
        lines.append("agents:")
        lines.append("  - name: ci")
        lines.append("    trigger: on_push")
        lines.append(f"    workflow: {ci_workflow}")
        lines.append('    description: "Continuous integration pipeline"')
    else:
        lines.append("agents: []")

    # Produces
    lines.append("")
    produces = ORGAN_PRODUCES.get(organ_num, [])
    if produces:
        lines.append("produces:")
        for p in produces:
            lines.append(f"  - type: {p['type']}")
            lines.append(f'    description: "{p["description"]}"')
    else:
        lines.append("produces: []")

    # Consumes
    lines.append("")
    consumes = ORGAN_CONSUMES.get(organ_num, [])
    if consumes:
        lines.append("consumes:")
        for c in consumes:
            lines.append(f"  - type: {c['type']}")
            lines.append(f"    source: {c['source']}")
            lines.append(f"    description: {c['description']}")
    else:
        lines.append("consumes: []")

    # Subscriptions
    lines.append("")
    subs = ORGAN_SUBSCRIPTIONS.get(organ_num, [])
    if subs:
        lines.append("subscriptions:")
        for s in subs:
            lines.append(f"  - event: {s['event']}")
            lines.append(f"    source: {s['source']}")
            lines.append(f"    action: {s['action']}")
    else:
        lines.append("subscriptions: []")

    lines.append("")  # trailing newline
    return "\n".join(lines)


# ── Push helpers ────────────────────────────────────────────

def push_local(repo_path: Path, content: str) -> tuple[bool, str]:
    """Write seed.yaml locally, git add + commit + push."""
    seed_file = repo_path / "seed.yaml"
    seed_file.write_text(content)

    # Detect default branch
    result = subprocess.run(
        ["git", "-C", str(repo_path), "branch", "--show-current"],
        capture_output=True, text=True,
    )
    branch = result.stdout.strip() or "main"

    # Pull to reconcile any remote-only commits (from previous gh api pushes)
    subprocess.run(
        ["git", "-C", str(repo_path), "pull", "--rebase", "origin", branch],
        capture_output=True, text=True, timeout=30,
    )

    # Git add + commit + push
    subprocess.run(["git", "-C", str(repo_path), "add", "seed.yaml"],
                    capture_output=True, text=True)

    result = subprocess.run(
        ["git", "-C", str(repo_path), "commit", "-m", "feat: add seed.yaml (SENSORIA sprint)"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        if "nothing to commit" in result.stdout or "nothing to commit" in result.stderr:
            return True, "already committed"
        return False, f"commit failed: {result.stderr.strip()}"

    result = subprocess.run(
        ["git", "-C", str(repo_path), "push", "origin", branch],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        return False, f"push failed: {result.stderr.strip()}"

    return True, "pushed"


def push_remote(org: str, repo: str, content: str) -> tuple[bool, str]:
    """Push seed.yaml via gh api (for repos without local clone)."""
    # Get default branch
    result = subprocess.run(
        ["gh", "api", f"repos/{org}/{repo}", "--jq", ".default_branch"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return False, f"cannot fetch repo info: {result.stderr.strip()}"
    branch = result.stdout.strip()

    # Check if file already exists
    result = subprocess.run(
        ["gh", "api", f"repos/{org}/{repo}/contents/seed.yaml", "--jq", ".sha"],
        capture_output=True, text=True,
    )
    sha = result.stdout.strip() if result.returncode == 0 else None

    encoded = base64.b64encode(content.encode()).decode()
    payload = {
        "message": "feat: add seed.yaml (SENSORIA sprint)",
        "content": encoded,
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha

    result = subprocess.run(
        ["gh", "api", f"repos/{org}/{repo}/contents/seed.yaml",
         "--method", "PUT", "--input", "-"],
        input=json.dumps(payload),
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        return False, f"API PUT failed: {result.stderr.strip()}"

    return True, "pushed via API"


# ── Main ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate seed.yaml for repos missing it")
    parser.add_argument("--write", action="store_true",
                        help="Write seed.yaml files locally (default is dry-run)")
    parser.add_argument("--push", action="store_true",
                        help="Also git push after writing (implies --write)")
    parser.add_argument("--remote-only", action="store_true",
                        help="Push via gh api even for repos without local clones")
    parser.add_argument("--organ", type=str, default=None,
                        help="Only process this organ (e.g. ORGAN-I)")
    parser.add_argument("--repo", type=str, default=None,
                        help="Only process this specific repo name")
    args = parser.parse_args()

    if args.push:
        args.write = True

    # Load registry
    if _engine_load is not None:
        registry = _engine_load(REGISTRY)
    else:
        with open(REGISTRY) as f:
            registry = json.load(f)

    missing = []
    skipped_archived = 0
    skipped_dotgithub = 0
    already_have = 0

    for organ_key, organ_data in registry["organs"].items():
        if args.organ and organ_key != args.organ:
            continue

        organ_num, organ_name, _ = ORGAN_MAP.get(organ_key, ("?", "?", "?"))

        for repo in organ_data["repositories"]:
            name = repo["name"]
            org = repo["org"]

            if args.repo and name != args.repo:
                continue

            # Skip archived
            impl_status = repo.get("implementation_status", repo.get("status", ""))
            if impl_status == "ARCHIVED":
                skipped_archived += 1
                continue

            # Skip .github profile repos
            if name == ".github":
                skipped_dotgithub += 1
                continue

            # Check if seed.yaml exists locally
            local_path = WORKSPACE / org / name
            seed_path = local_path / "seed.yaml"
            if seed_path.exists():
                already_have += 1
                continue

            missing.append((organ_key, organ_num, organ_name, repo, local_path))

    print(f"Registry scan: {already_have} have seed.yaml, {len(missing)} missing")
    print(f"Skipped: {skipped_archived} archived, {skipped_dotgithub} .github repos")
    print(f"Mode: {'WRITE' + (' + PUSH' if args.push else '') if args.write else 'DRY RUN'}")
    print()

    results = {"success": 0, "failed": 0, "skipped": 0}

    for organ_key, organ_num, organ_name, repo, local_path in missing:
        name = repo["name"]
        org = repo["org"]
        has_local = local_path.exists()

        # Detect language
        if has_local:
            language = detect_language_local(local_path)
        elif args.remote_only or args.push:
            language = detect_language_remote(org, name)
        else:
            language = "mixed"

        content = generate_seed_yaml(repo, organ_key, organ_num, organ_name, language)

        if not args.write:
            print(f"  [DRY] {org}/{name} (lang={language}, local={'yes' if has_local else 'no'})")
            results["success"] += 1
            continue

        if has_local:
            seed_file = local_path / "seed.yaml"
            seed_file.write_text(content)
            print(f"  [WROTE] {org}/{name} (lang={language})")

            if args.push:
                ok, msg = push_local(local_path, content)
                if ok:
                    print(f"    → {msg}")
                    results["success"] += 1
                else:
                    print(f"    ✗ {msg}")
                    results["failed"] += 1
            else:
                results["success"] += 1
        elif args.remote_only:
            ok, msg = push_remote(org, name, content)
            if ok:
                print(f"  [REMOTE] {org}/{name} → {msg}")
                results["success"] += 1
            else:
                print(f"  [FAIL] {org}/{name} → {msg}")
                results["failed"] += 1
        else:
            print(f"  [SKIP] {org}/{name} (no local clone, use --remote-only)")
            results["skipped"] += 1

    print(f"\nDone: {results['success']} ok, {results['failed']} failed, {results['skipped']} skipped")


if __name__ == "__main__":
    main()
