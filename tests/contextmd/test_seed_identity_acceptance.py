"""Acceptance regressions for registry-bound seed discovery and identity."""

import json

import pytest

from organvm_engine.contextmd.sync import sync_all


@pytest.fixture(autouse=True)
def isolate_emitters(monkeypatch):
    monkeypatch.setattr(
        "organvm_engine.contextmd.receipt.generator_git_identity",
        lambda **kwargs: {"commit": "a" * 40, "tree": "b" * 40},
    )
    monkeypatch.setattr("organvm_engine.contextmd.sync.precompute_ammoi", lambda: None)
    monkeypatch.setattr(
        "organvm_engine.pulse.emitter.emit_engine_event", lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "organvm_engine.ledger.emit.testament_emit", lambda *args, **kwargs: None,
    )


def make_registry(workspace, *, directory=None, shared_owner=False):
    registry = {
        "version": "2.0",
        "organs": {
            key: {
                "name": key,
                **({"directory": directory} if key == "ORGAN-I" and directory else {}),
                "repositories": [{
                    "name": "shared-name",
                    "org": "owner-one" if key == "ORGAN-I" or shared_owner else "owner-two",
                    "implementation_status": "ACTIVE",
                    "public": True,
                    "description": f"Repository of {key}",
                }],
            }
            for key in ("ORGAN-I", "ORGAN-II")
        },
    }
    path = workspace / "registry.json"
    path.write_text(json.dumps(registry), encoding="utf-8")
    return path


def make_seed(workspace, directory, *, owner, marker, organ=None):
    repo = workspace / directory / "shared-name"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "seed.yaml").write_text(
        f"repo: shared-name\norg: {owner}\n"
        + (f"organ: {organ}\n" if organ else "")
        + f"produces:\n  - type: {marker}\n    consumers: [META-ORGANVM]\n",
        encoding="utf-8",
    )
    return repo


@pytest.mark.parametrize("alias", ["organvm-i-theoria", "ORGAN-I", "OWNER-ONE"])
def test_owner_and_directory_aliases_keep_same_name_seeds_separate(tmp_path, alias):
    registry_path = make_registry(tmp_path)
    first = make_seed(tmp_path, "organvm-i-theoria", owner=alias, marker="first-only")
    second = make_seed(
        tmp_path, "organvm-ii-poiesis", owner="organvm-ii-poiesis", marker="second-only",
    )
    result = sync_all(
        workspace=tmp_path, registry_path=str(registry_path),
        additional_workspace_roots=[], receipt_path=tmp_path / "receipt.json",
    )
    assert result["errors"] == []
    for filename in ("AGENTS.md", "CLAUDE.md", "GEMINI.md"):
        assert "first-only" in (first / filename).read_text()
        assert "second-only" not in (first / filename).read_text()
        assert "second-only" in (second / filename).read_text()
        assert "first-only" not in (second / filename).read_text()


@pytest.mark.parametrize("owner", ["owner-one", "local-theory", "organvm-i-theoria"])
def test_explicit_directory_seed_is_rendered_and_bound(tmp_path, owner):
    registry_path = make_registry(tmp_path, directory="local-theory")
    repo = make_seed(tmp_path, "local-theory", owner=owner, marker="custom-only")
    sync_all(
        workspace=tmp_path, registry_path=str(registry_path), organs=["ORGAN-I"],
        additional_workspace_roots=[], receipt_path=tmp_path / "receipt.json",
    )
    assert "custom-only" in (repo / "AGENTS.md").read_text()
    receipt = json.loads((tmp_path / "receipt.json").read_text())
    assert {seed["path"] for seed in receipt["inputs"]["seeds"]} == {
        "local-theory/shared-name/seed.yaml",
    }


def test_duplicate_aliases_for_one_repository_fail_before_output_writes(tmp_path):
    registry_path = make_registry(tmp_path)
    make_seed(tmp_path, "organvm-i-theoria", owner="organvm-i-theoria", marker="first")
    make_seed(tmp_path, "flat", owner="owner-one", marker="duplicate")
    with pytest.raises(RuntimeError, match="duplicate seed repository identity"):
        sync_all(
            workspace=tmp_path, registry_path=str(registry_path),
            additional_workspace_roots=[tmp_path / "flat"],
            receipt_path=tmp_path / "receipt.json",
        )
    assert not (tmp_path / "AGENTS.md").exists()
    assert not (tmp_path / "receipt.json").exists()


