"""Tests for the workflow-ingest collector (organvm-engine #190).

The wired path is exercised offline: a fake fetch returns captured payloads,
so no test touches the network or a credential. The captured evidence is the
real tree listing at main ``53d00d00`` (14 workflow files, blob SHAs from the
live tree) plus the real ``ci.yml`` and ``monthly-infrastructure-audit.yml``
contents at that revision. The plan's step-7 counterexamples are each a test:
transfer/rename, duplicate pages, rate/permission failure, stale revision,
partial restore, privacy-export.
"""

import base64
import copy
import json
from pathlib import Path

import pytest

from organvm_engine.ci.workflow_ingest import (
    assess_freshness,
    collect_workflow_inventory,
    compare_snapshots,
    enumerate_workflows,
    fetch_workflow_bytes,
    owners_for_path,
    parse_codeowners,
    rebuild_snapshot,
    resolve_identity,
)
from organvm_engine.ci.workflow_intelligence import drift, inventory

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "workflow_ingest"

OWNER, REPO = "4444J99", "organvm-engine"
REVISION = "53d00d00b015ef304896bddca2d564ce8166b763"
TREE_SHA = "276b0d6f02a13c104a13627b5bbf80950ac14229"
REPO_ID = 1160447354
TOKEN = "ghp_testtoken"
CODEOWNERS = "* @4444j99\n"
OBSERVED = "2026-11-23T16:30:00Z"


def _load(name):
    return json.loads((FIXTURES / name).read_text())


def _contents_payload(text, sha):
    # GitHub wraps base64 content with newlines every 60 chars; the fake
    # serves the same shape so a strict decoder bug cannot hide in tests.
    raw = base64.b64encode(text.encode()).decode()
    wrapped = "\n".join(raw[i : i + 60] for i in range(0, len(raw), 60))
    return {
        "type": "file",
        "encoding": "base64",
        "size": len(text.encode()),
        "sha": sha,
        "content": wrapped,
    }


def _fake_fetch(tree=None, contents=None, repo_payload=None, codeowners=None, fail_urls=None):
    """Fake GitHub fetch serving captured payloads.

    ``contents`` maps path -> (text, blob_sha) or a state marker:
    ("404",) / ("symlink",) / ("oversize", size) / ("bad-utf8",).
    ``fail_urls`` maps a URL substring -> HTTP status to raise.
    """
    tree = tree if tree is not None else _load("organvm-engine-tree-53d00d00.json")
    contents = contents if contents is not None else {}
    fail_urls = fail_urls or {}
    calls = []

    def fetch(url, token):
        assert token == TOKEN, "token must reach the fetch"
        calls.append(url)
        for needle, status in fail_urls.items():
            if needle in url:
                raise ValueError(f"ingest: GitHub API {status} for {url}")
        if url.endswith(f"/repos/{OWNER}/{REPO}"):
            return copy.deepcopy(
                repo_payload
                if repo_payload is not None
                else {"id": REPO_ID, "full_name": f"{OWNER}/{REPO}", "default_branch": "main"},
            )
        if "/git/commits/" in url:
            return copy.deepcopy(_load("commit-53d00d00.json"))
        if "/git/trees/" in url:
            return copy.deepcopy(tree)
        if "/contents/.github/CODEOWNERS" in url:
            if codeowners is None:
                raise ValueError(f"ingest: GitHub API 404 for {url}")
            return _contents_payload(codeowners, "600e2dd7f6c07e490adfc409613bf1df173f8939")
        if "/contents/" in url:
            path = url.split("/contents/")[1].split("?")[0]
            if path not in contents:
                raise ValueError(f"ingest: GitHub API 404 for {url}")
            marker = contents[path]
            if marker[0] == "404":
                raise ValueError(f"ingest: GitHub API 404 for {url}")
            if marker[0] == "symlink":
                return {"type": "symlink", "sha": marker[1]}
            if marker[0] == "oversize":
                return {
                    "type": "file",
                    "encoding": "base64",
                    "size": marker[1],
                    "sha": marker[2],
                    "content": "",
                }
            if marker[0] == "bad-utf8":
                raw = b"\xff\xfe bad"
                return {
                    "type": "file",
                    "encoding": "base64",
                    "size": len(raw),
                    "sha": marker[1],
                    "content": base64.b64encode(raw).decode(),
                }
            text, sha = marker
            return _contents_payload(text, sha)
        raise AssertionError(f"unexpected url {url}")

    fetch.calls = calls
    return fetch


