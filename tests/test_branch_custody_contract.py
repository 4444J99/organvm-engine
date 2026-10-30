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

    # Critical workflow/governance paths need a separately observed, revision-
    # bound approval. Candidate-declared authority never suffices; this remains
    # only a structural check, not authentication of the snapshot's producer.
    protected = snapshot.get("protected_paths")
    if not isinstance(protected, list) or not protected or any(
        not isinstance(path, str)
        or not path
        or path.startswith("/")
        or any(segment in ("", ".", "..") for segment in path.split("/"))
        for path in protected
    ):
        failures.append("unverified_protected_path_inventory")
    else:
        affected = [
            path for path in paths
            if any(_overlaps(path, sensitive) for sensitive in protected)
        ]
        if affected:
            authorizations = snapshot.get("protected_write_approvals", {})
            approval = (
                authorizations.get(candidate.get("work_id"), {})
                if isinstance(authorizations, dict) else {}
            )
            if not isinstance(approval, dict) or (
                approval.get("disposition") != "approved"
                or approval.get("policy_sha") != snapshot.get("policy_sha")
                or approval.get("default_sha") != snapshot.get("default_sha")
                or approval.get("approver") in (None, "", candidate.get("writer"))
                or not isinstance(approval.get("paths"), list)
                or any(path not in approval.get("paths", []) for path in affected)
            ):
                failures.append("unapproved_protected_scope")

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

    # Declared tool effects are a separate authority surface from file/path
    # custody. These synthetic records can check structural consistency only:
    # a real host must authenticate effect grants, lifecycle and every call.
    effects = candidate.get("effect_requests", [])
    if not isinstance(effects, list) or any(
        not isinstance(effect, dict)
        or not isinstance(effect.get("operation"), str)
        or not effect.get("operation")
        or not isinstance(effect.get("target"), str)
        or not effect.get("target")
        for effect in effects
    ):
        failures.append("invalid_effect_request")
    elif effects:
        terminal = snapshot.get("terminal_work_ids")
        if not isinstance(terminal, list):
            failures.append("unknown_effect_lifecycle")
        elif candidate.get("work_id") in terminal:
            failures.append("effect_after_terminal")

        grants = snapshot.get("effect_approvals")
        grant = grants.get(candidate.get("work_id")) if isinstance(grants, dict) else None
        if not isinstance(grant, dict) or (
            grant.get("disposition") != "approved"
            or grant.get("approver") in (None, "", candidate.get("writer"))
            or grant.get("default_sha") != snapshot.get("default_sha")
            or grant.get("policy_sha") != snapshot.get("policy_sha")
            or not isinstance(grant.get("effects"), list)
        ):
            failures.append("unverified_effect_approval")
        elif any(effect not in grant["effects"] for effect in effects):
            failures.append("unapproved_secondary_effect")

    return ("structurally_prepared" if not failures else "hold", sorted(set(failures)))