def test_shared_owner_and_repository_name_without_organ_is_ambiguous(tmp_path):
    registry_path = make_registry(tmp_path, shared_owner=True)
    make_seed(tmp_path, "flat", owner="owner-one", marker="ambiguous")
    with pytest.raises(RuntimeError, match="ambiguous seed repository identity"):
        sync_all(
            workspace=tmp_path, registry_path=str(registry_path),
            additional_workspace_roots=[tmp_path / "flat"],
            receipt_path=tmp_path / "receipt.json",
        )
    assert not (tmp_path / "AGENTS.md").exists()


def test_explicit_seed_organ_disambiguates_shared_owner(tmp_path):
    from organvm_engine.contextmd.sync import _canonical_seed_identity, _registry_seed_aliases

    registry_path = make_registry(tmp_path, shared_owner=True)
    aliases, organ_aliases = _registry_seed_aliases(json.loads(registry_path.read_text()))
    for organ in ("I", "II"):
        seed = {"org": "owner-one", "repo": "shared-name", "organ": organ}
        assert _canonical_seed_identity(seed, aliases, organ_aliases) == (
            f"ORGAN-{organ}", "shared-name",
        )


def test_registry_change_during_custom_directory_discovery_is_rejected(tmp_path, monkeypatch):
    import organvm_engine.contextmd.receipt as receipt_mod

    registry_path = make_registry(tmp_path, directory="local-theory")
    repo = make_seed(tmp_path, "local-theory", owner="owner-one", marker="custom-only")
    real_capture = receipt_mod.capture_context_sync_inputs
    captures = 0

    def capture_then_change_registry(**kwargs):
        nonlocal captures
        result = real_capture(**kwargs)
        captures += 1
        if captures == 1:
            registry = json.loads(registry_path.read_text())
            registry["organs"]["ORGAN-I"]["directory"] = "different-directory"
            registry_path.write_text(json.dumps(registry), encoding="utf-8")
        return result

    monkeypatch.setattr(receipt_mod, "capture_context_sync_inputs", capture_then_change_registry)
    with pytest.raises(RuntimeError, match="inputs changed while binding registry directories"):
        sync_all(
            workspace=tmp_path, registry_path=str(registry_path),
            additional_workspace_roots=[], receipt_path=tmp_path / "receipt.json",
        )
    assert captures == 2
    assert not (repo / "AGENTS.md").exists()
    assert not (tmp_path / "receipt.json").exists()


def test_new_custom_directory_seed_before_publication_rolls_back(tmp_path, monkeypatch):
    import organvm_engine.contextmd.sync as sync_mod

    registry_path = make_registry(tmp_path, directory="local-theory")
    repo = make_seed(tmp_path, "local-theory", owner="owner-one", marker="custom-only")
    original = "# Manual context\n"
    (repo / "AGENTS.md").write_text(original, encoding="utf-8")
    real_discover = sync_mod._discover_registry_seeds
    discoveries = 0

    def discover_with_late_seed(root, registry):
        nonlocal discoveries
        discoveries += 1
        if discoveries == 2:
            late_repo = tmp_path / "local-theory" / "late-repo"
            late_repo.mkdir()
            (late_repo / "seed.yaml").write_text("repo: late-repo\n", encoding="utf-8")
        return real_discover(root, registry)

    monkeypatch.setattr(sync_mod, "_discover_registry_seeds", discover_with_late_seed)
    with pytest.raises(RuntimeError, match="seed evidence path set changed"):
        sync_all(
            workspace=tmp_path, registry_path=str(registry_path),
            additional_workspace_roots=[], receipt_path=tmp_path / "receipt.json",
        )
    assert (repo / "AGENTS.md").read_text() == original
    assert not (tmp_path / "AGENTS.md").exists()
    assert not (tmp_path / "receipt.json").exists()