def _all_valid_contents():
    """A minimal analyzable workflow for every tree path, keyed by path."""
    tree = _load("organvm-engine-tree-53d00d00.json")
    return {
        entry["path"]: (
            "name: %s\non: [push]\njobs:\n  x:\n    runs-on: ubuntu-24.04\n    steps:\n      - run: echo hi\n"
            % entry["path"],
            entry["sha"],
        )
        for entry in tree["tree"]
    }


def _real_contents():
    """The two captured workflow files, keyed by path with their live blob SHAs."""
    tree = _load("organvm-engine-tree-53d00d00.json")
    blobs = {e["path"]: e["sha"] for e in tree["tree"]}
    out = {}
    for name, fname in (
        (".github/workflows/ci.yml", "contents-ci.yml.json"),
        (
            ".github/workflows/monthly-infrastructure-audit.yml",
            "contents-monthly-infrastructure-audit.yml.json",
        ),
    ):
        payload = _load(fname)
        text = base64.b64decode(payload["content"]).decode()
        assert payload["sha"] == blobs[name]
        out[name] = (text, payload["sha"])
    return out


def _collect(**kwargs):
    kwargs.setdefault("owner", OWNER)
    kwargs.setdefault("repo", REPO)
    kwargs.setdefault("revision", REVISION)
    kwargs.setdefault("expected_repository_id", REPO_ID)
    kwargs.setdefault("token", TOKEN)
    kwargs.setdefault("codeowners_text", CODEOWNERS)
    kwargs.setdefault("observed_at", OBSERVED)
    return collect_workflow_inventory(**kwargs)


# --- identity ---------------------------------------------------------------


def test_identity_resolves_and_verifies_pin():
    fetch = _fake_fetch()
    identity = resolve_identity(OWNER, REPO, REPO_ID, token=TOKEN, fetch=fetch)
    assert identity["repository_id"] == REPO_ID
    assert identity["repository"] == "4444J99/organvm-engine"


def test_identity_rejects_transferred_or_renamed_repo():
    # Counterexample: transfer/rename — the API id no longer matches the pin.
    fetch = _fake_fetch(
        repo_payload={"id": 999, "full_name": "4444J99/organvm-engine", "default_branch": "main"},
    )
    with pytest.raises(ValueError, match="repository id mismatch"):
        resolve_identity(OWNER, REPO, REPO_ID, token=TOKEN, fetch=fetch)


def test_identity_rejects_missing_token():
    with pytest.raises(ValueError, match="no GitHub token"):
        collect_workflow_inventory(
            owner=OWNER, repo=REPO, revision=REVISION, expected_repository_id=REPO_ID, token=None,
        )


# --- enumeration ------------------------------------------------------------


def test_enumeration_uses_commit_tree_sha_not_echoed_revision():
    fetch = _fake_fetch()
    paths, tree_sha, blobs = enumerate_workflows(OWNER, REPO, REVISION, token=TOKEN, fetch=fetch)
    assert tree_sha == TREE_SHA
    assert tree_sha != REVISION
    assert len(paths) == 14
    assert paths[0] == ".github/workflows/ci.yml"
    assert blobs[".github/workflows/ci.yml"]["sha"] == "7369e520a13059d44309a9a6937906ab248f1206"


def test_enumeration_rejects_truncated_tree():
    tree = _load("organvm-engine-tree-53d00d00.json")
    tree["truncated"] = True
    fetch = _fake_fetch(tree=tree)
    with pytest.raises(ValueError, match="truncated"):
        enumerate_workflows(OWNER, REPO, REVISION, token=TOKEN, fetch=fetch)


# --- byte verification ------------------------------------------------------


def test_fetch_verifies_blob_sha():
    fetch = _fake_fetch(contents=_real_contents())
    text, state, note = fetch_workflow_bytes(
        OWNER,
        REPO,
        ".github/workflows/ci.yml",
        "7369e520a13059d44309a9a6937906ab248f1206",
        REVISION,
        token=TOKEN,
        fetch=fetch,
    )
    assert state == "fetched"
    assert "name: CI" in text or "CI" in text
    assert note["size"] == 1855


