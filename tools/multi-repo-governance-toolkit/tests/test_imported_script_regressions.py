"""Exercise the imported tools through their public command and file contracts."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_config_generation_preserves_the_separately_owned_meta_profile(tmp_path):
    config = tmp_path / "organvm.config.json"
    config.write_text(json.dumps({
        "orgs": {"ORGAN-I": {"suffix": "i-theoria", "display_name": "Theory"}},
        "shared": {"email_domain": "example.invalid"},
    }))
    output = tmp_path / "generated"
    output.mkdir()
    meta_profile = output / "meta-example.profile-README.md"
    meta_profile.write_text("Maintained by the corpus renderer.\n")

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "generate-github-configs.py"),
         "--config", str(config), "--output-dir", str(output), "--prefix", "example"],
        text=True, capture_output=True, check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (output / "example-i-theoria.template-config.yml").is_file()
    assert (output / "example-i-theoria.profile-README.md").is_file()
    assert meta_profile.read_text() == "Maintained by the corpus renderer.\n"
    assert "Meta profile not generated: use the owning corpus renderer" in result.stdout


@pytest.mark.parametrize("flags,should_push", [([], False), (["--remote-only"], True)])
def test_seed_remote_only_is_an_explicit_write_request(tmp_path, monkeypatch, flags, should_push):
    seed = load_script("generate-seed-yaml.py")
    registry = {"organs": {"ORGAN-I": {"repositories": [{"org": "example", "name": "missing"}]}}}
    monkeypatch.setattr(seed, "_engine_load", lambda path: registry)
    monkeypatch.setattr(seed, "WORKSPACE", tmp_path)
    monkeypatch.setattr(seed, "detect_language_remote", lambda org, repo: "python")
    push = Mock(return_value=(True, "pushed via API"))
    monkeypatch.setattr(seed, "push_remote", push)
    monkeypatch.setattr(sys, "argv", ["generate-seed-yaml.py", *flags])

    seed.main()

    assert push.call_count == int(should_push)
    assert not (tmp_path / "example" / "missing").exists()
    if should_push:
        assert push.call_args.args[:2] == ("example", "missing")
        assert "repo: missing" in push.call_args.args[2]


@pytest.fixture
def seed_checkout(tmp_path):
    remote = tmp_path / "remote.git"
    repo = tmp_path / "checkout"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test Fixture"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "fixture@example.invalid"], check=True)
    (repo / "README.md").write_text("Fixture repository.\n")
    subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "initial fixture"], check=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", str(remote)], check=True)
    subprocess.run(["git", "-C", str(repo), "push", "-q", "-u", "origin", "main"], check=True)
    return repo


def git_output(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def test_seed_push_publishes_only_the_new_seed_file(seed_checkout):
    seed = load_script("generate-seed-yaml.py")

    success, message = seed.push_local(seed_checkout, "repo: example\n")

    assert success, message
    assert (seed_checkout / "seed.yaml").read_text() == "repo: example\n"
    assert git_output(seed_checkout, "show", "--format=", "--name-only", "HEAD") == "seed.yaml"
    assert git_output(seed_checkout, "status", "--porcelain") == ""
    remote_head = git_output(seed_checkout, "ls-remote", "origin", "refs/heads/main").split()[0]
    assert remote_head == git_output(seed_checkout, "rev-parse", "HEAD")


def test_seed_push_does_not_commit_preexisting_staged_work(seed_checkout):
    seed = load_script("generate-seed-yaml.py")
    before = git_output(seed_checkout, "rev-parse", "HEAD")
    (seed_checkout / "unrelated.txt").write_text("Unrelated staged work.\n")
    subprocess.run(["git", "-C", str(seed_checkout), "add", "unrelated.txt"], check=True)

    success, message = seed.push_local(seed_checkout, "repo: example\n")

    assert not success
    assert "clean" in message
    assert git_output(seed_checkout, "rev-parse", "HEAD") == before
    assert git_output(seed_checkout, "diff", "--cached", "--name-only") == "unrelated.txt"
    assert not (seed_checkout / "seed.yaml").exists()


def test_seed_push_stops_before_writing_when_pull_fails(seed_checkout, tmp_path):
    seed = load_script("generate-seed-yaml.py")
    before = git_output(seed_checkout, "rev-parse", "HEAD")
    subprocess.run(["git", "-C", str(seed_checkout), "remote", "set-url", "origin",
                    str(tmp_path / "missing.git")], check=True)

    success, message = seed.push_local(seed_checkout, "repo: example\n")

    assert not success
    assert "pull failed" in message
    assert git_output(seed_checkout, "rev-parse", "HEAD") == before
    assert not (seed_checkout / "seed.yaml").exists()


def test_failed_seed_api_write_returns_a_failure_status(tmp_path, monkeypatch):
    seed = load_script("generate-seed-yaml.py")
    registry = {"organs": {"ORGAN-I": {"repositories": [{"org": "example", "name": "missing"}]}}}
    monkeypatch.setattr(seed, "_engine_load", lambda path: registry)
    monkeypatch.setattr(seed, "WORKSPACE", tmp_path)
    monkeypatch.setattr(seed, "detect_language_remote", lambda org, repo: "python")
    monkeypatch.setattr(seed, "push_remote", lambda *args: (False, "API write failed"))
    monkeypatch.setattr(sys, "argv", ["generate-seed-yaml.py", "--remote-only"])

    assert seed.main() == 1


@pytest.mark.parametrize("source,extension", [
    ("types/response.d.ts#L2-L4", "d.ts"),
    ("types/RESPONSE.D.MTS", "d.mts"),
    ("assets/application.min.js", "min.js"),
    ("assets/application.min.css", "min.css"),
])
def test_compound_artifact_suffixes_do_not_enter_signal(source, extension):
    quality = load_script("quality-filter.py")
    atom = {
        "id": "declaration",
        "label": "null",
        "source_file": source,
        "context": "export type OptionalResponse = { payload: null, status: number };",
    }

    result = quality.classify_atom(atom, {})

    assert result.is_noise
    assert f"code_extension:{extension}" in result.reasons
    atom["source_file"] = "src/response.ts"
    assert not quality.classify_atom(atom, {}).is_noise


def test_logged_atom_remains_usable_by_the_timeline_builder(tmp_path, monkeypatch):
    logger = load_script("plugins/atom_logger.py")
    timeline = load_script("timeline-graph.py")
    atoms = tmp_path / "data" / "atoms"
    atoms.mkdir(parents=True)
    tasks = atoms / "atomized-tasks.jsonl"
    assert logger.run([
        "--irf", "IRF-SYS-1", "--session", "test-session", "--title", "A logged work unit",
        "--target", str(tasks),
    ]) == 0
    task = json.loads(tasks.read_text())
    (atoms / "annotated-prompts.jsonl").write_text(json.dumps({
        "id": "prompt-1", "source": {"timestamp": "2026-11-06T00:00:00Z"},
    }) + "\n")
    (atoms / "atom-links.jsonl").write_text(json.dumps({
        "prompt_id": "prompt-1", "task_id": task["atom_id"],
    }) + "\n")
    (atoms / "ideal-forms.jsonl").write_text("")
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "timeline.jsonl"

    timeline.build(output)

    record = json.loads(output.read_text())
    assert record["linked_tasks"][0]["title"] == "A logged work unit"
    assert record["linked_tasks"][0]["task_id"] == task["id"] == task["atom_id"]
