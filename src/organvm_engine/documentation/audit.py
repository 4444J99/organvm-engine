"""Deterministic, read-only repository documentation audit."""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from html import unescape as html_unescape
from html.entities import html5
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from organvm_engine._stable_io import (
    StableReadError,
    StableReadSizeLimitError,
    read_stable_regular_bytes,
)
from organvm_engine.documentation.record import load_project_record, validate_project_record

DIMENSIONS = (
    "orientation",
    "technical_depth",
    "conceptual_depth",
    "commercial_relevance",
    "evidence",
    "seo_surface",
    "cross_linking",
)
SKIP_DIRS = frozenset(
    {".git", ".venv", "node_modules", "vendor", "dist", "build", "__pycache__"},
)
MAX_MARKDOWN_FILE_BYTES = 2_000_000
MAX_MARKDOWN_REPOSITORY_BYTES = 16_000_000
MAX_MARKDOWN_FILES = 4_096
MARKDOWN_FENCE = re.compile(r"^[ ]{0,3}(?P<fence>`{3,}|~{3,})")
MARKDOWN_BLOCKQUOTE = re.compile(r"^[ ]{0,3}>[ \t]?")
MARKDOWN_LIST_MARKER = re.compile(
    r"^(?P<indent>[ \t]*)(?P<marker>[-+*]|\d{1,9}[.)])(?P<spacing>[ \t]+)",
)
MARKDOWN_ESCAPABLE = frozenset(r"""!"#$%&'()*+,-./:;<=>?@[\]^_`{|}~""")
MARKDOWN_CHARACTER_REFERENCE = re.compile(
    r"&(?:#[xX][0-9A-Fa-f]{1,6}|#[0-9]{1,7}|[A-Za-z][A-Za-z0-9]{0,31});",
)
RAW_HTML_TYPE1_START = re.compile(
    r"^[ ]{0,3}<(?P<tag>script|pre|style|textarea)(?=[\t >]|\n|$)",
    flags=re.IGNORECASE,
)
RAW_HTML_TYPE1_END = re.compile(
    r"</(?:script|pre|style|textarea)>",
    flags=re.IGNORECASE,
)
RAW_HTML_TYPE2_START = re.compile(r"^[ ]{0,3}<!--")
RAW_HTML_TYPE2_END = re.compile(r"-->")
RAW_HTML_TYPE3_START = re.compile(r"^[ ]{0,3}<\?")
RAW_HTML_TYPE3_END = re.compile(r"\?>")
RAW_HTML_TYPE4_START = re.compile(r"^[ ]{0,3}<![A-Z]")
RAW_HTML_TYPE4_END = re.compile(r">")
RAW_HTML_TYPE5_START = re.compile(r"^[ ]{0,3}<!\[CDATA\[")
RAW_HTML_TYPE5_END = re.compile(r"\]\]>")
RAW_HTML_BLOCK_TAG_START = re.compile(
    r"^[ ]{0,3}</?(?:address|article|aside|base|basefont|blockquote|body|caption|"
    r"center|col|colgroup|dd|details|dialog|dir|div|dl|dt|fieldset|figcaption|"
    r"figure|footer|form|frame|frameset|h[1-6]|head|header|hr|html|iframe|legend|"
    r"li|link|main|menu|menuitem|nav|noframes|ol|optgroup|option|p|param|search|"
    r"section|summary|table|tbody|td|tfoot|th|thead|title|tr|track|ul)"
    r"(?=[\t >]|\n|/>|$)",
    flags=re.IGNORECASE,
)
RAW_HTML_TYPE7_START = re.compile(
    r"^[ ]{0,3}(?:"
    r"<[A-Za-z][A-Za-z0-9-]*"
    r"(?:[ \t]+[A-Za-z_:][A-Za-z0-9_.:-]*"
    r"(?:[ \t]*=[ \t]*(?:[^ \t\n\"'=<>`]+|'[^'\n]*'|\"[^\"\n]*\"))?)*"
    r"[ \t]*/?>|"
    r"</[A-Za-z][A-Za-z0-9-]*[ \t]*>)"
    r"[ \t]*(?:\n|$)",
)


def discover_repositories(workspace: str | Path) -> list[Path]:
    """Find repository roots below a workspace without descending into them."""
    workspace_path = Path(workspace).resolve()
    repositories: list[Path] = []
    for current, dirs, _files in os.walk(workspace_path):
        current_path = Path(current)
        dirs[:] = [
            item
            for item in dirs
            if item not in SKIP_DIRS or (current_path / item / ".git").exists()
        ]
        if (current_path / ".git").exists():
            repositories.append(current_path)
            dirs[:] = []
    return sorted(repositories)


def audit_repository(root: str | Path) -> dict[str, Any]:
    """Audit a repository's reader-mode documentation without mutating it."""
    root_path = Path(root).resolve()
    readme_path = _readme_path(root_path)
    readme = _read_bounded_markdown(readme_path) if readme_path else None
    if readme is None:
        readme_path = None
        readme = ""
    markdown_inputs, markdown_limit_exceeded = _markdown_inputs(root_path)
    markdown_files = [path for path, _text in markdown_inputs]
    corpus = "\n".join(text for _path, text in markdown_inputs)
    lowered = corpus.lower()
    readme_lower = readme.lower()
    valid_local_links, broken_local_links = _inspect_local_links(root_path, markdown_inputs)

    record_path = _record_path(root_path)
    record: dict[str, Any] | None = None
    record_errors: list[str] = []
    if record_path:
        try:
            record = load_project_record(record_path)
            record_errors = validate_project_record(record, root=root_path)
        except (OSError, ValueError) as exc:
            record_errors = [str(exc)]

    doc_class = str(record.get("documentation_class")) if record else _suggest_class(root_path, readme)
    signals = {
        "orientation": _score_orientation(readme_lower),
        "technical_depth": _score_categories(
            lowered,
            (
                ("architecture", "system design", "component boundary", "data flow"),
                ("install", "quick start", "getting started", "usage", "run locally"),
                ("test", "verification", "coverage", "quality assurance"),
                ("api", "interface", "schema", "endpoint", "protocol"),
                ("failure mode", "observability", "security", "technical debt", "operations"),
            ),
            bonus=_safe_markdown_file(
                root_path,
                root_path / "docs/audiences/technical.md",
            ),
        ),
        "conceptual_depth": _score_categories(
            lowered,
            (
                ("theory", "concept", "research question", "intellectual"),
                ("humanities", "aesthetic", "cultural", "epistemology", "ontology"),
                ("genealogy", "related work", "prior art", "tradition"),
                ("ethic", "pedagog", "authorship", "interpretation", "narrative"),
            ),
            bonus=_safe_markdown_file(
                root_path,
                root_path / "docs/audiences/humanities.md",
            ),
        ),
        "commercial_relevance": _score_categories(
            lowered,
            (
                ("problem statement", "primary user", "who experiences", "user need"),
                ("workflow", "inputs and outputs", "current workaround", "use case"),
                ("business model", "value proposition", "buyer", "customer"),
                ("integration", "risk", "constraint", "implementation requirement"),
                ("deployment status", "projected value", "operational", "industry"),
            ),
            bonus=_safe_markdown_file(
                root_path,
                root_path / "docs/audiences/business.md",
            ),
        ),
        "evidence": _score_categories(
            lowered,
            (
                ("test", "demo", "source", "revision history"),
                ("current state", "current status", "implementation status", "live status"),
                ("authorship", "contribution", "what anthony built", "initial condition"),
                ("limitation", "incomplete", "known issue", "not yet"),
                ("evidence record", "evidence", "verified", "proposed"),
            ),
            bonus=record_path is not None or _safe_markdown_file(
                root_path,
                root_path / "docs/evidence/README.md",
            ),
        ),
        "seo_surface": _score_seo(root_path, readme_lower, markdown_files),
        "cross_linking": _score_cross_linking(
            root_path,
            [text for _path, text in markdown_inputs],
            valid_local_links=len(valid_local_links),
        ),
    }
    findings = _findings(
        root_path,
        readme,
        record_path,
        record_errors,
        signals,
        broken_local_links,
        markdown_limit_exceeded,
    )

    return {
        "repository": root_path.name,
        "path": str(root_path),
        "documentation_class": doc_class,
        "class_source": "project-record" if record else "heuristic",
        "has_readme": readme_path is not None,
        "has_project_record": record_path is not None,
        "markdown_files": len(markdown_files),
        "markdown_input_limit_exceeded": markdown_limit_exceeded,
        "signals": signals,
        "signal_semantics": "structural markers only; not a quality score",
        "record_errors": record_errors,
        "findings": findings,
    }


