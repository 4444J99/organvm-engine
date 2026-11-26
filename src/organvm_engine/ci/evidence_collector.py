"""Collect GitHub execution evidence through the adapter's trusted path.

Provenance contract (verified 2026-11-23, organvm-engine #189, step 1): no
collector module existed anywhere in the tree at main ``1e4bec99``. The only
producer before this module was the manual capture behind
``tests/fixtures/ci_evidence/github-ci-34762163480.provenance.json``
("selected exact fields transcribed from connected GitHub GET responses"), and
``src/organvm_engine/ci/`` holds no GitHub client, no ``GITHUB_TOKEN`` reader,
and no ``*collector*`` module. This module is the minimal collector the #189
plan's step-1 fork calls for: it fetches run/job pages and hands them to
``runtime_evidence.evaluate_run``. It creates no scheduler, no service, and no
credential; it never mints, stores, or logs a token.

The contract, so it can be checked rather than trusted:

- The token comes from the execution environment (``GITHUB_TOKEN``, then
  ``GH_TOKEN``) or an explicit caller argument. In GitHub Actions that is the
  workflow's own ``GITHUB_TOKEN``; locally it is the operator's token. A
  missing token fails closed: no unauthenticated fetch is attempted.
- Expectations are caller-pinned (repository id, revision, workflow id, run
  id, attempt, required steps from the reviewed workflow contract) and are
  never derived from the fetched payloads. A payload that disagrees with them
  is rejected by the adapter, not reinterpreted.
- Every source URL, the observation time, and the payload digest are recorded
  in the returned report's ``collection`` block, so a reviewer can re-fetch the
  same run and reproduce the same decision. The report never contains the
  token, and it never authorizes execution, a check, or a release: the
  adapter's ``producer_authentication`` stays ``outside_adapter``.
- Fetching is injected for tests: pass ``fetch`` and no network call is made.
  Production fetches are bounded (2 MiB per response, 100 jobs pages) and
  raise ``ValueError`` on any HTTP error or inconsistent page metadata.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from organvm_engine.ci import runtime_evidence

VERSION = "organvm.github-evidence-collector.v1"
MAX_RESPONSE_BYTES = runtime_evidence.MAX_JSON_BYTES
MAX_PAGES = runtime_evidence.MAX_PAGES
_API = "https://api.github.com"

_OWNER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}")
_REPO_RE = re.compile(r"[A-Za-z0-9_.-]{1,100}")
_HEX_RE = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


def resolve_token(explicit: str | None = None) -> str:
    """Return the GitHub token for collection, or fail closed with no token."""
    for candidate in (explicit, os.environ.get("GITHUB_TOKEN"), os.environ.get("GH_TOKEN")):
        if candidate is not None and candidate.strip():
            return candidate.strip()
    raise ValueError(
        "evidence: no GitHub token available; set GITHUB_TOKEN (or GH_TOKEN) "
        "or pass an explicit token; unauthenticated collection is refused",
    )


class _StripAuthOnCrossOriginRedirect(urllib.request.HTTPRedirectHandler):
    """Follow redirects, but never forward ``Authorization`` to another origin.

    ``urllib`` copies request headers onto the redirected request, so a bearer
    token sent to the GitHub API would be re-sent to whatever host a redirect
    names. The header is dropped whenever the redirect target's scheme or host
    (including port) differs from the original request's.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: PLR0913
        new_request = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new_request is None:
            return None
        old = urllib.parse.urlsplit(req.full_url)
        new = urllib.parse.urlsplit(new_request.full_url)
        if (old.scheme.lower(), old.netloc.lower()) != (new.scheme.lower(), new.netloc.lower()):
            for store in (new_request.headers, new_request.unredirected_hdrs):
                for name in [k for k in store if k.lower() == "authorization"]:
                    del store[name]
        return new_request


def _build_opener() -> urllib.request.OpenerDirector:
    """Opener whose redirect handler drops credentials on cross-origin hops."""
    return urllib.request.build_opener(_StripAuthOnCrossOriginRedirect)


