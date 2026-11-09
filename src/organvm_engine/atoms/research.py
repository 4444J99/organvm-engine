"""Research activation stage for the atoms pipeline.

Scans research reference documents (e.g. in praxis-perpetua/research/) for
actionable implementation directives — concrete proposals with acceptance
criteria, technical specs, or named patterns — and emits them as atom tasks
with source_type "research-directive".

Each research doc can declare its status in YAML frontmatter:
    status: reference              # default, eligible for scanning
    status: reference-actionable   # explicitly flagged for extraction
    status: reference-activated    # already processed, skip

Extracted directives are appended to the atoms task JSONL alongside
plan-derived tasks.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(
    r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL,
)

_STATUS_RE = re.compile(r"^status:\s*[\"']?([^\"'\n]+)", re.MULTILINE)
_TITLE_RE = re.compile(r"^title:\s*[\"']?([^\"'\n]+)", re.MULTILINE)
_DATE_RE = re.compile(r"^date:\s*[\"']?(\d{4}-\d{2}-\d{2})", re.MULTILINE)
_TAGS_RE = re.compile(r"^tags:\s*\[([^\]]*)\]", re.MULTILINE)

# ---------------------------------------------------------------------------
# Directive extraction patterns
# ---------------------------------------------------------------------------

# Headings that signal actionable sections
_ACTIONABLE_HEADING_RE = re.compile(
    r"^(#{1,4})\s+"
    r"(?:.*(?:proposal|implementation|recommendation|directive|action item|"
    r"acceptance criteria|spec(?:ification)?|concrete|pattern|design|"
    r"architecture|integration|pipeline|workflow|extension|enhancement).*)",
    re.IGNORECASE,
)

# Checkbox items (inherently actionable)
_CHECKBOX_RE = re.compile(r"^(\s*)- \[([ xX~])\]\s+(.*)")

# Numbered list items within actionable sections
_NUMBERED_RE = re.compile(r"^(\s*)(\d+)\.\s+(.*)")

# Bold-prefixed directives: **Do X** or **Create Y**
_BOLD_DIRECTIVE_RE = re.compile(
    r"\*\*("
    r"(?:Implement|Create|Build|Add|Integrate|Extend|Design|Define|"
    r"Introduce|Deploy|Configure|Wire|Expose|Emit|Generate|Extract|"
    r"Score|Rehearse|Perform|Measure|Track|Monitor|Route|Classify)"
    r"[^*]{5,80})\*\*",
    re.IGNORECASE,
)

# Arrow-prefixed recommendations: → Do X
_ARROW_RE = re.compile(r"^\s*(?:→|->)\s+(.{15,200})$")

# Code fence detection
_CODE_FENCE_RE = re.compile(r"^```")

# File path references
_BACKTICK_PATH_RE = re.compile(r"`([a-zA-Z0-9_./-]+\.[a-zA-Z0-9]+)`")

# Known technology tags (subset of atomizer's list)
_KNOWN_TAGS = [
    "python", "typescript", "javascript", "rust", "go", "fastapi",
    "pytest", "mcp", "docker", "github-actions", "postgresql",
    "json", "yaml", "markdown", "html", "css", "react", "nextjs",
    "redis", "graphql", "openapi", "tailwind", "astro",
]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ResearchDirective:
    """A single actionable directive extracted from a research document."""
    title: str
    body: str = ""
    line_start: int = 0
    line_end: int = 0
    section: str = ""
    directive_type: str = "generic"  # proposal | pattern | spec | action_item | criteria
    confidence: float = 0.5  # 0.0-1.0 extraction confidence


@dataclass
class ResearchDoc:
    """A research document with its metadata and extracted directives."""
    path: Path
    title: str = ""
    date: str | None = None
    status: str = "reference"
    tags: list[str] = field(default_factory=list)
    directives: list[ResearchDirective] = field(default_factory=list)
    body_lines: list[str] = field(default_factory=list)

    @property
    def is_scannable(self) -> bool:
        """Whether this doc is eligible for directive extraction."""
        return self.status in ("reference", "reference-actionable")

    @property
    def is_activated(self) -> bool:
        """Whether this doc has already been processed."""
        return self.status == "reference-activated"


@dataclass
class ResearchActivationResult:
    """Result of scanning research docs for directives."""
    docs_scanned: int = 0
    docs_with_directives: int = 0
    docs_skipped: int = 0
    total_directives: int = 0
    tasks: list[dict] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)
    activation_candidates: list[Path] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------

def parse_frontmatter(text: str) -> dict[str, str | list[str]]:
    """Extract YAML-like frontmatter from markdown text."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}

    block = m.group(1)
    result: dict[str, str | list[str]] = {}

    sm = _STATUS_RE.search(block)
    if sm:
        result["status"] = sm.group(1).strip()

    tm = _TITLE_RE.search(block)
    if tm:
        result["title"] = tm.group(1).strip()

    dm = _DATE_RE.search(block)
    if dm:
        result["date"] = dm.group(1)

    tg = _TAGS_RE.search(block)
    if tg:
        raw_tags = tg.group(1)
        result["tags"] = [t.strip().strip("\"'") for t in raw_tags.split(",") if t.strip()]

    return result