def _readme_path(root: Path) -> Path | None:
    try:
        candidates = [
            path
            for path in root.iterdir()
            if _safe_markdown_file(root, path)
            and path.name.casefold() == "readme.md"
            and path.stat().st_size <= MAX_MARKDOWN_FILE_BYTES
        ]
    except OSError:
        return None
    return min(candidates, key=lambda path: (path.name != "README.md", path.name), default=None)


def _record_path(root: Path) -> Path | None:
    for name in ("project-record.yml", "project-record.yaml", "project-record.json"):
        path = root / name
        if _safe_audit_file(root, path):
            return path
    return None


def _markdown_inputs(root: Path) -> tuple[list[tuple[Path, str]], bool]:
    """Read a deterministic repository-bounded Markdown corpus."""
    inputs: list[tuple[Path, str]] = []
    total_bytes = 0
    for current, dirs, names in os.walk(root):
        dirs[:] = sorted(name for name in dirs if name not in SKIP_DIRS)
        current_path = Path(current)
        for name in sorted(names):
            if Path(name).suffix.casefold() != ".md":
                continue
            path = current_path / name
            try:
                if not _safe_markdown_file(root, path):
                    continue
            except OSError:
                continue
            try:
                payload = _read_bounded_markdown_payload(path)
            except StableReadSizeLimitError:
                return inputs, True
            if payload is None:
                continue
            text, byte_count = payload
            if (
                len(inputs) >= MAX_MARKDOWN_FILES
                or total_bytes + byte_count > MAX_MARKDOWN_REPOSITORY_BYTES
            ):
                return inputs, True
            inputs.append((path, text))
            total_bytes += byte_count
    return inputs, False


def _score_orientation(readme_lower: str) -> int:
    if not readme_lower:
        return 0
    score = 1
    first_screen = readme_lower[:1800]
    if any(term in first_screen for term in ("overview", "what is", "what am i looking at", "purpose")):
        score += 1
    if any(term in readme_lower for term in ("current state", "current status", "implementation status", "project status")):
        score += 1
    if any(term in readme_lower for term in ("choose your reading path", "read this project your way", "i am reading as")):
        score += 1
    return min(4, score)


def _score_categories(
    text: str,
    categories: tuple[tuple[str, ...], ...],
    *,
    bonus: bool = False,
) -> int:
    hits = sum(any(term in text for term in category) for category in categories)
    if bonus:
        hits += 1
    if hits == 0:
        return 0
    if hits == 1:
        return 1
    if hits == 2:
        return 2
    if hits <= 4:
        return 3
    return 4


def _score_seo(root: Path, readme_lower: str, markdown_files: list[Path]) -> int:
    score = 0
    if readme_lower and len(readme_lower[:900].split()) >= 20:
        score += 1
    relative_paths = {path.relative_to(root).as_posix() for path in markdown_files}
    if any(path.startswith("docs/audiences/") for path in relative_paths):
        score += 1
    if any(path.startswith("docs/concepts/") for path in relative_paths):
        score += 1
    if any(path.startswith("docs/industries/") for path in relative_paths):
        score += 1
    return min(4, score)


def _score_cross_linking(root: Path, documents: list[str], *, valid_local_links: int) -> int:
    links = [
        link
        for document in documents
        for link in _markdown_destinations(document)
        if not link.startswith("#")
    ]
    if not links:
        return 0
    score = 1
    external_repo = [link for link in links if "github.com/" in link]
    if valid_local_links >= 3:
        score += 1
    if len(external_repo) >= 2:
        score += 1
    typed_graph = any(
        term in document.lower()
        for document in documents
        for term in ("related systems", "dependencies", "implemented by", "canonical project")
    )
    if typed_graph and _safe_audit_directory(root, root / "docs/audiences"):
        score += 1
    return min(4, score)


def _inspect_local_links(
    root: Path,
    markdown_inputs: list[tuple[Path, str]],
) -> tuple[set[Path], list[str]]:
    valid: set[Path] = set()
    broken: list[str] = []
    for source, text in markdown_inputs:
        for raw_target in _markdown_destinations(text):
            target = raw_target.strip().strip("<>")
            if not target or target.startswith("#") or target.startswith("//"):
                continue
            try:
                parsed = urlparse(target)
            except ValueError:
                broken.append(f"{source.relative_to(root)} -> {target}")
                continue
            if parsed.scheme:
                continue
            path_text = unquote(target.split("#", 1)[0].split("?", 1)[0])
            if not path_text:
                continue
            try:
                candidate = (source.parent / path_text).resolve()
            except (OSError, RuntimeError, ValueError):
                broken.append(f"{source.relative_to(root)} -> {target}")
                continue
            try:
                candidate.relative_to(root)
            except ValueError:
                broken.append(f"{source.relative_to(root)} -> {target}")
                continue
            if candidate.exists():
                valid.add(candidate)
            else:
                broken.append(f"{source.relative_to(root)} -> {target}")
    return valid, sorted(set(broken))