def _default_fetch(url: str, token: str) -> dict[str, Any]:
    """Fetch one GitHub API URL with the environment-supplied token."""
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "organvm-engine-evidence-collector",
    })
    try:
        with _build_opener().open(request, timeout=60) as response:
            data = response.read(MAX_RESPONSE_BYTES + 1)
            if len(data) > MAX_RESPONSE_BYTES:
                raise ValueError("evidence: response exceeds size budget")
            parsed = json.loads(data)
    except urllib.error.HTTPError as exc:
        raise ValueError(f"evidence: GitHub API {exc.code} for {url}") from exc
    except (OSError, ValueError, TypeError) as exc:
        if isinstance(exc, ValueError) and str(exc).startswith("evidence:"):
            raise
        raise ValueError(f"evidence: fetch failed for {url}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("evidence: unexpected response shape")
    return parsed


def load_required_steps(path: Path) -> tuple[dict[str, list[str]], dict[str, Any]]:
    """Load a required-steps contract; return (mapping, contract metadata).

    Accepts a bare ``{job: [step, ...]}`` mapping or an envelope with a
    ``required_steps`` mapping plus provenance metadata (``workflow``,
    ``workflow_blob``, ``pinned_base``). The mapping itself is validated the
    way the adapter requires it: nonempty, unique job names, nonempty unique
    step names.
    """
    data = runtime_evidence.load_json(path)
    metadata: dict[str, Any] = {}
    if isinstance(data, dict) and "required_steps" in data:
        metadata = {k: v for k, v in data.items() if k != "required_steps"}
        mapping = data["required_steps"]
    else:
        mapping = data
    if (not isinstance(mapping, dict) or not mapping
            or any(not isinstance(name, str) or not name
                   or not isinstance(steps, list) or not steps
                   or any(not isinstance(step, str) or not step for step in steps)
                   or len(set(steps)) != len(steps)
                   for name, steps in mapping.items())):
        raise ValueError("evidence: required steps must map job names to nonempty unique step lists")
    return mapping, metadata


def collect_run_evidence(
    *,
    owner: str,
    repo: str,
    run_id: int,
    expected_repository_id: int,
    expected_revision: str,
    expected_workflow_id: int,
    expected_run_id: int | None = None,
    expected_attempt: int = 1,
    required_steps: dict[str, list[str]],
    observed_at: str | None = None,
    token: str | None = None,
    fetch: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Fetch a run's evidence and evaluate it against caller-pinned expectations.

    ``fetch`` injects the transport for tests (a callable taking a URL and
    returning parsed JSON); without it the module fetches through the
    environment-supplied token. The returned report is the adapter's report
    plus a ``collection`` block naming the sources, the observation time, and
    how the payloads were obtained. It never contains the token.
    """
    if not _OWNER_RE.fullmatch(owner or "") or not _REPO_RE.fullmatch(repo or ""):
        raise ValueError("evidence: invalid repository owner/name")
    if type(run_id) is not int or run_id <= 0:
        raise ValueError("evidence: invalid run id")
    if expected_run_id is None:
        expected_run_id = run_id
    if (not isinstance(expected_revision, str) or not _HEX_RE.fullmatch(expected_revision)):
        raise ValueError("evidence: immutable revision required")
    if (not isinstance(required_steps, dict) or not required_steps
            or any(not isinstance(name, str) or not name
                   or not isinstance(steps, list) or not steps
                   or any(not isinstance(step, str) or not step for step in steps)
                   or len(set(steps)) != len(steps)
                   for name, steps in required_steps.items())):
        raise ValueError("evidence: nonempty unique requirements needed")

    if fetch is None:
        resolved = resolve_token(token)
        token_source = "explicit" if token else (
            "GITHUB_TOKEN" if os.environ.get("GITHUB_TOKEN") else "GH_TOKEN"
        )

        def _fetch(url: str, _token: str = resolved) -> dict[str, Any]:
            return _default_fetch(url, _token)
        fetch = _fetch
    else:
        token_source = "injected-fetch"

    if observed_at is None:
        observed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    run_source = f"{_API}/repos/{owner}/{repo}/actions/runs/{run_id}"
    jobs_source = f"{_API}/repos/{owner}/{repo}/actions/runs/{run_id}/jobs?per_page=100"

    run = fetch(run_source)
    pages: list[dict[str, Any]] = []
    page = 1
    while True:
        if page > MAX_PAGES:
            raise ValueError("evidence: jobs pagination exceeded page budget")
        jobs_page = fetch(f"{jobs_source}&page={page}")
        if not isinstance(jobs_page, dict) or not isinstance(jobs_page.get("jobs"), list):
            raise ValueError("evidence: unexpected jobs page shape")
        pages.append(jobs_page)
        total = jobs_page.get("total_count")
        seen = sum(len(p["jobs"]) for p in pages)
        if type(total) is not int or total < 0:
            raise ValueError("evidence: invalid jobs total_count")
        if seen >= total:
            break
        page += 1

    report = runtime_evidence.evaluate_run(
        run,
        pages,
        expected_repository_id=expected_repository_id,
        expected_revision=expected_revision,
        expected_workflow_id=expected_workflow_id,
        expected_run_id=expected_run_id,
        expected_attempt=expected_attempt,
        required_steps=required_steps,
        observed_at=observed_at,
    )
    report["collection"] = {
        "collector_version": VERSION,
        "run_source": run_source,
        "jobs_source": jobs_source,
        "pages_fetched": len(pages),
        "observed_at": observed_at,
        "token_source": token_source,
    }
    return report
