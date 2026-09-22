"""Validate registry-v2.json against schema and governance rules."""

import hashlib
import json
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from organvm_engine._stable_io import StableReadError, read_stable_regular_bytes
from organvm_engine.registry.query import all_repos, find_repo

# Fallback enum values — used when schema-definitions is unavailable
_FALLBACK_STATUSES = {"ACTIVE", "PROTOTYPE", "SKELETON", "DESIGN_ONLY", "ARCHIVED"}
_FALLBACK_REVENUE_MODELS = {
    "subscription",
    "freemium",
    "one-time",
    "advertising",
    "marketplace",
    "internal",
    "none",
}
_FALLBACK_REVENUE_STATUSES = {"pre-launch", "beta", "live", "deprecated", "n/a"}
_FALLBACK_PROMOTION_STATES = {"LOCAL", "CANDIDATE", "PUBLIC_PROCESS", "GRADUATED", "ARCHIVED"}
_FALLBACK_TIERS = {"flagship", "standard", "stub", "archive", "infrastructure", "sovereign"}


@dataclass(frozen=True)
class RegistryValidationPolicy:
    """Immutable enum policy and portable provenance used for one validation."""

    statuses: frozenset[str]
    revenue_models: frozenset[str]
    revenue_statuses: frozenset[str]
    promotion_states: frozenset[str]
    tiers: frozenset[str]
    source_kind: str
    source_sha256: str

    def evidence(self) -> dict[str, str | list[str]]:
        """Return canonical, path-free receipt evidence for this policy."""
        return {
            "policy_version": "organvm.registry-validation-policy.v1",
            "source_kind": self.source_kind,
            "source_sha256": self.source_sha256,
            "statuses": sorted(self.statuses),
            "revenue_models": sorted(self.revenue_models),
            "revenue_statuses": sorted(self.revenue_statuses),
            "promotion_states": sorted(self.promotion_states),
            "tiers": sorted(self.tiers),
        }


def _schema_candidates() -> tuple[Path, ...]:
    """Return schema locations in precedence order."""
    return (
        Path(__file__).resolve().parents[4]
        / "schema-definitions"
        / "schemas"
        / "registry-v2.schema.json",
        Path.home()
        / "Workspace"
        / "meta-organvm"
        / "schema-definitions"
        / "schemas"
        / "registry-v2.schema.json",
    )


