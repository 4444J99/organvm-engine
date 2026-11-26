"""Tests for CLAUDE.md generator and sync (legacy module name).

These tests originally targeted organvm_engine.claudemd — now renamed to
organvm_engine.contextmd. See test_contextmd.py for comprehensive coverage.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from organvm_engine.contextmd.generator import (
    _build_sop_directives,
    generate_organ_section,
    generate_repo_section,
    generate_workspace_section,
)
from organvm_engine.contextmd.sync import sync_repo
from organvm_engine.sop.discover import SOPEntry


def _sop_entry(name, scope, path):
    return SOPEntry(
        path=Path(path),
        org="meta-organvm",
        repo="praxis-perpetua",
        filename=Path(path).name,
        title=f"SOP: {name}",
        doc_type="SOP",
        canonical=scope == "system",
        has_canonical_header=scope == "unknown",
        scope=scope,
        sop_name=name,
    )


@pytest.fixture
def mock_registry():
    return {
        "organs": {
            "ORGAN-I": {
                "name": "Theory",
                "organization": "organvm-i-theoria",
                "repositories": [
                    {"name": "repo-a", "tier": "flagship", "promotion_status": "GRADUATED"},
                    {"name": "repo-b", "tier": "standard", "promotion_status": "LOCAL"},
                ],
            },
        },
    }


class TestGenerator:
    def test_generate_repo_section(self, mock_registry):
        seed = {"repo": "repo-a", "produces": [{"target": "repo-b", "artifact": "docs"}]}
        section = generate_repo_section("repo-a", "organvm-i-theoria", mock_registry, seed)
        assert "## System Context" in section
        assert "## System Library" in section
        assert "**Organ:** ORGAN-I" in section
        assert "Produces" in section
        assert "repo-b" in section

    def test_directives_render_each_sop_once(self, mock_registry):
        """organvm-engine #76 step 2: a raw canonical + legacy pair renders
        one Active Directives row, not two."""
        seed = {"repo": "repo-a"}
        entries = [
            _sop_entry(
                "pitch-deck-rollout", "unknown",
                "/ws/4444J99/legacy-repo/docs/SOP--pitch-deck-rollout.md",
            ),
            _sop_entry(
                "pitch-deck-rollout", "system",
                "/ws/meta-organvm/praxis-perpetua/standards/SOP--pitch-deck-rollout.md",
            ),
        ]
        section = _build_sop_directives(entries)
        assert section.count("| pitch-deck-rollout |") == 1
        assert "| system | any | pitch-deck-rollout |" in section
        assert "| unknown | any | pitch-deck-rollout |" not in section

        # Same guarantee at the repo-section level (the CLAUDE.md path).
        full = generate_repo_section(
            "repo-a", "organvm-i-theoria", mock_registry, seed, sop_entries=entries,
        )
        assert full.count("| pitch-deck-rollout |") == 1

    def test_generate_organ_section(self, mock_registry):
        section = generate_organ_section("ORGAN-I", mock_registry, [])
        assert "## Organ Map" in section
        assert "2 repos" in section
        assert "1 flagship" in section

    def test_generate_workspace_section(self, mock_registry):
        section = generate_workspace_section(mock_registry, [])
        assert "## System Overview" in section
        assert "2 repos" in section
        assert "ORGAN-I" in section


class TestSync:
    @patch("organvm_engine.contextmd.sync._inject_section_result")
    def test_sync_repo(self, mock_inject, mock_registry):
        mock_inject.return_value = {"path": "/tmp/CLAUDE.md", "action": "updated", "change": None}
        res = sync_repo(Path("/tmp"), "repo-a", "org", mock_registry)
        assert res["action"] == "updated"
        assert "CLAUDE.md" in res["path"]
