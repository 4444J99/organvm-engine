"""Remote-parity and provenance tests for generated AGENTS dependency links."""

from organvm_engine.contextmd.generator import (
    generate_agents_section,
    resolve_agents_remote_references,
)


def _registry() -> dict:
    return {
        "organs": {
            "META-ORGANVM": {
                "name": "Meta",
                "repositories": [
                    {"name": "broker", "org": "organvm"},
                ],
            },
            "ORGAN-IV": {
                "name": "Orchestration",
                "repositories": [
                    {
                        "name": "schema-definitions",
                        "org": "organvm-iv-taxis",
                        "default_branch": "release/v2",
                    },
                ],
            },
        },
    }


def test_consumed_context_links_are_remote_valid_and_ref_encoded() -> None:
    seed = {
        "consumes": [
            {
                "type": "schema",
                "source": "external org/repo name",
                "ref": "feature/context #1",
            },
        ],
    }

    section = generate_agents_section("broker", "organvm", _registry(), seed)

    url = (
        "https://github.com/external%20org/repo%20name/"
        "blob/feature%2Fcontext%20%231/CLAUDE.md"
    )
    assert f"[`external org/repo name`]({url})" in section
    assert "../../external org/repo name/CLAUDE.md" not in section


def test_registry_default_branch_is_bound_in_remote_reference_receipt() -> None:
    seed = {
        "consumes": [
            {
                "type": "schema",
                "source": "organvm-iv-taxis/schema-definitions",
            },
        ],
    }

    references = resolve_agents_remote_references(
        seed,
        _registry(),
        default_owner="organvm",
    )

    assert references == [
        {
            "direction": "consumes",
            "repository": "organvm-iv-taxis/schema-definitions",
            "ref": "release/v2",
            "ref_source": "registry.default_branch",
            "path": "CLAUDE.md",
            "url": (
                "https://github.com/organvm-iv-taxis/schema-definitions/"
                "blob/release%2Fv2/CLAUDE.md"
            ),
        },
    ]


def test_produced_consumer_links_use_the_consumers_registered_owner() -> None:
    seed = {
        "produces": [
            {
                "type": "context",
                "consumers": [{"repo": "schema-definitions"}],
            },
        ],
    }

    section = generate_agents_section("broker", "organvm", _registry(), seed)

    assert (
        "[`schema-definitions`](https://github.com/organvm-iv-taxis/"
        "schema-definitions/blob/release%2Fv2/CLAUDE.md)"
    ) in section
    assert "../schema-definitions/CLAUDE.md" not in section


def test_same_name_consumer_prefers_default_owner() -> None:
    registry = _registry()
    registry["organs"]["META-ORGANVM"]["repositories"].extend([
        {"name": "shared", "org": "organvm", "default_branch": "owner-main"},
        {"name": "shared", "org": "other", "default_branch": "other-main"},
    ])
    references = resolve_agents_remote_references(
        {"produces": [{"type": "x", "consumers": [{"repo": "shared"}]}]},
        registry,
        default_owner="organvm",
    )
    assert references[0]["repository"] == "organvm/shared"
    assert references[0]["ref"] == "owner-main"


def test_same_name_consumer_without_owner_match_is_rejected() -> None:
    import pytest
    registry = _registry()
    registry["organs"]["META-ORGANVM"]["repositories"].extend([
        {"name": "shared", "org": "first"},
        {"name": "shared", "org": "second"},
    ])
    with pytest.raises(ValueError, match="Ambiguous consumer"):
        resolve_agents_remote_references(
            {"produces": [{"type": "x", "consumers": [{"repo": "shared"}]}]},
            registry,
            default_owner="unregistered",
        )


def test_unknown_repository_ref_falls_back_explicitly_to_main() -> None:
    seed = {
        "consumes": [
            {"type": "artifact", "source": "external/unknown"},
        ],
    }

    references = resolve_agents_remote_references(
        seed,
        _registry(),
        default_owner="organvm",
    )

    assert references[0]["ref"] == "main"
    assert references[0]["ref_source"] == "fallback.main"
    assert references[0]["url"].endswith("/blob/main/CLAUDE.md")


def test_rendered_and_receipted_references_share_normalized_identity() -> None:
    seed = {
        "consumes": [
            {"type": "artifact", "source": " organvm/unknown "},
        ],
        "produces": [
            {
                "type": "context",
                "consumers": [
                    {"repo": " unknown ", "github_org": " organvm "},
                ],
            },
        ],
    }

    references = resolve_agents_remote_references(
        seed,
        _registry(),
        default_owner="organvm",
    )
    section = generate_agents_section("broker", "organvm", _registry(), seed)

    assert {reference["url"] for reference in references} == {
        "https://github.com/organvm/unknown/blob/main/CLAUDE.md",
    }
    assert "https://github.com/%20organvm/unknown%20/" not in section
    for reference in references:
        assert reference["url"] in section


def test_registry_branch_is_not_borrowed_across_repository_owners() -> None:
    seed = {
        "consumes": [
            {"type": "artifact", "source": "external/schema-definitions"},
        ],
    }

    references = resolve_agents_remote_references(
        seed,
        _registry(),
        default_owner="organvm",
    )

    assert references == [
        {
            "direction": "consumes",
            "repository": "external/schema-definitions",
            "ref": "main",
            "ref_source": "fallback.main",
            "path": "CLAUDE.md",
            "url": (
                "https://github.com/external/schema-definitions/"
                "blob/main/CLAUDE.md"
            ),
        },
    ]
