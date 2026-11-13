#!/usr/bin/env python3
"""MANIFESTATIO Sprint: System-wide code substance audit.

Audits ALL active (non-archived, non-.github) repos across the 8-organ system.
Produces code-substance-report.json with per-repo and aggregate metrics.

Usage:
    python3 scripts/manifestatio-code-audit.py [--output code-substance-report.json]
"""

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REGISTRY_PATH = Path(__file__).parent.parent / "repo-registry.json"

# Code file extensions per language
CODE_EXTENSIONS = {
    "Python": {".py"},
    "TypeScript": {".ts", ".tsx", ".js", ".jsx"},
    "Jekyll": {".rb", ".html", ".scss", ".css", ".js"},
    "Go": {".go"},
    "Rust": {".rs"},
    "Shell": {".sh", ".bash", ".zsh"},
}

# All code extensions combined
ALL_CODE_EXTS = set()
for exts in CODE_EXTENSIONS.values():
    ALL_CODE_EXTS.update(exts)

# Test patterns per language
TEST_PATTERNS = {
    "Python": ["test_", "_test.py", "tests/", "spec_", "conftest.py"],
    "TypeScript": [".test.", ".spec.", "__tests__/", "tests/"],
    "Jekyll": ["_spec.", "test"],
    "Go": ["_test.go"],
    "Rust": ["tests/", "#[test]"],
    "Shell": ["test", "bats"],
}


def gh_api(endpoint, jq_filter=None):
    """Call GitHub API via gh CLI."""
    cmd = ["gh", "api", endpoint]
    if jq_filter:
        cmd.extend(["--jq", jq_filter])
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None, result.stderr.strip()
    return result.stdout.strip(), None


def detect_language(paths):
    """Detect primary language from file extensions in tree."""
    counts = {}
    for p in paths:
        if "." not in p:
            continue
        ext = "." + p.rsplit(".", 1)[-1]
        for lang, exts in CODE_EXTENSIONS.items():
            if ext in exts:
                counts[lang] = counts.get(lang, 0) + 1
    if not counts:
        return "Unknown"
    return max(counts, key=counts.get)


def audit_repo(org, repo, language_hint=None):
    """Audit a single repo for code substance."""
    full = f"{org}/{repo}"
    report = {
        "org": org,
        "repo": repo,
        "audited": datetime.now(timezone.utc).isoformat(),
    }

    # Get file tree
    tree_data, err = gh_api(
        f"repos/{full}/git/trees/HEAD?recursive=1",
        "[.tree[] | .path]"
    )
    if err:
        report["error"] = f"Could not fetch tree: {err}"
        report["classification"] = "ERROR"
        report["language"] = language_hint or "Unknown"
        return report

    try:
        paths = json.loads(tree_data)
    except (json.JSONDecodeError, TypeError):
        report["error"] = "Could not parse tree response"
        report["classification"] = "ERROR"
        report["language"] = language_hint or "Unknown"
        return report

    # Detect language from actual file contents
    language = detect_language(paths)
    if language == "Unknown" and language_hint:
        language = language_hint
    report["language"] = language

    code_exts = CODE_EXTENSIONS.get(language, set())
    test_pats = TEST_PATTERNS.get(language, [])

    code_files = []
    test_files = []
    doc_files = []
    config_files = []
    total_files = len(paths)

    # Code-capable dotdirs (contain real scripts, not just config)
    code_dotdirs = {".github", ".ci"}

    for p in paths:
        lower = p.lower()
        ext = "." + p.rsplit(".", 1)[-1] if "." in p else ""

        # Skip truly hidden directories
        if any(seg.startswith(".") for seg in p.split("/") if seg not in code_dotdirs):
            config_files.append(p)
            continue

        # Test detection — code extension + test pattern
        is_test = any(pat in lower for pat in test_pats)
        if is_test and ext in code_exts:
            test_files.append(p)
            continue

        # Code detection — BEFORE docs/config to avoid misclassifying
        if ext in code_exts:
            code_files.append(p)
            continue

        # Doc detection — only for doc extensions or docs/ with non-code files
        if ext in {".md", ".txt", ".rst", ".adoc"}:
            doc_files.append(p)
            continue
        if lower.startswith("docs/") and ext not in ALL_CODE_EXTS:
            doc_files.append(p)
            continue

        # Config detection
        if ext in {".yml", ".yaml", ".toml", ".json", ".cfg", ".ini", ".lock"}:
            config_files.append(p)
            continue

    # Check for test directories
    has_tests_dir = any(
        p.startswith("tests/") or p.startswith("test/") or "/tests/" in p or "/__tests__/" in p
        for p in paths
    )

    # CI status
    ci_data, ci_err = gh_api(
        f"repos/{full}/actions/runs?per_page=1",
        ".workflow_runs[0] | {status, conclusion, name, created_at}"
    )
    ci_status = None
    if ci_data and ci_data != "null":
        try:
            ci_status = json.loads(ci_data)
        except json.JSONDecodeError:
            pass

    # Classify
    code_count = len(code_files)
    test_count = len(test_files)

    if code_count >= 20 and test_count >= 5:
        classification = "SUBSTANTIAL"
    elif code_count >= 10 or (code_count >= 5 and test_count >= 1):
        classification = "PARTIAL"
    elif code_count >= 1:
        classification = "MINIMAL"
    else:
        classification = "SKELETON"

    report.update({
        "total_files": total_files,
        "code_files": code_count,
        "test_files": test_count,
        "doc_files": len(doc_files),
        "config_files": len(config_files),
        "has_tests_dir": has_tests_dir,
        "ci_latest": ci_status,
        "classification": classification,
    })

    return report


