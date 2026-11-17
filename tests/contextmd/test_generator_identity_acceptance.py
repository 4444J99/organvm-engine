"""Repeated repository names must not inherit another organ's context."""

import pytest

from organvm_engine.contextmd import generator


@pytest.fixture
def repeated_registry():
    return {"organs": {
        "ORGAN-I": {"name": "Theory", "directory": "local-theory", "repositories": [
            {"name": "shared", "org": "theory-owner", "tier": "flagship"},
        ]},
        "ORGAN-II": {"name": "Art", "directory": "local-art", "repositories": [
            {"name": "shared", "org": "art-owner", "tier": "standard"},
        ]},
    }}


@pytest.mark.parametrize("owner", ["art-owner", "local-art", "ORGAN-II"])
def test_generators_select_complete_repository_identity(repeated_registry, owner):
    section = generator.generate_repo_section(
        "shared", owner, repeated_registry, include_live_context=False,
    )
    assert "ORGAN-II" in section
    assert "ORGAN-I (Theory)" not in section
    assert "flagship" not in section
    agents = generator.generate_agents_section("shared", owner, repeated_registry)
    assert "ORGAN-II" in agents
    assert "Theory" not in agents


def test_generators_reject_ambiguous_owner(repeated_registry):
    with pytest.raises(ValueError, match="ambiguous context repository identity"):
        generator.generate_agents_section("shared", "unrelated", repeated_registry)