def test_fetch_rejects_blob_sha_mismatch():
    # Counterexamples: stale revision / duplicate pages — the bytes do not
    # match the tree entry they claim to be.
    contents = _real_contents()
    text, sha = contents[".github/workflows/ci.yml"]
    contents[".github/workflows/ci.yml"] = (text, "0" * 40)
    fetch = _fake_fetch(contents=contents)
    with pytest.raises(ValueError, match="blob SHA mismatch"):
        fetch_workflow_bytes(
            OWNER,
            REPO,
            ".github/workflows/ci.yml",
            "7369e520a13059d44309a9a6937906ab248f1206",
            REVISION,
            token=TOKEN,
            fetch=fetch,
        )


def test_fetch_rejects_symlink():
    contents = {".github/workflows/ci.yml": ("symlink", "abc123")}
    fetch = _fake_fetch(contents=contents)
    with pytest.raises(ValueError, match="symlink refused"):
        fetch_workflow_bytes(
            OWNER,
            REPO,
            ".github/workflows/ci.yml",
            "7369e520a13059d44309a9a6937906ab248f1206",
            REVISION,
            token=TOKEN,
            fetch=fetch,
        )


def test_fetch_records_unavailable_on_404():
    contents = {".github/workflows/ci.yml": ("404",)}
    fetch = _fake_fetch(contents=contents)
    text, state, note = fetch_workflow_bytes(
        OWNER,
        REPO,
        ".github/workflows/ci.yml",
        "7369e520a13059d44309a9a6937906ab248f1206",
        REVISION,
        token=TOKEN,
        fetch=fetch,
    )
    assert text is None and state == "unavailable"


def test_fetch_records_truncated_over_budget():
    contents = {
        ".github/workflows/ci.yml": ("oversize", 300000, "7369e520a13059d44309a9a6937906ab248f1206"),
    }
    fetch = _fake_fetch(contents=contents)
    text, state, note = fetch_workflow_bytes(
        OWNER,
        REPO,
        ".github/workflows/ci.yml",
        "7369e520a13059d44309a9a6937906ab248f1206",
        REVISION,
        token=TOKEN,
        fetch=fetch,
    )
    assert text is None and state == "truncated"


def test_fetch_records_invalid_encoding():
    contents = {
        ".github/workflows/ci.yml": ("bad-utf8", "7369e520a13059d44309a9a6937906ab248f1206"),
    }
    fetch = _fake_fetch(contents=contents)
    text, state, _ = fetch_workflow_bytes(
        OWNER,
        REPO,
        ".github/workflows/ci.yml",
        "7369e520a13059d44309a9a6937906ab248f1206",
        REVISION,
        token=TOKEN,
        fetch=fetch,
    )
    assert text is None and state == "invalid_encoding"


def test_rate_or_permission_failure_fails_closed():
    fetch = _fake_fetch(fail_urls={"/git/trees/": 403})
    with pytest.raises(ValueError, match="GitHub API 403"):
        enumerate_workflows(OWNER, REPO, REVISION, token=TOKEN, fetch=fetch)


# --- CODEOWNERS -------------------------------------------------------------


def test_codeowners_last_match_wins():
    rules = parse_codeowners("# comment\n*.yml @team-a\n.github/workflows/ci.yml @team-b\n")
    assert owners_for_path(".github/workflows/ci.yml", rules) == ["@team-b"]
    assert owners_for_path(".github/workflows/other.yml", rules) == ["@team-a"]
    assert owners_for_path(".github/workflows/ci.yml", parse_codeowners("* @all")) == ["@all"]
    assert owners_for_path(".github/workflows/ci.yml", []) is None


# --- full collection ---------------------------------------------------------


