"""Source-independent negative controls for Engine issue #187's custody contract.

Structural checks only: fixture records are untrusted assertions, not proof of
GitHub ownership, provider admission, monitored execution, or merge authority.
No network, credentials, files, or process effects are performed.
"""

from __future__ import annotations

from copy import deepcopy


def _overlaps(a: str, b: str) -> bool:
    return a == b or a.startswith(b.rstrip("/") + "/") or b.startswith(a.rstrip("/") + "/")


def _has_cycle(graph: dict[str, list[str]]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        for dependency in graph.get(node, []):
            if visit(dependency):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in graph)


def inspect_custody(snapshot: dict, candidate: dict) -> tuple[str, list[str]]:
    """Return structural readiness, never execution or integration authority."""
    failures: list[str] = []
    if snapshot.get("coverage") != "complete":
        failures.append("incomplete_observation")
    if not isinstance(snapshot.get("repository_id"), int) or snapshot["repository_id"] <= 0:
        failures.append("unknown_repository")
    if candidate.get("repository_id") != snapshot.get("repository_id"):
        failures.append("wrong_repository")
    if not candidate.get("writer") or not candidate.get("work_id"):
        failures.append("missing_work_identity")
    if candidate.get("base_sha") != snapshot.get("default_sha"):
        failures.append("stale_base")
    if candidate.get("policy_sha") != snapshot.get("policy_sha"):
        failures.append("stale_policy")

    paths = candidate.get("paths")
    if not isinstance(paths, list) or not paths or any(
        not isinstance(path, str)
        or not path
        or path.startswith("/")
        or any(segment in ("", ".", "..") for segment in path.split("/"))
        for path in paths
    ):
        failures.append("invalid_path_scope")
        paths = []

    # A current writer's path or directory reservation cannot be stolen by a
    # different work identity. Repo-wide locking is not implied.
    for active in snapshot.get("active_writers", []):
        if active.get("work_id") == candidate.get("work_id"):
            continue
        if any(_overlaps(path, prior) for path in paths for prior in active.get("paths", [])):
            failures.append("overlapping_writer")
            break

    graph = dict(snapshot.get("dependencies", {}))
    graph[str(candidate.get("work_id"))] = list(candidate.get("dependencies", []))
    if _has_cycle(graph):
        failures.append("dependency_cycle")

    if candidate.get("requires_broker") and (
        candidate.get("admission", {}).get("state") != "accepted"
        or not candidate.get("admission", {}).get("lease_id")
    ):
        failures.append("unverified_admission")

    # These fields are a *necessary* coverage assertion, not an authenticating
    # monitor receipt. An agent must not attest its own monitor coverage.
    if candidate.get("monitoring_required"):
        monitor = snapshot.get("monitor", {})
        if monitor.get("coverage") != "complete":
            failures.append("unverified_monitor_coverage")
        if monitor.get("observer") in (None, "", candidate.get("writer")):
            failures.append("non_independent_monitor")
        if monitor.get("disposition") == "disabled":
            failures.append("monitor_disabled")

    return ("structurally_prepared" if not failures else "hold", sorted(set(failures)))


def _case() -> tuple[dict, dict]:
    snapshot = {
        "repository_id": 1160447354,
        "default_sha": "a" * 40,
        "policy_sha": "b" * 40,
        "coverage": "complete",
        "active_writers": [{"work_id": "W1", "paths": ["src/agent_eval.py"]}],
        "dependencies": {"W1": []},
        "monitor": {"observer": "external-audit", "coverage": "complete", "disposition": "enabled"},
    }
    candidate = {
        "repository_id": 1160447354,
        "work_id": "W2",
        "writer": "agent-2",
        "base_sha": "a" * 40,
        "policy_sha": "b" * 40,
        "paths": ["docs/BRANCHES.md"],
        "dependencies": ["W1"],
        "requires_broker": True,
        "admission": {"state": "accepted", "lease_id": "observed-example-only"},
        "monitoring_required": True,
    }
    return snapshot, candidate


def test_disjoint_and_fully_observed_is_structurally_prepared() -> None:
    assert inspect_custody(*_case()) == ("structurally_prepared", [])


def test_missing_owner_fails_closed() -> None:
    state, claim = deepcopy(_case())
    claim["writer"] = None
    assert "missing_work_identity" in inspect_custody(state, claim)[1]


def test_stale_base_fails_closed() -> None:
    state, claim = deepcopy(_case())
    state["default_sha"] = "c" * 40
    assert "stale_base" in inspect_custody(state, claim)[1]


def test_stale_policy_fails_closed() -> None:
    state, claim = deepcopy(_case())
    state["policy_sha"] = "d" * 40
    assert "stale_policy" in inspect_custody(state, claim)[1]


def test_directory_and_file_reservations_conflict() -> None:
    state, claim = deepcopy(_case())
    claim["paths"] = ["src"]
    assert "overlapping_writer" in inspect_custody(state, claim)[1]


def test_dependency_cycle_blocks() -> None:
    state, claim = deepcopy(_case())
    state["dependencies"]["W1"] = ["W2"]
    assert "dependency_cycle" in inspect_custody(state, claim)[1]


def test_missing_broker_acknowledgement_blocks() -> None:
    state, claim = deepcopy(_case())
    claim["admission"] = {"state": "requested"}
    assert "unverified_admission" in inspect_custody(state, claim)[1]


def test_partial_collection_is_not_all_clear() -> None:
    state, claim = deepcopy(_case())
    state["coverage"] = "partial"
    assert "incomplete_observation" in inspect_custody(state, claim)[1]


def test_monitor_cannot_attest_its_own_coverage() -> None:
    state, claim = deepcopy(_case())
    state["monitor"]["observer"] = claim["writer"]
    assert "non_independent_monitor" in inspect_custody(state, claim)[1]


def test_disabled_monitor_not_treated_as_normal() -> None:
    state, claim = deepcopy(_case())
    state["monitor"]["disposition"] = "disabled"
    assert "monitor_disabled" in inspect_custody(state, claim)[1]


def test_absent_coverage_and_bad_path_are_held() -> None:
    state, claim = deepcopy(_case())
    state["monitor"] = {}
    claim["paths"] = ["../private"]
    verdict, failures = inspect_custody(state, claim)
    assert verdict == "hold"
    assert "invalid_path_scope" in failures
    assert "unverified_monitor_coverage" in failures


def test_no_broker_rule_does_not_invent_a_lease() -> None:
    state, claim = deepcopy(_case())
    claim["requires_broker"] = False
    claim["admission"] = {}
    assert inspect_custody(state, claim)[0] == "structurally_prepared"