def _markdown_destinations(text: str) -> list[str]:
    """Extract inline Markdown link destinations without swallowing link titles.

    This intentionally stays smaller than a renderer while handling the pieces
    needed for repository link validation: angle-bracket destinations, escaped
    characters, balanced parentheses, and optional whitespace-separated titles.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n").expandtabs(4)
    text = _mask_markdown_html_blocks(text)
    text = _mask_markdown_block_code(text)
    text = _mask_markdown_html_comments(text)
    text = _mask_markdown_code_spans(text)
    text, reference_destinations = _reference_destinations(text)
    destinations: list[str] = list(reference_destinations)
    for position in _markdown_link_destination_starts(text):
        while position < len(text) and text[position] in " \t\n":
            position += 1
        if position >= len(text):
            continue

        destination: list[str] = []
        if text[position] == "<":
            position += 1
            escaped = False
            closed = False
            while position < len(text):
                character = text[position]
                if escaped:
                    destination.append(character)
                    escaped = False
                    position += 1
                elif (
                    character == "\\"
                    and position + 1 < len(text)
                    and text[position + 1] in MARKDOWN_ESCAPABLE
                ):
                    destination.append(character)
                    escaped = True
                    position += 1
                elif character == ">":
                    position += 1
                    closed = True
                    break
                elif character in "<\n":
                    break
                else:
                    destination.append(character)
                    position += 1
            if not closed:
                continue
        else:
            depth = 0
            escaped = False
            while position < len(text):
                character = text[position]
                if escaped:
                    destination.append(character)
                    escaped = False
                    position += 1
                elif (
                    character == "\\"
                    and position + 1 < len(text)
                    and text[position + 1] in MARKDOWN_ESCAPABLE
                ):
                    destination.append(character)
                    escaped = True
                    position += 1
                elif character == "(":
                    depth += 1
                    destination.append(character)
                    position += 1
                elif character == ")":
                    if depth == 0:
                        break
                    depth -= 1
                    destination.append(character)
                    position += 1
                elif character.isspace() and depth == 0:
                    break
                else:
                    destination.append(character)
                    position += 1

        rendered = _markdown_unescape("".join(destination))
        if rendered and _markdown_link_has_closing_delimiter(text, position):
            destinations.append(rendered)
    return destinations


def _markdown_link_destination_starts(text: str) -> Iterator[int]:
    """Yield inline-link destination starts in one forward bracket pass."""
    open_brackets = 0
    for position, character in enumerate(text):
        if character not in "[]" or _markdown_character_is_escaped(text, position):
            continue
        if character == "[":
            open_brackets += 1
            continue
        if open_brackets == 0:
            continue
        open_brackets -= 1
        if text.startswith("](", position):
            yield position + 2


def _markdown_link_has_closing_delimiter(text: str, position: int) -> bool:
    """Return whether a parsed destination has a valid outer closing delimiter."""
    if position < len(text) and text[position] == ")":
        return True
    if position >= len(text) or not text[position].isspace():
        return False
    while position < len(text) and text[position].isspace():
        position += 1
    if position < len(text) and text[position] == ")":
        return True
    if position >= len(text) or text[position] not in "\"'(":
        return False
    opener = text[position]
    closer = ")" if opener == "(" else opener
    position += 1
    while position < len(text):
        if (
            text[position] == "\\"
            and position + 1 < len(text)
            and text[position + 1] in MARKDOWN_ESCAPABLE
        ):
            position += 2
            continue
        if text[position] == closer:
            position += 1
            break
        position += 1
    else:
        return False
    while position < len(text) and text[position].isspace():
        position += 1
    return position < len(text) and text[position] == ")"


def _markdown_character_is_escaped(text: str, position: int) -> bool:
    """Return whether a Markdown punctuation character has an odd slash prefix."""
    backslashes = 0
    position -= 1
    while position >= 0 and text[position] == "\\":
        backslashes += 1
        position -= 1
    return backslashes % 2 == 1


def _safe_markdown_file(root: Path, path: Path) -> bool:
    """Reject symlinked Markdown inputs and paths resolving outside the root."""
    return _safe_audit_file(root, path)


def _safe_audit_directory(root: Path, path: Path) -> bool:
    """Require a contained directory reached without traversing a symlink."""
    try:
        relative = path.relative_to(root)
        current = root
        for part in relative.parts:
            current = current / part
            if current.is_symlink() or not current.is_dir():
                return False
        path.resolve(strict=True).relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return False
    return True


def _read_bounded_markdown(path: Path) -> str | None:
    """Read at most the documented Markdown input limit, including races."""
    try:
        payload = _read_bounded_markdown_payload(path)
    except StableReadSizeLimitError:
        return None
    return payload[0] if payload is not None else None


def _read_bounded_markdown_payload(path: Path) -> tuple[str, int] | None:
    """Read one stable, bounded Markdown input through no-follow binding."""
    try:
        payload = read_stable_regular_bytes(
            path,
            maximum_bytes=MAX_MARKDOWN_FILE_BYTES,
        )
    except StableReadSizeLimitError:
        raise
    except StableReadError:
        return None
    return payload.decode("utf-8", errors="replace"), len(payload)


def _safe_audit_file(root: Path, path: Path) -> bool:
    """Return whether an audit input is a regular in-repository file."""
    try:
        if (
            not _safe_audit_directory(root, path.parent)
            or path.is_symlink()
            or not path.is_file()
        ):
            return False
        path.resolve(strict=True).relative_to(root)
    except (OSError, ValueError):
        return False
    return True


def _reference_destinations(text: str) -> tuple[str, list[str]]:
    """Resolve destinations used through CommonMark-style reference links."""
    definitions: dict[str, str] = {}
    visible_lines: list[str] = []
    visible_prefixes: list[tuple[tuple[str, int], ...]] = []
    lines = text.splitlines(keepends=True)
    index = 0
    paragraph_open = False
    active_prefixes: tuple[tuple[str, int], ...] = ()
    paragraph_prefixes: tuple[tuple[str, int], ...] = ()
    while index < len(lines):
        line = lines[index]
        if not line.strip(" \t\r\n"):
            visible_lines.append(line)
            visible_prefixes.append(())
            active_prefixes = _markdown_prefixes_after_unmarked_blank(
                active_prefixes,
            )
            paragraph_open = False
            paragraph_prefixes = ()
            index += 1
            continue

        if paragraph_open:
            paragraph_line, matched = _markdown_apply_container_prefixes_partial(
                line,
                paragraph_prefixes,
            )
            if not paragraph_line.strip(" \t\r\n"):
                visible_lines.append(line)
                visible_prefixes.append(paragraph_prefixes)
                paragraph_open = False
                paragraph_prefixes = ()
                index += 1
                continue
            if matched == len(paragraph_prefixes) and _markdown_is_setext_underline(
                paragraph_line,
            ):
                visible_lines.append(line)
                visible_prefixes.append(paragraph_prefixes[:matched])
                active_prefixes = paragraph_prefixes[:matched]
                paragraph_open = False
                paragraph_prefixes = ()
                index += 1
                continue
            if matched < len(paragraph_prefixes):
                if not _markdown_starts_block_after_container(paragraph_line):
                    visible_lines.append(line)
                    visible_prefixes.append(paragraph_prefixes)
                    index += 1
                    continue
            elif not _markdown_interrupts_lazy_continuation(paragraph_line):
                visible_lines.append(line)
                visible_prefixes.append(paragraph_prefixes)
                index += 1
                continue
            paragraph_open = False
            paragraph_prefixes = ()

        remainder, matched = _markdown_apply_container_prefixes_partial(
            line,
            active_prefixes,
        )
        common_prefixes = active_prefixes[:matched]
        definition_line, additional_prefixes = _markdown_reference_containers(
            remainder,
        )
        container_prefixes = (*common_prefixes, *additional_prefixes)
        active_prefixes = container_prefixes
        if not definition_line.strip(" \t\r\n"):
            visible_lines.append(line)
            visible_prefixes.append(container_prefixes)
            paragraph_open = False
            paragraph_prefixes = ()
            index += 1
            continue

        parsed = _parse_reference_definition(
            lines,
            index,
            initial_value=definition_line,
            container_prefixes=container_prefixes,
        )
        if parsed is None:
            visible_lines.append(line)
            visible_prefixes.append(container_prefixes)
            paragraph_open = _markdown_opens_paragraph(definition_line)
            paragraph_prefixes = container_prefixes if paragraph_open else ()
            index += 1
            continue

        label, destination, consumed_lines = parsed
        definitions.setdefault(label, _markdown_unescape(destination))
        for consumed in lines[index : index + consumed_lines]:
            visible_lines.append(
                "".join("\n" if char == "\n" else " " for char in consumed),
            )
            visible_prefixes.append(container_prefixes)
        index += consumed_lines
        paragraph_open = False
        paragraph_prefixes = ()

    visible = "".join(visible_lines)
    destinations: list[str] = []
    for label in _markdown_reference_usages(
        visible,
        line_prefixes=tuple(visible_prefixes),
    ):
        destination = definitions.get(label)
        if destination is not None:
            destinations.append(destination)
    return visible, destinations


def _parse_reference_definition(
    lines: list[str],
    index: int,
    *,
    initial_value: str | None = None,
    container_prefixes: tuple[tuple[str, int], ...] | None = None,
) -> tuple[str, str, int] | None:
    """Parse one complete reference definition, including a multiline label."""
    if initial_value is None or container_prefixes is None:
        value, parsed_prefixes = _markdown_reference_containers(lines[index])
        container_prefixes = parsed_prefixes
    else:
        value = initial_value
    position = _markdown_optional_indent_end(value)
    if position is None or position >= len(value) or value[position] != "[":
        return None

    label: list[str] = []
    label_length = 0
    line_index = index
    position += 1
    while True:
        line_end = _markdown_line_end(value)
        while position < line_end:
            character = value[position]
            if (
                character == "\\"
                and position + 1 < line_end
                and value[position + 1] in MARKDOWN_ESCAPABLE
            ):
                label.extend((character, value[position + 1]))
                label_length += 2
                position += 2
                continue
            if character == "[":
                return None
            if character == "]":
                break
            label.append(character)
            label_length += 1
            position += 1
        else:
            if (
                not value.endswith("\n")
                or label_length >= 999
                or not value[:line_end].strip(" \t")
            ):
                return None
            label.append("\n")
            label_length += 1
            line_index += 1
            if line_index >= len(lines):
                return None
            continuation = _markdown_apply_reference_containers_or_lazy(
                lines[line_index],
                container_prefixes,
            )
            if continuation is None:
                return None
            value = continuation
            position = 0
            continue
        break

    if label_length > 999 or position + 1 >= len(value) or value[position + 1] != ":":
        return None
    normalized_label = _normalize_reference_label("".join(label))
    if not normalized_label:
        return None

    position += 2
    while position < _markdown_line_end(value) and value[position] in " \t":
        position += 1
    if position == _markdown_line_end(value):
        line_index += 1
        if line_index >= len(lines):
            return None
        continuation = _markdown_apply_reference_containers_or_lazy(
            lines[line_index],
            container_prefixes,
        )
        if continuation is None:
            return None
        value = continuation
        position = _markdown_spaces_tabs_end(value)

    parsed_destination = _parse_reference_destination(value, position)
    if parsed_destination is None:
        return None
    destination, position = parsed_destination
    line_end = _markdown_line_end(value)
    suffix_start = position
    while position < line_end and value[position] in " \t":
        position += 1

    if position < line_end:
        if suffix_start == position:
            return None
        title_end = _parse_reference_title(
            lines,
            line_index,
            value,
            position,
            container_prefixes,
        )
        if title_end is None:
            return None
        line_index = title_end
    elif line_index + 1 < len(lines):
        possible_title = _markdown_apply_reference_containers_or_lazy(
            lines[line_index + 1],
            container_prefixes,
        )
        if possible_title is not None:
            title_start = _markdown_spaces_tabs_end(possible_title)
            if (
                title_start < _markdown_line_end(possible_title)
                and possible_title[title_start] in "\"'("
            ):
                title_end = _parse_reference_title(
                    lines,
                    line_index + 1,
                    possible_title,
                    title_start,
                    container_prefixes,
                )
                if title_end is not None:
                    line_index = title_end

    return normalized_label, destination, line_index - index + 1


def _parse_reference_destination(value: str, position: int) -> tuple[str, int] | None:
    """Parse a reference destination without accepting a partial line prefix."""
    line_end = _markdown_line_end(value)
    if position >= line_end:
        return None
    destination: list[str] = []
    if value[position] == "<":
        position += 1
        while position < line_end:
            character = value[position]
            if (
                character == "\\"
                and position + 1 < line_end
                and value[position + 1] in MARKDOWN_ESCAPABLE
            ):
                destination.extend((character, value[position + 1]))
                position += 2
                continue
            if character == ">":
                return "".join(destination), position + 1
            if character == "<":
                return None
            destination.append(character)
            position += 1
        return None

    depth = 0
    while position < line_end and not value[position].isspace():
        character = value[position]
        if (
            character == "\\"
            and position + 1 < line_end
            and value[position + 1] in MARKDOWN_ESCAPABLE
        ):
            destination.extend((character, value[position + 1]))
            position += 2
            continue
        if character == "(":
            depth += 1
            if depth > 32:
                return None
        elif character == ")":
            if depth == 0:
                break
            depth -= 1
        destination.append(character)
        position += 1
    if not destination or depth:
        return None
    return "".join(destination), position


def _parse_reference_title(
    lines: list[str],
    line_index: int,
    value: str,
    position: int,
    container_prefixes: tuple[tuple[str, int], ...],
) -> int | None:
    """Return the last line of a complete optional reference title."""
    opener = value[position]
    closer = ")" if opener == "(" else opener
    position += 1
    while True:
        line_end = _markdown_line_end(value)
        while position < line_end:
            character = value[position]
            if (
                character == "\\"
                and position + 1 < line_end
                and value[position + 1] in MARKDOWN_ESCAPABLE
            ):
                position += 2
                continue
            if opener == "(" and character == "(":
                return None
            if character == closer:
                position += 1
                while position < line_end and value[position] in " \t":
                    position += 1
                return line_index if position == line_end else None
            position += 1
        if not value.endswith("\n") or not value[:line_end].strip(" \t"):
            return None
        line_index += 1
        if line_index >= len(lines):
            return None
        continuation = _markdown_apply_reference_containers_or_lazy(
            lines[line_index],
            container_prefixes,
        )
        if continuation is None:
            return None
        value = continuation
        position = 0


def _markdown_optional_indent_end(value: str) -> int | None:
    """Return the end of up to three leading indentation columns."""
    position = 0
    columns = 0
    while position < len(value) and value[position] in " \t":
        if value[position] == " ":
            columns += 1
        else:
            columns += 4 - (columns % 4)
        if columns > 3:
            return None
        position += 1
    return position


def _markdown_spaces_tabs_end(value: str) -> int:
    """Return the end of an unrestricted spaces-and-tabs prefix."""
    position = 0
    while position < len(value) and value[position] in " \t":
        position += 1
    return position


def _markdown_line_end(value: str) -> int:
    """Return a logical line's content end, excluding its newline."""
    return len(value) - 1 if value.endswith("\n") else len(value)


