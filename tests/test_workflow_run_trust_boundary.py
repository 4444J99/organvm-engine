"""Regressions for contributor-controlled workflow-run values and literal selectors."""

import pytest
import yaml

from organvm_engine.ci.workflow_intelligence import analyze_workflow

HEAD = "${{ github.event.workflow_run.head_sha }}"
REPOSITORY = "${{ github.event.workflow_run.head_repository.full_name }}"


def codes(step, event="workflow_run"):
    """Analyze one synthetic step without executing or submitting the workflow."""
    source = yaml.safe_dump({
        "on": event,
        "permissions": {"contents": "read"},
        "jobs": {"check": {"runs-on": "ubuntu-latest", "timeout-minutes": 5,
                           "steps": [step]}},
    })
    return {item["code"] for item in analyze_workflow(source)["findings"]}


def checkout(ref=HEAD, repository=REPOSITORY):
    """Build a checkout declaration pinned to a synthetic action commit."""
    return {"uses": "actions/checkout@" + "a" * 40,
            "with": {"ref": ref, "repository": repository}}


@pytest.mark.parametrize("field", ["message", "author.name", "committer.email"])
@pytest.mark.parametrize("prefix", [
    "github.event.workflow_run.head_commit.",
    "github['event']['workflow_run']['head_commit'].",
    "github.event.head_commit.",
])
def test_contributor_commit_metadata_is_untrusted(prefix, field):
    """Both nested and top-level commit prose require safe shell handling."""
    script = "echo ${{ " + prefix + field + " }}"
    assert "untrusted_run_expression" in codes({"run": script})


@pytest.mark.parametrize("expression", [
    "'github.event.workflow_run.head_commit.message'",
    "format('literal }} {0}', 'github.event.workflow_run.head_commit.message')",
    "github.event.workflow_run.head_sha",
])
def test_literal_or_immutable_commit_values_are_not_prose(expression):
    """Literal text and the immutable revision are not untrusted commit prose."""
    assert "untrusted_run_expression" not in codes({"run": "echo ${{ " + expression + " }}"})


def test_formatted_nested_commit_message_remains_detectable():
    """Quoted closing braces must not hide a real context argument."""
    script = "echo ${{ format('}} {0}', github.event.workflow_run.head_commit.message) }}"
    assert "untrusted_run_expression" in codes({"run": script})


@pytest.mark.parametrize("ref,repository", [
    (HEAD, REPOSITORY),
    ("${{ github['event']['workflow_run']['head_sha'] }}", REPOSITORY),
    (HEAD, "${{ github['event']['workflow_run']['head_repository']['full_name'] }}"),
    ("${{ format('{0}', github.event.workflow_run.head_sha) }}", REPOSITORY),
])
def test_actual_workflow_run_head_checkout_is_flagged(ref, repository):
    """Genuine ref/repository selectors retain the privileged checkout finding."""
    assert "privileged_head_checkout" in codes(checkout(ref, repository))


@pytest.mark.parametrize("ref,repository", [
    ("${{ 'github.event.workflow_run.head_sha' }}", REPOSITORY),
    (HEAD, "${{ 'github.event.workflow_run.head_repository.full_name' }}"),
    ("${{ format('{0}', 'github.event.workflow_run.head_sha') }}", REPOSITORY),
    ("${{ 'literal }} github.event.workflow_run.head_sha' }}", REPOSITORY),
    ("${{ 'it''s github.event.workflow_run.head_sha' }}", REPOSITORY),
    ("github.event.workflow_run.head_sha", REPOSITORY),
    (HEAD, "github.event.workflow_run.head_repository.full_name"),
    ("main", REPOSITORY),
    (HEAD, "example/trusted"),
])
def test_literal_or_fixed_selectors_are_not_dynamic_head_checkout(ref, repository):
    """Context-looking literal data must not become a critical false positive."""
    assert "privileged_head_checkout" not in codes(checkout(ref, repository))


def test_literal_then_real_reference_is_not_masked():
    """A safe literal elsewhere must not hide a second genuine expression."""
    ref = ("${{ 'github.event.workflow_run.head_sha' }}"
           "${{ github.event.workflow_run.head_sha }}")
    assert "privileged_head_checkout" in codes(checkout(ref))


def test_nonprivileged_trigger_does_not_acquire_privileged_finding():
    """This rule remains scoped to the privileged workflow-run event."""
    assert "privileged_head_checkout" not in codes(checkout(), event="push")
