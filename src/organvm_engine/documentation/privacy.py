"""Shared privacy matching for generated public documentation artifacts."""

from __future__ import annotations

import re
from typing import Any

REPOSITORY_CHARACTER = r"A-Za-z0-9._-"
PUBLIC_PROSE_REWRITES = (
    ("current personal profile/portfolio", "current individual profile/portfolio"),
    ("current personal profile", "current individual profile"),
    ("the personal profile", "the individual profile"),
    ("personal information management", "individual information management"),
)
PUBLIC_EXACT_REWRITES = {"contrib": "contribution"}


def bounded_identifier_pattern(
    identifiers: set[str],
    *,
    longer_public_identifiers: set[str] | None = None,
) -> str:
    """Build a longest-first, repository-token-bounded identifier pattern."""
    if not identifiers:
        return r"(?!)"
    alternatives = []
    for value in sorted(identifiers, key=lambda item: (-len(item), item)):
        # A known public name such as owner/project.md must win over the
        # private prefix owner/project; a longer private name still wins.
        longer_public = {
            public for public in (longer_public_identifiers or set())
            if len(public) > len(value) and public.casefold().startswith(value.casefold())
        }
        guard = (
            rf"(?!{bounded_identifier_pattern(longer_public)})"
            if longer_public else ""
        )
        alternatives.append(guard + re.escape(value))
    alternatives_pattern = "|".join(alternatives)
    return (
        rf"(?<![A-Za-z0-9_-])(?:{alternatives_pattern})"
        rf"(?=\.|$|[^{REPOSITORY_CHARACTER}])"
    )


def private_only_repository_slugs(
    private_full_identifiers: set[str],
    public_full_identifiers: set[str],
) -> set[str]:
    """Return private slugs that do not collide with a public repository slug."""
    private_slugs = {
        repository.split("/", 1)[-1] for repository in private_full_identifiers
    }
    public_slug_keys = {
        repository.split("/", 1)[-1].casefold()
        for repository in public_full_identifiers
    }
    return {
        slug for slug in private_slugs if slug.casefold() not in public_slug_keys
    }


def repository_reference_pattern(
    private_full_identifiers: set[str],
    private_only_slugs: set[str],
    public_full_identifiers: set[str],
) -> re.Pattern[str]:
    """Match every private-only reference while shielding complete public names."""
    if {value.casefold() for value in private_full_identifiers} & {
        value.casefold() for value in public_full_identifiers
    }:
        raise RuntimeError("A repository identifier is both public and private")
    public_slugs = {value.split("/", 1)[-1] for value in public_full_identifiers}
    # Consume a complete public bare slug, including interior dot components,
    # before searching inside it for a private suffix. Longer private slugs
    # still take precedence over a shorter public bare slug.
    return re.compile(
        rf"(?P<private_full>{bounded_identifier_pattern(private_full_identifiers, longer_public_identifiers=public_full_identifiers)})"
        rf"|(?P<public_full>{bounded_identifier_pattern(public_full_identifiers)}|{bounded_identifier_pattern(public_slugs, longer_public_identifiers=private_only_slugs)})"
        rf"|(?P<private_slug>{bounded_identifier_pattern(private_only_slugs, longer_public_identifiers=public_slugs)})",
        flags=re.IGNORECASE,
    )


def redact_private_references(
    value: Any,
    pattern: re.Pattern[str],
) -> Any:
    """Redact private references recursively while preserving public identities."""
    if isinstance(value, str):
        value = PUBLIC_EXACT_REWRITES.get(value, value)
        for original, replacement in PUBLIC_PROSE_REWRITES:
            value = value.replace(original, replacement)
        return pattern.sub(
            lambda match: (
                match.group(0)
                if match.lastgroup == "public_full"
                else "[private repository]"
            ),
            value,
        )
    if isinstance(value, list):
        return [redact_private_references(item, pattern) for item in value]
    if isinstance(value, dict):
        return {
            key: redact_private_references(item, pattern)
            for key, item in value.items()
        }
    return value
