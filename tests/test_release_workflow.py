"""Structural checks on the release and workflow-inventory workflows."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"


def _load(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text())


def test_publish_needs_every_gate():
    needs = _load("release.yml")["jobs"]["publish"]["needs"]
    assert set(needs) == {"build", "smoke", "rollback"}


def test_release_permissions_are_least_privilege():
    wf = _load("release.yml")
    assert wf["permissions"] == {"contents": "read"}
    assert wf["jobs"]["publish"]["permissions"] == {"contents": "write"}
    for name, job in wf["jobs"].items():
        if name != "publish":
            assert "permissions" not in job, f"{name} must inherit read-only"


def test_rollback_version_is_not_hardcoded():
    wf = _load("release.yml")
    rollback = wf["jobs"]["rollback"]
    text = yaml.safe_dump(rollback)
    assert "--version 0.1.0" not in text
    assert "pyproject.toml" in text
    assert "steps.version.outputs.version" in text


def test_workflow_inventory_ontologia_pinned_to_full_sha():
    text = (WORKFLOWS / "workflow-inventory.yml").read_text()
    match = re.search(r"organvm-ontologia\.git@([^\"\s]+)", text)
    assert match, "organvm-ontologia install must name a ref"
    assert re.fullmatch(r"[0-9a-f]{40}", match.group(1))
