"""Collect a revision-pinned workflow inventory through the trusted path.

Provenance contract (organvm-engine #190; plan: issue comment 6978075819 —
treated as a one-take draft, every load-bearing claim re-verified at main
``53d00d00`` this run):

- At that head ``workflow_intelligence.inventory()`` / ``drift()`` had zero
  production callers: nothing in ``src/`` imports the module, no CLI
  subcommand wired it, and the monthly audit workflow never called it. This
  module is the minimal collector the plan calls for: it enumerates the
  workflow set, fetches each file's bytes, verifies them against Git object
  identity, and hands the result to the existing ``inventory()`` — it does
  not reimplement the analysis.
- The token comes from the execution environment (``GITHUB_TOKEN``, then
  ``GH_TOKEN``) or an explicit caller argument. In GitHub Actions that is
  the workflow's own ``GITHUB_TOKEN``; locally it is the operator's token. A
  missing token fails closed: no unauthenticated fetch is attempted. The
  token is never recorded in the envelope, never minted, stored, or logged.
- Identity is pinned before any workflow definition is read. The stable
  repository id comes from the GitHub API repo object and is verified
  against the caller-pinned ``--repository-id``; the revision is the
  caller-pinned full commit SHA, and the tree is fetched at that revision.
  The expected path set comes from that tree (full recursive listing, never
  a first-page sample); a truncated tree response fails the collection.
- Each file's bytes are verified against Git object identity: the contents
  response's blob SHA must equal the tree entry's blob SHA, and the decoded
  size must match. A symlink or path escape fails the collection — a trust
  boundary event, not ordinary missing data. A fetch 404 or an over-budget
  file is retained as a distinct per-path collection state
  (``unavailable`` / ``truncated``) in the envelope; the snapshot records
  such a path ``unavailable`` through ``inventory()`` — never success, never
  deletion.
- Enumeration completeness and analyzed-file coverage stay separate fields:
  the snapshot carries both, exactly as ``inventory()`` returns them.
  ``coverage`` reads ``complete`` only when the enumeration is complete AND
  every expected path analyzed.
- Ownership is joined with explicit unknowns. CODEOWNERS is fetched from the
  same pinned tree (blob-verified like any workflow); a path with no matching
  entry records ``owners: null`` with the reason. Canonical criticality /
  dependency data comes from the registry only when the caller supplies one
  (``--registry``): the registry carries no numeric GitHub id and the corpus
  repo is not checked out on a bare runner, so the registry join is
  optional and its absence is recorded, not papered over. The registry
  carries ``tier`` and ``dependencies``; no criticality number is invented
  from them.
- Freshness / retention budget (evidence-backed, in code and in
  ``docs/research/2026-11-23-workflow-ingest.md``): a snapshot is stale
  after 35 days — the cycle runs on the 1st of each month, so 35 days is one
  cycle plus grace — and at most 3 cycles are retained, because ``drift()``
  needs two snapshots and restore needs one spare. The workflow artifact
  retention is 90 days, the same as the monthly audit's.
- The envelope never authorizes execution, a check, or a release, and it
  creates no scheduler, service, or second source of truth: the retained
  cycle artifact (envelope + fetched file bytes) is the evidence the
  snapshot was rebuilt from, and :func:`rebuild_snapshot` proves the
  rebuild matches the recorded digest.
"""

from __future__ import annotations

import base64
import binascii
import fnmatch
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable

from organvm_engine.ci.agent_eval import digest
from organvm_engine.ci.evidence_collector import resolve_token
from organvm_engine.ci.workflow_intelligence import (
    MAX_BYTES,
    drift,
    inventory,
)
from organvm_engine.ci.workflow_intelligence import (
    _path as _validate_workflow_path,
)