def _markdown_reference_usages(
    text: str,
    *,
    line_prefixes: tuple[tuple[tuple[str, int], ...], ...] | None = None,
) -> Iterator[str]:
    """Yield normalized full, collapsed, and shortcut reference labels."""
    position = 0
    line_start = 0
    line_number = 0
    line_limit = text.find("\n") + 1
    if line_limit == 0:
        line_limit = len(text) + 1
    line_container_prefixes: tuple[tuple[str, int], ...] | None = None
    while (start := text.find("[", position)) >= 0:
        if _markdown_character_is_escaped(text, start) or (
            start > 0
            and text[start - 1] == "!"
            and not _markdown_character_is_escaped(text, start - 1)
        ):
            position = start + 1
            continue
        while start >= line_limit:
            line_start = line_limit
            line_number += 1
            newline = text.find("\n", line_start)
            line_limit = newline + 1 if newline >= 0 else len(text) + 1
            line_container_prefixes = None
        if line_container_prefixes is None:
            if line_prefixes is not None and line_number < len(line_prefixes):
                line_container_prefixes = line_prefixes[line_number]
            else:
                line_end = min(line_limit, len(text))
                _content, prefixes = _markdown_reference_containers(
                    text[line_start:line_end],
                )
                line_container_prefixes = prefixes
        primary = _parse_markdown_link_label(
            text,
            start,
            container_prefixes=line_container_prefixes,
        )
        if primary is None:
            position = start + 1
            continue
        primary_label, primary_end = primary
        if primary_end < len(text) and text[primary_end] == "(":
            position = primary_end + 1
            continue
        if primary_end < len(text) and text[primary_end] == "[":
            if primary_end + 1 < len(text) and text[primary_end + 1] == "]":
                yield _normalize_reference_label(primary_label)
                position = primary_end + 2
                continue
            secondary = _parse_markdown_link_label(
                text,
                primary_end,
                container_prefixes=line_container_prefixes,
            )
            if secondary is not None:
                secondary_label, secondary_end = secondary
                yield _normalize_reference_label(secondary_label)
                position = secondary_end
                continue
            position = primary_end + 1
            continue
        yield _normalize_reference_label(primary_label)
        position = primary_end