def _case() -> tuple[dict, dict]:
    snapshot = {
        "repository_id": 1160447354,
        "default_sha": "a" * 40,
        "policy_sha": "b" * 40,
        "coverage": "complete",
        "active_writers": [{"work_id": "W1", "paths": ["src/agent_eval.py"]}],
        "dependencies": {"W1": []},
        "protected_paths": [".github/workflows", "signatures/cla.json"],
        "protected_write_approvals": {},
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

def test_injected_new_workflow_requires_separate_approval() -> None:
    state, claim = deepcopy(_case())
    claim["paths"] = [".github/workflows/security-audit.yml"]
    assert "unapproved_protected_scope" in inspect_custody(state, claim)[1]


def test_broad_workflow_directory_claim_requires_exact_scope() -> None:
    state, claim = deepcopy(_case())
    claim["paths"] = [".github"]
    state["protected_write_approvals"]["W2"] = {
        "disposition": "approved", "approver": "owner",
        "default_sha": "a" * 40, "policy_sha": "b" * 40,
        "paths": [".github/workflows/security-audit.yml"],
    }
    assert "unapproved_protected_scope" in inspect_custody(state, claim)[1]


def test_candidate_self_attestation_cannot_grant_workflow_access() -> None:
    state, claim = deepcopy(_case())
    claim["paths"] = [".github/workflows/ci.yml"]
    claim["protected_write_approval"] = {"disposition": "approved"}
    assert "unapproved_protected_scope" in inspect_custody(state, claim)[1]


def test_self_approved_protected_write_is_held() -> None:
    state, claim = deepcopy(_case())
    claim["paths"] = [".github/workflows/ci.yml"]
    state["protected_write_approvals"]["W2"] = {
        "disposition": "approved", "approver": claim["writer"],
        "default_sha": "a" * 40, "policy_sha": "b" * 40,
        "paths": [".github/workflows/ci.yml"],
    }
    assert "unapproved_protected_scope" in inspect_custody(state, claim)[1]


def test_stale_protected_write_approval_is_held() -> None:
    state, claim = deepcopy(_case())
    claim["paths"] = ["signatures/cla.json"]
    state["protected_write_approvals"]["W2"] = {
        "disposition": "approved", "approver": "owner",
        "default_sha": "old", "policy_sha": "b" * 40,
        "paths": ["signatures/cla.json"],
    }
    assert "unapproved_protected_scope" in inspect_custody(state, claim)[1]


def test_unknown_protected_path_inventory_is_not_an_all_clear() -> None:
    state, claim = deepcopy(_case())
    del state["protected_paths"]
    assert "unverified_protected_path_inventory" in inspect_custody(state, claim)[1]


def test_revision_bound_independent_scope_is_structurally_prepared() -> None:
    state, claim = deepcopy(_case())
    claim["paths"] = [".github/workflows/ci.yml"]
    state["protected_write_approvals"]["W2"] = {
        "disposition": "approved", "approver": "owner",
        "default_sha": "a" * 40, "policy_sha": "b" * 40,
        "paths": [".github/workflows/ci.yml"],
    }
    assert inspect_custody(state, claim) == ("structurally_prepared", [])


def test_normal_documentation_path_needs_no_protected_path_approval() -> None:
    assert inspect_custody(*_case()) == ("structurally_prepared", [])


def _authorized_effect_case() -> tuple[dict, dict]:
    state, claim = deepcopy(_case())
    state["terminal_work_ids"] = []
    state["effect_approvals"] = {"W2": {
        "disposition": "approved", "approver": "independent-owner",
        "default_sha": "a" * 40, "policy_sha": "b" * 40,
        "effects": [{"operation": "get_issue", "target": "github:engine/187"}],
    }}
    claim["effect_requests"] = [{"operation": "get_issue", "target": "github:engine/187"}]
    return state, claim


def test_independently_approved_exact_effect_is_structurally_prepared() -> None:
    assert inspect_custody(*_authorized_effect_case()) == ("structurally_prepared", [])


def test_extra_post_task_logging_tool_call_is_not_implicitly_authorized() -> None:
    state, claim = _authorized_effect_case()
    claim["effect_requests"].append({"operation": "save_logs", "target": "external:attacker"})
    assert "unapproved_secondary_effect" in inspect_custody(state, claim)[1]


def test_approved_scope_does_not_survive_terminal_completion() -> None:
    state, claim = _authorized_effect_case()
    state["terminal_work_ids"].append("W2")
    assert "effect_after_terminal" in inspect_custody(state, claim)[1]


def test_effect_grant_from_the_agent_itself_is_rejected() -> None:
    state, claim = _authorized_effect_case()
    state["effect_approvals"]["W2"]["approver"] = claim["writer"]
    assert "unverified_effect_approval" in inspect_custody(state, claim)[1]


def test_stale_effect_grant_does_not_carry_forward() -> None:
    state, claim = _authorized_effect_case()
    state["effect_approvals"]["W2"]["default_sha"] = "old"
    assert "unverified_effect_approval" in inspect_custody(state, claim)[1]


def test_unproven_effect_lifecycle_is_not_open_ended() -> None:
    state, claim = _authorized_effect_case()
    del state["terminal_work_ids"]
    assert "unknown_effect_lifecycle" in inspect_custody(state, claim)[1]


def test_malformed_effect_request_does_not_grant_authority() -> None:
    state, claim = _authorized_effect_case()
    claim["effect_requests"] = [{"operation": "save_logs", "target": ""}]
    assert "invalid_effect_request" in inspect_custody(state, claim)[1]


def test_candidate_declared_effect_approval_is_not_independent_proof() -> None:
    state, claim = _authorized_effect_case()
    del state["effect_approvals"]
    claim["effect_approval"] = {"disposition": "approved", "effects": claim["effect_requests"]}
    assert "unverified_effect_approval" in inspect_custody(state, claim)[1]