VERSION = "organvm.workflow-ingest.v1"
_API = "https://api.github.com"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
# One monthly cycle plus grace: the cycle runs on the 1st, so a snapshot
# older than 35 days cannot be the latest cycle's output.
SNAPSHOT_STALE_AFTER_SECONDS = 35 * 24 * 3600
# Two snapshots for drift() plus one spare; the workflow artifact keeps 90 days.
RETAINED_CYCLES = 3
ARTIFACT_RETENTION_DAYS = 90
_CODEOWNERS_PATH = ".github/CODEOWNERS"
_HEX_RE = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}$")
_OWNER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
_REPO_RE = re.compile(r"[A-Za-z0-9_.-]{1,100}$")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _fetch_json(url: str, token: str) -> dict[str, Any]:
    """Fetch one GitHub API URL with the environment-supplied token."""
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "organvm-engine-workflow-ingest",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read(MAX_RESPONSE_BYTES + 1)
            if len(data) > MAX_RESPONSE_BYTES:
                raise ValueError("ingest: response exceeds size budget")
            parsed = json.loads(data)
    except urllib.error.HTTPError as exc:
        raise ValueError(f"ingest: GitHub API {exc.code} for {url}") from exc
    except (OSError, ValueError, TypeError) as exc:
        if isinstance(exc, ValueError) and str(exc).startswith("ingest:"):
            raise
        raise ValueError(f"ingest: fetch failed for {url}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("ingest: unexpected response shape")
    return parsed


def resolve_identity(
    owner: str,
    repo: str,
    expected_repository_id: int,
    *,
    token: str,
    fetch: Callable[[str, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resolve stable repository identity from the API and verify the pin.

    Returns the numeric id, full name and default branch. A payload that
    disagrees with the caller-pinned id is rejected, not reinterpreted:
    a renamed or transferred repository never silently stands in for the
    expected one.
    """
    if not _OWNER_RE.fullmatch(owner) or not _REPO_RE.fullmatch(repo):
        raise ValueError("ingest: owner/repo names are invalid")
    if type(expected_repository_id) is not int or expected_repository_id <= 0:
        raise ValueError("ingest: stable repository ID required")
    getter = fetch or _fetch_json
    payload = getter(f"{_API}/repos/{owner}/{repo}", token)
    repository_id = payload.get("id")
    if type(repository_id) is not int or repository_id <= 0:
        raise ValueError("ingest: repository identity missing from API response")
    if repository_id != expected_repository_id:
        raise ValueError(
            "ingest: repository id mismatch: API reports %r, expected %r "
            "(renamed, transferred, or wrong repository)" % (repository_id, expected_repository_id),
        )
    full_name = payload.get("full_name")
    if full_name != f"{owner}/{repo}":
        raise ValueError("ingest: repository full name mismatch: %r" % (full_name,))
    return {
        "repository_id": repository_id,
        "repository": full_name,
        "default_branch": payload.get("default_branch"),
        "source_url": f"{_API}/repos/{owner}/{repo}",
    }


def enumerate_workflows(
    owner: str,
    repo: str,
    revision: str,
    *,
    token: str,
    fetch: Callable[[str, str], dict[str, Any]] | None = None,
) -> tuple[list[str], str, dict[str, dict[str, Any]]]:
    """Enumerate the workflow set from the pinned tree, fully paginated.

    Returns (expected_paths, tree_sha, blobs) where blobs maps each path to
    its tree entry (blob SHA + size). The tree SHA comes from the commit
    object, not the tree response: the trees endpoint echoes the requested
    revision in its ``sha`` field, so it cannot bind the listing to the
    revision on its own. A truncated tree response fails the collection: a
    partial enumeration must never be certified as complete.
    """
    if not _HEX_RE.fullmatch(revision or ""):
        raise ValueError("ingest: immutable revision required (40/64 hex)")
    getter = fetch or _fetch_json
    commit = getter(f"{_API}/repos/{owner}/{repo}/git/commits/{revision}", token)
    tree_sha = (commit.get("tree") or {}).get("sha") if isinstance(commit, dict) else None
    if not isinstance(tree_sha, str) or not tree_sha:
        raise ValueError("ingest: tree SHA missing from commit object")
    payload = getter(f"{_API}/repos/{owner}/{repo}/git/trees/{revision}?recursive=1", token)
    if payload.get("truncated") is True:
        raise ValueError("ingest: tree listing truncated; enumeration incomplete")
    entries = payload.get("tree")
    if not isinstance(entries, list):
        raise ValueError("ingest: tree listing missing from API response")
    blobs: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("type") != "blob":
            continue
        path = entry.get("path")
        if not isinstance(path, str) or not path.startswith(".github/workflows/"):
            continue
        _validate_workflow_path(path)
        if path in blobs:
            raise ValueError("ingest: duplicate tree entry for %s" % path)
        blobs[path] = {"sha": entry.get("sha"), "size": entry.get("size")}
    return sorted(blobs), tree_sha, blobs


def fetch_workflow_bytes(
    owner: str,
    repo: str,
    path: str,
    blob_sha: str,
    revision: str,
    *,
    token: str,
    fetch: Callable[[str, str], dict[str, Any]] | None = None,
) -> tuple[str | None, str, dict[str, Any]]:
    """Fetch one workflow file's bytes, verified against Git object identity.

    Returns (text, state, note) where state is ``fetched``,
    ``unavailable`` (fetch 404), ``truncated`` (over the byte budget) or
    ``invalid_encoding`` (not decodable UTF-8). A symlink, a path escape,
    or a blob-SHA mismatch raises ValueError: the collection refuses to
    certify bytes it cannot verify.
    """
    _validate_workflow_path(path)
    getter = fetch or _fetch_json
    url = f"{_API}/repos/{owner}/{repo}/contents/{path}?ref={revision}"
    try:
        payload = getter(url, token)
    except ValueError as exc:
        if "ingest: GitHub API 404" in str(exc):
            return None, "unavailable", {"source_url": url, "blob_sha": blob_sha}
        raise
    if payload.get("type") == "symlink":
        raise ValueError("ingest: symlink refused at %s (path escape)" % path)
    if payload.get("type") != "file":
        raise ValueError("ingest: unexpected contents type %r at %s" % (payload.get("type"), path))
    if payload.get("sha") != blob_sha:
        raise ValueError(
            "ingest: blob SHA mismatch at %s: contents reports %r, tree lists %r "
            "(stale revision or duplicate page)" % (path, payload.get("sha"), blob_sha),
        )
    size = payload.get("size")
    if type(size) is not int or size < 0:
        raise ValueError("ingest: contents size missing at %s" % path)
    if size > MAX_BYTES:
        return None, "truncated", {"source_url": url, "blob_sha": blob_sha, "size": size}
    if payload.get("encoding") != "base64":
        raise ValueError("ingest: unexpected contents encoding at %s" % path)
    try:
        # GitHub wraps base64 content with newlines; strip them before
        # the strict decode so wrapped (but otherwise valid) content parses.
        encoded = re.sub(r"\s+", "", payload.get("content") or "")
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("ingest: contents not valid base64 at %s" % path) from exc
    if len(raw) != size:
        raise ValueError("ingest: decoded size mismatch at %s" % path)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None, "invalid_encoding", {"source_url": url, "blob_sha": blob_sha, "size": size}
    return text, "fetched", {"source_url": url, "blob_sha": blob_sha, "size": size}


def parse_codeowners(text: str) -> list[tuple[str, list[str]]]:
    """Parse CODEOWNERS into (pattern, owners) rules, in file order.

    Blank lines and comments are skipped. A rule is a pattern followed by
    one or more ``@owner`` / email tokens. Last matching rule wins, per
    GitHub semantics; matching is done by :func:`owners_for_path`.
    """
    rules: list[tuple[str, list[str]]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) < 2:
            continue
        rules.append((parts[0], parts[1:]))
    return rules


def owners_for_path(path: str, rules: list[tuple[str, list[str]]]) -> list[str] | None:
    """Return the owners for a path under CODEOWNERS rules, or None.

    ``*`` matches everything; a pattern with a slash is anchored at the
    repository root; otherwise it matches the basename or any trailing
    path suffix. The last matching rule wins.
    """
    owners: list[str] | None = None
    segments = path.split("/")
    for pattern, rule_owners in rules:
        matched = False
        if pattern == "*":
            matched = True
        elif pattern.startswith("/"):
            matched = fnmatch.fnmatchcase(path, pattern[1:])
        elif "/" in pattern.rstrip("/"):
            matched = fnmatch.fnmatchcase(path, pattern)
        else:
            matched = any(
                fnmatch.fnmatchcase("/".join(segments[i:]), pattern) for i in range(len(segments))
            )
        if matched:
            owners = rule_owners
    return owners


def assess_freshness(snapshot: dict, now: str | None = None) -> dict[str, Any]:
    """Assess a snapshot against the retention budget.

    ``fresh`` while the snapshot is at most 35 days old (one monthly cycle
    plus grace); ``stale`` after that. The budget lives in the code so a
    reviewer can check the number rather than trust a comment.
    """
    from organvm_engine.ci.workflow_intelligence import _time

    observed = _time(snapshot["observed_at"])
    current = _time(now or _utcnow())
    age = int((current - observed).total_seconds())
    return {
        "status": "fresh" if age <= SNAPSHOT_STALE_AFTER_SECONDS else "stale",
        "age_seconds": age,
        "stale_after_seconds": SNAPSHOT_STALE_AFTER_SECONDS,
        "observed_at": snapshot["observed_at"],
    }


def collect_workflow_inventory(
    *,
    owner: str,
    repo: str,
    revision: str,
    expected_repository_id: int,
    token: str | None = None,
    fetch: Callable[[str, str], dict[str, Any]] | None = None,
    codeowners_text: str | None = None,
    registry: dict | None = None,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Collect one revision-pinned workflow inventory cycle.

    Pins identity first (API id vs the caller expectation), enumerates the
    workflow set from the pinned tree, fetches each file's bytes with blob
    verification, runs the existing ``inventory()`` on the fetched files,
    and joins CODEOWNERS + registry data with explicit unknowns. The
    returned envelope never contains the token.
    """
    resolved_token = resolve_token(token)
    getter = fetch or _fetch_json
    identity = resolve_identity(
        owner,
        repo,
        expected_repository_id,
        token=resolved_token,
        fetch=getter,
    )
    expected_paths, tree_sha, blobs = enumerate_workflows(
        owner,
        repo,
        revision,
        token=resolved_token,
        fetch=getter,
    )
    observed = observed_at or _utcnow()
    files: dict[str, str] = {}
    collection: dict[str, dict[str, Any]] = {}
    for path in expected_paths:
        text, state, note = fetch_workflow_bytes(
            owner,
            repo,
            path,
            blobs[path]["sha"],
            revision,
            token=resolved_token,
            fetch=getter,
        )
        record = {"state": state, **note}
        collection[path] = record
        if state == "fetched" and text is not None:
            files[path] = text
    snapshot = inventory(
        identity["repository_id"],
        revision,
        files,
        expected_paths=expected_paths,
        observed_at=observed,
        enumeration_complete=True,
    )

    if codeowners_text is None:
        codeowners_text = _fetch_codeowners(
            owner,
            repo,
            revision,
            token=resolved_token,
            fetch=getter,
        )
    rules = parse_codeowners(codeowners_text) if codeowners_text else []
    registry_entry = None
    if registry is not None:
        from organvm_engine.registry.query import find_repo

        found = find_repo(registry, repo)
        registry_entry = found[1] if found else None
    ownership: dict[str, dict[str, Any]] = {}
    for path in expected_paths:
        owners = owners_for_path(path, rules)
        entry: dict[str, Any] = {
            "owners": owners,
            "unknown_reason": None
            if owners
            else (
                "no CODEOWNERS entry matches this path"
                if codeowners_text
                else "no CODEOWNERS file at this revision"
            ),
            "tier": None,
            "dependencies": None,
            "criticality": None,
            "criticality_unknown_reason": (
                "no canonical criticality field; tier recorded instead"
                if registry_entry is not None
                else "no canonical registry supplied in this run"
            ),
        }
        if registry_entry is not None:
            entry["tier"] = registry_entry.get("tier")
            entry["dependencies"] = registry_entry.get("dependencies")
            entry["criticality_unknown_reason"] = (
                "no canonical criticality field; tier recorded instead"
            )
        ownership[path] = entry

    return {
        "schema_version": VERSION,
        "repository": identity["repository"],
        "repository_id": identity["repository_id"],
        "revision": revision,
        "tree_sha": tree_sha,
        "observed_at": observed,
        "enumeration_complete": True,
        "expected_paths": expected_paths,
        "collection": collection,
        "snapshot": snapshot,
        "snapshot_digest": digest(snapshot),
        "ownership": ownership,
        "budget": {
            "stale_after_seconds": SNAPSHOT_STALE_AFTER_SECONDS,
            "retained_cycles": RETAINED_CYCLES,
            "artifact_retention_days": ARTIFACT_RETENTION_DAYS,
        },
        "freshness": assess_freshness(snapshot),
        "files": files,
        "authorizes_mutation": False,
        "authorizes_release": False,
    }


def _fetch_codeowners(
    owner: str,
    repo: str,
    revision: str,
    *,
    token: str,
    fetch: Callable[[str, str], dict[str, Any]],
) -> str | None:
    """Fetch CODEOWNERS from the pinned revision, blob-verified.

    Returns None when the file is absent (a 404 is ordinary here, not a
    collection failure — ownership is then unknown with the reason
    recorded). A symlink or blob mismatch still fails loudly.
    """
    url = f"{_API}/repos/{owner}/{repo}/contents/{_CODEOWNERS_PATH}?ref={revision}"
    try:
        payload = fetch(url, token)
    except ValueError as exc:
        if "ingest: GitHub API 404" in str(exc):
            return None
        raise
    if payload.get("type") == "symlink":
        raise ValueError("ingest: symlink refused at %s (path escape)" % _CODEOWNERS_PATH)
    if payload.get("type") != "file" or payload.get("encoding") != "base64":
        raise ValueError("ingest: unexpected CODEOWNERS payload")
    try:
        encoded = re.sub(r"\s+", "", payload.get("content") or "")
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("ingest: CODEOWNERS not valid base64") from exc
    return raw.decode("utf-8", errors="strict")


def rebuild_snapshot(artifact: dict) -> tuple[dict, str]:
    """Rebuild the inventory snapshot from a retained cycle artifact.

    Takes the envelope a cycle wrote (it must carry the retained ``files``
    mapping, the expected paths, the enumeration flag, the identity and the
    observation time) and re-runs ``inventory()`` on exactly those inputs.
    Returns (snapshot, digest). The caller compares the digest with the
    artifact's recorded ``snapshot_digest``: a match proves the retained
    evidence reproduces the snapshot digest-for-digest, with no second
    source of truth.
    """
    snapshot = inventory(
        artifact["repository_id"],
        artifact["revision"],
        artifact["files"],
        expected_paths=artifact["expected_paths"],
        observed_at=artifact["observed_at"],
        enumeration_complete=artifact["enumeration_complete"],
    )
    return snapshot, digest(snapshot)


def compare_snapshots(previous: dict, current: dict) -> dict:
    """Run ``drift()`` between two collected snapshots, via their envelopes.

    Thin wrapper kept here so callers do not reach into the envelope
    shape: it takes two envelopes (or two raw snapshots) and returns the
    ``drift()`` report. A missing path reads ``unavailable_comparison``
    unless the current enumeration is complete — never deletion from
    partial data.
    """
    prev = previous.get("snapshot", previous)
    cur = current.get("snapshot", current)
    return drift(prev, cur)


__all__ = [
    "ARTIFACT_RETENTION_DAYS",
    "RETAINED_CYCLES",
    "SNAPSHOT_STALE_AFTER_SECONDS",
    "VERSION",
    "assess_freshness",
    "collect_workflow_inventory",
    "compare_snapshots",
    "enumerate_workflows",
    "fetch_workflow_bytes",
    "owners_for_path",
    "parse_codeowners",
    "rebuild_snapshot",
    "resolve_identity",
    "resolve_token",
]
