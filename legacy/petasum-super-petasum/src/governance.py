"""Cross-organ governance checks and compliance reporting."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

try:
    from organvm_engine.governance.audit import run_audit as _engine_run_audit
    from organvm_engine.governance.rules import (
        load_governance_rules as _engine_load_governance_rules,
    )

    _HAS_ENGINE_GOVERNANCE = True
except ImportError:
    _HAS_ENGINE_GOVERNANCE = False


def _build_engine_registry(repos: list[dict]) -> dict[str, Any]:
    """Normalize simple repo dictionaries into the registry shape engine audit expects."""
    organs: dict[str, dict[str, Any]] = {}
    for repo in repos:
        organ = repo.get("org", "") or "UNKNOWN"
        organ_entry = organs.setdefault(organ, {"repositories": []})
        organ_entry["repositories"].append(
            {
                "name": repo.get("name", "unknown"),
                "ci_workflow": "ci.yml" if repo.get("ci_conclusion") == "success" else "",
                "documentation_status": repo.get("documentation_status", "EMPTY"),
                "implementation_status": repo.get("implementation_status", "ACTIVE"),
                "promotion_status": repo.get("promotion_status", "LOCAL"),
                "last_validated": repo.get("last_validated", ""),
                "dependencies": repo.get("dependencies", []),
            }
        )
    return {"organs": organs}


@dataclass
class HealthCheck:
    """Result of a single health check."""

    name: str
    passed: bool
    message: str
    organ: str = ""


@dataclass
class GovernanceReport:
    """Aggregated governance health report."""

    checks: list[HealthCheck] = field(default_factory=list)

    @classmethod
    def from_engine_audit(cls, result: Any) -> "GovernanceReport":
        """Build a local report from a canonical organvm-engine audit result."""
        report = cls()
        for item in getattr(result, "critical", []):
            report.add_check(HealthCheck(name="engine-critical", passed=False, message=item))
        for item in getattr(result, "warnings", []):
            report.add_check(HealthCheck(name="engine-warning", passed=False, message=item))
        for item in getattr(result, "info", []):
            report.add_check(HealthCheck(name="engine-info", passed=True, message=item))
        return report

    def add_check(self, check: HealthCheck) -> None:
        self.checks.append(check)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def pass_count(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def fail_count(self) -> int:
        return sum(1 for c in self.checks if not c.passed)

    def by_organ(self, organ: str) -> list[HealthCheck]:
        return [c for c in self.checks if c.organ == organ]

    def summary(self) -> str:
        total = len(self.checks)
        if total == 0:
            return "No checks performed"
        pct = (self.pass_count / total) * 100
        status = "PASS" if self.passed else "FAIL"
        return f"{status}: {self.pass_count}/{total} checks passed ({pct:.0f}%)"


def check_ci_health(repos: list[dict]) -> list[HealthCheck]:
    """Check CI health across repositories."""
    if _HAS_ENGINE_GOVERNANCE:
        try:
            registry = _build_engine_registry(repos)
            result = _engine_run_audit(registry, _engine_load_governance_rules())
            engine_messages = " ".join(
                [*getattr(result, "critical", []), *getattr(result, "warnings", [])]
            )
            checks: list[HealthCheck] = []
            for repo in repos:
                name = repo.get("name", "unknown")
                org = repo.get("org", "")
                passed = repo.get("ci_conclusion", "unknown") == "success"
                if not passed and name in engine_messages and "CI" in engine_messages:
                    checks.append(
                        HealthCheck(
                            name=f"ci-{name}",
                            passed=False,
                            message=f"CI failing for {name}",
                            organ=org,
                        )
                    )
                else:
                    checks.append(
                        HealthCheck(
                            name=f"ci-{name}",
                            passed=passed,
                            message=f"CI {'passing' if passed else 'failing'} for {name}",
                            organ=org,
                        )
                    )
            return checks
        except Exception:
            pass

    checks = []
    for repo in repos:
        name = repo.get("name", "unknown")
        org = repo.get("org", "")
        ci_status = repo.get("ci_conclusion", "unknown")
        passed = ci_status == "success"
        checks.append(
            HealthCheck(
                name=f"ci-{name}",
                passed=passed,
                message=f"CI {'passing' if passed else 'failing'} for {name}",
                organ=org,
            )
        )
    return checks


def check_documentation_coverage(repos: list[dict]) -> list[HealthCheck]:
    """Check documentation coverage across repositories."""
    if _HAS_ENGINE_GOVERNANCE:
        try:
            registry = _build_engine_registry(repos)
            result = _engine_run_audit(registry, _engine_load_governance_rules())
            engine_messages = " ".join(
                [*getattr(result, "critical", []), *getattr(result, "warnings", [])]
            )
            checks: list[HealthCheck] = []
            for repo in repos:
                name = repo.get("name", "unknown")
                org = repo.get("org", "")
                doc_status = repo.get("documentation_status", "EMPTY")
                passed = doc_status in ("DEPLOYED", "ACTIVE")
                if not passed and name in engine_messages and "README" in engine_messages:
                    checks.append(
                        HealthCheck(
                            name=f"docs-{name}",
                            passed=False,
                            message=f"Docs {doc_status.lower()} for {name}",
                            organ=org,
                        )
                    )
                else:
                    checks.append(
                        HealthCheck(
                            name=f"docs-{name}",
                            passed=passed,
                            message=f"Docs {'deployed' if passed else doc_status.lower()} for {name}",
                            organ=org,
                        )
                    )
            return checks
        except Exception:
            pass

    checks = []
    for repo in repos:
        name = repo.get("name", "unknown")
        org = repo.get("org", "")
        doc_status = repo.get("documentation_status", "EMPTY")
        passed = doc_status in ("DEPLOYED", "ACTIVE")
        checks.append(
            HealthCheck(
                name=f"docs-{name}",
                passed=passed,
                message=f"Docs {'deployed' if passed else doc_status.lower()} for {name}",
                organ=org,
            )
        )
    return checks
