"""Atomize plan files into atomic tasks with expansive metadata.

Parses .md plan files into atomic tasks, each with rich metadata including
hierarchy, status, task type, file references, dependencies, and tags.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SKIP_FILES = {
    "atomize_plans.py",
    "archive-plans.py",
    "ATOMIZED-SUMMARY.md",
    "atomized-tasks.jsonl",
}

AGENT_SUBPLAN_RE = re.compile(r"-agent-a[0-9a-f]+(?:\.md)?$", re.IGNORECASE)

PHASE_RE = re.compile(
    r"^(#{1,3})\s+(?:Phase|Stage)\s+(\w+)[:\s\u2014\u2013\-]*(.*)", re.IGNORECASE,
)
STEP_RE = re.compile(
    r"^(#{1,4})\s+(?:Step|Task)\s+(\w+)[:\s\u2014\u2013\-]*(.*)", re.IGNORECASE,
)
SPRINT_RE = re.compile(r"^(#{1,3})\s+Sprint\s+(\d+)(.*)", re.IGNORECASE)
STREAM_RE = re.compile(r"^(#{1,3})\s+Stream\s+(\w+)(.*)", re.IGNORECASE)
NUMBERED_HEADING_RE = re.compile(r"^(#{1,4})\s+(\d+[\w.]*)\.\s+(.*)")
GENERIC_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)")

CHECKBOX_RE = re.compile(r"^(\s*)- \[([ xX~])\]\s+(.*)")
NUMBERED_ITEM_RE = re.compile(r"^(\s*)(\d+)\.\s+(.*)")
TABLE_SEP_RE = re.compile(r"^\|[\s\-:|]+\|")
TABLE_ROW_RE = re.compile(r"^\|(.+)\|$")
CODE_FENCE_RE = re.compile(r"^```")

# File path patterns
BACKTICK_PATH_RE = re.compile(r"`([a-zA-Z0-9_./-]+\.[a-zA-Z0-9]+)`")
BOLD_FILE_RE = re.compile(r"\*\*(?:File|Path)\*\*:\s*`([^`]+)`")
FILE_ACTION_RE = re.compile(
    r"(?:NEW|MODIFIED|CREATE|DELETE|MIGRATE)\b.*?`([a-zA-Z0-9_./-]+\.[a-zA-Z0-9]+)`",
    re.IGNORECASE,
)
STANDALONE_PATH_RE = re.compile(
    r"(?:^|\s)`?((?:src|lib|scripts|tests|docs|server|client|app|packages|config)"
    r"/[a-zA-Z0-9_./-]+\.[a-zA-Z0-9]+)`?",
)

# Task type keyword triggers (checked in order; first match wins)
TASK_TYPE_TRIGGERS: list[tuple[str, list[str]]] = [
    ("create_file", ["create", "new file", "NEW", "| Create |", "scaffold"]),
    ("modify_file", ["modify", "update", "add to", "MODIFIED", "change", "edit"]),
    ("delete_file", ["delete", "remove file", "rm ", "DROP"]),
    ("write_test", ["test", "_test.py", ".test.ts", ".spec.", "pytest", "vitest"]),
    ("run_test", ["run test", "execute test", "test suite"]),
    ("verify", ["verify", "confirm", "check", "validate", "assert"]),
    ("deploy", ["deploy", "push", "publish", "ship", "release"]),
    ("document", ["README", "CHANGELOG", ".md", "document", "docstring"]),
    ("research", ["investigate", "explore", "audit", "analyze", "research", "survey"]),
    ("configure", ["config", ".yml", ".yaml", "CI", "env var", "setup", ".toml"]),
    ("git_operation", ["git ", "commit", "branch", "merge", "rebase", "tag"]),
    ("refactor", ["refactor", "clean", "simplify", "reorganize", "restructure"]),
    ("migrate", ["migrate", "move", "transfer", "port", "upgrade"]),
    ("exploration", ["exploration", "discovery", "inventory", "assessment"]),
    ("review", ["review", "evaluate", "inspect", "critique"]),
]

KNOWN_TAGS = [
    "python", "typescript", "javascript", "rust", "go", "ruby", "react", "nextjs",
    "vite", "three.js", "three-js", "p5.js", "p5-js", "chezmoi", "docker",
    "cloudflare", "vercel", "neon", "postgresql", "postgres", "github-actions",
    "mcp", "pytest", "vitest", "supercollider", "astro", "tailwind", "jekyll",
    "openapi", "graphql", "redis", "nginx", "aws", "gcp", "terraform",
    "kubernetes", "k8s", "playwright", "cypress", "express", "fastapi",
    "django", "flask", "svelte", "vue", "angular", "webpack", "rollup",
    "esbuild", "bun", "deno", "node", "zsh", "bash", "homebrew",
]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class FileRef:
    path: str
    action: str = "unknown"
    estimated_loc: Optional[int] = None


@dataclass
class AtomicTask:
    id: str = ""
    title: str = ""
    source_file: str = ""
    plan_title: str = ""
    plan_date: Optional[str] = None
    plan_status: Optional[str] = None
    line_start: int = 0
    line_end: int = 0
    is_agent_subplan: bool = False
    parent_plan: Optional[str] = None
    project_slug: str = ""
    archived: bool = False
    agent: str = "claude"
    breadcrumb: str = ""
    phase: Optional[str] = None
    phase_index: Optional[int] = None
    section: Optional[str] = None
    step: Optional[str] = None
    step_index: Optional[int] = None
    depth: int = 0
    status: str = "pending"
    task_type: str = "generic"
    actionable: bool = True
    files_touched: list = field(default_factory=list)
    depends_on: list = field(default_factory=list)
    blocks: list = field(default_factory=list)
    phase_order: Optional[int] = None
    estimated_loc: Optional[int] = None
    has_code_block: bool = False
    code_block_lines: int = 0
    sub_item_count: int = 0
    tags: list = field(default_factory=list)
    domain_fingerprint: str = ""
    raw_text: str = ""
    _organ: Optional[str] = field(default=None, repr=False)
    _repo: Optional[str] = field(default=None, repr=False)

    def compute_id(self):
        key = f"{self.source_file}|{self.breadcrumb}|{self.title}"
        self.id = hashlib.sha256(key.encode()).hexdigest()[:12]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "source": {
                "file": self.source_file,
                "plan_title": self.plan_title,
                "plan_date": self.plan_date,
                "plan_status": self.plan_status,
                "line_start": self.line_start,
                "line_end": self.line_end,
                "is_agent_subplan": self.is_agent_subplan,
                "parent_plan": self.parent_plan,
            },
            "agent": self.agent,
            "project": {
                "slug": self.project_slug,
                "archived": self.archived,
                "organ": getattr(self, "_organ", None),
                "repo": getattr(self, "_repo", None),
            },
            "hierarchy": {
                "breadcrumb": self.breadcrumb,
                "phase": self.phase,
                "phase_index": self.phase_index,
                "section": self.section,
                "step": self.step,
                "step_index": self.step_index,
                "depth": self.depth,
            },
            "status": self.status,
            "task_type": self.task_type,
            "actionable": self.actionable,
            "files_touched": [
                {"path": f.path, "action": f.action, "estimated_loc": f.estimated_loc}
                for f in self.files_touched
            ],
            "dependencies": {
                "depends_on": self.depends_on,
                "blocks": self.blocks,
                "phase_order": self.phase_order,
            },
            "complexity": {
                "estimated_loc": self.estimated_loc,
                "has_code_block": self.has_code_block,
                "code_block_lines": self.code_block_lines,
                "sub_item_count": self.sub_item_count,
            },
            "tags": self.tags,
            "domain_fingerprint": self.domain_fingerprint,
            "raw_text": self.raw_text,
        }


# ---------------------------------------------------------------------------
# Inference helpers
# ---------------------------------------------------------------------------

def infer_project_slug(filepath: Path, plans_dir: Path) -> tuple[str, bool]:
    """Derive project slug and archived status from file path.

    Uses the shared normalizer so plan slugs align with session-derived slugs.
    """
    from organvm_engine.project_slug import slug_from_plan_dir

    rel = filepath.relative_to(plans_dir)
    parts = list(rel.parts)

    archived = False
    if parts and parts[0] == "archive":
        archived = True
        parts = parts[1:]

    if len(parts) > 1:
        # All directory components except the filename
        dir_parts = parts[:-1]
        raw_slug = "/".join(dir_parts)
        # If it's a single flat directory name, normalize it
        if len(dir_parts) == 1:
            return slug_from_plan_dir(dir_parts[0]), archived
        return raw_slug, archived
    return "_root", archived


def detect_agent_subplan(filepath: Path) -> tuple[bool, Optional[str]]:
    """Check if file is an agent sub-plan; return (is_agent, parent_plan_name)."""
    name = filepath.stem
    if AGENT_SUBPLAN_RE.search(name):
        parent = re.sub(r"-agent-a[0-9a-f]+$", "", name, flags=re.IGNORECASE)
        return True, parent + ".md"
    return False, None


def extract_plan_date(filepath: Path, lines: list[str]) -> Optional[str]:
    """Try to extract date from filename or content."""
    m = re.match(r"(\d{4}-\d{2}-\d{2})", filepath.stem)
    if m:
        return m.group(1)
    for line in lines[:20]:
        m = re.search(r"(\d{4}-\d{2}-\d{2})", line)
        if m:
            return m.group(1)
        m = re.search(r"(\d{2}-\d{2})\b", line)
        if m:
            return f"2026-{m.group(1)}"
    return None


def extract_plan_title(lines: list[str]) -> str:
    """Extract plan title from first heading."""
    for line in lines[:10]:
        m = re.match(r"^#\s+(.+)", line)
        if m:
            return m.group(1).strip()
    return "Untitled Plan"


def extract_plan_status(lines: list[str]) -> Optional[str]:
    """Look for explicit status markers in first 15 lines."""
    for line in lines[:15]:
        m = re.search(
            r"\*\*Status\*\*:\s*(.+?)(?:\s*\*\*|\s*$)", line, re.IGNORECASE,
        )
        if m:
            return m.group(1).strip()
    return None


def infer_task_type(title: str, body: str) -> str:
    """Infer task type from title and body text."""
    combined = (title + " " + body).lower()
    for ttype, triggers in TASK_TYPE_TRIGGERS:
        for trigger in triggers:
            if trigger.lower() in combined:
                return ttype
    return "generic"


def infer_status_from_checkbox(marker: str) -> str:
    if marker in ("x", "X"):
        return "completed"
    if marker == "~":
        return "in_progress"
    return "pending"


def extract_file_refs(text: str) -> list[FileRef]:
    """Extract file references from text."""
    refs = []
    seen: set[str] = set()

    for pattern, action in [
        (BOLD_FILE_RE, "unknown"),
        (FILE_ACTION_RE, "inferred"),
        (STANDALONE_PATH_RE, "unknown"),
    ]:
        for m in pattern.finditer(text):
            path = m.group(1)
            if path not in seen and not path.startswith("http"):
                seen.add(path)
                ctx = text[max(0, m.start() - 40):m.end() + 40].lower()
                a = action
                if a == "inferred":
                    if any(w in ctx for w in ["new", "create", "scaffold"]):
                        a = "create"
                    elif any(w in ctx for w in ["delete", "remove", "drop"]):
                        a = "delete"
                    elif any(w in ctx for w in ["modify", "update", "edit", "add"]):
                        a = "modify"
                loc_m = re.search(r"~?(\d+)\s*(?:lines|LOC|loc)", ctx)
                loc = int(loc_m.group(1)) if loc_m else None
                refs.append(FileRef(path=path, action=a, estimated_loc=loc))

    for m in BACKTICK_PATH_RE.finditer(text):
        path = m.group(1)
        if path not in seen and "/" in path and not path.startswith("http"):
            seen.add(path)
            refs.append(FileRef(path=path, action="unknown"))

    return refs


def extract_tags(text: str) -> list[str]:
    """Extract known technology tags from text."""
    lower = text.lower()
    tags = []
    for tag in KNOWN_TAGS:
        pattern = re.escape(tag.lower())
        if re.search(rf"(?:^|[\s`/.,;:(]){pattern}(?:$|[\s`/.,;:)])", lower):
            tags.append(tag)
    return sorted(set(tags))


def extract_loc_estimate(text: str) -> Optional[int]:
    """Extract LOC estimate from text like '~180 lines' or '(300 LOC)'."""
    m = re.search(r"~?(\d+)\s*(?:lines|LOC|loc)\b", text)
    return int(m.group(1)) if m else None


def is_actionable(title: str, body: str, archetype: str) -> bool:
    """Determine if a task is actionable vs informational."""
    if archetype in ("exploration", "post_hoc"):
        return False
    lower = (title + " " + body).lower()
    non_actionable = [
        "summary", "context", "overview", "background", "analysis complete",
        "investigation complete", "evaluation", "findings",
    ]
    return not (any(w in lower for w in non_actionable) and not any(w in lower for w in ["create", "implement", "build", "add", "fix", "write"]))


# ---------------------------------------------------------------------------
# Archetype classification
# ---------------------------------------------------------------------------

def classify_archetype(lines: list[str]) -> str:
    """Classify a plan into an archetype to choose the right parser strategy."""
    checkbox_count = 0
    has_phases = False
    has_table_sep = False
    has_numbered = False
    has_steps = False

    for line in lines:
        if CHECKBOX_RE.match(line):
            checkbox_count += 1
        if PHASE_RE.match(line.strip()):
            has_phases = True
        if TABLE_SEP_RE.match(line.strip()):
            has_table_sep = True
        if NUMBERED_HEADING_RE.match(line.strip()):
            has_numbered = True
        if STEP_RE.match(line.strip()):
            has_steps = True

    text = "\n".join(lines)

    prose_lines = 0
    in_code = False
    for line in lines:
        if CODE_FENCE_RE.match(line):
            in_code = not in_code
            continue
        if in_code:
            continue
        stripped = line.strip()
        if (
            stripped
            and not stripped.startswith("#")
            and not stripped.startswith("- ")
            and not stripped.startswith("|")
            and not re.match(r"^\d+\.", stripped)
        ):
            prose_lines += 1

    title = extract_plan_title(lines)
    title_lower = title.lower()
    is_post_hoc = any(
        w in title_lower
        for w in ["summary", "audit", "analysis", "evaluation", "review", "findings"]
    ) and not any(w in title_lower for w in ["plan", "implement", "build"])

    if checkbox_count >= 3 and has_phases:
        return "phase_checkbox"
    if checkbox_count >= 3:
        return "checkbox"
    if has_phases and (has_steps or has_numbered):
        return "phase_task"
    if has_table_sep and re.search(
        r"\|.*(?:file|path|action|create|modify|status).*\|", text, re.IGNORECASE,
    ):
        return "table_inventory"
    if has_numbered or has_phases:
        return "sequenced_list"
    if is_post_hoc:
        return "post_hoc"
    if checkbox_count < 3 and prose_lines > 100:
        return "exploration"

    return "generic"


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class PlanParser:
    """State machine parser that walks lines and emits atomic tasks."""

    def __init__(
        self,
        lines: list[str],
        filepath: Path,
        plans_dir: Path,
        agent: str = "claude",
        organ: str | None = None,
        repo: str | None = None,
    ):
        self.lines = lines
        self.filepath = filepath
        self.plans_dir = plans_dir
        self.agent = agent
        self.organ = organ
        self.repo = repo
        self.tasks: list[AtomicTask] = []
        self.used_task_ids: set[str] = set()

        self.project_slug, self.archived = infer_project_slug(filepath, plans_dir)
        self.is_agent, self.parent_plan = detect_agent_subplan(filepath)
        self.plan_title = extract_plan_title(lines)
        self.plan_date = extract_plan_date(filepath, lines)
        self.plan_status = extract_plan_status(lines)
        self.rel_path = str(filepath.relative_to(plans_dir))
        self.archetype = classify_archetype(lines)

        self.stack: list[tuple[str, int, str]] = []
        self.current_lines: list[str] = []
        self.current_line_start: int = 0
        self.in_code_block: bool = False
        self.code_block_lines: int = 0
        self.in_table: bool = False
        self.table_headers: list[str] = []
        self.step_counter: int = 0

    def parse(self) -> list[AtomicTask]:
        """Main parse loop."""
        for i, line in enumerate(self.lines, start=1):
            self._process_line(line, i)

        self._flush_accumulated(len(self.lines))

        if not self.tasks:
            self._emit_doc_level_task()

        self._wire_dependencies()
        self._enrich_tags()

        return self.tasks

    def _process_line(self, line: str, lineno: int):
        stripped = line.strip()

        if CODE_FENCE_RE.match(stripped):
            self.in_code_block = not self.in_code_block
            if self.in_code_block:
                self.code_block_lines = 0
            self.current_lines.append(line)
            return

        if self.in_code_block:
            self.code_block_lines += 1
            self.current_lines.append(line)
            return

        if TABLE_SEP_RE.match(stripped):
            self.in_table = True
            if self.current_lines:
                header_line = self.current_lines[-1]
                if TABLE_ROW_RE.match(header_line.strip()):
                    cells = [c.strip() for c in header_line.strip().strip("|").split("|")]
                    self.table_headers = cells
            self.current_lines.append(line)
            return

        if self.in_table:
            if TABLE_ROW_RE.match(stripped):
                self._handle_table_row(stripped, lineno)
                self.current_lines.append(line)
                return
            self.in_table = False
            self.table_headers = []

        cb_match = CHECKBOX_RE.match(line)
        if cb_match:
            indent, marker, text = cb_match.groups()
            self._emit_checkbox_task(text, marker, lineno)
            return

        heading_match = self._match_heading(stripped)
        if heading_match:
            htype, level, index, title_text = heading_match
            self._flush_accumulated(lineno - 1)
            self._push_heading(title_text, level, htype, index)
            self.current_line_start = lineno
            return

        num_match = NUMBERED_ITEM_RE.match(line)
        if num_match and self.stack and self.archetype in (
            "sequenced_list", "phase_task", "generic",
        ):
            indent, num, text = num_match.groups()
            depth = len(indent) // 2
            if depth == 0 and len(text) > 15:
                self._emit_numbered_task(text, int(num), lineno)
                return

        self.current_lines.append(line)

    def _match_heading(self, line: str):
        for regex, htype in [
            (PHASE_RE, "phase"),
            (STEP_RE, "step"),
            (SPRINT_RE, "sprint"),
            (STREAM_RE, "stream"),
            (NUMBERED_HEADING_RE, "numbered"),
            (GENERIC_HEADING_RE, "generic"),
        ]:
            m = regex.match(line)
            if m:
                level = len(m.group(1))
                if htype in ("phase", "step", "sprint", "stream"):
                    idx = m.group(2)
                    title = m.group(3).strip() if m.group(3) else m.group(2)
                    full_title = line.lstrip("#").strip()
                    return htype, level, idx, full_title
                if htype == "numbered":
                    idx = m.group(2)
                    title = m.group(3).strip()
                    return htype, level, idx, f"{idx}. {title}"
                title = m.group(2).strip()
                return htype, level, None, title
        return None

    def _push_heading(self, text: str, level: int, htype: str, index):
        while self.stack and self.stack[-1][1] >= level:
            self.stack.pop()
        self.stack.append((text, level, htype))

    def _get_breadcrumb(self) -> str:
        return " > ".join(item[0] for item in self.stack)

    def _get_phase(self) -> tuple[Optional[str], Optional[int]]:
        for text, _level, htype in self.stack:
            if htype in ("phase", "sprint", "stage"):
                m = re.search(r"(\d+)", text)
                idx = int(m.group(1)) if m else None
                return text, idx
        return None, None

    def _flush_accumulated(self, end_line: int):
        if not self.current_lines or not self.stack:
            self.current_lines = []
            return

        top = self.stack[-1] if self.stack else None
        if top and top[2] in ("step", "numbered") and self.archetype in (
            "phase_task", "sequenced_list",
        ):
            body = "\n".join(self.current_lines).strip()
            if body and len(body) > 20:
                self._emit_task(
                    title=top[0],
                    body=body,
                    line_start=self.current_line_start,
                    line_end=end_line,
                )

        self.current_lines = []

    def _emit_checkbox_task(self, text: str, marker: str, lineno: int):
        status = infer_status_from_checkbox(marker)
        task = self._make_task(
            title=text[:120],
            body=text,
            line_start=lineno,
            line_end=lineno,
            status=status,
        )
        self.tasks.append(task)

    def _emit_numbered_task(self, text: str, num: int, lineno: int):
        task = self._make_task(
            title=text[:120],
            body=text,
            line_start=lineno,
            line_end=lineno,
        )
        task.step_index = num
        self.tasks.append(task)

    def _handle_table_row(self, row: str, lineno: int):
        cells = [c.strip() for c in row.strip("|").split("|")]
        if not self.table_headers or len(cells) < 2:
            return

        headers_lower = [h.lower() for h in self.table_headers]
        has_file_col = any(
            h in col for col in headers_lower for h in ["file", "path", "script", "module"]
        )
        has_action_col = any(
            h in col
            for col in headers_lower
            for h in ["action", "type", "status", "safe action"]
        )

        if has_file_col or has_action_col:
            title_parts = []
            for _i, cell in enumerate(cells):
                if cell and cell != "#" and not cell.isdigit():
                    title_parts.append(cell.strip("`*"))
                    if len(title_parts) >= 2:
                        break
            title = " \u2014 ".join(title_parts) if title_parts else row

            task = self._make_task(
                title=title[:120],
                body=row,
                line_start=lineno,
                line_end=lineno,
            )
            self.tasks.append(task)

    def _emit_task(self, title: str, body: str, line_start: int, line_end: int,
                   status: str = "pending"):
        task = self._make_task(title, body, line_start, line_end, status)
        self.tasks.append(task)

    def _emit_doc_level_task(self):
        body = "\n".join(self.lines[:50]).strip()
        task = self._make_task(
            title=self.plan_title,
            body=body,
            line_start=1,
            line_end=len(self.lines),
        )
        if self.archetype in ("exploration", "post_hoc"):
            task.actionable = False
            if self.archetype == "post_hoc":
                task.status = "completed"
            task.task_type = self.archetype
        self.tasks.append(task)

    def _make_task(self, title: str, body: str, line_start: int, line_end: int,
                   status: str = "pending") -> AtomicTask:
        phase, phase_index = self._get_phase()
        breadcrumb = self._get_breadcrumb()

        title = re.sub(r"^\*\*(.+?)\*\*", r"\1", title).strip()
        title = re.sub(r"^`(.+?)`", r"\1", title).strip()

        task = AtomicTask(
            title=title,
            source_file=self.rel_path,
            plan_title=self.plan_title,
            plan_date=self.plan_date,
            plan_status=self.plan_status,
            line_start=line_start,
            line_end=line_end,
            is_agent_subplan=self.is_agent,
            parent_plan=self.parent_plan,
            project_slug=self.project_slug,
            archived=self.archived,
            breadcrumb=breadcrumb if breadcrumb else title,
            phase=phase,
            phase_index=phase_index,
            section=self.stack[-2][0] if len(self.stack) >= 2 else None,
            step=self.stack[-1][0] if self.stack else None,
            depth=len(self.stack),
            status=status,
            task_type=infer_task_type(title, body),
            raw_text=body[:500],
            files_touched=extract_file_refs(body),
            estimated_loc=extract_loc_estimate(body),
            has_code_block="```" in body,
            code_block_lines=self.code_block_lines,
        )
        task.agent = self.agent
        task._organ = self.organ
        task._repo = self.repo
        task.actionable = is_actionable(title, body, self.archetype)
        task.phase_order = phase_index
        task.compute_id()
        base_id = task.id
        suffix = 0
        while task.id in self.used_task_ids:
            key = f"{base_id}|{line_start}|{suffix}"
            task.id = hashlib.sha256(key.encode()).hexdigest()[:12]
            suffix += 1
        self.used_task_ids.add(task.id)

        from organvm_engine.domain import domain_fingerprint as _dfp
        task.domain_fingerprint = _dfp(
            task.tags, [f.path for f in task.files_touched],
        )
        return task

    def _wire_dependencies(self):
        phases: dict[Optional[int], list[AtomicTask]] = {}
        for t in self.tasks:
            phases.setdefault(t.phase_index, []).append(t)

        sorted_phase_keys = sorted(
            (k for k in phases if k is not None), key=lambda x: x,
        )
        for pk in sorted_phase_keys:
            phase_tasks = phases[pk]
            for i in range(1, len(phase_tasks)):
                phase_tasks[i].depends_on.append(phase_tasks[i - 1].id)

        for i in range(1, len(sorted_phase_keys)):
            prev_key = sorted_phase_keys[i - 1]
            curr_key = sorted_phase_keys[i]
            prev_last = phases[prev_key][-1]
            curr_first = phases[curr_key][0]
            curr_first.depends_on.append(prev_last.id)
            prev_last.blocks.append(curr_first.id)

    def _enrich_tags(self):
        full_text = "\n".join(self.lines)
        plan_tags = extract_tags(full_text)
        for task in self.tasks:
            task_tags = extract_tags(task.raw_text)
            task.tags = sorted(set(plan_tags + task_tags))


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover_plans(plans_dir: Path) -> list[Path]:
    """Walk plans_dir and return all .md files to parse."""
    files = []
    for p in sorted(plans_dir.rglob("*.md")):
        if p.name in SKIP_FILES:
            continue
        files.append(p)
    return files


# ---------------------------------------------------------------------------
# High-level API
# ---------------------------------------------------------------------------

@dataclass
class AtomizeResult:
    """Result of atomizing a plans directory."""
    tasks: list[dict]
    plans_parsed: int
    errors: list[tuple[str, str]]
    archetype_counts: dict[str, int]
    status_counts: dict[str, int]


def atomize_plans(
    plans_dir: Path,
    plan_files_override: list | None = None,
) -> AtomizeResult:
    """Parse all plan files in a directory into atomic tasks.

    Args:
        plans_dir: Root directory for plan files (used as base for relative paths).
        plan_files_override: Optional list of PlanFile objects from unified discovery.
            When provided, uses these instead of walking plans_dir.

    Returns an AtomizeResult with all tasks as dicts, ready for
    serialization or summary generation.
    """
    all_tasks: list[dict] = []
    errors: list[tuple[str, str]] = []
    archetype_counts: dict[str, int] = {}

    if plan_files_override is not None:
        # Use PlanFile objects from unified discovery
        for pf in plan_files_override:
            try:
                text = pf.path.read_text(encoding="utf-8", errors="replace")
                lines = text.splitlines()
                if not lines:
                    continue

                # Use plans_dir as base; fall back to parent if path isn't relative
                try:
                    base = plans_dir if pf.path.is_relative_to(plans_dir) else pf.path.parent
                except (TypeError, AttributeError):
                    base = pf.path.parent

                parser = PlanParser(
                    lines, pf.path, base,
                    agent=pf.agent,
                    organ=pf.organ,
                    repo=pf.repo,
                )
                tasks = parser.parse()
                archetype_counts[parser.archetype] = (
                    archetype_counts.get(parser.archetype, 0) + 1
                )

                for task in tasks:
                    all_tasks.append(task.to_dict())
            except Exception as e:
                errors.append((str(pf.path), str(e)))

        plans_parsed = len(plan_files_override)
    else:
        # Original behavior: walk plans_dir
        raw_files = discover_plans(plans_dir)
        for filepath in raw_files:
            try:
                text = filepath.read_text(encoding="utf-8", errors="replace")
                lines = text.splitlines()
                if not lines:
                    continue

                parser = PlanParser(lines, filepath, plans_dir)
                tasks = parser.parse()
                archetype_counts[parser.archetype] = (
                    archetype_counts.get(parser.archetype, 0) + 1
                )

                for task in tasks:
                    all_tasks.append(task.to_dict())
            except Exception as e:
                errors.append((str(filepath.relative_to(plans_dir)), str(e)))

        plans_parsed = len(raw_files)

    status_counts: dict[str, int] = {}
    for t in all_tasks:
        status_counts[t["status"]] = status_counts.get(t["status"], 0) + 1

    return AtomizeResult(
        tasks=all_tasks,
        plans_parsed=plans_parsed,
        errors=errors,
        archetype_counts=archetype_counts,
        status_counts=status_counts,
    )


def atomize_all(
    workspace: Path | None = None,
    agent: str | None = None,
    organ: str | None = None,
) -> AtomizeResult:
    """Discover plans from the workspace and atomize them all.

    Convenience function that bridges unified discovery with atomization.
    """
    from organvm_engine.session.plans import discover_plans as unified_discover

    plan_files = unified_discover(
        workspace=workspace, agent=agent, organ=organ,
    )
    base = workspace or Path.home() / "Workspace"
    return atomize_plans(base, plan_files_override=plan_files)


class DuplicateTaskIdError(ValueError):
    """A task collection has ambiguous IDs."""


def write_jsonl(tasks: list[dict], output_path: Path) -> None:
    """Write tasks as JSONL."""
    ids: set[str] = set()
    for task in tasks:
        task_id = task.get("id")
        if task_id in ids:
            raise DuplicateTaskIdError(f"duplicate task ID: {task_id}")
        ids.add(task_id)
    with output_path.open("w", encoding="utf-8") as f:
        for task in tasks:
            f.write(json.dumps(task, ensure_ascii=False) + "\n")