# ---------------------------------------------------------------------------
# Document scanning
# ---------------------------------------------------------------------------

def discover_research_docs(
    research_dir: Path,
    recursive: bool = True,
) -> list[Path]:
    """Find markdown files in a research directory."""
    if not research_dir.is_dir():
        return []
    pattern = "**/*.md" if recursive else "*.md"
    return sorted(research_dir.glob(pattern))


def parse_research_doc(filepath: Path) -> ResearchDoc:
    """Parse a research document, extracting frontmatter and body."""
    text = filepath.read_text(encoding="utf-8", errors="replace")
    fm = parse_frontmatter(text)

    # Strip frontmatter from body
    body = _FRONTMATTER_RE.sub("", text)
    lines = body.splitlines()

    # Extract title from frontmatter or first heading
    title = str(fm.get("title", ""))
    if not title:
        for line in lines[:10]:
            m = re.match(r"^#\s+(.+)", line)
            if m:
                title = m.group(1).strip()
                break
    if not title:
        title = filepath.stem

    # Extract date from frontmatter or filename
    date = fm.get("date")
    if not date:
        dm = re.match(r"(\d{4}-\d{2}-\d{2})", filepath.stem)
        if dm:
            date = dm.group(1)

    tags_raw = fm.get("tags", [])
    tags = list(tags_raw) if isinstance(tags_raw, list) else []

    return ResearchDoc(
        path=filepath,
        title=title,
        date=str(date) if date else None,
        status=str(fm.get("status", "reference")),
        tags=tags,
        body_lines=lines,
    )


# ---------------------------------------------------------------------------
# Directive extraction
# ---------------------------------------------------------------------------

def _classify_directive_type(title: str, section: str) -> str:
    """Classify a directive by its content and context."""
    combined = (title + " " + section).lower()
    if any(w in combined for w in ["acceptance criteria", "criteria", "requirement"]):
        return "criteria"
    if any(w in combined for w in ["pattern", "principle", "design"]):
        return "pattern"
    if any(w in combined for w in ["spec", "specification", "schema", "api"]):
        return "spec"
    if any(w in combined for w in ["action item", "todo", "next step"]):
        return "action_item"
    return "proposal"


def _extract_tags_from_text(text: str) -> list[str]:
    """Extract known technology tags from text."""
    lower = text.lower()
    found = []
    for tag in _KNOWN_TAGS:
        pattern = re.escape(tag.lower())
        if re.search(rf"(?:^|[\s`/.,;:(]){pattern}(?:$|[\s`/.,;:)])", lower):
            found.append(tag)
    return sorted(set(found))


def _extract_file_refs(text: str) -> list[str]:
    """Extract file path references from text."""
    refs = []
    seen: set[str] = set()
    for m in _BACKTICK_PATH_RE.finditer(text):
        path = m.group(1)
        if path not in seen and "/" in path and not path.startswith("http"):
            seen.add(path)
            refs.append(path)
    return refs


