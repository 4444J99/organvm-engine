"""Read-only promotion queue: what stands between each repo and its next state.

``organvm governance promote`` answers the question for one repo and, because it
routes through ``execute_transition``, emits events as a side effect. This module
answers it for the whole registry without writing anything: every repo that is
not terminal gets an assessment of its next promotion step, the blockers
(invalid transition, missing ``functional_class``, failing infrastructure
mechanisms) and whether those blockers could actually be verified (a repo with
no local checkout is ``unverified``, never silently ``ready``).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from organvm_engine.governance.state_machine import check_transition

#: The forward step for each promotable state. GRADUATED/ARCHIVED are terminal
#: for promotion purposes (GRADUATED -> ARCHIVED is a retirement, not a promotion).
NEXT_STATE: dict[str, str] = {
    "INCUBATOR": "LOCAL",
    "LOCAL": "CANDIDATE",
    "CANDIDATE": "PUBLIC_PROCESS",
    "PUBLIC_PROCESS": "GRADUATED",
}

STATUS_READY = "ready"
STATUS_BLOCKED = "blocked"
STATUS_UNVERIFIED = "unverified"

_STATUS_ORDER = {STATUS_READY: 0, STATUS_UNVERIFIED: 1, STATUS_BLOCKED: 2}


@dataclass
class PromotionAssessment:
    """Assessment of one repo's next promotion step."""

    repo: str
    organ: str
    org: str
    tier: str
    current: str
    target: str
    status: str
    blockers: list[str] = field(default_factory=list)
    checkout: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def assess_repo(
    organ_key: str,
    entry: dict,
    *,
    repo_path: Path | None,
    rules_path: Path | str | None = None,
) -> PromotionAssessment | None:
    """Assess one registry entry; ``None`` when it has no forward step."""
    current = entry.get("promotion_status", "LOCAL")
    target = NEXT_STATE.get(current)
    if target is None:
        return None

    name = entry.get("name", "")
    org = entry.get("org", "")
    tier = entry.get("tier", "standard")
    blockers: list[str] = []

    valid, message = check_transition(current, target, rules_path)
    if not valid:
        blockers.append(f"transition: {message}")

    if target in ("CANDIDATE", "PUBLIC_PROCESS", "GRADUATED") and not entry.get(
        "functional_class",
    ):
        blockers.append("registry: missing functional_class")

    verified = False
    if repo_path is not None:
        try:
            from organvm_engine.ci.audit import check_promotion_infrastructure

            _ok, failures = check_promotion_infrastructure(
                repo_path=repo_path,
                repo_name=name,
                organ=organ_key,
                org=org,
                current_status=current,
                target_status=target,
                tier=tier,
            )
            blockers.extend(f"infrastructure: {f}" for f in failures)
            verified = True
        except Exception as exc:  # audit must never take the whole queue down
            blockers.append(f"audit-error: {type(exc).__name__}: {exc}")

    if blockers:
        status = STATUS_BLOCKED
    elif verified:
        status = STATUS_READY
    else:
        status = STATUS_UNVERIFIED

    return PromotionAssessment(
        repo=name,
        organ=organ_key,
        org=org,
        tier=tier,
        current=current,
        target=target,
        status=status,
        blockers=blockers,
        checkout=str(repo_path) if repo_path is not None else None,
    )


def build_queue(
    registry: dict,
    *,
    workspace: Path | None = None,
    organ: str | None = None,
    rules_path: Path | str | None = None,
) -> list[PromotionAssessment]:
    """Assess every promotable repo; ready first, then unverified, then blocked.

    Within a status, fewer blockers sort first so the nearest promotions lead.
    """
    from organvm_engine.ci.mandate import _resolve_repo_path
    from organvm_engine.organ_config import registry_key_to_dir
    from organvm_engine.paths import workspace_root
    from organvm_engine.registry.query import all_repos, resolve_organ_key

    ws = workspace if workspace is not None else workspace_root()
    key_to_dir = registry_key_to_dir()
    wanted = resolve_organ_key(organ) if organ else None

    queue: list[PromotionAssessment] = []
    for organ_key, entry in all_repos(registry):
        if wanted and organ_key != wanted:
            continue
        path = _resolve_repo_path(
            entry.get("org", ""), entry.get("name", ""), organ_key, ws, key_to_dir,
        )
        assessment = assess_repo(organ_key, entry, repo_path=path, rules_path=rules_path)
        if assessment is not None:
            queue.append(assessment)

    queue.sort(
        key=lambda a: (_STATUS_ORDER[a.status], len(a.blockers), a.organ, a.repo),
    )
    return queue


def summarize(queue: list[PromotionAssessment]) -> dict[str, Any]:
    """Counts by status and by (current -> target) step, plus top blocker causes."""
    by_status: dict[str, int] = {}
    by_step: dict[str, int] = {}
    causes: dict[str, int] = {}
    for a in queue:
        by_status[a.status] = by_status.get(a.status, 0) + 1
        step = f"{a.current}->{a.target}"
        by_step[step] = by_step.get(step, 0) + 1
        for b in a.blockers:
            causes[b] = causes.get(b, 0) + 1
    top = sorted(causes.items(), key=lambda kv: (-kv[1], kv[0]))
    return {
        "total": len(queue),
        "by_status": by_status,
        "by_step": by_step,
        "top_blockers": [{"blocker": k, "repos": v} for k, v in top],
    }


def format_queue(queue: list[PromotionAssessment], *, limit: int | None = None) -> str:
    """Render the queue as plain text."""
    summary = summarize(queue)
    lines = [
        f"Promotion queue: {summary['total']} repos with a forward step",
        "  " + ", ".join(f"{k}={v}" for k, v in sorted(summary["by_status"].items())),
    ]
    shown = queue if limit is None else queue[:limit]
    for a in shown:
        lines.append(
            f"  [{a.status:<10}] {a.repo} ({a.organ}, {a.tier}) {a.current} -> {a.target}",
        )
        lines.extend(f"      - {b}" for b in a.blockers)
    if limit is not None and len(queue) > limit:
        lines.append(f"  ... {len(queue) - limit} more (use --limit 0 for all)")
    if summary["top_blockers"]:
        lines.append("Most common blockers:")
        lines.extend(
            f"  {t['repos']:>4}  {t['blocker']}" for t in summary["top_blockers"][:10]
        )
    return "\n".join(lines)
