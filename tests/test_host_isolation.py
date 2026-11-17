"""The suite must give the same answer on every host.

A developer shell exports ORGANVM_* overrides and a global git ignore file;
neither may reach a test. These checks pin the isolation that conftest sets up.
"""

import os
import subprocess

from organvm_engine import paths


def test_host_organvm_env_overrides_do_not_reach_tests():
    leaked = [n for n in os.environ if n.startswith(("ORGANVM_", "LIMEN_GOV_"))]
    assert leaked == []


def test_additional_roots_ignore_host_override(monkeypatch, tmp_path):
    # The autouse fixture scrubs the variable; an explicit setenv still wins.
    assert paths.additional_workspace_roots(workspace=tmp_path) == []
    monkeypatch.setenv("ORGANVM_ADDITIONAL_WORKSPACE_ROOTS", str(tmp_path / "x"))
    assert paths.additional_workspace_roots(workspace=tmp_path) == [tmp_path / "x"]


def test_global_git_ignore_does_not_hide_untracked_files(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    (repo / "scratch.tmp").write_text("x")
    status = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        check=True, capture_output=True, text=True,
    ).stdout
    assert "scratch.tmp" in status


def test_engine_workspace_resolves_this_checkout(engine_workspace):
    module = engine_workspace / "meta-organvm/organvm-engine/src/organvm_engine/governance"
    assert module.is_dir()