def extract_directives(doc: ResearchDoc) -> list[ResearchDirective]:
    """Extract actionable directives from a research document.

    Scans for:
    - Checkbox items (always actionable)
    - Content under actionable section headings
    - Bold-prefixed directives (**Implement X**)
    - Arrow-prefixed recommendations (-> Do X)
    """
    directives: list[ResearchDirective] = []
    lines = doc.body_lines

    in_actionable_section = False
    current_section = ""
    section_depth = 0
    in_code_block = False

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()

        # Track code fences
        if _CODE_FENCE_RE.match(stripped):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue

        # Check for heading
        heading_match = re.match(r"^(#{1,6})\s+(.*)", stripped)
        if heading_match:
            depth = len(heading_match.group(1))
            heading_text = heading_match.group(2).strip()

            # Check if this is an actionable section
            if _ACTIONABLE_HEADING_RE.match(stripped):
                in_actionable_section = True
                current_section = heading_text
                section_depth = depth
            elif depth <= section_depth:
                # Left the actionable section
                in_actionable_section = False
                current_section = heading_text
                section_depth = depth
            continue

        # Checkbox items: always extract as directives
        cb_match = _CHECKBOX_RE.match(line)
        if cb_match:
            marker = cb_match.group(2)
            text = cb_match.group(3).strip()
            if len(text) > 15:  # Skip trivial items
                directives.append(ResearchDirective(
                    title=text[:120],
                    body=text,
                    line_start=i,
                    line_end=i,
                    section=current_section,
                    directive_type="action_item",
                    confidence=0.8 if marker == " " else 0.3,  # Completed = low confidence
                ))
            continue

        # Only extract from actionable sections or via strong signals
        if in_actionable_section:
            # Numbered items within actionable sections
            num_match = _NUMBERED_RE.match(line)
            if num_match:
                text = num_match.group(3).strip()
                if len(text) > 15:
                    directives.append(ResearchDirective(
                        title=text[:120],
                        body=text,
                        line_start=i,
                        line_end=i,
                        section=current_section,
                        directive_type=_classify_directive_type(text, current_section),
                        confidence=0.6,
                    ))
                continue

        # Bold directives: strong signal regardless of section
        for bm in _BOLD_DIRECTIVE_RE.finditer(line):
            directives.append(ResearchDirective(
                title=bm.group(1).strip(),
                body=stripped,
                line_start=i,
                line_end=i,
                section=current_section,
                directive_type=_classify_directive_type(bm.group(1), current_section),
                confidence=0.7,
            ))

        # Arrow-prefixed recommendations
        arrow_match = _ARROW_RE.match(line)
        if arrow_match:
            text = arrow_match.group(1).strip()
            directives.append(ResearchDirective(
                title=text[:120],
                body=text,
                line_start=i,
                line_end=i,
                section=current_section,
                directive_type="proposal",
                confidence=0.5,
            ))

    return directives


# ---------------------------------------------------------------------------
# Task emission
# ---------------------------------------------------------------------------

def _directive_id(doc_path: str, directive: ResearchDirective) -> str:
    """Compute a stable ID for a research directive."""
    key = f"research|{doc_path}|{directive.section}|{directive.title}"
    return hashlib.sha256(key.encode()).hexdigest()[:12]


