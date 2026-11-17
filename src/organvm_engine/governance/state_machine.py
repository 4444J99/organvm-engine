"""Promotion state machine: LOCAL -> CANDIDATE -> PUBLIC_PROCESS -> GRADUATED -> ARCHIVED.

Implements: SPEC-004, LOG-001 through LOG-014
Resolves: AX-000-005 DRIFT (engine #16, #30)

The transition table is loaded from governance-rules.json when available,
falling back to the hardcoded FALLBACK_TRANSITIONS dict if the file cannot
be read. Every successful transition emits a constitutional event to the
EventSpine (INST-EVENT-SPINE).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hardcoded fallback — used only when governance-rules.json is unavailable
# ---------------------------------------------------------------------------

FALLBACK_TRANSITIONS: dict[str, list[str]] = {
    "INCUBATOR": ["LOCAL", "ARCHIVED"],
    "LOCAL": ["CANDIDATE", "ARCHIVED"],
    "CANDIDATE": ["PUBLIC_PROCESS", "LOCAL", "ARCHIVED"],
    "PUBLIC_PROCESS": ["GRADUATED", "CANDIDATE", "ARCHIVED"],
    "GRADUATED": ["ARCHIVED"],
    "ARCHIVED": [],
}

# Module-level alias preserved for backward compatibility.
# Existing code that reads `state_machine.TRANSITIONS` still works.
TRANSITIONS = FALLBACK_TRANSITIONS


# ---------------------------------------------------------------------------
# Data-driven loader
# ---------------------------------------------------------------------------

_loaded_transitions: dict[str, list[str]] | None = None


def load_transitions_from_rules(
    rules_path: Path | str | None = None,
) -> dict[str, list[str]]:
    """Load the transition table from governance-rules.json.

    Reads the ``state_machine.transitions`` section. If the file is missing
    or malformed, returns an empty dict (caller should fall back).

    Args:
        rules_path: Explicit path to governance-rules.json.
            When None, resolves via ``organvm_engine.paths``.

    Returns:
        Dict mapping current-state to list of valid target-states,
        or empty dict on failure.
    """
    if rules_path is None:
        try:
            from organvm_engine.paths import governance_rules_path as _default_rules_path

            rules_path = _default_rules_path()
        except Exception:
            return {}

    path = Path(rules_path)
    if not path.is_file():
        return {}

    try:
        with path.open() as f:
            rules = json.load(f)
        sm = rules.get("state_machine", {})
        transitions = sm.get("transitions", {})
        if not isinstance(transitions, dict):
            return {}
        # Validate structure: every value must be a list of strings
        for key, targets in transitions.items():
            if not isinstance(targets, list):
                logger.warning(
                    "governance-rules.json: state_machine.transitions[%s] is not a list", key,
                )
                return {}
            for t in targets:
                if not isinstance(t, str):
                    logger.warning(
                        "governance-rules.json: non-string target in transitions[%s]", key,
                    )
                    return {}
        return transitions
    except (json.JSONDecodeError, OSError) as exc:
        logger.debug("Could not load transitions from %s: %s", path, exc)
        return {}


def _get_transitions(rules_path: Path | str | None = None) -> dict[str, list[str]]:
    """Return the active transition table.

    Priority: loaded from rules file > hardcoded fallback.
    """
    global _loaded_transitions  # noqa: PLW0603

    if _loaded_transitions is not None:
        return _loaded_transitions

    loaded = load_transitions_from_rules(rules_path)
    if loaded:
        _loaded_transitions = loaded
        return _loaded_transitions

    return FALLBACK_TRANSITIONS


def reset_loaded_transitions() -> None:
    """Clear the cached loaded transitions (useful for tests)."""
    global _loaded_transitions  # noqa: PLW0603
    _loaded_transitions = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_valid_transitions(
    current_state: str,
    rules_path: Path | str | None = None,
) -> list[str]:
    """Get valid target states for a given current state.

    Args:
        current_state: Current promotion_status.
        rules_path: Optional explicit path to governance-rules.json.

    Returns:
        List of valid target states.
    """
    transitions = _get_transitions(rules_path)
    return transitions.get(current_state, [])


def check_transition(
    current_state: str,
    target_state: str,
    rules_path: Path | str | None = None,
) -> tuple[bool, str]:
    """Check if a state transition is valid.

    Uses the data-driven transition table from governance-rules.json when
    available, falling back to FALLBACK_TRANSITIONS otherwise.

    Args:
        current_state: Current promotion_status.
        target_state: Desired promotion_status.
        rules_path: Optional explicit path to governance-rules.json.

    Returns:
        (valid, message) tuple.
    """
    transitions = _get_transitions(rules_path)
    valid = transitions.get(current_state)
    if valid is None:
        return False, f"Unknown state '{current_state}'"

    if target_state in valid:
        return True, f"{current_state} -> {target_state}"

    return False, (
        f"Cannot transition {current_state} -> {target_state}. "
        f"Valid targets: {', '.join(valid) if valid else 'none (terminal state)'}"
    )


def execute_transition(
    repo_name: str,
    current_state: str,
    target_state: str,
    *,
    rules_path: Path | str | None = None,
    actor: str = "cli",
    spine_path: Path | str | None = None,
    seed: dict | None = None,
    repo_path: Path | str | None = None,
    organ: str = "",
    org: str = "",
    tier: str = "standard",
    enforce_infrastructure: bool = True,
    registry_entry: dict | None = None,
    reason: str = "",
    dry_run: bool = False,
) -> tuple[bool, str]:
    """Validate and execute a state transition, emitting events on success.

    This is the preferred entry point when the caller wants both validation
    and event emission in one call.

    Args:
        repo_name: Repository name (used as entity_uid in the event).
        current_state: Current promotion_status.
        target_state: Desired promotion_status.
        rules_path: Optional path to governance-rules.json.
        actor: Who/what is requesting the transition.
        spine_path: Optional path for the EventSpine JSONL file.
        seed: Optional parsed seed.yaml for authorization checking.
        repo_path: Filesystem path to repo (for infrastructure audit).
        organ: Organ registry key (for infrastructure audit).
        org: GitHub org (for infrastructure audit).
        tier: Repository tier (for infrastructure audit).
        enforce_infrastructure: If True, block promotion when
            infrastructure requirements are not met. Default True.
        registry_entry: Optional registry entry dict for the repo.
            When provided, a ``promotion_history`` record is appended
            on successful transition (F-002).
        reason: Optional human-readable reason for the transition.
        dry_run: If True, run every validation but emit no events and record
            no promotion_history (a pure eligibility check).

    Returns:
        (valid, message) tuple — same semantics as check_transition.
    """
    ok, msg = check_transition(current_state, target_state, rules_path)
    if not ok:
        return ok, msg

    # Post-flood constitutional gate: repos above LOCAL must have functional_class
    if (
        target_state in ("CANDIDATE", "PUBLIC_PROCESS", "GRADUATED")
        and registry_entry
        and not registry_entry.get("functional_class")
    ):
        return False, (
            "Cannot promote above LOCAL without functional_class "
            "(post-flood constitutional requirement)"
        )

    # Infrastructure check (The Descent Protocol)
    if enforce_infrastructure and repo_path is not None and target_state != "ARCHIVED":
        try:
            from organvm_engine.ci.audit import check_promotion_infrastructure

            rp = Path(repo_path) if not isinstance(repo_path, Path) else repo_path
            infra_ok, failures = check_promotion_infrastructure(
                repo_path=rp,
                repo_name=repo_name,
                organ=organ,
                org=org,
                current_status=current_state,
                target_status=target_state,
                tier=tier,
            )
            if not infra_ok:
                missing = ", ".join(failures)
                return False, (
                    f"Infrastructure requirements not met for {target_state}. "
                    f"Missing: {missing}. "
                    f"Deploy required infrastructure before promoting. "
                    f"See: SOP--the-descent-protocol.md"
                )
        except Exception:
            logger.warning(
                "Infrastructure audit could not run for %s (promotion proceeds)",
                repo_name,
                exc_info=True,
            )

    # Authorization check (advisory mode — logs but does not block)
    if seed is not None:
        try:
            from organvm_engine.governance.authorization import (
                authorize_transition as _authorize,
            )

            auth = _authorize(actor, target_state, seed, enforce=False)
            if not auth.authorized:
                logger.warning(
                    "Authorization advisory for %s: %s (transition proceeds in advisory mode)",
                    repo_name,
                    auth.reason,
                )
        except Exception:
            logger.debug("Authorization check failed (non-fatal)", exc_info=True)

    if dry_run:
        return ok, f"{msg} (dry run: no event emitted, nothing recorded)"

    # Emit constitutional event via EventSpine
    _emit_spine_event(
        repo_name=repo_name,
        previous_state=current_state,
        new_state=target_state,
        actor=actor,
        spine_path=spine_path,
    )

    # Also emit to the existing pulse bus (backward compat)
    emit_promotion_event(repo_name, current_state, target_state)

    # Record promotion_history on the registry entry (F-002)
    if registry_entry is not None:
        try:
            from organvm_engine.registry.updater import _record_promotion_history

            _record_promotion_history(
                registry_entry, current_state, target_state, reason=reason,
            )
        except Exception:
            logger.debug("promotion_history recording failed (non-fatal)", exc_info=True)

    return ok, msg


# ---------------------------------------------------------------------------
# Event emission
# ---------------------------------------------------------------------------

def _emit_spine_event(
    repo_name: str,
    previous_state: str,
    new_state: str,
    actor: str = "cli",
    spine_path: Path | str | None = None,
) -> None:
    """Emit a PROMOTION event to the constitutional EventSpine.

    Fail-safe: never raises. If the EventSpine cannot be imported or
    written to, the transition still succeeds.
    """
    try:
        from organvm_engine.events.spine import EventSpine, EventType

        spine_kwargs: dict[str, Any] = {}
        if spine_path is not None:
            spine_kwargs["path"] = spine_path

        spine = EventSpine(**spine_kwargs)
        spine.emit(
            event_type=EventType.PROMOTION,
            entity_uid=repo_name,
            payload={
                "previous_state": previous_state,
                "new_state": new_state,
            },
            source_spec="SPEC-004",
            actor=actor,
        )
    except Exception:
        logger.debug("EventSpine emission failed (non-fatal)", exc_info=True)


def emit_promotion_event(
    repo_name: str,
    previous_state: str,
    new_state: str,
) -> None:
    """Emit a promotion change event to the unified pulse bus.

    Retained for backward compatibility with the pulse/emitter pipeline.
    """
    try:
        from organvm_engine.pulse.emitter import emit_engine_event
        from organvm_engine.pulse.types import PROMOTION_CHANGED

        emit_engine_event(
            event_type=PROMOTION_CHANGED,
            source="governance",
            subject_entity=repo_name,
            payload={
                "previous_state": previous_state,
                "new_state": new_state,
            },
        )
    except Exception:
        pass