def _parse_markdown_link_label(
    text: str,
    start: int,
    *,
    container_prefixes: tuple[tuple[str, int], ...] = (),
) -> tuple[str, int] | None:
    """Parse a multiline link label while rejecting nested unescaped brackets."""
    label: list[str] = []
    position = start + 1
    label_length = 0
    while position < len(text) and label_length <= 999:
        character = text[position]
        if (
            character == "\\"
            and position + 1 < len(text)
            and text[position + 1] in MARKDOWN_ESCAPABLE
        ):
            label.extend((character, text[position + 1]))
            label_length += 2
            position += 2
            continue
        if character == "[":
            return None
        if character == "\n":
            next_position = position + 1
            next_line_end = text.find("\n", next_position)
            if next_line_end < 0:
                next_line_end = len(text)
            else:
                next_line_end += 1
            next_line = text[next_position:next_line_end]
            continuation = _markdown_apply_reference_containers_or_lazy(
                next_line,
                container_prefixes,
            )
            if continuation is None:
                return None
            label.append(character)
            label_length += 1
            position = next_line_end - len(continuation)
            continue
        if character == "]":
            rendered = "".join(label)
            if label_length <= 999 and _normalize_reference_label(rendered):
                return rendered, position + 1
            return None
        label.append(character)
        label_length += 1
        position += 1
    return None


def _markdown_reference_containers(
    value: str,
) -> tuple[str, tuple[tuple[str, int], ...]]:
    """Strip quote/list prefixes and retain operations for a continuation line."""
    prefixes: list[tuple[str, int]] = []
    while True:
        quote = MARKDOWN_BLOCKQUOTE.match(value)
        if quote is not None:
            prefixes.append(("quote", 0))
            value = value[quote.end() :]
            continue
        list_prefix = _markdown_list_prefix(value)
        if list_prefix is None:
            break
        prefix_end, content_indent = list_prefix
        prefixes.append(("indent", content_indent))
        value = value[prefix_end:]
    return value, tuple(prefixes)


def _markdown_apply_container_prefixes_partial(
    value: str,
    prefixes: tuple[tuple[str, int], ...],
) -> tuple[str, int]:
    """Apply the longest retained prefix sequence and return its length."""
    matched = 0
    for kind, columns in prefixes:
        if kind == "quote":
            quote = MARKDOWN_BLOCKQUOTE.match(value)
            if quote is None:
                break
            value = value[quote.end() :]
        else:
            if _markdown_indent_columns(value) < columns:
                break
            value = _markdown_remove_indent(value, columns)
        matched += 1
    return value, matched


def _markdown_apply_fence_containers(
    value: str,
    prefixes: tuple[tuple[str, int], ...],
) -> str | None:
    """Apply an open fence's exact containers, allowing blank list padding."""
    for kind, columns in prefixes:
        if kind == "quote":
            quote = MARKDOWN_BLOCKQUOTE.match(value)
            if quote is None:
                return None
            value = value[quote.end() :]
            continue
        if _markdown_indent_columns(value) >= columns:
            value = _markdown_remove_indent(value, columns)
            continue
        if not value.strip(" \t\r\n"):
            return value
        return None
    return value


def _markdown_apply_reference_containers_or_lazy(
    value: str,
    prefixes: tuple[tuple[str, int], ...],
) -> str | None:
    """Apply definition containers, allowing a valid lazy paragraph line."""
    for kind, columns in prefixes:
        if kind == "quote":
            quote = MARKDOWN_BLOCKQUOTE.match(value)
            if quote is not None:
                value = value[quote.end() :]
                continue
        elif _markdown_indent_columns(value) >= columns:
            value = _markdown_remove_indent(value, columns)
            continue
        if not value.strip(" \t\r\n") or _markdown_starts_block_after_container(value):
            return None
        return value
    if not value.strip(" \t\r\n") or _markdown_interrupts_lazy_continuation(value):
        return None
    return value


def _normalize_reference_label(label: str) -> str:
    return re.sub(r"\s+", " ", label.strip()).casefold()


def _markdown_unescape(value: str) -> str:
    """Decode CommonMark punctuation escapes and complete character references."""
    rendered: list[str] = []
    position = 0
    while position < len(value):
        if (
            value[position] == "\\"
            and position + 1 < len(value)
            and value[position + 1] in MARKDOWN_ESCAPABLE
        ):
            rendered.append(value[position + 1])
            position += 2
            continue
        if value[position] == "&":
            reference = MARKDOWN_CHARACTER_REFERENCE.match(value, position)
            if reference is not None:
                rendered.append(_decode_markdown_character_reference(reference.group(0)))
                position = reference.end()
                continue
        rendered.append(value[position])
        position += 1
    return "".join(rendered)