def directive_to_task(
    directive: ResearchDirective,
    doc: ResearchDoc,
    research_dir: Path,
) -> dict:
    """Convert a ResearchDirective into an atom task dict.

    Output format matches AtomicTask.to_dict() so tasks can be
    appended to the same JSONL stream.
    """
    rel_path = str(doc.path.relative_to(research_dir)) if doc.path.is_relative_to(
        research_dir,
    ) else str(doc.path)

    task_id = _directive_id(rel_path, directive)
    body = directive.body
    tags = _extract_tags_from_text(body + " " + doc.title)
    # Merge doc-level tags
    tags = sorted(set(tags + doc.tags))
    file_refs = _extract_file_refs(body)

    from organvm_engine.domain import domain_fingerprint

    return {
        "id": task_id,
        "title": directive.title,
        "source": {
            "file": rel_path,
            "plan_title": doc.title,
            "plan_date": doc.date,
            "plan_status": doc.status,
            "line_start": directive.line_start,
            "line_end": directive.line_end,
            "is_agent_subplan": False,
            "parent_plan": None,
        },
        "source_type": "research-directive",
        "agent": "research",
        "project": {
            "slug": _infer_project_slug(doc, research_dir),
            "archived": False,
            "organ": None,
            "repo": None,
        },
        "hierarchy": {
            "breadcrumb": f"{doc.title} > {directive.section}" if directive.section else doc.title,
            "phase": None,
            "phase_index": None,
            "section": directive.section or None,
            "step": None,
            "step_index": None,
            "depth": 1 if directive.section else 0,
        },
        "status": "pending",
        "task_type": directive.directive_type,
        "actionable": True,
        "files_touched": [{"path": r, "action": "unknown", "estimated_loc": None} for r in file_refs],
        "dependencies": {
            "depends_on": [],
            "blocks": [],
            "phase_order": None,
        },
        "complexity": {
            "estimated_loc": None,
            "has_code_block": "```" in body,
            "code_block_lines": 0,
            "sub_item_count": 0,
        },
        "tags": tags,
        "domain_fingerprint": domain_fingerprint(tags, file_refs),
        "raw_text": body[:500],
        "research_metadata": {
            "directive_type": directive.directive_type,
            "confidence": directive.confidence,
            "source_doc": rel_path,
        },
    }


def _infer_project_slug(doc: ResearchDoc, research_dir: Path) -> str:
    """Infer a project slug from the research doc's location."""
    try:
        rel = doc.path.relative_to(research_dir)
        parts = list(rel.parts)
        if len(parts) > 1:
            return parts[0]
    except ValueError:
        pass
    return "praxis-perpetua/research"


# ---------------------------------------------------------------------------
# Status update
# ---------------------------------------------------------------------------

def mark_doc_activated(filepath: Path) -> bool:
    """Update a research doc's frontmatter status to reference-activated.

    Returns True if the file was modified, False if no change was needed.
    """
    text = filepath.read_text(encoding="utf-8", errors="replace")
    fm_match = _FRONTMATTER_RE.match(text)

    if fm_match:
        block = fm_match.group(1)
        sm = _STATUS_RE.search(block)
        if sm:
            old_status = sm.group(1).strip()
            if old_status == "reference-activated":
                return False
            new_block = block[:sm.start(1)] + "reference-activated" + block[sm.end(1):]
            new_text = f"---\n{new_block}\n---\n" + text[fm_match.end():]
        else:
            new_block = block + "\nstatus: reference-activated"
            new_text = f"---\n{new_block}\n---\n" + text[fm_match.end():]
    else:
        # No frontmatter — add it
        new_text = "---\nstatus: reference-activated\n---\n" + text

    filepath.write_text(new_text, encoding="utf-8")
    return True


# ---------------------------------------------------------------------------
# High-level API
# ---------------------------------------------------------------------------

def activate_research(
    research_dir: Path,
    min_confidence: float = 0.4,
    mark_activated: bool = False,
) -> ResearchActivationResult:
    """Scan a research directory and extract actionable directives.

    Args:
        research_dir: Directory containing research markdown files.
        min_confidence: Minimum extraction confidence to include (0.0-1.0).
        mark_activated: If True, update scanned docs' status to reference-activated.

    Returns:
        ResearchActivationResult with all extracted tasks.
    """
    result = ResearchActivationResult()

    doc_paths = discover_research_docs(research_dir)
    if not doc_paths:
        return result

    for doc_path in doc_paths:
        try:
            doc = parse_research_doc(doc_path)

            if doc.is_activated:
                result.docs_skipped += 1
                continue

            if not doc.is_scannable:
                result.docs_skipped += 1
                continue

            result.docs_scanned += 1
            directives = extract_directives(doc)

            # Filter by confidence
            directives = [d for d in directives if d.confidence >= min_confidence]

            if not directives:
                continue

            result.docs_with_directives += 1
            result.total_directives += len(directives)

            for directive in directives:
                task = directive_to_task(directive, doc, research_dir)
                result.tasks.append(task)

            result.activation_candidates.append(doc_path)
            if mark_activated:
                mark_doc_activated(doc_path)

        except Exception as e:
            result.errors.append((str(doc_path), str(e)))

    return result
