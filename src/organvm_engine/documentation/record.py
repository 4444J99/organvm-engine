"""Canonical project-record loading and integrity validation."""

from __future__ import annotations

import hashlib
import json
import os
import re
import selectors
import subprocess
import time
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from organvm_engine._stable_io import StableReadError, read_stable_regular_bytes


class _UniqueKeySafeLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects ambiguous duplicate mapping keys."""


def _construct_unique_mapping(
    loader: _UniqueKeySafeLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise ValueError(f"unhashable YAML mapping key: {key!r}") from exc
        if duplicate:
            raise ValueError(f"duplicate mapping key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)

CONTRACT_NAME = "project-record.v1"
CONTRACT_VERSION = 1
MAX_STRUCTURED_RECORD_BYTES = 2_000_000
MAX_EVIDENCE_BYTES = 128_000_000
GIT_EVIDENCE_TIMEOUT_SECONDS = 30.0
MAX_FRESHNESS_AGE_SECONDS = 315_576_000
DOCUMENTATION_CLASSES = frozenset("ABCDEF")
IMPLEMENTATION_STATUSES = frozenset(
    {"ACTIVE", "PROTOTYPE", "SKELETON", "DESIGN_ONLY", "ARCHIVED"},
)
DEPLOYMENT_STATUSES = frozenset(
    {"not-deployed", "internal", "pilot", "public", "retired", "not-applicable"},
)
CANONICAL_REDIRECT_STATUSES = frozenset({"planned", "active", "retired"})
EVIDENCE_TYPES = frozenset(
    {
        "immutable_source_event",
        "ratified_constitutional_record",
        "owner_record",
        "fresh_verifier_receipt",
        "primary_source",
        "secondary_source",
        "artifact",
        "other",
    },
)
AUDIENCE_MODES = frozenset(
    {"general", "technical", "humanities", "business", "evaluator"},
)
CLAIM_POSTURES = frozenset(
    {"implemented", "partial", "proposed", "unknown", "contradicted"},
)
ASSERTION_CLASSES = frozenset(
    {
        "external_fact",
        "operator_directive",
        "current_state",
        "inference",
        "historical_record",
        "ratified_axiom",
    },
)
VERIFICATION_STATES = frozenset({"unverified", "verified", "stale", "disputed"})
FRESHNESS_STATUSES = frozenset({"fresh", "stale", "not_applicable"})
INDUSTRY_STATUSES = frozenset({"deployed", "piloted", "proposed"})
DEPLOYMENT_STATUS_POSTURES: dict[str, frozenset[str]] = {
    "pilot": frozenset({"implemented", "partial"}),
    "public": frozenset({"implemented", "partial"}),
    # A retired deployment may be established by its historical operation or
    # by verified evidence that the former deployment is now unavailable.
    "retired": frozenset({"implemented", "partial", "contradicted"}),
}
ROLE_CLASS_RULES: dict[str, str] = {
    "mirror": "D",
    "deployment-artifact": "D",
    "archive": "F",
    "upstream-fork": "F",
    "contribution": "F",
}
REPOSITORY_ROLES = frozenset(
    {
        "canonical",
        "mirror",
        "deployment-artifact",
        "archive",
        "contribution",
        "upstream-fork",
        "profile",
        "governance",
    },
)
GIT_EVIDENCE_REFERENCE = re.compile(
    r"^git:(?P<commit>(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64}))(?::(?P<path>.+))?$",
)
REPOSITORY_SLUG = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
AUDIENCE_ROUTE_PATH = re.compile(
    r"^docs/audiences/[a-z0-9-]+\.md$",
)
CLASS_ROUTE_RULES: dict[str, tuple[frozenset[str], int, int | None]] = {
    "A": (AUDIENCE_MODES, 5, 5),
    "B": (frozenset(), 2, 3),
    "C": (frozenset({"technical"}), 1, None),
    "D": (frozenset(), 0, 0),
    "E": (frozenset({"humanities"}), 1, None),
    "F": (frozenset(), 0, 0),
}
REQUIRED_FIELDS = (
    "contract_name",
    "contract_version",
    "project_id",
    "name",
    "canonical_repository",
    "repository_role",
    "documentation_class",
    "one_sentence",
    "problem",
    "intended_users",
    "implementation_status",
    "deployment_status",
    "authorship",
    "claim_references",
    "limitations",
    "audience_routes",
    "search_intents",
    "links",
    "generated_at",
    "verified_at",
)
PROJECT_ID = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
AUTHORSHIP_FIELDS = frozenset(
    {"owner", "role", "contributions", "collaborators", "generated", "inherited", "external"},
)


def load_project_record(path: str | Path) -> dict[str, Any]:
    """Load a YAML/JSON project record as a mapping."""
    record_path = Path(path)
    if not record_path.is_file():
        raise FileNotFoundError(record_path)
    data = _load_structured_data(record_path)
    if not isinstance(data, dict):
        raise ValueError(f"Project record is not a mapping: {record_path}")
    return _normalize_structured_data(data, record_path)


def _builtin_record_shape_errors(record: Mapping[str, Any]) -> list[str]:
    """Enforce the project-record.v1 baseline without an optional schema file."""
    return _schema_errors(
        _normalize_yaml_datetimes(dict(record)),
        _builtin_schema("project-record-v1.schema.json"),
        prefix="project-record.v1",
    )


def _builtin_schema(name: str) -> dict:
    """Load the packaged canonical contract; caller schemas are additive."""
    from importlib.resources import files

    return json.loads(
        files("organvm_engine.documentation").joinpath("schemas", name).read_text(
            encoding="utf-8",
        ),
    )


def validate_project_record(
    record: Mapping[str, Any],
    *,
    root: str | Path | None = None,
    schema: Mapping[str, Any] | None = None,
    assertion_schema: Mapping[str, Any] | None = None,
    now: datetime | None = None,
    require_git_tracked_evidence: bool = False,
    actual_repository: str | None = None,
) -> list[str]:
    """Return deterministic integrity errors for a canonical project record.

    JSON Schema validates shape. These checks additionally enforce uniqueness,
    local-path containment, cross-reference integrity, and agreement between a
    claim reference and its assertion-evidence record. Pass
    ``actual_repository`` when the caller knows the checked-out owner/name so
    canonical and noncanonical delivery roles can be bound to the repository
    that CI is actually validating.
    """
    errors: list[str] = []
    validation_now = now or datetime.now(timezone.utc)
    if validation_now.tzinfo is None:
        errors.append("validation time must include a timezone")
        validation_now = validation_now.replace(tzinfo=timezone.utc)
    for field in REQUIRED_FIELDS:
        if field not in record:
            errors.append(f"missing required field: {field}")
    errors.extend(_builtin_record_shape_errors(record))

    if record.get("contract_name") != CONTRACT_NAME:
        errors.append(
            f"unsupported contract_name: {record.get('contract_name')!r}; "
            f"expected {CONTRACT_NAME!r}",
        )
    contract_version = record.get("contract_version")
    if (
        not isinstance(contract_version, int)
        or isinstance(contract_version, bool)
        or contract_version != CONTRACT_VERSION
    ):
        errors.append(
            f"unsupported contract_version: {contract_version!r}; "
            f"expected {CONTRACT_VERSION}",
        )

    doc_class = record.get("documentation_class")
    if not isinstance(doc_class, str) or doc_class not in DOCUMENTATION_CLASSES:
        errors.append(f"invalid documentation_class: {doc_class!r}")
    implementation_status = record.get("implementation_status")
    if (
        not isinstance(implementation_status, str)
        or implementation_status not in IMPLEMENTATION_STATUSES
    ):
        errors.append(f"invalid implementation_status: {record.get('implementation_status')!r}")
    deployment_status = record.get("deployment_status")
    if (
        not isinstance(deployment_status, str)
        or deployment_status not in DEPLOYMENT_STATUSES
    ):
        errors.append(f"invalid deployment_status: {record.get('deployment_status')!r}")

    repository = record.get("canonical_repository")
    if not isinstance(repository, str) or not _valid_repository_slug(repository):
        errors.append("canonical_repository must use owner/name form")
    repository_role = record.get("repository_role")
    repository_role_valid = (
        isinstance(repository_role, str) and repository_role in REPOSITORY_ROLES
    )
    if not repository_role_valid:
        errors.append(f"invalid repository_role: {repository_role!r}")

    if actual_repository is not None:
        if not _valid_repository_slug(actual_repository):
            errors.append("actual_repository must use owner/name form")
        elif isinstance(repository, str) and _valid_repository_slug(repository):
            same_repository = repository.casefold() == actual_repository.casefold()
            if repository_role_valid and repository_role == "canonical" and not same_repository:
                errors.append(
                    "repository_role 'canonical' requires canonical_repository to "
                    "equal actual_repository",
                )
            if (
                repository_role_valid
                and repository_role in {"mirror", "deployment-artifact", "upstream-fork"}
                and same_repository
            ):
                errors.append(
                    f"repository_role {repository_role!r} requires canonical_repository "
                    "to differ from actual_repository",
                )

    project_timestamps: dict[str, datetime] = {}
    for field in ("generated_at", "verified_at"):
        value = record.get(field)
        parsed = _parse_datetime(value)
        if parsed is None:
            errors.append(f"{field} must be an ISO 8601 date-time with a timezone")
        else:
            project_timestamps[field] = parsed
            if parsed > validation_now.astimezone(timezone.utc):
                errors.append(f"{field} cannot be in the future")
    generated_at = project_timestamps.get("generated_at")
    verified_at = project_timestamps.get("verified_at")
    if generated_at is not None and verified_at is not None and verified_at > generated_at:
        errors.append("verified_at must be less than or equal to generated_at")

    links = record.get("links", {})
    if not isinstance(links, Mapping):
        errors.append("links must be a mapping")
        links = {}
    repository_link = links.get("repository")
    if isinstance(repository_link, str) and _web_uri_has_credentials(repository_link):
        errors.append("links.repository must be a canonical GitHub repository URL")
    elif not isinstance(repository_link, str) or not _valid_web_uri(repository_link):
        errors.append(
            "links.repository must be a canonical GitHub repository URL"
            if isinstance(repository_link, str) and _has_http_authority(repository_link)
            else "links.repository must be an absolute HTTP(S) URI",
        )
    else:
        linked_repository = _github_repository_slug(repository_link)
        if linked_repository is None:
            errors.append(
                "links.repository must be a canonical GitHub repository URL",
            )
        elif (
            (repository_role == "canonical" or doc_class == "D")
            and isinstance(repository, str)
            and repository.count("/") == 1
            and linked_repository.casefold() != repository.casefold()
        ):
            errors.append(
                "canonical_repository must agree with links.repository GitHub owner/name",
            )
    for key in ("project_page", "demo", "deployment"):
        value = links.get(key)
        if value is not None and (not isinstance(value, str) or not _valid_web_uri(value)):
            errors.append(f"links.{key} must be an absolute HTTP(S) URI")
    local_link_paths: list[tuple[str, str]] = []
    for key in ("documentation", "evidence"):
        value = links.get(key)
        if value is None:
            if key == "documentation":
                errors.append(f"links.{key} is required")
            continue
        if not isinstance(value, str) or not value:
            errors.append(
                f"links.{key} must be a contained local path or absolute HTTP(S) URI",
            )
        elif _valid_web_uri(value):
            continue
        elif _reference_is_remote_or_absolute(value):
            errors.append(
                f"links.{key} must be a contained local path or absolute HTTP(S) URI",
            )
        else:
            local_link_paths.append((key, value))

    if doc_class == "D" and (
        not repository_role_valid
        or repository_role not in {"mirror", "deployment-artifact"}
    ):
        errors.append(
            "documentation_class D requires repository_role 'mirror' or "
            "'deployment-artifact'",
        )
    if isinstance(repository_role, str) and repository_role in ROLE_CLASS_RULES:
        required_class = ROLE_CLASS_RULES[repository_role]
        if doc_class != required_class:
            errors.append(
                f"repository_role {repository_role!r} requires documentation_class {required_class}",
            )
    redirect = record.get("redirect")
    canonical_redirect_required = (
        doc_class == "D"
        or (
            isinstance(repository_role, str)
            and repository_role in {"mirror", "deployment-artifact"}
        )
    )
    redirect_requirement = (
        "class D"
        if doc_class == "D"
        else f"repository_role {repository_role!r}"
    )
    if canonical_redirect_required and not isinstance(redirect, Mapping):
        errors.append(f"{redirect_requirement} requires a canonical redirect")
    if isinstance(redirect, Mapping):
        target = redirect.get("target")
        if not isinstance(target, str) or not _valid_web_uri(target):
            errors.append("redirect.target must be an absolute HTTP(S) URI")
        if canonical_redirect_required:
            redirect_status = redirect.get("status")
            if (
                not isinstance(redirect_status, str)
                or redirect_status not in CANONICAL_REDIRECT_STATUSES
            ):
                errors.append(
                    f"{redirect_requirement} requires redirect.status to be one of: "
                    + ", ".join(sorted(CANONICAL_REDIRECT_STATUSES)),
                )
            target_repository = (
                _github_repository_slug(target) if isinstance(target, str) else None
            )
            if target_repository is None:
                errors.append(
                    f"{redirect_requirement} redirect.target must be a GitHub repository URL",
                )
            elif (
                isinstance(repository, str)
                and repository.count("/") == 1
                and target_repository.casefold() != repository.casefold()
            ):
                errors.append(
                    f"{redirect_requirement} redirect.target must resolve to canonical_repository",
                )

    if isinstance(doc_class, str) and doc_class in {"A", "B"}:
        evidence_link = links.get("evidence")
        if not isinstance(evidence_link, str) or not evidence_link:
            errors.append(f"class {doc_class} requires links.evidence")

    claims = record.get("claim_references", [])
    claim_ids: list[str] = []
    claim_scopes: list[str] = []
    claim_assertion_paths: list[tuple[int, str, str, str]] = []
    claims_by_id: dict[str, Mapping[str, Any]] = {}
    if not isinstance(claims, list) or not claims:
        errors.append("claim_references must be a non-empty list")
        claims = []
    for index, claim in enumerate(claims):
        if not isinstance(claim, Mapping):
            errors.append(f"claim_references[{index}] must be a mapping")
            continue
        claim_id = claim.get("id")
        if not isinstance(claim_id, str) or not claim_id:
            errors.append(f"claim_references[{index}] requires a non-empty id")
        else:
            claim_ids.append(claim_id)
            claims_by_id[claim_id] = claim
        if claim.get("assertion_contract") != "assertion-evidence.v1":
            errors.append(
                f"claim_references[{index}] must use assertion-evidence.v1",
            )
        scope = claim.get("scope")
        if isinstance(scope, str):
            claim_scopes.append(scope)
        claim_posture = claim.get("claim_posture")
        if not isinstance(claim_posture, str) or claim_posture not in CLAIM_POSTURES:
            errors.append(
                f"claim_references[{index}] has invalid claim_posture: {claim_posture!r}",
            )
        assertion_id = claim.get("assertion_id")
        assertion_ref = claim.get("assertion_ref")
        if not isinstance(assertion_id, str) or not assertion_id:
            errors.append(f"claim_references[{index}] requires assertion_id")
        if not isinstance(assertion_ref, str) or not assertion_ref:
            errors.append(f"claim_references[{index}] requires assertion_ref")
        elif _reference_is_remote_or_absolute(assertion_ref):
            errors.append(
                f"claim_references[{index}] remote or absolute assertion_ref is unsupported by project-record.v1",
            )
        elif isinstance(assertion_id, str) and isinstance(claim_id, str):
            claim_assertion_paths.append((index, assertion_ref, assertion_id, claim_id))

    for claim_id in _duplicates(claim_ids):
        errors.append(f"duplicate claim reference id: {claim_id}")
    claim_id_set = set(claim_ids)
    if "status" not in claim_scopes:
        errors.append("project record requires a 'status' claim reference")
    qualifying_status_claim_ids = [
        claim_id
        for claim_id, claim in claims_by_id.items()
        if claim.get("scope") == "status"
        and isinstance(claim.get("claim_posture"), str)
        and claim.get("claim_posture") in {"implemented", "partial"}
    ]
    if not qualifying_status_claim_ids:
        errors.append("implementation_status requires an implemented or partial status claim")
    if root is None:
        errors.append("implementation_status requires a repository root to verify assertion evidence")
    qualifying_deployment_claim_ids: list[str] = []
    allowed_deployment_postures = (
        DEPLOYMENT_STATUS_POSTURES.get(deployment_status)
        if isinstance(deployment_status, str)
        else None
    )
    if allowed_deployment_postures is not None:
        deployment_claims = [
            (claim_id, claim)
            for claim_id, claim in claims_by_id.items()
            if claim.get("scope") == "deployment"
        ]
        qualifying_deployment_claim_ids = [
            claim_id
            for claim_id, claim in deployment_claims
            if isinstance(claim.get("claim_posture"), str)
            and claim.get("claim_posture") in allowed_deployment_postures
        ]
        if not deployment_claims:
            errors.append(
                f"deployment_status {deployment_status!r} requires a 'deployment' "
                "claim reference",
            )
        elif not qualifying_deployment_claim_ids:
            rendered_postures = ", ".join(
                repr(posture) for posture in sorted(allowed_deployment_postures)
            )
            errors.append(
                f"deployment_status {deployment_status!r} requires at least one "
                f"deployment claim with claim_posture in {{{rendered_postures}}}",
            )
        if root is None:
            errors.append(
                f"deployment_status {deployment_status!r} requires a repository root "
                "to verify assertion evidence",
            )
    if doc_class == "F":
        for required_scope in ("provenance",):
            if required_scope not in claim_scopes:
                errors.append(
                    f"class F requires a {required_scope!r} claim reference",
                )

    limitation_ids: list[str] = []
    limitation_assertion_paths: list[tuple[int, str, str]] = []
    limitations = record.get("limitations", [])
    if not isinstance(limitations, list):
        errors.append("limitations must be a list")
        limitations = []
    for index, limitation in enumerate(limitations):
        if not isinstance(limitation, Mapping):
            errors.append(f"limitations[{index}] must be a mapping")
            continue
        limitation_id = limitation.get("id")
        if isinstance(limitation_id, str) and limitation_id:
            limitation_ids.append(limitation_id)
        else:
            errors.append(f"limitations[{index}] requires a non-empty id")
        assertion_ref = limitation.get("assertion_ref")
        assertion_id = limitation.get("assertion_id")
        if isinstance(assertion_ref, str) and assertion_ref:
            if not isinstance(assertion_id, str) or not assertion_id:
                errors.append(
                    f"limitations[{index}] assertion_ref requires assertion_id",
                )
            if _reference_is_remote_or_absolute(assertion_ref):
                errors.append(
                    f"limitations[{index}] remote or absolute assertion_ref is unsupported by project-record.v1",
                )
            elif isinstance(assertion_id, str) and assertion_id:
                limitation_assertion_paths.append((index, assertion_ref, assertion_id))
        elif assertion_id is not None:
            errors.append(f"limitations[{index}] assertion_id requires assertion_ref")
    for limitation_id in _duplicates(limitation_ids):
        errors.append(f"duplicate limitation id: {limitation_id}")

    routes = record.get("audience_routes", [])
    modes: list[str] = []
    route_paths: list[str] = []
    if not isinstance(routes, list):
        errors.append("audience_routes must be a list")
        routes = []
    for index, route in enumerate(routes):
        if not isinstance(route, Mapping):
            errors.append(f"audience_routes[{index}] must be a mapping")
            continue
        mode = route.get("mode")
        path = route.get("path")
        if not isinstance(mode, str) or mode not in AUDIENCE_MODES:
            errors.append(f"audience_routes[{index}] has invalid mode: {mode!r}")
        else:
            modes.append(mode)
        if not isinstance(path, str) or AUDIENCE_ROUTE_PATH.fullmatch(path) is None:
            errors.append(
                f"audience_routes[{index}] path must match "
                "docs/audiences/<slug>.md",
            )
        else:
            route_paths.append(path)

    for mode in _duplicates(modes):
        errors.append(f"duplicate audience mode: {mode}")
    for path in _duplicates(route_paths):
        errors.append(f"duplicate audience route path: {path}")
    if "evaluator" in modes and "authorship" not in claim_scopes:
        errors.append("evaluator audience route requires an 'authorship' claim reference")
    if isinstance(doc_class, str) and doc_class in CLASS_ROUTE_RULES:
        required_modes, minimum, maximum = CLASS_ROUTE_RULES[doc_class]
        missing_modes = sorted(required_modes - set(modes))
        if missing_modes:
            errors.append(
                f"class {doc_class} is missing audience modes: {', '.join(missing_modes)}",
            )
        if len(modes) < minimum:
            errors.append(f"class {doc_class} requires at least {minimum} audience route(s)")
        if maximum is not None and len(modes) > maximum:
            errors.append(f"class {doc_class} allows at most {maximum} audience route(s)")

    industry_names: list[str] = []
    industry_paths: list[tuple[int, str]] = []
    industries = record.get("industries", [])
    if not isinstance(industries, list):
        errors.append("industries must be a list")
        industries = []
    for index, industry in enumerate(industries):
        if not isinstance(industry, Mapping):
            errors.append(f"industries[{index}] must be a mapping")
            continue
        name = industry.get("name")
        if isinstance(name, str) and name:
            industry_names.append(name.casefold())
        path = industry.get("path")
        if isinstance(path, str) and path:
            industry_paths.append((index, path))
        status = industry.get("status")
        if not isinstance(status, str) or status not in INDUSTRY_STATUSES:
            errors.append(f"industries[{index}] has invalid status: {status!r}")
        refs = industry.get("claim_references", [])
        if isinstance(status, str) and status in {"deployed", "piloted"} and not refs:
            errors.append(f"industries[{index}] status {status!r} requires claim_references")
        if not isinstance(refs, list):
            errors.append(f"industries[{index}].claim_references must be a list")
            refs = []
        for claim_id in refs:
            if not isinstance(claim_id, str) or claim_id not in claim_id_set:
                errors.append(f"industries[{index}] references unknown claim id: {claim_id}")
    for industry_name in _duplicates(industry_names):
        errors.append(f"duplicate industry name: {industry_name}")

    search_intent_names: list[str] = []
    search_intents = record.get("search_intents", [])
    if not isinstance(search_intents, list):
        errors.append("search_intents must be a list")
        search_intents = []
    for index, search_intent in enumerate(search_intents):
        if not isinstance(search_intent, Mapping):
            errors.append(f"search_intents[{index}] must be a mapping")
            continue
        intent = search_intent.get("intent")
        if isinstance(intent, str) and intent:
            search_intent_names.append(intent)
    for intent in _duplicates(search_intent_names):
        errors.append(f"duplicate search intent: {intent}")

    pinned_head: str | None = None
    if root is not None:
        root_path = Path(root).resolve()
        if require_git_tracked_evidence:
            pinned_head, head_errors = _resolve_validation_head(root_path)
            errors.extend(head_errors)
        evidence_digest_cache: dict[str, tuple[str | None, str | None]] = {}
        evidence_identity_cache: dict[tuple[Path, str], str | None] = {}
        for relative in route_paths:
            _validate_local_file(root_path, relative, "audience path", errors)

        for index, reference in industry_paths:
            _validate_local_file(
                root_path,
                reference,
                f"industries[{index}] path",
                errors,
            )

        for key, reference in local_link_paths:
            _validate_local_file(root_path, reference, f"links.{key}", errors)

        resolved_claim_assertions: dict[str, Mapping[str, Any]] = {}
        for index, reference, assertion_id, claim_id in claim_assertion_paths:
            assertion, assertion_errors = _validate_assertion_target(
                root=root_path,
                reference=reference,
                assertion_id=assertion_id,
                label=f"claim_references[{index}]",
                assertion_schema=assertion_schema,
                now=validation_now,
                require_git_tracked_evidence=require_git_tracked_evidence,
                pinned_head=pinned_head,
                evidence_digest_cache=evidence_digest_cache,
                evidence_identity_cache=evidence_identity_cache,
            )
            errors.extend(assertion_errors)
            if assertion is not None:
                resolved_claim_assertions[claim_id] = assertion

        for index, reference, assertion_id in limitation_assertion_paths:
            _assertion, assertion_errors = _validate_assertion_target(
                root=root_path,
                reference=reference,
                assertion_id=assertion_id,
                label=f"limitations[{index}]",
                assertion_schema=assertion_schema,
                now=validation_now,
                require_git_tracked_evidence=require_git_tracked_evidence,
                pinned_head=pinned_head,
                evidence_digest_cache=evidence_digest_cache,
                evidence_identity_cache=evidence_identity_cache,
            )
            errors.extend(assertion_errors)

        if not any(
            _verified_status_fact_matches(
                resolved_claim_assertions.get(claim_id),
                "implementation_status",
                implementation_status,
                record.get("canonical_repository"),
            )
            for claim_id in qualifying_status_claim_ids
        ):
            errors.append(
                "implementation_status requires a verified implementation_status fact "
                "whose subject is canonical_repository and whose value matches implementation_status",
            )

        if (
            allowed_deployment_postures is not None
            and qualifying_deployment_claim_ids
            and isinstance(deployment_status, str)
        ):
            verified_deployment_claims = [
                claim_id
                for claim_id in qualifying_deployment_claim_ids
                if _verified_deployment_fact_matches(
                    resolved_claim_assertions.get(claim_id),
                    deployment_status,
                    canonical_repository=record.get("canonical_repository"),
                    now=validation_now,
                )
            ]
            if not verified_deployment_claims:
                errors.append(
                    f"deployment_status {deployment_status!r} requires at least one "
                    "qualifying deployment claim that resolves to a verified assertion "
                    "whose fact predicate/value exactly matches deployment_status; "
                    "pilot/public additionally require a fresh current_state fact "
                    "whose subject is canonical_repository",
                )

        errors.extend(
            _industry_evidence_errors(
                industries,
                claims_by_id=claims_by_id,
                resolved_assertions=resolved_claim_assertions,
                canonical_repository=record.get("canonical_repository"),
                now=validation_now,
            ),
        )

    if schema is not None:
        errors.extend(
            _schema_errors(_normalize_yaml_datetimes(dict(record)), schema, prefix="schema"),
        )
    if root is not None and require_git_tracked_evidence and pinned_head is not None:
        errors.extend(_validation_head_drift_errors(root_path, pinned_head))
    return sorted(set(errors))


def _validate_assertion_target(
    *,
    root: Path,
    reference: str,
    assertion_id: str,
    label: str,
    assertion_schema: Mapping[str, Any] | None,
    now: datetime,
    require_git_tracked_evidence: bool,
    pinned_head: str | None,
    evidence_digest_cache: dict[str, tuple[str | None, str | None]],
    evidence_identity_cache: dict[tuple[Path, str], str | None],
) -> tuple[Mapping[str, Any] | None, list[str]]:
    errors: list[str] = []
    if _references_git_metadata(reference):
        return None, [f"{label} assertion path under .git is forbidden: {reference}"]
    if _path_contains_symlink(root, reference):
        return None, [f"{label} symlink assertion is forbidden: {reference}"]
    candidate = _contained_path(root, reference)
    if candidate is None:
        return None, [f"{label} assertion path escapes repository root: {reference}"]
    if not candidate.is_file():
        return None, [f"{label} assertion path does not exist: {reference}"]
    assertion_binding_errors: list[str] = []
    if require_git_tracked_evidence:
        assertion_binding_errors = _git_tracked_path_errors(
            root=root,
            relative=reference,
            label=label,
            object_name="assertion",
            pinned_head=pinned_head,
        )
        errors.extend(assertion_binding_errors)
    try:
        assertion, assertion_payload = _load_mapping_with_payload(candidate)
    except (OSError, ValueError) as exc:
        return None, [f"{label} cannot load assertion: {exc}"]
    if require_git_tracked_evidence and not assertion_binding_errors:
        errors.extend(
            _git_head_payload_errors(
                root=root,
                relative=reference,
                payload=assertion_payload,
                label=label,
                object_name="assertion",
                pinned_head=pinned_head,
            ),
        )

    assertion_contract_matches = assertion.get("contract_name") == "assertion-evidence.v1"
    if not assertion_contract_matches:
        errors.append(f"{label} target is not assertion-evidence.v1: {reference}")
    assertion_contract_version = assertion.get("contract_version")
    if (
        not isinstance(assertion_contract_version, int)
        or isinstance(assertion_contract_version, bool)
        or assertion_contract_version != CONTRACT_VERSION
    ):
        errors.append(
            f"{label} target has unsupported assertion contract_version: "
            f"{assertion_contract_version!r}; expected {CONTRACT_VERSION}",
        )
    if assertion.get("assertion_id") != assertion_id:
        errors.append(f"{label} assertion_id does not match {reference}")
    if assertion_contract_matches:
        errors.extend(
            f"assertion {reference}: semantic: {error}"
            for error in _assertion_semantic_errors(
                assertion,
                now=now,
                root=root,
                evidence_identity_cache=evidence_identity_cache,
            )
        )
        errors.extend(
            _assertion_evidence_binding_errors(
                assertion,
                root=root,
                reference=reference,
                require_git_tracked_evidence=require_git_tracked_evidence,
                pinned_head=pinned_head,
                evidence_digest_cache=evidence_digest_cache,
                evidence_identity_cache=evidence_identity_cache,
            ),
        )
    if assertion_schema is not None:
        errors.extend(
            _schema_errors(
                assertion,
                assertion_schema,
                prefix=f"assertion {reference}",
            ),
        )
    return assertion, errors


def _industry_evidence_errors(
    industries: list[Any],
    *,
    claims_by_id: Mapping[str, Mapping[str, Any]],
    resolved_assertions: Mapping[str, Mapping[str, Any]],
    canonical_repository: Any,
    now: datetime,
) -> list[str]:
    errors: list[str] = []
    evidence_scopes = {"deployment", "adoption"}
    for index, industry in enumerate(industries):
        if not isinstance(industry, Mapping):
            continue
        status = industry.get("status")
        references = industry.get("claim_references", [])
        if not isinstance(references, list):
            continue
        matching_fact = False
        for claim_id in references:
            if not isinstance(claim_id, str) or claim_id not in claims_by_id:
                continue
            claim = claims_by_id[claim_id]
            assertion = resolved_assertions.get(claim_id)
            if isinstance(status, str) and status in {"deployed", "piloted"}:
                claim_scope = claim.get("scope")
                if not isinstance(claim_scope, str) or claim_scope not in evidence_scopes:
                    errors.append(
                        f"industries[{index}] {status!r} claim {claim_id!r} must use "
                        "deployment or adoption scope",
                    )
                if assertion is not None and assertion.get("verification_state") != "verified":
                    errors.append(
                        f"industries[{index}] {status!r} claim {claim_id!r} must resolve "
                        "to a verified assertion",
                    )
                if (
                    assertion is not None
                    and isinstance(claim_scope, str)
                    and claim_scope in evidence_scopes
                    and _verified_status_fact_matches(
                        assertion, "industry_status", status, industry.get("name"),
                    )
                    and _fresh_current_state(assertion, now)
                    and assertion["fact"].get("project_repository") == canonical_repository
                ):
                    matching_fact = True
            elif status == "proposed":
                if claim.get("claim_posture") != "proposed":
                    errors.append(
                        f"industries[{index}] proposed claim {claim_id!r} requires "
                        "claim_posture 'proposed'",
                    )
                if assertion is not None and (
                    assertion.get("assertion_class") != "inference"
                    or not isinstance(assertion.get("inference_label"), str)
                    or not assertion.get("inference_label")
                ):
                    errors.append(
                        f"industries[{index}] proposed claim {claim_id!r} must resolve "
                        "to a labeled inference",
                    )
        if isinstance(status, str) and status in {"deployed", "piloted"} and not matching_fact:
            errors.append(
                f"industries[{index}] {status!r} requires a fresh current_state industry_status "
                "fact whose subject is the industry name, whose value matches its status, "
                "and whose project_repository is canonical_repository",
            )
    return errors


def _duplicates(values: list[str]) -> list[str]:
    return sorted(value for value, count in Counter(values).items() if count > 1)


def _contained_path(root: Path, relative: str) -> Path | None:
    try:
        candidate = (root / relative).resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def _validate_local_file(root: Path, relative: str, label: str, errors: list[str]) -> None:
    candidate = _contained_path(root, relative)
    if candidate is None:
        errors.append(f"{label} escapes repository root: {relative}")
    elif not candidate.is_file():
        errors.append(f"{label} does not exist: {relative}")


def _valid_web_uri(value: str) -> bool:
    if any(character.isspace() for character in value):
        return False
    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme in {"http", "https"}
        and parsed.hostname is not None
        and (port is None or 1 <= port <= 65535)
        and parsed.username is None
        and parsed.password is None
    )


def _web_uri_has_credentials(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return parsed.username is not None or parsed.password is not None


def _has_http_authority(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _valid_repository_slug(value: str) -> bool:
    """Return whether a repository identifier is a non-traversal owner/name slug."""
    if REPOSITORY_SLUG.fullmatch(value) is None:
        return False
    return all(part not in {".", ".."} for part in value.split("/"))


def _github_repository_slug(value: str) -> str | None:
    """Extract owner/name from one canonical GitHub repository URL."""
    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or parsed.netloc != "github.com"
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2:
        return None
    owner, name = parts
    if name.endswith(".git"):
        name = name[:-4]
    slug = f"{owner}/{name}"
    if not _valid_repository_slug(slug):
        return None
    return slug


def _reference_is_remote_or_absolute(reference: str) -> bool:
    """Return whether an assertion reference cannot be resolved inside the root."""
    try:
        has_scheme = bool(urlparse(reference).scheme)
    except ValueError:
        return True
    return has_scheme or Path(reference).is_absolute()


def _references_git_metadata(reference: str) -> bool:
    """Return whether a relative path names Git metadata on any common filesystem."""
    return any(part.casefold() == ".git" for part in Path(reference).parts)


def _resolved_evidence_identity(root: Path, reference: Any) -> str | None:
    """Resolve an evidence reference to the local file or immutable Git object."""
    if not isinstance(reference, str) or not reference:
        return None
    git_match = GIT_EVIDENCE_REFERENCE.fullmatch(reference)
    if git_match is not None:
        commit = git_match.group("commit")
        path = git_match.group("path")
        if path is not None and (
            _reference_is_remote_or_absolute(path)
            or ".." in Path(path).parts
            or _references_git_metadata(path)
        ):
            return None
        revision = f"{commit}^{{commit}}" if path is None else f"{commit}:{path}"
        resolved = _run_git(root, "rev-parse", "--verify", revision)
        identity = resolved.stdout.strip().decode("ascii", errors="replace")
        if resolved.returncode != 0 or re.fullmatch(r"[a-f0-9]{40,64}", identity) is None:
            return None
        kind = "commit" if path is None else "object"
        return f"git-{kind}:{identity}"
    if _reference_is_remote_or_absolute(reference):
        return None
    if _references_git_metadata(reference) or _path_contains_symlink(root, reference):
        return None
    candidate = _contained_path(root, reference)
    if candidate is None or not candidate.is_file():
        return None
    try:
        file_status = candidate.stat()
    except OSError:
        return None
    if file_status.st_ino:
        return f"file:{file_status.st_dev}:{file_status.st_ino}"
    return f"file:{candidate}"


def _cached_evidence_identity(
    root: Path,
    reference: Any,
    evidence_identity_cache: dict[tuple[Path, str], str | None],
) -> str | None:
    """Resolve one evidence identity at most once in a validation run."""
    if not isinstance(reference, str):
        return None
    cache_key = (root, reference)
    if cache_key not in evidence_identity_cache:
        evidence_identity_cache[cache_key] = _resolved_evidence_identity(root, reference)
    return evidence_identity_cache[cache_key]


def _assertion_semantic_errors(
    assertion: Mapping[str, Any],
    *,
    now: datetime,
    root: Path,
    evidence_identity_cache: dict[tuple[Path, str], str | None],
) -> list[str]:
    """Validate assertion-evidence invariants that JSON Schema cannot express."""
    errors = _schema_errors(
        _normalize_yaml_datetimes(dict(assertion)),
        _builtin_schema("assertion-evidence.v1.schema.json"),
        prefix="assertion-evidence.v1",
    )
    assertion_class = assertion.get("assertion_class")
    if not isinstance(assertion_class, str) or assertion_class not in ASSERTION_CLASSES:
        errors.append(f"invalid assertion_class: {assertion_class!r}")
    verification_state = assertion.get("verification_state")
    if (
        not isinstance(verification_state, str)
        or verification_state not in VERIFICATION_STATES
    ):
        errors.append(f"invalid verification_state: {verification_state!r}")

    evidence = assertion.get("evidence_references")
    if not isinstance(evidence, list):
        if verification_state == "verified":
            errors.append("a verified assertion requires a non-empty evidence_references list")
        evidence = []
    if verification_state == "verified" and not evidence:
        errors.append("a verified assertion requires a non-empty evidence_references list")

    if verification_state == "verified":
        for index, item in enumerate(evidence):
            if not isinstance(item, Mapping):
                errors.append(f"evidence_references[{index}] must be a mapping")
                continue
            required_strings = ("evidence_id", "independence_group", "reference")
            for field in required_strings:
                value = item.get(field)
                if not isinstance(value, str) or not value.strip():
                    errors.append(
                        f"evidence_references[{index}].{field} must be a non-empty string",
                    )
            evidence_type = item.get("evidence_type")
            if (
                not isinstance(evidence_type, str)
                or evidence_type not in EVIDENCE_TYPES
            ):
                errors.append(
                    f"evidence_references[{index}].evidence_type must be one of: "
                    + ", ".join(sorted(EVIDENCE_TYPES)),
                )
            body_hash = item.get("body_hash")
            if (
                not isinstance(body_hash, str)
                or re.fullmatch(r"sha256:[a-f0-9]{64}", body_hash) is None
            ):
                errors.append(
                    f"evidence_references[{index}].body_hash must use "
                    "sha256:<64-lowercase-hex>",
                )

    evidence_ids = [
        item.get("evidence_id") for item in evidence if isinstance(item, Mapping)
    ]
    duplicate_evidence_ids = _duplicates(
        [value for value in evidence_ids if isinstance(value, str)],
    )
    if duplicate_evidence_ids:
        errors.append(
            "evidence_references contain duplicate evidence_id values: "
            f"{duplicate_evidence_ids}",
        )

    freshness = assertion.get("freshness")
    if isinstance(freshness, Mapping):
        freshness_status = freshness.get("status")
        if (
            not isinstance(freshness_status, str)
            or freshness_status not in FRESHNESS_STATUSES
        ):
            errors.append(f"freshness.status is invalid: {freshness_status!r}")
        raw_max_age_seconds = freshness.get("max_age_seconds")
        max_age_seconds = (
            raw_max_age_seconds
            if isinstance(raw_max_age_seconds, int)
            and not isinstance(raw_max_age_seconds, bool)
            and 0 < raw_max_age_seconds <= MAX_FRESHNESS_AGE_SECONDS
            else None
        )
        if (
            isinstance(freshness_status, str)
            and freshness_status in {"fresh", "stale"}
            and max_age_seconds is None
        ):
            errors.append(
                "freshness.max_age_seconds must be an integer between 1 and "
                f"{MAX_FRESHNESS_AGE_SECONDS}",
            )
        elif raw_max_age_seconds is not None and max_age_seconds is None:
            errors.append(
                "freshness.max_age_seconds, when present, must be an integer between "
                f"1 and {MAX_FRESHNESS_AGE_SECONDS}",
            )
        verified_at = freshness.get("verified_at")
        parsed_verified_at = (
            _parse_datetime(verified_at) if isinstance(verified_at, str) else None
        )
        if parsed_verified_at is None:
            errors.append(
                "freshness.verified_at must be an ISO 8601 date-time with a timezone",
            )
        else:
            normalized_now = now.astimezone(timezone.utc)
            if parsed_verified_at > normalized_now:
                errors.append("freshness.verified_at cannot be in the future")
            if (
                freshness_status == "fresh"
                and max_age_seconds is not None
                and (normalized_now - parsed_verified_at).total_seconds()
                > max_age_seconds
            ):
                errors.append(
                    "freshness.status 'fresh' is expired at validation time",
                )

    if verification_state != "verified":
        return errors

    evidence_bindings = [
        (
            item.get("independence_group"),
            item.get("evidence_type"),
            _cached_evidence_identity(
                root,
                item.get("reference"),
                evidence_identity_cache,
            ),
        )
        for item in evidence
        if isinstance(item, Mapping)
        and isinstance(item.get("independence_group"), str)
        and item.get("independence_group")
        and isinstance(item.get("evidence_type"), str)
        and isinstance(item.get("reference"), str)
    ]
    has_independent_objects = any(
        first_group != second_group and first_identity != second_identity
        for first_index, (first_group, _first_type, first_identity) in enumerate(
            evidence_bindings,
        )
        if first_identity is not None
        for second_group, _second_type, second_identity in evidence_bindings[
            first_index + 1 :
        ]
        if second_identity is not None
    )
    evidence_types = {
        item.get("evidence_type")
        for item in evidence
        if isinstance(item, Mapping) and isinstance(item.get("evidence_type"), str)
    }
    if assertion_class == "external_fact" and not has_independent_objects:
        errors.append(
            "a verified external_fact requires at least two independent evidence groups "
            "backed by distinct resolved evidence objects",
        )
    if assertion_class == "operator_directive":
        if not has_independent_objects:
            errors.append(
                "a verified operator_directive requires at least two independent evidence "
                "groups backed by distinct resolved evidence objects",
            )
        required = {"immutable_source_event", "ratified_constitutional_record"}
        missing = sorted(required - evidence_types)
        if missing:
            errors.append(
                "a verified operator_directive is missing evidence types: "
                + ", ".join(missing),
            )
        elif not any(
            first_identity != second_identity
            for first_group, first_type, first_identity in evidence_bindings
            if first_type == "immutable_source_event" and first_identity is not None
            for second_group, second_type, second_identity in evidence_bindings
            if second_type == "ratified_constitutional_record"
            and second_identity is not None
        ):
            errors.append(
                "a verified operator_directive requires its immutable source event and "
                "ratified constitutional record to resolve to distinct evidence objects",
            )
        freshness_status = freshness.get("status") if isinstance(freshness, Mapping) else None
        if (
            not isinstance(freshness_status, str)
            or freshness_status not in {"fresh", "not_applicable"}
        ):
            errors.append(
                "a verified operator_directive requires non-stale freshness",
            )
    if assertion_class == "current_state":
        required = {"owner_record", "fresh_verifier_receipt"}
        missing = sorted(required - evidence_types)
        if missing:
            errors.append(
                "a verified current_state is missing evidence types: "
                + ", ".join(missing),
            )
        if not isinstance(freshness, Mapping) or freshness.get("status") != "fresh":
            errors.append("a verified current_state requires freshness.status 'fresh'")
        else:
            current_state_max_age = freshness.get("max_age_seconds")
            if (
                not isinstance(current_state_max_age, int)
                or isinstance(current_state_max_age, bool)
                or current_state_max_age <= 0
            ):
                errors.append(
                    "a verified current_state with freshness.status 'fresh' requires "
                    "max_age_seconds to be a positive integer",
                )
            elif current_state_max_age > MAX_FRESHNESS_AGE_SECONDS:
                errors.append(
                    "a verified current_state freshness.max_age_seconds must not exceed "
                    f"{MAX_FRESHNESS_AGE_SECONDS}",
                )

    return errors


def _verified_deployment_fact_matches(
    assertion: Mapping[str, Any] | None,
    deployment_status: str,
    *,
    canonical_repository: Any,
    now: datetime,
) -> bool:
    """Return whether verified evidence asserts this exact deployment state."""
    if assertion is None or assertion.get("verification_state") != "verified":
        return False
    if deployment_status in {"pilot", "public"}:
        return _fresh_current_state(assertion, now) and _verified_status_fact_matches(
            assertion, "deployment_status", deployment_status, canonical_repository,
        )
    fact = assertion.get("fact")
    return (
        isinstance(fact, Mapping)
        and fact.get("predicate") == "deployment_status"
        and fact.get("value") == deployment_status
    )


def _verified_status_fact_matches(
    assertion: Mapping[str, Any] | None,
    predicate: str,
    value: Any,
    subject: Any,
) -> bool:
    if assertion is None or assertion.get("verification_state") != "verified":
        return False
    fact = assertion.get("fact")
    return (
        isinstance(fact, Mapping)
        and isinstance(subject, str)
        and bool(subject)
        and fact.get("predicate") == predicate
        and fact.get("subject") == subject
        and fact.get("value") == value
    )


def _fresh_current_state(assertion: Mapping[str, Any] | None, now: datetime) -> bool:
    if assertion is None or assertion.get("assertion_class") != "current_state":
        return False
    freshness = assertion.get("freshness")
    if not isinstance(freshness, Mapping) or freshness.get("status") != "fresh":
        return False
    maximum_age = freshness.get("max_age_seconds")
    verified_at = _parse_datetime(freshness.get("verified_at"))
    return (
        isinstance(maximum_age, int)
        and not isinstance(maximum_age, bool)
        and 0 < maximum_age <= MAX_FRESHNESS_AGE_SECONDS
        and verified_at is not None
        and 0 <= (now.astimezone(timezone.utc) - verified_at).total_seconds() <= maximum_age
    )


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return None
    try:
        return parsed.astimezone(timezone.utc)
    except (OverflowError, ValueError):
        return None


def _assertion_evidence_binding_errors(
    assertion: Mapping[str, Any],
    *,
    root: Path,
    reference: str,
    require_git_tracked_evidence: bool,
    pinned_head: str | None,
    evidence_digest_cache: dict[str, tuple[str | None, str | None]],
    evidence_identity_cache: dict[tuple[Path, str], str | None],
) -> list[str]:
    """Bind evidence to local bytes or deterministic local Git objects."""
    errors: list[str] = []
    evidence = assertion.get("evidence_references")
    if not isinstance(evidence, list):
        return errors

    for index, item in enumerate(evidence):
        if not isinstance(item, Mapping):
            continue
        evidence_reference = item.get("reference")
        if not isinstance(evidence_reference, str) or not evidence_reference:
            continue
        label = f"assertion {reference}: evidence_references[{index}]"
        body_hash = item.get("body_hash")
        if not isinstance(body_hash, str) or not body_hash.startswith("sha256:"):
            errors.append(f"{label} body_hash must use sha256:<hex>")
            continue
        if evidence_reference.startswith("git:"):
            errors.extend(
                _git_evidence_binding_errors(
                    root=root,
                    evidence_reference=evidence_reference,
                    body_hash=body_hash,
                    label=label,
                    evidence_digest_cache=evidence_digest_cache,
                    evidence_identity_cache=evidence_identity_cache,
                ),
            )
            continue
        if _reference_is_remote_or_absolute(evidence_reference):
            errors.append(
                f"{label} remote or opaque reference cannot be content-verified by "
                "project-record.v1; cite a committed local snapshot or receipt: "
                f"{evidence_reference}",
            )
            continue
        if _references_git_metadata(evidence_reference):
            errors.append(f"{label} reference under .git is forbidden: {evidence_reference}")
            continue
        if _path_contains_symlink(root, evidence_reference):
            errors.append(f"{label} symlink evidence is forbidden: {evidence_reference}")
            continue

        candidate = _contained_path(root, evidence_reference)
        if candidate is None:
            errors.append(
                f"{label} reference escapes repository root: {evidence_reference}",
            )
            continue
        if not candidate.is_file():
            errors.append(
                f"{label} reference does not exist: {evidence_reference}",
            )
            continue
        evidence_binding_errors: list[str] = []
        if require_git_tracked_evidence:
            evidence_binding_errors = _git_tracked_path_errors(
                root=root,
                relative=evidence_reference,
                label=label,
                pinned_head=pinned_head,
            )
            errors.extend(evidence_binding_errors)
        initial_identity = _cached_evidence_identity(
            root,
            evidence_reference,
            evidence_identity_cache,
        )
        cache_key = initial_identity or f"file-path:{candidate}"
        cached_digest = evidence_digest_cache.get(cache_key)
        if cached_digest is None:
            try:
                local_digest = "sha256:" + _stream_sha256(candidate)
                final_identity = _resolved_evidence_identity(root, evidence_reference)
                if initial_identity is None or final_identity != initial_identity:
                    raise StableReadError(
                        f"evidence identity changed while hashing: {evidence_reference}",
                    )
                cached_digest = (local_digest, None)
            except (OSError, StableReadError) as exc:
                cached_digest = (None, str(exc))
            evidence_digest_cache[cache_key] = cached_digest
        actual, read_error = cached_digest
        if read_error is not None:
            errors.append(
                f"{label} cannot read evidence bytes for {evidence_reference}: "
                f"{read_error}",
            )
            continue
        if actual is None:
            errors.append(
                f"{label} cannot read evidence bytes for {evidence_reference}",
            )
            continue
        if body_hash != actual:
            errors.append(
                f"{label} body_hash does not match raw bytes for {evidence_reference}: "
                f"expected {actual}, found {body_hash}",
            )
        if require_git_tracked_evidence and not evidence_binding_errors:
            errors.extend(
                _git_head_digest_errors(
                    root=root,
                    relative=evidence_reference,
                    digest=actual,
                    label=label,
                    object_name="evidence",
                    pinned_head=pinned_head,
                ),
            )
    return errors


def _git_evidence_binding_errors(
    *,
    root: Path,
    evidence_reference: str,
    body_hash: str,
    label: str,
    evidence_digest_cache: dict[str, tuple[str | None, str | None]],
    evidence_identity_cache: dict[tuple[Path, str], str | None],
) -> list[str]:
    def result_errors(
        cached: tuple[str | None, str | None],
    ) -> list[str]:
        actual, resolution_error = cached
        if resolution_error is not None:
            return [f"{label} {resolution_error}"]
        if actual is None:
            return [f"{label} cannot resolve git evidence: {evidence_reference}"]
        if body_hash != actual:
            return [
                f"{label} body_hash does not match Git object bytes for "
                f"{evidence_reference}: expected {actual}, found {body_hash}",
            ]
        return []

    reference_cache_key = f"git-reference:{evidence_reference}"
    cached_digest = evidence_digest_cache.get(reference_cache_key)
    if cached_digest is not None:
        return result_errors(cached_digest)

    match = GIT_EVIDENCE_REFERENCE.fullmatch(evidence_reference)
    if match is None:
        resolution_error = (
            "git evidence must use git:<full-40-sha> or "
            "git:<full-40-sha>:<contained-path>"
        )
        cached_digest = (None, resolution_error)
        evidence_digest_cache[reference_cache_key] = cached_digest
        return result_errors(cached_digest)
    commit = match.group("commit")
    path = match.group("path")
    if path is not None and (
        _reference_is_remote_or_absolute(path)
        or ".." in Path(path).parts
        or _references_git_metadata(path)
    ):
        cached_digest = (None, f"git evidence path is not contained: {path}")
        evidence_digest_cache[reference_cache_key] = cached_digest
        return result_errors(cached_digest)

    commit_check = _run_git(root, "cat-file", "-e", f"{commit}^{{commit}}")
    if commit_check.returncode != 0:
        cached_digest = (
            None,
            f"git commit is unavailable locally (possibly shallow): {commit}",
        )
        evidence_digest_cache[reference_cache_key] = cached_digest
        return result_errors(cached_digest)
    if path is not None:
        tree_entry = _run_git(root, "ls-tree", commit, "--", path)
        if tree_entry.returncode != 0 or not tree_entry.stdout:
            cached_digest = (
                None,
                f"git evidence path does not exist at {commit}: {path}",
            )
            evidence_digest_cache[reference_cache_key] = cached_digest
            return result_errors(cached_digest)
        mode = tree_entry.stdout.split(None, 1)[0].decode("ascii", errors="replace")
        if mode not in {"100644", "100755"}:
            cached_digest = (
                None,
                f"git evidence path must be a regular blob, not mode {mode}: {path}",
            )
            evidence_digest_cache[reference_cache_key] = cached_digest
            return result_errors(cached_digest)
    object_type = "commit" if path is None else "blob"
    object_name = commit if path is None else f"{commit}:{path}"
    object_cache_key = _cached_evidence_identity(
        root,
        evidence_reference,
        evidence_identity_cache,
    )
    cached_digest = (
        evidence_digest_cache.get(object_cache_key)
        if object_cache_key is not None
        else None
    )
    if cached_digest is None:
        try:
            digest, returncode = _stream_git_object_sha256(root, object_type, object_name)
        except StableReadError as exc:
            cached_digest = (None, str(exc))
        else:
            if returncode != 0 or digest is None:
                cached_digest = (
                    None,
                    f"cannot resolve git evidence: {evidence_reference}",
                )
            else:
                cached_digest = ("sha256:" + digest, None)
        if object_cache_key is not None:
            evidence_digest_cache[object_cache_key] = cached_digest
    evidence_digest_cache[reference_cache_key] = cached_digest
    return result_errors(cached_digest)


def _stream_sha256(path: Path) -> str:
    """Hash one bounded, stable regular file through no-follow path binding."""
    payload = read_stable_regular_bytes(path, maximum_bytes=MAX_EVIDENCE_BYTES)
    return hashlib.sha256(payload).hexdigest()


def _stream_git_object_sha256(
    root: Path,
    object_type: str,
    object_name: str,
) -> tuple[str | None, int]:
    """Hash a Git object with the same bound and a finite subprocess deadline."""
    process = subprocess.Popen(
        ["git", "-C", str(root), "cat-file", object_type, object_name],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if process.stdout is None:
        process.kill()
        process.wait()
        return None, process.returncode
    digest = hashlib.sha256()
    total = 0
    deadline = time.monotonic() + GIT_EVIDENCE_TIMEOUT_SECONDS
    selector = selectors.DefaultSelector()
    try:
        os_fd = process.stdout.fileno()
        os.set_blocking(os_fd, False)
        selector.register(os_fd, selectors.EVENT_READ)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise StableReadError(
                    f"Git evidence read exceeded {GIT_EVIDENCE_TIMEOUT_SECONDS:g}s timeout",
                )
            if not selector.select(remaining):
                raise StableReadError(
                    f"Git evidence read exceeded {GIT_EVIDENCE_TIMEOUT_SECONDS:g}s timeout",
                )
            try:
                chunk = os.read(os_fd, 1024 * 1024)
            except BlockingIOError:
                continue
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_EVIDENCE_BYTES:
                raise StableReadError(
                    f"Git evidence exceeds {MAX_EVIDENCE_BYTES} byte limit",
                )
            digest.update(chunk)
        remaining = max(0.0, deadline - time.monotonic())
        try:
            returncode = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired as exc:
            raise StableReadError(
                f"Git evidence read exceeded {GIT_EVIDENCE_TIMEOUT_SECONDS:g}s timeout",
            ) from exc
        return (digest.hexdigest() if returncode == 0 else None), returncode
    except Exception:
        if process.poll() is None:
            process.kill()
        process.wait()
        raise
    finally:
        selector.close()
        process.stdout.close()


def _git_head_payload_errors(
    *,
    root: Path,
    relative: str,
    payload: bytes,
    label: str,
    object_name: str,
    pinned_head: str | None,
) -> list[str]:
    """Require captured working-tree bytes to equal one exact HEAD blob."""
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    return _git_head_digest_errors(
        root=root,
        relative=relative,
        digest=digest,
        label=label,
        object_name=object_name,
        pinned_head=pinned_head,
    )


def _git_head_digest_errors(
    *,
    root: Path,
    relative: str,
    digest: str,
    label: str,
    object_name: str,
    pinned_head: str | None,
) -> list[str]:
    """Compare captured bytes with the blob from the validation-wide HEAD."""
    if pinned_head is None:
        return [f"{label} cannot resolve HEAD for committed {object_name}: {relative}"]
    try:
        head_digest, returncode = _stream_git_object_sha256(
            root,
            "blob",
            f"{pinned_head}:{relative}",
        )
    except StableReadError as exc:
        return [f"{label} cannot read committed {object_name} bytes: {exc}"]
    expected = f"sha256:{head_digest}" if head_digest is not None else None
    if returncode != 0 or expected is None:
        return [f"{label} cannot resolve committed {object_name} path: {relative}"]
    if digest != expected:
        return [
            f"{label} {object_name} bytes do not match HEAD {pinned_head}: {relative}",
        ]
    return []


def _git_tracked_path_errors(
    *,
    root: Path,
    relative: str,
    label: str,
    object_name: str = "evidence",
    pinned_head: str | None = None,
) -> list[str]:
    inside = _run_git(root, "rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0 or inside.stdout.strip() != b"true":
        return [f"{label} commit-bound validation requires a Git work tree"]
    staged = _run_git(root, "ls-files", "--stage")
    for line in staged.stdout.splitlines():
        fields = line.split(None, 3)
        if len(fields) != 4 or fields[0] != b"160000":
            continue
        submodule_path = fields[3].decode("utf-8", errors="replace")
        if relative == submodule_path or relative.startswith(submodule_path + "/"):
            return [
                f"{label} {object_name} inside a submodule is forbidden: {relative}",
            ]

    literal_pathspec = f":(literal){relative}"
    tracked = _run_git(root, "ls-files", "--error-unmatch", "--", literal_pathspec)
    if tracked.returncode != 0:
        return [f"{label} {object_name} is ignored or untracked: {relative}"]

    index_state = _run_git(root, "ls-files", "-v", "-z", "--", literal_pathspec)
    if index_state.returncode != 0 or not index_state.stdout:
        return [f"{label} cannot inspect committed {object_name} path: {relative}"]
    tag = index_state.stdout[:1]
    index_errors: list[str] = []
    if tag.islower():
        index_errors.append(
            f"{label} {object_name} is marked assume-unchanged: {relative}",
        )
    if tag.upper() == b"S":
        index_errors.append(
            f"{label} {object_name} is marked skip-worktree: {relative}",
        )
    if index_errors:
        return index_errors

    if pinned_head is None:
        return [f"{label} cannot resolve HEAD for committed {object_name}: {relative}"]

    for args in (
        ("diff", "--quiet", pinned_head, "--", literal_pathspec),
        ("diff", "--cached", "--quiet", pinned_head, "--", literal_pathspec),
    ):
        result = _run_git(root, *args)
        if result.returncode == 1:
            return [
                f"{label} {object_name} differs from the checked-out commit: {relative}",
            ]
        if result.returncode > 1:
            return [
                f"{label} cannot verify committed {object_name} path: {relative}",
            ]
    return []


def _resolve_validation_head(root: Path) -> tuple[str | None, list[str]]:
    """Resolve the single commit used by every commit-bound comparison."""
    resolved = _run_git(root, "rev-parse", "--verify", "HEAD^{commit}")
    head = resolved.stdout.strip().decode("ascii", errors="replace")
    if resolved.returncode != 0 or re.fullmatch(r"[a-f0-9]{40,64}", head) is None:
        return None, ["commit-bound validation cannot resolve HEAD"]
    return head, []


def _validation_head_drift_errors(root: Path, pinned_head: str) -> list[str]:
    """Reject a run if HEAD moved after the validation snapshot was pinned."""
    resolved = _run_git(root, "rev-parse", "--verify", "HEAD^{commit}")
    current = resolved.stdout.strip().decode("ascii", errors="replace")
    if resolved.returncode != 0 or current != pinned_head:
        return [
            "commit-bound validation HEAD changed during validation: "
            f"expected {pinned_head}, found {current or '<unresolved>'}",
        ]
    return []


def _path_contains_symlink(root: Path, relative: str) -> bool:
    candidate = root
    for part in Path(relative).parts:
        candidate /= part
        if candidate.is_symlink():
            return True
    return False


def _run_git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _load_mapping(path: Path) -> dict[str, Any]:
    data = _load_structured_data(path)
    if not isinstance(data, dict):
        raise ValueError(f"not a mapping: {path}")
    return _normalize_structured_data(data, path)


def _load_mapping_with_payload(path: Path) -> tuple[dict[str, Any], bytes]:
    """Load one mapping while retaining the exact stable bytes that were parsed."""
    payload = _read_bounded_record_bytes(path)
    data = _parse_structured_payload(payload, path)
    if not isinstance(data, dict):
        raise ValueError(f"not a mapping: {path}")
    return _normalize_structured_data(data, path), payload


def _load_structured_data(path: Path) -> Any:
    """Load bounded JSON/YAML while rejecting duplicate mapping keys."""
    payload = _read_bounded_record_bytes(path)
    return _parse_structured_payload(payload, path)


def _parse_structured_payload(payload: bytes, path: Path) -> Any:
    """Parse exact bounded structured bytes without reopening their pathname."""
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"structured record is not valid UTF-8: {path}") from exc
    if path.suffix.lower() == ".json":
        try:
            return json.loads(text, object_pairs_hook=_unique_json_mapping)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
        except RecursionError as exc:
            raise ValueError(f"JSON nesting exceeds supported depth: {path}") from exc
    try:
        return yaml.load(text, Loader=_UniqueKeySafeLoader)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in {path}: {exc}") from exc
    except RecursionError as exc:
        raise ValueError(f"YAML nesting exceeds supported depth: {path}") from exc


def _unique_json_mapping(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Build one JSON object while rejecting repeated member names."""
    mapping: dict[str, Any] = {}
    for key, value in pairs:
        if key in mapping:
            raise ValueError(f"duplicate mapping key: {key!r}")
        mapping[key] = value
    return mapping