def _fallback_policy() -> RegistryValidationPolicy:
    enum_evidence = {
        "statuses": sorted(_FALLBACK_STATUSES),
        "revenue_models": sorted(_FALLBACK_REVENUE_MODELS),
        "revenue_statuses": sorted(_FALLBACK_REVENUE_STATUSES),
        "promotion_states": sorted(_FALLBACK_PROMOTION_STATES),
        "tiers": sorted(_FALLBACK_TIERS),
    }
    payload = json.dumps(
        enum_evidence,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return RegistryValidationPolicy(
        statuses=frozenset(_FALLBACK_STATUSES),
        revenue_models=frozenset(_FALLBACK_REVENUE_MODELS),
        revenue_statuses=frozenset(_FALLBACK_REVENUE_STATUSES),
        promotion_states=frozenset(_FALLBACK_PROMOTION_STATES),
        tiers=frozenset(_FALLBACK_TIERS),
        source_kind="embedded-fallback",
        source_sha256="sha256:" + hashlib.sha256(payload).hexdigest(),
    )


def capture_registry_validation_policy(
    schema_candidates: Iterable[Path] | None = None,
) -> RegistryValidationPolicy:
    """Load enum values from registry-v2 JSON schema.

    Searches for the schema file in known locations. Falls back to
    hardcoded values with a warning if the schema is unavailable. The
    returned policy is immutable so validation cannot silently switch to
    different module globals after capture.
    """
    candidates = (
        _schema_candidates() if schema_candidates is None else schema_candidates
    )
    for schema_path in candidates:
        if schema_path.is_file():
            try:
                schema_payload = read_stable_regular_bytes(schema_path)
                schema = json.loads(schema_payload)
                if not isinstance(schema, dict):
                    raise TypeError("registry schema root is not a mapping")
                definitions = schema.get("$defs")
                if not isinstance(definitions, dict):
                    raise TypeError("registry schema $defs is not a mapping")
                repository = definitions.get("repository")
                if not isinstance(repository, dict):
                    raise TypeError(
                        "registry schema repository definition is not a mapping",
                    )
                repo_props = repository.get("properties")
                if not isinstance(repo_props, dict):
                    raise TypeError(
                        "registry schema repository properties are not a mapping",
                    )
                fallback = _fallback_policy()
                return RegistryValidationPolicy(
                    statuses=_schema_enum(
                        repo_props,
                        "implementation_status",
                        fallback.statuses,
                    ),
                    revenue_models=_schema_enum(
                        repo_props,
                        "revenue_model",
                        fallback.revenue_models,
                    ),
                    revenue_statuses=_schema_enum(
                        repo_props,
                        "revenue_status",
                        fallback.revenue_statuses,
                    ),
                    promotion_states=_schema_enum(
                        repo_props,
                        "promotion_status",
                        fallback.promotion_states,
                    ),
                    tiers=_schema_enum(repo_props, "tier", fallback.tiers),
                    source_kind="external-schema",
                    source_sha256="sha256:" + hashlib.sha256(schema_payload).hexdigest(),
                )
            except (StableReadError, json.JSONDecodeError, KeyError, TypeError) as e:
                warnings.warn(f"Failed to parse registry-v2 schema enums: {e}", stacklevel=2)
                break

    return _fallback_policy()


def _schema_enum(
    properties: dict,
    key: str,
    fallback: frozenset[str],
) -> frozenset[str]:
    """Return one validated schema enum, retaining historical empty fallback."""
    definition = properties.get(key)
    if definition is None:
        return fallback
    if not isinstance(definition, dict):
        raise TypeError(f"registry schema {key} definition is not a mapping")
    values = definition.get("enum")
    if values is None or values == []:
        return fallback
    if not isinstance(values, list) or any(
        not isinstance(value, str) or not value for value in values
    ):
        raise TypeError(f"registry schema {key} enum is not a list of nonempty strings")
    return frozenset(values)


_DEFAULT_VALIDATION_POLICY = capture_registry_validation_policy()

VALID_STATUSES = _DEFAULT_VALIDATION_POLICY.statuses
VALID_REVENUE_MODELS = _DEFAULT_VALIDATION_POLICY.revenue_models
VALID_REVENUE_STATUSES = _DEFAULT_VALIDATION_POLICY.revenue_statuses
VALID_PROMOTION_STATES = _DEFAULT_VALIDATION_POLICY.promotion_states
VALID_TIERS = _DEFAULT_VALIDATION_POLICY.tiers

REQUIRED_FIELDS = {"name", "org", "implementation_status", "public", "description"}
ORGAN_III_EXTRA = {"type", "revenue_model", "revenue_status"}


@dataclass
class ValidationResult:
    """Result of a registry validation run."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    total_repos: int = 0

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0

    def summary(self) -> str:
        lines = [f"Registry Validation: {self.total_repos} repos checked"]
        if self.errors:
            lines.append(f"ERRORS ({len(self.errors)}):")
            for e in self.errors:
                lines.append(f"  {e}")
        if self.warnings:
            lines.append(f"WARNINGS ({len(self.warnings)}):")
            for w in self.warnings:
                lines.append(f"  {w}")
        if self.passed and not self.warnings:
            lines.append("All checks passed.")
        return "\n".join(lines)


def validate_registry(
    registry: dict,
    *,
    policy: RegistryValidationPolicy | None = None,
) -> ValidationResult:
    """Run full validation on a registry dict.

    Checks:
    - Required fields present on all repos
    - Enum values valid (status, revenue, promotion, tier)
    - ORGAN-III repos have revenue fields
    - No back-edge dependencies in I->II->III chain
    - Dependency targets exist in registry
    - Count consistency (declared vs actual)

    Args:
        registry: Loaded registry dict.

    Returns:
        ValidationResult with errors and warnings.
    """
    result = ValidationResult()
    validation_policy = policy or _DEFAULT_VALIDATION_POLICY

    for organ_key, repo in all_repos(registry):
        result.total_repos += 1
        name = repo.get("name", f"<unnamed in {organ_key}>")

        # Required fields
        for f in REQUIRED_FIELDS:
            if f not in repo:
                result.errors.append(f"{name}: missing required field '{f}'")

        # Status enum
        status = repo.get("implementation_status")
        if status and status not in validation_policy.statuses:
            result.errors.append(
                f"{name}: invalid implementation_status '{status}' "
                f"(valid: {', '.join(sorted(validation_policy.statuses))})",
            )

        # Promotion status enum
        promo = repo.get("promotion_status")
        if promo and promo not in validation_policy.promotion_states:
            result.errors.append(f"{name}: invalid promotion_status '{promo}'")

        # Tier enum
        tier = repo.get("tier")
        if tier and tier not in validation_policy.tiers:
            result.errors.append(f"{name}: invalid tier '{tier}'")

        # ORGAN-III revenue fields
        if organ_key == "ORGAN-III":
            for f in ORGAN_III_EXTRA:
                if f not in repo:
                    result.warnings.append(f"{name}: ORGAN-III repo missing '{f}'")

            rm = repo.get("revenue_model")
            if rm and rm not in validation_policy.revenue_models:
                result.errors.append(f"{name}: invalid revenue_model '{rm}'")

            rs = repo.get("revenue_status")
            if rs and rs not in validation_policy.revenue_statuses:
                result.errors.append(f"{name}: invalid revenue_status '{rs}'")

        # Dependency validation
        organ_num = {"ORGAN-I": 1, "ORGAN-II": 2, "ORGAN-III": 3}.get(organ_key)
        for dep in repo.get("dependencies", []):
            # Check target exists
            dep_name = dep.split("/")[-1] if "/" in dep else dep
            dep_result = find_repo(registry, dep_name)
            if not dep_result:
                result.warnings.append(f"{name}: dependency '{dep}' not found in registry")
                continue

            # Back-edge check
            dep_organ = dep_result[0]
            dep_num = {"ORGAN-I": 1, "ORGAN-II": 2, "ORGAN-III": 3}.get(dep_organ)
            if organ_num and dep_num and organ_num < dep_num:
                result.errors.append(
                    f"{name}: back-edge dependency on {dep} ({organ_key} -> {dep_organ})",
                )

    # Count consistency
    organs = registry.get("organs", {})
    for organ_key, organ in organs.items():
        declared = organ.get("repository_count")
        actual = len(organ.get("repositories", []))
        if declared is not None and declared != actual:
            result.warnings.append(f"{organ_key}: repository_count={declared} but found {actual}")

    return result
