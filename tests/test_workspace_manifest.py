"""Tests for workspace manifest."""

from pathlib import Path

import pytest
import yaml
from conftest import replace_with_nonregular

from organvm_engine._stable_io import StableReadError
from organvm_engine.seed.manifest import (
    is_partial_workspace,
    load_workspace_manifest,
    organs_in_manifest,
)

FIXTURES = Path(__file__).parent / "fixtures"


class TestManifestLoading:
    def test_load_manifest(self):
        manifest = load_workspace_manifest(FIXTURES / "workspace-manifest.yaml")
        assert manifest is not None
        assert manifest["workspace_name"] == "chris-studio"

    def test_load_missing_returns_none(self, tmp_path):
        result = load_workspace_manifest(tmp_path / "nonexistent.yaml")
        assert result is None

    def test_organs_in_manifest(self):
        manifest = load_workspace_manifest(FIXTURES / "workspace-manifest.yaml")
        organs = organs_in_manifest(manifest)
        assert "II" in organs
        assert "META" in organs

    def test_organs_none_manifest(self):
        assert organs_in_manifest(None) == []

    def test_is_partial(self):
        manifest = load_workspace_manifest(FIXTURES / "workspace-manifest.yaml")
        assert is_partial_workspace(manifest) is True

    def test_full_workspace_not_partial(self):
        assert is_partial_workspace(None) is False

    @pytest.mark.parametrize("replacement_kind", ["fifo", "symlink", "directory"])
    def test_is_file_to_nonregular_swap_fails_closed_without_blocking(
        self,
        tmp_path,
        monkeypatch,
        replacement_kind,
    ):
        import organvm_engine.seed.manifest as manifest_mod

        manifest_path = tmp_path / "workspace-manifest.yaml"
        manifest_path.write_text("organs_present: [II]\n", encoding="utf-8")
        outside = tmp_path / "outside.yaml"
        outside.write_text("organs_present: [META]\n", encoding="utf-8")
        real_read = manifest_mod.read_stable_regular_bytes
        swapped = False

        def swap_after_is_file(path, *args, **kwargs):
            nonlocal swapped
            if Path(path) == manifest_path and not swapped:
                replace_with_nonregular(manifest_path, replacement_kind, outside)
                swapped = True
            return real_read(path, *args, **kwargs)

        monkeypatch.setattr(
            manifest_mod,
            "read_stable_regular_bytes",
            swap_after_is_file,
        )

        with pytest.raises(StableReadError):
            load_workspace_manifest(manifest_path)
        assert swapped is True


class TestDiscoverWithManifest:
    def test_discover_respects_manifest(self, tmp_path):
        from organvm_engine.seed.discover import discover_seeds

        # Create workspace with manifest limiting to organ II only
        manifest = {
            "schema_version": "1.0",
            "organs_present": ["II"],
            "partial": True,
        }
        manifest_path = tmp_path / "workspace-manifest.yaml"
        manifest_path.write_text(yaml.dump(manifest))

        # Create organ dirs with seeds
        for org_dir_name in ["organvm-i-theoria", "organvm-ii-poiesis"]:
            repo_dir = tmp_path / org_dir_name / "test-repo"
            repo_dir.mkdir(parents=True)
            (repo_dir / "seed.yaml").write_text("organ: Test\nrepo: test\norg: test\n")

        # With manifest, should only find ORGAN-II seeds
        seeds = discover_seeds(tmp_path)
        seed_orgs = [s.parent.parent.name for s in seeds]
        assert "organvm-ii-poiesis" in seed_orgs
        assert "organvm-i-theoria" not in seed_orgs

    def test_discover_without_manifest_finds_all(self, tmp_path):
        from organvm_engine.seed.discover import discover_seeds

        # No manifest — should scan all organ dirs
        for org_dir_name in ["organvm-i-theoria", "organvm-ii-poiesis"]:
            repo_dir = tmp_path / org_dir_name / "test-repo"
            repo_dir.mkdir(parents=True)
            (repo_dir / "seed.yaml").write_text("organ: Test\nrepo: test\norg: test\n")

        seeds = discover_seeds(tmp_path)
        seed_orgs = [s.parent.parent.name for s in seeds]
        assert "organvm-i-theoria" in seed_orgs
        assert "organvm-ii-poiesis" in seed_orgs

    def test_discover_explicit_orgs_overrides_manifest(self, tmp_path):
        from organvm_engine.seed.discover import discover_seeds

        # Manifest says II only, but explicit orgs says theoria
        manifest = {"organs_present": ["II"], "partial": True}
        (tmp_path / "workspace-manifest.yaml").write_text(yaml.dump(manifest))

        for org_dir_name in ["organvm-i-theoria", "organvm-ii-poiesis"]:
            repo_dir = tmp_path / org_dir_name / "test-repo"
            repo_dir.mkdir(parents=True)
            (repo_dir / "seed.yaml").write_text("organ: Test\nrepo: test\norg: test\n")

        # Explicit orgs parameter takes precedence over manifest
        seeds = discover_seeds(tmp_path, orgs=["organvm-i-theoria"])
        seed_orgs = [s.parent.parent.name for s in seeds]
        assert "organvm-i-theoria" in seed_orgs
        assert "organvm-ii-poiesis" not in seed_orgs
