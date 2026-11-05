"""Tests for audit/compliance functionality and CLI entry points."""

from __future__ import annotations

import json
import os
import tempfile

from src.__main__ import load_registry, main
from src.governance import (
    GovernanceReport,
    HealthCheck,
    check_ci_health,
    check_documentation_coverage,
)


def _write_registry(repos: list[dict]) -> str:
    """Write a temporary registry JSON file and return its path."""
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(repos, f)
    return path


class TestAuditCompliance:
    """Tests for audit and compliance-checking logic."""

    def test_all_repos_healthy(self):
        repos = [
            {
                "name": "r1",
                "org": "I",
                "ci_conclusion": "success",
                "documentation_status": "DEPLOYED",
            },
            {
                "name": "r2",
                "org": "II",
                "ci_conclusion": "success",
                "documentation_status": "ACTIVE",
            },
        ]
        report = GovernanceReport()
        for c in check_ci_health(repos):
            report.add_check(c)
        for c in check_documentation_coverage(repos):
            report.add_check(c)
        assert report.passed is True
        assert report.fail_count == 0

    def test_mixed_health(self):
        repos = [
            {
                "name": "r1",
                "org": "I",
                "ci_conclusion": "success",
                "documentation_status": "DEPLOYED",
            },
            {
                "name": "r2",
                "org": "II",
                "ci_conclusion": "failure",
                "documentation_status": "SKELETON",
            },
        ]
        report = GovernanceReport()
        for c in check_ci_health(repos):
            report.add_check(c)
        for c in check_documentation_coverage(repos):
            report.add_check(c)
        assert report.passed is False
        assert report.fail_count == 2  # CI fail + doc fail

    def test_empty_repo_list(self):
        report = GovernanceReport()
        for c in check_ci_health([]):
            report.add_check(c)
        assert report.passed is True
        assert "No checks" in report.summary()

    def test_documentation_empty_status(self):
        repos = [{"name": "r1", "org": "I", "documentation_status": "EMPTY"}]
        checks = check_documentation_coverage(repos)
        assert checks[0].passed is False

    def test_ci_unknown_status(self):
        repos = [{"name": "r1", "org": "I", "ci_conclusion": "unknown"}]
        checks = check_ci_health(repos)
        assert checks[0].passed is False

    def test_organ_filter_isolates_checks(self):
        report = GovernanceReport()
        report.add_check(HealthCheck(name="a", passed=True, message="ok", organ="I"))
        report.add_check(HealthCheck(name="b", passed=False, message="fail", organ="II"))
        organ_i = report.by_organ("I")
        assert all(c.passed for c in organ_i)

    def test_multiple_repos_per_organ(self):
        repos = [
            {"name": "r1", "org": "III", "ci_conclusion": "success"},
            {"name": "r2", "org": "III", "ci_conclusion": "success"},
            {"name": "r3", "org": "III", "ci_conclusion": "failure"},
        ]
        checks = check_ci_health(repos)
        organ_iii = [c for c in checks if c.organ == "III"]
        assert len(organ_iii) == 3
        assert sum(1 for c in organ_iii if not c.passed) == 1


class TestCLIEntryPoints:
    """Tests for the CLI interface (argparse commands)."""

    def test_main_no_args_returns_2(self, capsys):
        result = main([])
        assert result == 2

    def test_evaluate_all_pass(self, capsys):
        path = _write_registry(
            [
                {
                    "name": "r1",
                    "org": "I",
                    "ci_conclusion": "success",
                    "documentation_status": "DEPLOYED",
                },
            ]
        )
        try:
            result = main(["evaluate", "--registry", path])
            assert result == 0
            captured = capsys.readouterr()
            assert "PASS" in captured.out
        finally:
            os.unlink(path)

    def test_evaluate_with_failure(self, capsys):
        path = _write_registry(
            [
                {
                    "name": "r1",
                    "org": "I",
                    "ci_conclusion": "failure",
                    "documentation_status": "DEPLOYED",
                },
            ]
        )
        try:
            result = main(["evaluate", "--registry", path])
            assert result == 1
            captured = capsys.readouterr()
            assert "FAIL" in captured.out
        finally:
            os.unlink(path)

    def test_audit_pass(self, capsys):
        path = _write_registry(
            [
                {
                    "name": "r1",
                    "org": "I",
                    "ci_conclusion": "success",
                    "documentation_status": "DEPLOYED",
                },
            ]
        )
        try:
            result = main(["audit", "--registry", path])
            assert result == 0
            captured = capsys.readouterr()
            assert "AUDIT PASS" in captured.out
        finally:
            os.unlink(path)

    def test_audit_organ_filter(self, capsys):
        path = _write_registry(
            [
                {
                    "name": "r1",
                    "org": "I",
                    "ci_conclusion": "success",
                    "documentation_status": "DEPLOYED",
                },
                {
                    "name": "r2",
                    "org": "II",
                    "ci_conclusion": "failure",
                    "documentation_status": "SKELETON",
                },
            ]
        )
        try:
            # Audit for organ I should pass (only r1)
            result = main(["audit", "--registry", path, "--organ", "I"])
            assert result == 0
        finally:
            os.unlink(path)

    def test_report_system_wide(self, capsys):
        path = _write_registry(
            [
                {
                    "name": "r1",
                    "org": "I",
                    "ci_conclusion": "success",
                    "documentation_status": "DEPLOYED",
                },
            ]
        )
        try:
            result = main(["report", "--registry", path])
            assert result == 0
            captured = capsys.readouterr()
            assert "System Governance Report" in captured.out
        finally:
            os.unlink(path)

    def test_report_organ_specific(self, capsys):
        path = _write_registry(
            [
                {
                    "name": "r1",
                    "org": "I",
                    "ci_conclusion": "success",
                    "documentation_status": "DEPLOYED",
                },
            ]
        )
        try:
            result = main(["report", "--registry", path, "--organ", "I"])
            assert result == 0
            captured = capsys.readouterr()
            assert "ORGAN-I" in captured.out
        finally:
            os.unlink(path)

    def test_report_to_file(self, capsys):
        reg_path = _write_registry(
            [
                {
                    "name": "r1",
                    "org": "I",
                    "ci_conclusion": "success",
                    "documentation_status": "DEPLOYED",
                },
            ]
        )
        fd, out_path = tempfile.mkstemp(suffix=".md")
        os.close(fd)
        try:
            result = main(["report", "--registry", reg_path, "-o", out_path])
            assert result == 0
            with open(out_path) as f:
                content = f.read()
            assert "System Governance Report" in content
        finally:
            os.unlink(reg_path)
            os.unlink(out_path)


class TestLoadRegistry:
    """Tests for the registry loading logic."""

    def test_load_list_format(self):
        path = _write_registry([{"name": "r1"}])
        try:
            repos = load_registry(path)
            assert len(repos) == 1
        finally:
            os.unlink(path)

    def test_load_dict_with_repositories_key(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as f:
            json.dump({"repositories": [{"name": "r1"}, {"name": "r2"}]}, f)
        try:
            repos = load_registry(path)
            assert len(repos) == 2
        finally:
            os.unlink(path)