def test_collect_two_captured_files_partial_coverage():
    # Only 2 of 14 files served: the snapshot is partial, the missing 12
    # stay unavailable — never success, never deletion.
    fetch = _fake_fetch(contents=_real_contents())
    env = _collect(fetch=fetch)
    assert env["repository_id"] == REPO_ID
    assert env["revision"] == REVISION
    assert env["tree_sha"] == TREE_SHA
    assert env["snapshot"]["coverage"] == "partial"
    assert env["snapshot"]["analyzed_count"] == 2
    assert env["snapshot"]["enumerated_count"] == 14
    assert env["snapshot"]["workflows"][".github/workflows/cla.yml"]["status"] == "unavailable"
    assert env["collection"][".github/workflows/cla.yml"]["state"] == "unavailable"
    assert env["ownership"][".github/workflows/ci.yml"]["owners"] == ["@4444j99"]
    assert env["snapshot_digest"]
    assert env["authorizes_mutation"] is False
    assert env["authorizes_release"] is False


def test_collect_complete_when_all_files_fetched():
    fetch = _fake_fetch(contents=_all_valid_contents())
    env = _collect(fetch=fetch)
    assert env["snapshot"]["coverage"] == "complete"
    assert env["snapshot"]["analyzed_count"] == 14
    assert all(v["state"] == "fetched" for v in env["collection"].values())


def test_collect_records_unknown_ownership_without_codeowners():
    fetch = _fake_fetch(contents=_real_contents())
    env = _collect(fetch=fetch, codeowners_text="")
    entry = env["ownership"][".github/workflows/ci.yml"]
    assert entry["owners"] is None
    assert "no CODEOWNERS" in entry["unknown_reason"]


def test_collect_records_unknown_registry_fields_without_registry():
    fetch = _fake_fetch(contents=_real_contents())
    env = _collect(fetch=fetch)
    entry = env["ownership"][".github/workflows/ci.yml"]
    assert entry["tier"] is None and entry["dependencies"] is None
    assert "no canonical registry supplied" in entry["criticality_unknown_reason"]


def test_collect_joins_registry_tier_and_dependencies():
    registry = {
        "version": "2.0",
        "organs": {
            "ORGAN-IV": {
                "repositories": [
                    {
                        "name": "organvm-engine",
                        "org": "4444J99",
                        "tier": "flagship",
                        "dependencies": ["organvm-ontologia"],
                    },
                ],
            },
        },
    }
    fetch = _fake_fetch(contents=_real_contents())
    env = _collect(fetch=fetch, registry=registry)
    entry = env["ownership"][".github/workflows/ci.yml"]
    assert entry["tier"] == "flagship"
    assert entry["dependencies"] == ["organvm-ontologia"]
    assert entry["criticality"] is None  # never invented from tier


def test_collect_never_records_token():
    fetch = _fake_fetch(contents=_real_contents())
    env = _collect(fetch=fetch)
    assert TOKEN not in json.dumps(env)


def test_collect_fetches_codeowners_from_tree_when_not_supplied():
    fetch = _fake_fetch(contents=_real_contents(), codeowners="* @4444j99\n")
    env = _collect(fetch=fetch, codeowners_text=None)
    assert env["ownership"][".github/workflows/ci.yml"]["owners"] == ["@4444j99"]


# --- freshness, drift, restore ----------------------------------------------


def test_freshness_budget():
    snapshot = {"observed_at": "2026-11-23T16:30:00Z"}
    assert assess_freshness(snapshot, now="2026-12-20T16:30:00Z")["status"] == "fresh"
    assert assess_freshness(snapshot, now="2026-12-29T16:30:00Z")["status"] == "stale"


def test_drift_between_two_cycles_no_change():
    # Both cycles complete: every path analyzed, same digests — drift is empty.
    fetch = _fake_fetch(contents=_all_valid_contents())
    first = _collect(fetch=fetch)
    second = _collect(fetch=fetch, observed_at="2026-11-23T17:30:00Z")
    report = compare_snapshots(first, second)
    assert report["changes"] == []


def test_drift_missing_path_fetch_failure_is_unavailable_not_removal():
    # A path still enumerated but un-fetchable in the second cycle must
    # read unavailable_comparison — never removed_from_enumeration.
    first = _collect(fetch=_fake_fetch(contents=_all_valid_contents()))
    contents = _all_valid_contents()
    contents[".github/workflows/cla.yml"] = ("404",)
    second = _collect(fetch=_fake_fetch(contents=contents), observed_at="2026-11-23T17:30:00Z")
    report = compare_snapshots(first, second)
    kinds = {c["path"]: c["kind"] for c in report["changes"]}
    assert kinds.get(".github/workflows/cla.yml") == "unavailable_comparison"