def _normalize_structured_data(data: dict[str, Any], path: Path) -> dict[str, Any]:
    """Normalize one parsed record while converting depth failure to validation."""
    try:
        return _normalize_yaml_datetimes(data)
    except RecursionError as exc:
        format_name = "JSON" if path.suffix.lower() == ".json" else "YAML"
        raise ValueError(
            f"{format_name} nesting exceeds supported depth: {path}",
        ) from exc


def _read_bounded_record_bytes(path: Path) -> bytes:
    """Read one stable, bounded structured record without following replacements."""
    try:
        payload = read_stable_regular_bytes(
            path,
            maximum_bytes=MAX_STRUCTURED_RECORD_BYTES,
        )
    except StableReadError as exc:
        if "exceeds size limit" in str(exc):
            raise ValueError(
                f"structured record exceeds {MAX_STRUCTURED_RECORD_BYTES} bytes: {path}",
            ) from exc
        raise OSError(str(exc)) from exc
    return payload


def _normalize_yaml_datetimes(
    value: Any,
    *,
    _active_container_ids: set[int] | None = None,
    _memoized_containers: dict[int, Any] | None = None,
) -> Any:
    """Normalize timestamps while preserving acyclic aliases and rejecting cycles."""
    if isinstance(value, datetime):
        rendered = value.isoformat()
        return rendered.replace("+00:00", "Z")
    if isinstance(value, (dict, list)):
        active = _active_container_ids if _active_container_ids is not None else set()
        memo = _memoized_containers if _memoized_containers is not None else {}
        identity = id(value)
        if identity in active:
            raise ValueError("recursive YAML aliases are unsupported")
        if identity in memo:
            return memo[identity]
        active.add(identity)
        try:
            if isinstance(value, dict):
                normalized_mapping: dict[Any, Any] = {}
                memo[identity] = normalized_mapping
                for key, item in value.items():
                    normalized_mapping[key] = _normalize_yaml_datetimes(
                        item,
                        _active_container_ids=active,
                        _memoized_containers=memo,
                    )
                return normalized_mapping
            normalized_list: list[Any] = []
            memo[identity] = normalized_list
            normalized_list.extend(
                _normalize_yaml_datetimes(
                    item,
                    _active_container_ids=active,
                    _memoized_containers=memo,
                )
                for item in value
            )
            return normalized_list
        finally:
            active.remove(identity)
    return value


def _schema_errors(data: dict, schema: Mapping[str, Any], *, prefix: str) -> list[str]:
    from jsonschema import Draft202012Validator, FormatChecker

    try:
        Draft202012Validator.check_schema(schema)
        found = sorted(
            Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(data),
            key=lambda error: list(error.absolute_path),
        )
    except Exception as exc:  # pragma: no cover - jsonschema supplies detail
        return [f"invalid validation schema: {exc}"]
    messages: list[str] = []
    for error in found:
        location = "/".join(str(part) for part in error.absolute_path) or "<root>"
        messages.append(f"{prefix} {location}: {error.message}")
    return messages
