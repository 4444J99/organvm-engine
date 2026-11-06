"""Regression cases from the second bounded review of the imported tools."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_configuration_prose_round_trips_through_yaml():
    generator = load_script("generate-github-configs.py")
    organ = {
        "suffix": "i-theoria", "display_name": "The organization's research\nand more",
        "description": "A quoted \"value\": it's valid.\nA second line # still prose.",
        "profile_tagline": "We're building: safely", "domain": "Theory: research",
        "etymology": "A scholar's view", "license": "MIT",
    }
    shared = {"email_domain": "example.invalid", "teams": {"leadership": "researcher's-team"},
              "discord_invite": "https://example.invalid/invite?label=it's"}

    generated = yaml.safe_load(generator.generate_template_config(
        "ORGAN-I", organ, shared, "example", "owner",
    ))

    assert generated["org"]["display_name"] == organ["display_name"]
    assert generated["organ"]["description"] == organ["description"]
    assert generated["organ"]["tagline"] == organ["profile_tagline"]
    assert generated["organ"]["etymology"] == organ["etymology"]
    assert generated["teams"]["leadership"] == shared["teams"]["leadership"]
    assert generated["social"]["discord_invite"] == shared["discord_invite"]


def test_polish_help_does_not_require_an_unshipped_template():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "platinum-polish-vi-vii.py"), "--help"],
        text=True, capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert "--ci-template" in result.stdout


def test_polish_accepts_an_external_template_and_previews_without_gh(tmp_path):
    template = tmp_path / "ci.yml"
    template.write_text("name: Example\non: push\njobs: {}\n")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "platinum-polish-vi-vii.py"),
         "--ci-template", str(template)],
        cwd=tmp_path, env=dict(os.environ, PATH=str(tmp_path / "empty-bin")),
        text=True, capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert "DRY RUN" in result.stdout
    assert "salon-archive" in result.stdout
    assert "--write" in result.stdout


def test_missing_polish_template_reports_actionable_configuration_error(tmp_path):
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "platinum-polish-vi-vii.py"),
         "--ci-template", str(tmp_path / "missing.yml")],
        text=True, capture_output=True,
    )
    assert result.returncode == 2
    assert "--ci-template" in result.stderr
    assert "Traceback" not in result.stderr


def test_polish_stops_if_default_branch_lookup_fails(tmp_path, monkeypatch):
    polish = load_script("platinum-polish-vi-vii.py")
    template = tmp_path / "ci.yml"
    template.write_text("name: Example\non: push\njobs: {}\n")
    monkeypatch.setattr(polish, "REPOS", [("example", "repo", "Markdown", "VI", "Community", "000000")])
    api = Mock(return_value=subprocess.CompletedProcess([], 1, "", "authentication failed"))
    monkeypatch.setattr(polish.subprocess, "run", api)

    assert polish.main(["--ci-template", str(template), "--write"]) == 1
    assert api.call_count == 1
    assert "PUT" not in api.call_args.args[0]


def test_polish_uses_the_external_template_for_explicit_writes(tmp_path, monkeypatch):
    polish = load_script("platinum-polish-vi-vii.py")
    template = tmp_path / "ci.yml"
    template.write_text("name: External template\non: push\njobs: {}\n")
    monkeypatch.setattr(polish, "REPOS", [("example", "repo", "Markdown", "VI", "Community", "000000")])
    monkeypatch.setattr(polish, "get_default_branch", lambda *args: "main")
    writes = Mock(return_value=True)
    monkeypatch.setattr(polish, "put_file", writes)
    monkeypatch.setattr(polish.subprocess, "run", Mock(return_value=subprocess.CompletedProcess([], 0, "# Repository\n", "")))
    monkeypatch.setattr(polish.time, "sleep", lambda delay: None)

    assert polish.main(["--ci-template", str(template), "--write"]) == 0
    assert writes.call_args_list[0].args[2:4] == (".github/workflows/ci.yml", template.read_text())


@pytest.mark.parametrize("fetch_success", [(False,), (True, False), (True,)])
def test_readme_audits_require_complete_fetch_coverage(tmp_path, monkeypatch, capsys, fetch_success):
    audit = load_script("v1-v2-link-tbd-audit.py")
    registry = {"organs": {"ORGAN-I": {"repositories": [
        {"org": "example", "name": f"repo-{i}", "documentation_status": "DEPLOYED"}
        for i in range(len(fetch_success))
    ]}}}
    monkeypatch.setattr(audit, "load_registry", lambda: registry)
    monkeypatch.setattr(audit, "__file__", str(tmp_path / "audit.py"))
    monkeypatch.setattr(audit, "fetch_readme", lambda org, repo: (
        ("# Complete documentation\n", None) if fetch_success[int(repo.split("-")[-1])]
        else (None, "API authentication failed")
    ))

    status = audit.main()

    report = json.loads((tmp_path / "v1-v2-report.json").read_text())
    complete = all(fetch_success)
    assert report["v1_link_audit"]["pass"] is complete
    assert report["v2_tbd_scan"]["pass"] is complete
    assert report["readme_coverage_complete"] is complete
    assert report["readmes_fetched"] == sum(fetch_success)
    assert status == (0 if complete else 1)
    if not complete:
        output = capsys.readouterr().out
        assert "V1 RESULT: INCOMPLETE" in output
        assert "V2 RESULT: INCOMPLETE" in output
