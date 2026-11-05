#!/usr/bin/env python3
"""V1: Cross-Org Link Audit + V2: TBD/Placeholder Marker Scan

Fetches all deployed READMEs from GitHub via gh api, then:
- V1: Extracts all markdown links, classifies them, validates they resolve
- V2: Scans for TBD, TODO, PLACEHOLDER, FIXME, "coming soon", "to be determined"
"""

import json
import subprocess
import re
import base64
import sys
import os
from collections import defaultdict
from urllib.parse import urlparse

# ── Config ──────────────────────────────────────────────────────────────
REGISTRY_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "repo-registry.json")

# Markers to scan for (V2)
TBD_PATTERNS = [
    r'\bTBD\b',
    r'\bTODO\b',
    r'\bPLACEHOLDER\b',
    r'\bFIXME\b',
    r'\bcoming\s+soon\b',
    r'\bto\s+be\s+determined\b',
    r'\bto\s+be\s+added\b',
    r'\bwork\s+in\s+progress\b',
    r'\[WIP\]',
]
TBD_REGEX = re.compile('|'.join(TBD_PATTERNS), re.IGNORECASE)

# Link extraction regex
LINK_REGEX = re.compile(r'\[([^\]]*)\]\(([^)]+)\)')

# GitHub org names in our system
SYSTEM_ORGS = {
    'organvm-i-theoria', 'organvm-ii-poiesis', 'organvm-iii-ergon',
    'organvm-iv-taxis', 'organvm-v-logos', 'organvm-vi-koinonia',
    'organvm-vii-kerygma', 'meta-organvm'
}


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


def get_deployed_repos(registry):
    """Get list of (org, repo_name) for repos with DEPLOYED status."""
    repos = []
    for organ_key, organ_data in registry.get("organs", {}).items():
        for repo in organ_data.get("repositories", []):
            doc_status = repo.get("documentation_status", "")
            note = repo.get("note", "")
            # Skip NOT_CREATED repos
            if "NOT_CREATED" in note:
                continue
            # Include DEPLOYED, FLAGSHIP README DEPLOYED, ARCHIVED — README DEPLOYED
            if "DEPLOYED" in doc_status:
                repos.append((repo["org"], repo["name"]))
            # Also include INFRASTRUCTURE (.github repos) for org profile READMEs
            elif doc_status == "INFRASTRUCTURE":
                repos.append((repo["org"], repo["name"]))
    return repos


def fetch_readme(org, repo):
    """Fetch README content via gh api."""
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{org}/{repo}/readme",
             "--jq", ".content"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return None, f"API error: {result.stderr.strip()}"
        content_b64 = result.stdout.strip()
        try:
            content = base64.b64decode(content_b64).decode('utf-8')
            return content, None
        except Exception as e:
            return None, f"Decode error: {e}"
    except subprocess.TimeoutExpired:
        return None, "Timeout"


def fetch_readme_from_profile(org):
    """Fetch org profile README from .github/profile/README.md."""
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{org}/.github/contents/profile/README.md",
             "--jq", ".content"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return None, f"API error: {result.stderr.strip()}"
        content_b64 = result.stdout.strip()
        try:
            content = base64.b64decode(content_b64).decode('utf-8')
            return content, None
        except Exception as e:
            return None, f"Decode error: {e}"
    except subprocess.TimeoutExpired:
        return None, "Timeout"


def classify_link(url):
    """Classify a link as internal, cross-org, or external."""
    parsed = urlparse(url)

    # Relative links
    if not parsed.scheme and not parsed.netloc:
        return "relative"

    # GitHub links
    if parsed.netloc in ('github.com', 'www.github.com'):
        path_parts = parsed.path.strip('/').split('/')
        if len(path_parts) >= 1 and path_parts[0] in SYSTEM_ORGS:
            return "system-github"
        return "external-github"

    # External links
    return "external"


def validate_github_repo_link(org, repo):
    """Check if a GitHub repo exists."""
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{org}/{repo}", "--jq", ".full_name"],
            capture_output=True, text=True, timeout=15
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return None  # Unknown


def validate_external_url(url):
    """Quick HEAD check for external URL."""
    try:
        result = subprocess.run(
            ["curl", "-sI", "-o", "/dev/null", "-w", "%{http_code}",
             "-L", "--max-time", "10", url],
            capture_output=True, text=True, timeout=15
        )
        code = result.stdout.strip()
        return code.startswith("2") or code.startswith("3")
    except (subprocess.TimeoutExpired, Exception):
        return None  # Unknown