def _decode_markdown_character_reference(reference: str) -> str:
    """Decode one already validated semicolon-terminated character reference."""
    if reference.startswith("&#"):
        return html_unescape(reference)
    return html5.get(reference[1:], reference)


def _mask_markdown_html_comments(text: str) -> str:
    """Mask rendered-out HTML comments while retaining source line structure."""
    characters = list(text)
    position = 0
    while (start := text.find("<!--", position)) >= 0:
        closing = text.find("-->", start + 4)
        if closing < 0:
            break
        end = closing + 3
        for index in range(start, end):
            if characters[index] != "\n":
                characters[index] = " "
        position = end
    return "".join(characters)


def _mask_markdown_html_blocks(text: str) -> str:
    """Mask CommonMark raw HTML blocks that do not render Markdown links."""

    def masked(value: str) -> str:
        return "".join("\n" if character == "\n" else " " for character in value)

    def masked_content(value: str, content: str) -> str:
        """Mask block content while retaining exact container prefixes."""
        prefix_length = len(value) - len(content)
        hidden = list(masked(content))
        for index, character in enumerate(hidden):
            if character != "\n":
                # Keep list-marker padding and downstream block boundaries without
                # exposing any link syntax from the raw HTML payload.
                hidden[index] = "<"
                break
        return value[:prefix_length] + "".join(hidden)

    visible: list[str] = []
    end_pattern: re.Pattern[str] | None = None
    blank_terminated = False
    block_prefixes: tuple[tuple[str, int], ...] = ()
    active_prefixes: tuple[tuple[str, int], ...] = ()
    paragraph_open = False
    paragraph_prefixes: tuple[tuple[str, int], ...] = ()
    fence_character: str | None = None
    fence_length = 0
    fence_prefixes: tuple[tuple[str, int], ...] = ()
    for line in text.splitlines(keepends=True):
        if end_pattern is not None or blank_terminated:
            block_line = _markdown_apply_fence_containers(line, block_prefixes)
            if block_line is None:
                end_pattern = None
                blank_terminated = False
                block_prefixes = ()
            elif blank_terminated and not block_line.strip(" \t\n"):
                blank_terminated = False
                block_prefixes = ()
                visible.append(line)
                paragraph_open = False
                paragraph_prefixes = ()
                continue
            else:
                visible.append(masked_content(line, block_line))
                if end_pattern is not None and end_pattern.search(block_line):
                    end_pattern = None
                    block_prefixes = ()
                continue

        if fence_character is not None:
            fenced_line = _markdown_apply_fence_containers(line, fence_prefixes)
            if fenced_line is not None:
                visible.append(line)
                match = MARKDOWN_FENCE.match(fenced_line)
                if match is not None:
                    fence = match.group("fence")
                    if (
                        fence[0] == fence_character
                        and len(fence) >= fence_length
                        and not fenced_line[match.end() :].strip()
                    ):
                        fence_character = None
                        fence_length = 0
                        fence_prefixes = ()
                continue
            fence_character = None
            fence_length = 0
            _remainder, matched = _markdown_apply_container_prefixes_partial(
                line,
                fence_prefixes,
            )
            active_prefixes = fence_prefixes[:matched]
            fence_prefixes = ()

        if not line.strip(" \t\r\n"):
            visible.append(line)
            active_prefixes = _markdown_prefixes_after_unmarked_blank(
                active_prefixes,
            )
            paragraph_open = False
            paragraph_prefixes = ()
            continue

        if paragraph_open:
            paragraph_line, matched = _markdown_apply_container_prefixes_partial(
                line,
                paragraph_prefixes,
            )
            if not paragraph_line.strip(" \t\r\n"):
                visible.append(line)
                paragraph_open = False
                paragraph_prefixes = ()
                continue
            if matched == len(paragraph_prefixes) and _markdown_is_setext_underline(
                paragraph_line,
            ):
                visible.append(line)
                active_prefixes = paragraph_prefixes[:matched]
                paragraph_open = False
                paragraph_prefixes = ()
                continue
            type7_after_exit = (
                matched < len(paragraph_prefixes)
                and RAW_HTML_TYPE7_START.fullmatch(paragraph_line) is not None
            )
            if matched < len(paragraph_prefixes):
                if (
                    not type7_after_exit
                    and not _markdown_starts_block_after_container(paragraph_line)
                ):
                    visible.append(line)
                    continue
            elif not _markdown_interrupts_lazy_continuation(paragraph_line):
                visible.append(line)
                continue
            paragraph_open = False
            paragraph_prefixes = ()

        remainder, matched = _markdown_apply_container_prefixes_partial(
            line,
            active_prefixes,
        )
        common_prefixes = active_prefixes[:matched]
        block_line, additional_prefixes = _markdown_reference_containers(remainder)
        prefixes = (*common_prefixes, *additional_prefixes)
        active_prefixes = prefixes
        match = MARKDOWN_FENCE.match(block_line)
        if match is not None:
            opening_fence = match.group("fence")
            info_string = block_line[match.end() :].rstrip("\r\n")
            if opening_fence[0] == "`" and _markdown_has_unescaped_backtick(
                info_string,
            ):
                match = None
        if match is not None:
            fence = match.group("fence")
            fence_character = fence[0]
            fence_length = len(fence)
            fence_prefixes = prefixes
            visible.append(line)
            paragraph_open = False
            paragraph_prefixes = ()
            continue
        if _markdown_indent_columns(block_line) >= 4:
            visible.append(line)
            paragraph_open = False
            paragraph_prefixes = ()
            continue
        explicit_end: re.Pattern[str] | None = None
        for start_pattern, candidate_end in (
            (RAW_HTML_TYPE1_START, RAW_HTML_TYPE1_END),
            (RAW_HTML_TYPE2_START, RAW_HTML_TYPE2_END),
            (RAW_HTML_TYPE3_START, RAW_HTML_TYPE3_END),
            (RAW_HTML_TYPE4_START, RAW_HTML_TYPE4_END),
            (RAW_HTML_TYPE5_START, RAW_HTML_TYPE5_END),
        ):
            if start_pattern.match(block_line):
                explicit_end = candidate_end
                break
        if explicit_end is not None:
            end_pattern = explicit_end
            block_prefixes = prefixes
            visible.append(masked_content(line, block_line))
            if end_pattern.search(block_line):
                end_pattern = None
                block_prefixes = ()
            paragraph_open = False
            paragraph_prefixes = ()
            continue

        if RAW_HTML_BLOCK_TAG_START.match(block_line) or (
            RAW_HTML_TYPE7_START.fullmatch(block_line)
        ):
            blank_terminated = True
            block_prefixes = prefixes
            visible.append(masked_content(line, block_line))
            paragraph_open = False
            paragraph_prefixes = ()
            continue

        visible.append(line)
        stripped = block_line.strip(" \t\n")
        paragraph_open = _markdown_opens_paragraph(block_line) or stripped.startswith("<")
        paragraph_prefixes = prefixes if paragraph_open else ()

    return "".join(visible)