def main():
    parser = argparse.ArgumentParser(description="System-wide code substance audit")
    parser.add_argument("--output", default="code-substance-report.json",
                        help="Output JSON report path")
    args = parser.parse_args()

    print("=" * 60)
    print("MANIFESTATIO Sprint — System-Wide Code Substance Audit")
    print("=" * 60)

    with open(REGISTRY_PATH) as f:
        reg = json.load(f)

    targets = []
    for organ_key, organ_data in reg["organs"].items():
        for repo in organ_data.get("repositories", []):
            if repo.get("implementation_status") == "ARCHIVED":
                continue
            if repo["name"] == ".github":
                continue
            lang_hint = "Python"
            ci = repo.get("ci_workflow") or ""
            if "typescript" in ci:
                lang_hint = "TypeScript"
            elif "python" in ci:
                lang_hint = "Python"
            targets.append({
                "org": repo.get("org", ""),
                "repo": repo["name"],
                "organ": organ_key.replace("ORGAN-", "").replace("META-ORGANVM", "Meta"),
                "language_hint": lang_hint,
            })

    reports = []
    classifications = {"SUBSTANTIAL": 0, "PARTIAL": 0, "MINIMAL": 0, "SKELETON": 0, "ERROR": 0}
    repos_with_10_plus_code = 0
    repos_with_tests_dir = 0
    total_code_files = 0
    total_test_files = 0

    for i, target in enumerate(targets, 1):
        full = f"{target['org']}/{target['repo']}"
        print(f"\n[{i}/{len(targets)}] Auditing {full}")
        report = audit_repo(target["org"], target["repo"], target["language_hint"])
        report["organ"] = target["organ"]

        cls = report.get("classification", "ERROR")
        classifications[cls] = classifications.get(cls, 0) + 1

        code_count = report.get("code_files", 0)
        test_count = report.get("test_files", 0)
        total_code_files += code_count
        total_test_files += test_count

        if code_count >= 10:
            repos_with_10_plus_code += 1
        if report.get("has_tests_dir"):
            repos_with_tests_dir += 1

        status_icon = {
            "SUBSTANTIAL": "+",
            "PARTIAL": "~",
            "MINIMAL": "-",
            "SKELETON": "!",
            "ERROR": "X",
        }.get(cls, "?")

        ci_conclusion = ""
        if report.get("ci_latest"):
            ci_conclusion = f", CI: {report['ci_latest'].get('conclusion', 'unknown')}"

        print(f"  [{status_icon}] {cls}: {code_count} code, "
              f"{test_count} test, {report.get('language', '?')}"
              f"{ci_conclusion}")

        reports.append(report)

    # Summary
    print(f"\n{'=' * 60}")
    print("SYSTEM-WIDE CODE SUBSTANCE SUMMARY")
    print(f"{'=' * 60}")
    for cls, count in sorted(classifications.items()):
        if count > 0:
            print(f"  {cls}: {count}")
    print(f"\n  Total repos audited: {len(reports)}")
    print(f"  Repos with 10+ code files: {repos_with_10_plus_code}")
    print(f"  Repos with test directories: {repos_with_tests_dir}")
    print(f"  Total code files: {total_code_files}")
    print(f"  Total test files: {total_test_files}")

    # CI summary
    ci_passing = sum(1 for r in reports if r.get("ci_latest", {}) and r.get("ci_latest", {}).get("conclusion") == "success")
    ci_failing = sum(1 for r in reports if r.get("ci_latest", {}) and r.get("ci_latest", {}).get("conclusion") == "failure")
    ci_none = sum(1 for r in reports if not r.get("ci_latest"))
    print(f"\n  CI passing: {ci_passing}")
    print(f"  CI failing: {ci_failing}")
    print(f"  CI none: {ci_none}")

    output_data = {
        "audit_date": datetime.now(timezone.utc).isoformat(),
        "sprint": "MANIFESTATIO",
        "total_audited": len(reports),
        "summary": {
            "classifications": classifications,
            "repos_with_10_plus_code_files": repos_with_10_plus_code,
            "repos_with_test_directories": repos_with_tests_dir,
            "total_code_files": total_code_files,
            "total_test_files": total_test_files,
            "ci_passing": ci_passing,
            "ci_failing": ci_failing,
            "ci_none": ci_none,
        },
        "repos": reports,
    }

    output_path = Path(args.output)
    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)
        f.write("\n")

    print(f"\n  Report: {output_path}")


if __name__ == "__main__":
    main()