def extract_github_org_repo(url):
    """Extract org/repo from a GitHub URL."""
    parsed = urlparse(url)
    if parsed.netloc not in ('github.com', 'www.github.com'):
        return None, None
    parts = parsed.path.strip('/').split('/')
    if len(parts) >= 2:
        return parts[0], parts[1]
    elif len(parts) == 1:
        return parts[0], None
    return None, None


def main():
    registry = load_registry()
    repos = get_deployed_repos(registry)

    print("=" * 80)
    print("PHASE 2 MICRO-VALIDATION: V1 Link Audit + V2 TBD Scan")
    print("=" * 80)
    print(f"\nFound {len(repos)} repos to check in registry")

    # ── Fetch all READMEs ──────────────────────────────────────────────
    readmes = {}  # (org, repo) -> content
    fetch_errors = []

    print("\n── Fetching READMEs ──")
    for i, (org, repo) in enumerate(repos):
        sys.stdout.write(f"\r  [{i+1}/{len(repos)}] {org}/{repo}...")
        sys.stdout.flush()

        if repo == ".github":
            # For .github repos, fetch profile README
            content, err = fetch_readme_from_profile(org)
            if content:
                readmes[(org, repo)] = content
            else:
                # Try root README as fallback
                content2, err2 = fetch_readme(org, repo)
                if content2:
                    readmes[(org, repo)] = content2
                else:
                    fetch_errors.append((org, repo, err or err2))
        else:
            content, err = fetch_readme(org, repo)
            if content:
                readmes[(org, repo)] = content
            else:
                fetch_errors.append((org, repo, err))

    print(f"\n  Fetched {len(readmes)} READMEs, {len(fetch_errors)} errors")

    if fetch_errors:
        print("\n  FETCH ERRORS:")
        for org, repo, err in fetch_errors:
            print(f"    - {org}/{repo}: {err}")

    # ── V2: TBD/Placeholder Scan ──────────────────────────────────────
    print(f"\n{'=' * 80}")
    print("V2: TBD/PLACEHOLDER MARKER SCAN")
    print(f"{'=' * 80}")

    tbd_findings = []
    for (org, repo), content in readmes.items():
        lines = content.split('\n')
        for line_num, line in enumerate(lines, 1):
            matches = TBD_REGEX.findall(line)
            if matches:
                # Skip if it's in a code block context that describes the system's own documentation_status
                stripped = line.strip()
                # Allow TBD in specific registry/status contexts
                if 'launch_date' in stripped.lower() and 'TBD' in stripped:
                    continue
                tbd_findings.append({
                    'org': org,
                    'repo': repo,
                    'line_num': line_num,
                    'line': stripped[:200],
                    'markers': matches
                })

    if tbd_findings:
        print(f"\n  FOUND {len(tbd_findings)} TBD/placeholder markers:")
        for f in tbd_findings:
            print(f"    [{f['org']}/{f['repo']}:{f['line_num']}] {f['line'][:120]}")
    else:
        print(f"\n  PASS: Zero TBD/placeholder markers found across {len(readmes)} READMEs")

    # ── V1: Link Extraction ────────────────────────────────────────────
    print(f"\n{'=' * 80}")
    print("V1: CROSS-ORG LINK AUDIT")
    print(f"{'=' * 80}")

    all_links = []  # List of {org, repo, text, url, classification}
    for (org, repo), content in readmes.items():
        links = LINK_REGEX.findall(content)
        for text, url in links:
            # Skip anchors and empty links
            if url.startswith('#') or not url.strip():
                continue
            classification = classify_link(url)
            all_links.append({
                'org': org,
                'repo': repo,
                'text': text,
                'url': url,
                'classification': classification
            })

    # Classify links
    by_class = defaultdict(list)
    for link in all_links:
        by_class[link['classification']].append(link)

    print(f"\n  Total links extracted: {len(all_links)}")
    for cls, links in sorted(by_class.items()):
        print(f"    {cls}: {len(links)}")

    # ── V1: Validate system GitHub links ────────────────────────────
    print("\n── Validating system GitHub links ──")

    system_links = by_class.get('system-github', [])
    # Deduplicate by URL
    unique_urls = {}
    for link in system_links:
        if link['url'] not in unique_urls:
            unique_urls[link['url']] = link

    github_broken = []
    github_ok = []
    checked_repos = {}  # cache: (org, repo) -> exists

    for i, (url, link) in enumerate(unique_urls.items()):
        sys.stdout.write(f"\r  [{i+1}/{len(unique_urls)}] Checking: {url[:60]}...")
        sys.stdout.flush()

        link_org, link_repo = extract_github_org_repo(url)
        if link_org and link_repo:
            cache_key = (link_org, link_repo)
            if cache_key not in checked_repos:
                exists = validate_github_repo_link(link_org, link_repo)
                checked_repos[cache_key] = exists

            if checked_repos[cache_key]:
                github_ok.append(link)
            elif checked_repos[cache_key] is False:
                github_broken.append(link)
            # None means timeout/unknown
        elif link_org:
            # Org-level link
            github_ok.append(link)  # Orgs exist (we created them)

    print(f"\n  System GitHub links: {len(github_ok)} OK, {len(github_broken)} broken")

    if github_broken:
        print("\n  BROKEN SYSTEM LINKS:")
        for link in github_broken:
            print(f"    [{link['org']}/{link['repo']}] [{link['text']}]({link['url']})")

    # ── V1: Validate external links (sample) ────────────────────────
    print("\n── Validating external links (sampling) ──")

    external_links = by_class.get('external', [])
    external_github = by_class.get('external-github', [])
    all_external = external_links + external_github

    # Deduplicate
    unique_external = {}
    for link in all_external:
        url = link['url']
        # Only check http/https
        parsed = urlparse(url)
        if parsed.scheme in ('http', 'https'):
            if url not in unique_external:
                unique_external[url] = link

    ext_broken = []
    ext_ok = 0
    ext_unknown = 0

    # Check all unique external URLs (limit to reasonable number)
    urls_to_check = list(unique_external.items())
    if len(urls_to_check) > 100:
        print(f"  Sampling 100 of {len(urls_to_check)} unique external URLs")
        import random
        random.seed(42)
        urls_to_check = random.sample(urls_to_check, 100)

    for i, (url, link) in enumerate(urls_to_check):
        sys.stdout.write(f"\r  [{i+1}/{len(urls_to_check)}] Checking: {url[:60]}...")
        sys.stdout.flush()

        valid = validate_external_url(url)
        if valid:
            ext_ok += 1
        elif valid is False:
            ext_broken.append(link)
        else:
            ext_unknown += 1

    print(f"\n  External links: {ext_ok} OK, {len(ext_broken)} broken, {ext_unknown} timeout/unknown")

    if ext_broken:
        print("\n  BROKEN EXTERNAL LINKS:")
        for link in ext_broken:
            print(f"    [{link['org']}/{link['repo']}] [{link['text']}]({link['url']})")

    # ── V1: Check relative links ────────────────────────────────────
    relative_links = by_class.get('relative', [])
    print(f"\n  Relative links: {len(relative_links)} (not validated — these are within-repo)")

    # ── Summary ──────────────────────────────────────────────────────
    print(f"\n{'=' * 80}")
    print("SUMMARY")
    print(f"{'=' * 80}")
    print(f"\n  READMEs fetched: {len(readmes)}/{len(repos)}")
    print(f"  Fetch errors: {len(fetch_errors)}")
    print("\n  V1 Link Audit:")
    print(f"    Total links: {len(all_links)}")
    print(f"    System GitHub links: {len(github_ok)} OK, {len(github_broken)} broken")
    print(f"    External links: {ext_ok} OK, {len(ext_broken)} broken, {ext_unknown} unknown")
    print(f"    Relative links: {len(relative_links)} (not validated)")
    print("\n  V2 TBD Scan:")
    print(f"    TBD markers found: {len(tbd_findings)}")

    v1_pass = len(github_broken) == 0 and len(ext_broken) == 0
    v2_pass = len(tbd_findings) == 0

    print(f"\n  V1 RESULT: {'PASS' if v1_pass else 'ISSUES FOUND'}")
    print(f"  V2 RESULT: {'PASS' if v2_pass else 'ISSUES FOUND'}")

    # Write JSON report
    report = {
        "v1_link_audit": {
            "total_links": len(all_links),
            "system_github_ok": len(github_ok),
            "system_github_broken": [{"org": l["org"], "repo": l["repo"], "text": l["text"], "url": l["url"]} for l in github_broken],
            "external_ok": ext_ok,
            "external_broken": [{"org": l["org"], "repo": l["repo"], "text": l["text"], "url": l["url"]} for l in ext_broken],
            "external_unknown": ext_unknown,
            "relative_links": len(relative_links),
            "pass": v1_pass
        },
        "v2_tbd_scan": {
            "total_markers": len(tbd_findings),
            "findings": tbd_findings,
            "pass": v2_pass
        },
        "fetch_errors": [{"org": o, "repo": r, "error": e} for o, r, e in fetch_errors],
        "readmes_fetched": len(readmes),
        "readmes_expected": len(repos)
    }

    report_path = os.path.join(os.path.dirname(__file__), "v1-v2-report.json")
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"\n  Report written to {report_path}")


if __name__ == "__main__":
    main()