def _mask_markdown_code(text: str) -> str:
    """Mask block and inline code while retaining source line structure."""
    return _mask_markdown_code_spans(_mask_markdown_block_code(text))


def _mask_markdown_block_code(text: str) -> str:
    """Mask fenced and indented code inside Markdown block containers."""

    def masked(value: str) -> str:
        return "".join("\n" if character == "\n" else " " for character in value)

    visible: list[str] = []
    active_prefixes: tuple[tuple[str, int], ...] = ()
    paragraph_prefixes: tuple[tuple[str, int], ...] = ()
    paragraph_open = False
    fence_character: str | None = None
    fence_length = 0
    fence_prefixes: tuple[tuple[str, int], ...] = ()

    for line in text.splitlines(keepends=True):
        if fence_character is not None:
            fenced_line = _markdown_apply_fence_containers(line, fence_prefixes)
            if fenced_line is not None:
                visible.append(masked(line))
                match = MARKDOWN_FENCE.match(fenced_line)
                if match is not None:
                    fence = match.group("fence")
                    remainder = fenced_line[match.end() :].strip()
                    if (
                        fence[0] == fence_character
                        and len(fence) >= fence_length
                        and not remainder
                    ):
                        fence_character = None
                        fence_length = 0
                        fence_prefixes = ()
                continue
            fence_character = None
            fence_length = 0
            _remainder, matched = _markdown_apply_container_prefixes_partial(
                line,
                fence_prefixes,
            )
            active_prefixes = fence_prefixes[:matched]
            fence_prefixes = ()

        if not line.strip(" \t\r\n"):
            visible.append(line)
            active_prefixes = _markdown_prefixes_after_unmarked_blank(
                active_prefixes,
            )
            paragraph_open = False
            paragraph_prefixes = ()
            continue

        if paragraph_open:
            paragraph_line, matched = _markdown_apply_container_prefixes_partial(
                line,
                paragraph_prefixes,
            )
            if not paragraph_line.strip(" \t\r\n"):
                visible.append(line)
                paragraph_open = False
                paragraph_prefixes = ()
                continue
            if matched == len(paragraph_prefixes) and _markdown_is_setext_underline(
                paragraph_line,
            ):
                visible.append(line)
                active_prefixes = paragraph_prefixes[:matched]
                paragraph_open = False
                paragraph_prefixes = ()
                continue
            if matched < len(paragraph_prefixes):
                if not _markdown_starts_block_after_container(paragraph_line):
                    visible.append(line)
                    continue
            elif not _markdown_interrupts_lazy_continuation(paragraph_line):
                visible.append(line)
                continue
            paragraph_open = False
            paragraph_prefixes = ()

        remainder, matched = _markdown_apply_container_prefixes_partial(
            line,
            active_prefixes,
        )
        common_prefixes = active_prefixes[:matched]
        content, additional_prefixes = _markdown_reference_containers(remainder)
        effective_prefixes = (*common_prefixes, *additional_prefixes)
        active_prefixes = effective_prefixes

        if not content.strip(" \t\r\n"):
            visible.append(line)
            continue

        match = MARKDOWN_FENCE.match(content)
        if match is not None:
            opening_fence = match.group("fence")
            info_string = content[match.end() :].rstrip("\r\n")
            if opening_fence[0] == "`" and _markdown_has_unescaped_backtick(
                info_string,
            ):
                match = None
        if match is not None:
            fence = match.group("fence")
            fence_character = fence[0]
            fence_length = len(fence)
            fence_prefixes = effective_prefixes
            visible.append(masked(line))
            continue

        if _markdown_indent_columns(content) >= 4:
            visible.append(masked(line))
            continue

        visible.append(line)
        paragraph_open = _markdown_opens_paragraph(content)
        paragraph_prefixes = effective_prefixes if paragraph_open else ()

    return "".join(visible)


def _mask_markdown_code_spans(rendered: str) -> str:
    """Mask code spans using linear, sequential exact-run matching."""
    characters = list(rendered)
    runs: list[tuple[int, int, bool]] = []
    position = 0
    while position < len(rendered):
        position = rendered.find("`", position)
        if position < 0:
            break
        run_end = position + 1
        while run_end < len(rendered) and rendered[run_end] == "`":
            run_end += 1
        runs.append(
            (position, run_end, _markdown_character_is_escaped(rendered, position)),
        )
        position = run_end

    next_closing_run: list[int | None] = [None] * len(runs)
    last_by_length: dict[int, int] = {}
    for run_index in range(len(runs) - 1, -1, -1):
        start, end, escaped_outside = runs[run_index]
        raw_length = end - start
        opener_length = raw_length - 1 if escaped_outside else raw_length
        if opener_length:
            next_closing_run[run_index] = last_by_length.get(opener_length)
        # Backslashes are literal after a code span opens, so a candidate closer
        # always contributes its complete raw run even when it was escaped in the
        # surrounding Markdown context.
        last_by_length[raw_length] = run_index

    run_index = 0
    while run_index < len(runs):
        start, _end, escaped_outside = runs[run_index]
        closing_index = next_closing_run[run_index]
        if closing_index is None:
            run_index += 1
            continue
        if escaped_outside:
            start += 1
        end = runs[closing_index][1]
        line_has_sentinel = False
        for index in range(start, end):
            if characters[index] == "\n":
                line_has_sentinel = False
            elif line_has_sentinel:
                characters[index] = " "
            else:
                characters[index] = "x"
                line_has_sentinel = True
        run_index = closing_index + 1
    return "".join(characters)


def _markdown_has_unescaped_backtick(value: str) -> bool:
    """Return whether a fence info string contains a literal raw backtick."""
    position = value.find("`")
    while position >= 0:
        if not _markdown_character_is_escaped(value, position):
            return True
        position = value.find("`", position + 1)
    return False


def _markdown_indent_columns(value: str) -> int:
    """Return CommonMark-style columns occupied by leading spaces and tabs."""
    columns = 0
    for character in value:
        if character == " ":
            columns += 1
        elif character == "\t":
            columns += 4 - (columns % 4)
        else:
            break
    return columns


def _markdown_list_prefix(value: str) -> tuple[int, int] | None:
    """Return a list prefix end/width while preserving excess marker padding."""
    match = MARKDOWN_LIST_MARKER.match(value)
    if match is None or _markdown_indent_columns(value) > 3:
        return None
    spacing_start = match.start("spacing")
    prefix_before_spacing = _markdown_column_width(value[:spacing_start])
    spacing_columns = (
        _markdown_column_width(value[: match.end()]) - prefix_before_spacing
    )
    prefix_end = match.end() if spacing_columns <= 4 else spacing_start + 1
    return prefix_end, _markdown_column_width(value[:prefix_end])