def test_drift_path_removed_from_complete_enumeration():
    # The same path genuinely absent from a complete second enumeration at a
    # NEW revision is a removal — the distinction the plan's counterexample
    # turns on. (At an unchanged revision drift() refuses the comparison:
    # a complete enumeration cannot legitimately lose a path there.)
    first = _collect(fetch=_fake_fetch(contents=_all_valid_contents()))
    tree = _load("organvm-engine-tree-53d00d00.json")
    tree["tree"] = [e for e in tree["tree"] if e["path"] != ".github/workflows/cla.yml"]
    contents = _all_valid_contents()
    del contents[".github/workflows/cla.yml"]
    second = _collect(
        fetch=_fake_fetch(tree=tree, contents=contents),
        revision="b" * 40,
        observed_at="2026-11-23T17:30:00Z",
    )
    report = compare_snapshots(first, second)
    kinds = {c["path"]: c["kind"] for c in report["changes"]}
    assert kinds.get(".github/workflows/cla.yml") == "removed_from_enumeration"


def test_drift_added_path_with_complete_previous():
    fetch = _fake_fetch(contents=_real_contents())
    first = _collect(fetch=fetch)
    tree = _load("organvm-engine-tree-53d00d00.json")
    tree["tree"] = tree["tree"] + [
        {
            "path": ".github/workflows/new.yml",
            "mode": "100644",
            "type": "blob",
            "sha": "a" * 40,
            "size": 100,
        },
    ]
    contents = _real_contents()
    contents[".github/workflows/new.yml"] = (
        "name: new\non: [push]\njobs:\n  x:\n    runs-on: ubuntu-24.04\n    steps:\n      - run: echo hi\n",
        "a" * 40,
    )
    fetch2 = _fake_fetch(tree=tree, contents=contents)
    # New path at a new revision: at an unchanged revision drift() refuses
    # a complete-enumeration path-set change as contradictory.
    second = _collect(fetch=fetch2, revision="b" * 40, observed_at="2026-11-23T17:30:00Z")
    report = compare_snapshots(first, second)
    kinds = {c["path"]: c["kind"] for c in report["changes"]}
    assert kinds.get(".github/workflows/new.yml") == "added"


def test_restore_rebuilds_snapshot_digest_for_digest():
    fetch = _fake_fetch(contents=_real_contents())
    env = _collect(fetch=fetch)
    rebuilt, rebuilt_digest = rebuild_snapshot(env)
    assert rebuilt_digest == env["snapshot_digest"]
    assert rebuilt == env["snapshot"]


def test_partial_restore_detects_tampered_file():
    # Counterexample: partial restore — a retained file changed after the
    # cycle must break the digest match, not silently rebuild.
    fetch = _fake_fetch(contents=_real_contents())
    env = _collect(fetch=fetch)
    tampered = copy.deepcopy(env)
    tampered["files"][".github/workflows/ci.yml"] += "\n# tampered\n"
    _, rebuilt_digest = rebuild_snapshot(tampered)
    assert rebuilt_digest != env["snapshot_digest"]


def test_inventory_and_drift_primitives_still_hold():
    minimal = (
        "name: x\non: [push]\njobs:\n  x:\n    runs-on: ubuntu-24.04\n"
        "    steps:\n      - run: echo hi\n"
    )
    path = ".github/workflows/a.yml"
    snap = inventory(
        1,
        "a" * 40,
        {path: minimal},
        expected_paths=[path],
        observed_at=OBSERVED,
        enumeration_complete=True,
    )
    assert snap["coverage"] == "complete"
    assert drift(snap, snap)["changes"] == []
    partial = inventory(
        1,
        "a" * 40,
        {path: minimal},
        expected_paths=[path, ".github/workflows/b.yml"],
        observed_at=OBSERVED,
        enumeration_complete=True,
    )
    assert partial["coverage"] == "partial"
    assert partial["workflows"][".github/workflows/b.yml"]["status"] == "unavailable"
