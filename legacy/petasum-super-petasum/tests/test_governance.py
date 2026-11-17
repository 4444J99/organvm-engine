"""Tests for the governance module."""

from src.governance import (
    GovernanceReport,
    HealthCheck,
    check_ci_health,
    check_documentation_coverage,
)


class TestHealthCheck:
    def test_basic(self):
        check = HealthCheck(name="test", passed=True, message="OK")
        assert check.passed is True


class TestGovernanceReport:
    def test_empty_report(self):
        report = GovernanceReport()
        assert report.passed is True
        assert "No checks" in report.summary()

    def test_all_passing(self):
        report = GovernanceReport()
        report.add_check(HealthCheck(name="a", passed=True, message="ok"))
        report.add_check(HealthCheck(name="b", passed=True, message="ok"))
        assert report.passed is True
        assert report.pass_count == 2

    def test_with_failure(self):
        report = GovernanceReport()
        report.add_check(HealthCheck(name="a", passed=True, message="ok"))
        report.add_check(HealthCheck(name="b", passed=False, message="fail"))
        assert report.passed is False
        assert report.fail_count == 1

    def test_by_organ(self):
        report = GovernanceReport()
        report.add_check(HealthCheck(name="a", passed=True, message="ok", organ="I"))
        report.add_check(HealthCheck(name="b", passed=True, message="ok", organ="II"))
        assert len(report.by_organ("I")) == 1

    def test_summary_format(self):
        report = GovernanceReport()
        report.add_check(HealthCheck(name="a", passed=True, message="ok"))
        assert "PASS" in report.summary()
        assert "1/1" in report.summary()


class TestCheckCIHealth:
    def test_passing_repo(self):
        repos = [{"name": "test", "org": "I", "ci_conclusion": "success"}]
        checks = check_ci_health(repos)
        assert len(checks) == 1
        assert checks[0].passed is True

    def test_failing_repo(self):
        repos = [{"name": "test", "org": "I", "ci_conclusion": "failure"}]
        checks = check_ci_health(repos)
        assert checks[0].passed is False


class TestCheckDocumentation:
    def test_deployed_docs(self):
        repos = [{"name": "test", "org": "I", "documentation_status": "DEPLOYED"}]
        checks = check_documentation_coverage(repos)
        assert checks[0].passed is True

    def test_skeleton_docs(self):
        repos = [{"name": "test", "org": "I", "documentation_status": "SKELETON"}]
        checks = check_documentation_coverage(repos)
        assert checks[0].passed is False