def _markdown_list_can_interrupt_paragraph(value: str) -> bool:
    """Apply CommonMark's start-at-one rule for interrupting ordered lists."""
    value = _markdown_strip_blockquotes(value)
    match = MARKDOWN_LIST_MARKER.match(value)
    if match is None or _markdown_list_prefix(value) is None:
        return False
    if not value[match.end() :].strip(" \t\r\n"):
        return False
    marker = match.group("marker")
    return not marker[0].isdigit() or int(marker[:-1]) == 1


def _markdown_strip_blockquotes(value: str) -> str:
    """Strip nested CommonMark blockquote markers for code classification."""
    return _markdown_strip_blockquotes_with_depth(value)[0]


def _markdown_strip_blockquotes_with_depth(value: str) -> tuple[str, int]:
    """Strip nested blockquote markers and return their container depth."""
    depth = 0
    while (match := MARKDOWN_BLOCKQUOTE.match(value)) is not None:
        value = value[match.end() :]
        depth += 1
    return value, depth


def _markdown_opens_paragraph(value: str) -> bool:
    """Return whether a visible line keeps an ordinary paragraph open."""
    stripped = value.strip(" \t\r\n")
    if not stripped or _markdown_indent_columns(value) >= 4:
        return False
    if re.match(r"^(?:#{1,6}(?:[ \t]+|$)|(?:[-*_][ \t]*){3,}$)", stripped):
        return False
    if MARKDOWN_FENCE.match(value) is not None or _markdown_list_prefix(value) is not None:
        return False
    return not stripped.startswith(("<", ">"))


def _markdown_is_setext_underline(value: str) -> bool:
    """Return whether a line is a CommonMark setext heading underline."""
    return (
        _markdown_indent_columns(value) <= 3
        and re.fullmatch(r"[=-]+[ \t]*(?:\r?\n)?", value) is not None
    )


def _markdown_interrupts_paragraph(value: str) -> bool:
    """Return whether a line can end an already open Markdown paragraph."""
    if _markdown_indent_columns(value) > 3:
        return False
    if MARKDOWN_BLOCKQUOTE.match(value) is not None:
        return True
    stripped = value.strip(" \t\r\n")
    if re.match(
        r"^(?:#{1,6}(?:[ \t]+|$)|[=-]+[ \t]*$|(?:[-*_][ \t]*){3,}$)",
        stripped,
    ):
        return True
    if MARKDOWN_FENCE.match(value) is not None:
        return True
    return _markdown_list_can_interrupt_paragraph(value)


def _markdown_interrupts_lazy_continuation(value: str) -> bool:
    """Recognize blocks that can interrupt a lazy paragraph continuation."""
    if _markdown_interrupts_paragraph(value):
        return True
    return any(
        pattern.match(value) is not None
        for pattern in (
            RAW_HTML_TYPE1_START,
            RAW_HTML_TYPE2_START,
            RAW_HTML_TYPE3_START,
            RAW_HTML_TYPE4_START,
            RAW_HTML_TYPE5_START,
            RAW_HTML_BLOCK_TAG_START,
        )
    )


def _markdown_starts_block_after_container(value: str) -> bool:
    """Recognize a new block after an enclosing container has ended."""
    return (
        _markdown_interrupts_lazy_continuation(value)
        or _markdown_list_prefix(value) is not None
    )


def _markdown_prefixes_after_unmarked_blank(
    prefixes: tuple[tuple[str, int], ...],
) -> tuple[tuple[str, int], ...]:
    """Close a quote, and containers nested in it, across an unmarked blank.

    List items may continue after a blank line without repeating their marker,
    but block quotes cannot.  Retaining a quote's nested list indentation here
    can misclassify a newly opened quote's indented code as ordinary Markdown.
    """
    for index, (kind, _columns) in enumerate(prefixes):
        if kind == "quote":
            return prefixes[:index]
    return prefixes


def _markdown_column_width(value: str) -> int:
    """Return display columns occupied by a single Markdown line prefix."""
    columns = 0
    for character in value:
        if character in "\r\n":
            break
        if character == "\t":
            columns += 4 - (columns % 4)
        else:
            columns += 1
    return columns


def _markdown_remove_indent(value: str, columns: int) -> str:
    """Remove up to ``columns`` of container indentation from a line."""
    consumed_columns = 0
    position = 0
    while position < len(value) and consumed_columns < columns:
        character = value[position]
        if character == " ":
            consumed_columns += 1
        elif character == "\t":
            consumed_columns += 4 - (consumed_columns % 4)
        else:
            break
        position += 1
    return value[position:]


def _suggest_class(root: Path, readme: str) -> str:
    name = root.name.lower()
    lowered = readme.lower()
    if "archived" in name or "⚠️ archived" in lowered or "this repository is archived" in lowered:
        return "F"
    if name.endswith("-play") or name.startswith("pages--") or "compiled build" in lowered:
        return "D"
    if any(term in name for term in ("theory", "research", "inquiry", "corpus")):
        return "E"
    if any(term in name for term in ("sdk", "schema", "engine", "framework", "bridge")):
        return "C"
    return "B"


def _findings(
    root: Path,
    readme: str,
    record_path: Path | None,
    record_errors: list[str],
    signals: dict[str, int],
    broken_local_links: list[str],
    markdown_limit_exceeded: bool,
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    if not readme:
        findings.append({"severity": "error", "code": "missing-readme", "message": "Root README is missing."})
    if record_path is None:
        findings.append(
            {
                "severity": "error",
                "code": "missing-project-record",
                "message": "No canonical project-record.yml exists; all documentation classes require one.",
            },
        )
    for error in record_errors:
        findings.append({"severity": "error", "code": "invalid-project-record", "message": error})
    if broken_local_links:
        preview = "; ".join(broken_local_links[:3])
        findings.append(
            {
                "severity": "error",
                "code": "broken-local-links",
                "message": f"{len(broken_local_links)} broken local link(s): {preview}",
            },
        )
    if markdown_limit_exceeded:
        findings.append(
            {
                "severity": "error",
                "code": "markdown-input-limit",
                "message": (
                    "Markdown audit input exceeds the repository-wide "
                    f"{MAX_MARKDOWN_FILES}-file or "
                    f"{MAX_MARKDOWN_REPOSITORY_BYTES}-byte limit."
                ),
            },
        )
    for dimension, signal_count in signals.items():
        if signal_count <= 1:
            findings.append(
                {
                    "severity": "warning",
                    "code": f"few-{dimension.replace('_', '-')}-signals",
                    "message": (
                        f"Automated scan found {signal_count} {dimension.replace('_', ' ')} "
                        "structural marker(s); human quality assessment is still required."
                    ),
                },
            )
    if (root / "docs").is_dir() and signals["cross_linking"] <= 1:
        findings.append(
            {
                "severity": "warning",
                "code": "orphan-docs",
                "message": "Documentation exists but is weakly linked from the project surface.",
            },
        )
    return findings


def load_schema(path: str | Path) -> dict[str, Any]:
    """Load a JSON Schema stored as YAML or JSON."""
    schema_path = Path(path)
    try:
        return load_project_record(schema_path)
    except ValueError as exc:
        if str(exc) == f"Project record is not a mapping: {schema_path}":
            raise ValueError(f"Schema is not a mapping: {schema_path}") from exc
        raise
