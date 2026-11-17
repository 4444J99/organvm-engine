"""One-off migration of legacy full ORGANVM:AUTO blocks to the pointer.

The registry-driven sync (``organvm context sync``) only reaches registered
repositories. Instruction files elsewhere still carry a full generated block
between the AUTO markers. This module moves that block's text, verbatim, into
``docs/organvm-context.md`` beside the instruction file and replaces the block
with the standard pointer, keeping the block's own ``Last synced`` stamp. It is
pure file work: no registry, no ontologia, atomic replace for every write.

Per directory the document comes from CLAUDE.md, else AGENTS.md, else GEMINI.md.
Sibling blocks whose text differs from it are still replaced by the pointer and
reported as differing (their text is not in the document). An existing document
is never overwritten.
"""

from __future__ import annotations

import os
import re
import secrets
import stat
from dataclasses import asdict, dataclass, field
from pathlib import Path

from organvm_engine.contextmd import AUTO_END, AUTO_START, CONTEXT_DOCUMENT_RELPATH
from organvm_engine.contextmd.generator import generate_context_pointer
from organvm_engine.contextmd.reader import is_pointer_block

# Which sibling supplies the document when several carry a full block.
SOURCE_ORDER = ("CLAUDE.md", "AGENTS.md", "GEMINI.md")
EXCLUDED_PATH_PARTS = ("custody-staging", "session-corpus", "/receipts/", "/legacy/")
PRUNED_DIRECTORIES = frozenset({".git", "node_modules", ".venv", "venv", "__pycache__"})
STAMP = re.compile(r"\*Last synced: (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\*")

SKIP_LINKED_WORKTREE = "linked-worktree"
SKIP_EXCLUDED_PATH = "excluded-path"
SKIP_SYMLINKED_FILE = "symlinked-file"
SKIP_SYMLINKED_DIRECTORY = "symlinked-directory"
SKIP_MALFORMED_MARKERS = "malformed-markers"
SKIP_NO_STAMP = "no-last-synced-stamp"


@dataclass
class FileResult:
    """One instruction file's outcome."""

    path: str
    action: str  # migrate | unchanged | skipped | error
    reason: str = ""
    words_before: int = 0
    words_after: int = 0
    repo: str = ""
    differing: bool = False
    document: str = ""  # created | exists | "" for non-source files / skips
    document_path: str = ""


@dataclass
class MigrationReport:
    """Everything one migration run saw."""

    dry_run: bool
    files: list[FileResult] = field(default_factory=list)
    skipped_directories: list[str] = field(default_factory=list)

    def by_action(self, action: str) -> list[FileResult]:
        return [item for item in self.files if item.action == action]

    def to_dict(self) -> dict:
        return {
            "dry_run": self.dry_run,
            "files": [asdict(item) for item in self.files],
            "skipped_directories": list(self.skipped_directories),
        }


def migrate_legacy(paths: list[Path | str], *, write: bool = False) -> MigrationReport:
    """Migrate legacy full blocks under ``paths`` (files or directories)."""
    report = MigrationReport(dry_run=not write)
    candidates: list[Path] = []
    for raw in paths:
        candidates.extend(_collect(Path(raw), report))

    pending: dict[Path, list[_Legacy]] = {}
    for path in sorted(set(candidates)):
        legacy = _classify(path, report)
        if legacy is not None:
            pending.setdefault(path.parent, []).append(legacy)

    for directory in sorted(pending):
        _migrate_directory(directory, pending[directory], report, write=write)
    report.files.sort(key=lambda item: item.path)
    return report


# ── discovery ─────────────────────────────────────────────────────────


def _collect(root: Path, report: MigrationReport) -> list[Path]:
    """Return instruction files under ``root``; never descend into symlinked directories."""
    if root.is_symlink() and root.is_dir():
        report.skipped_directories.append(str(root))
        return []
    if root.is_file() or root.is_symlink():
        return [root] if root.name in SOURCE_ORDER else []
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        kept = []
        for name in sorted(dirnames):
            child = Path(dirpath) / name
            if name in PRUNED_DIRECTORIES:
                continue
            if child.is_symlink():
                report.skipped_directories.append(str(child))
                continue
            kept.append(name)
        dirnames[:] = kept
        found.extend(Path(dirpath) / name for name in filenames if name in SOURCE_ORDER)
    return found


@dataclass
class _Legacy:
    path: Path
    original: bytes
    text: str
    start: int
    end_exclusive: int
    inner: str
    stamp: str


def _classify(path: Path, report: MigrationReport) -> _Legacy | None:
    """Return the legacy block of ``path``, or record why it is not migratable."""
    try:
        original = path.read_bytes()
    except OSError as exc:
        report.files.append(FileResult(str(path), "error", f"unreadable: {exc}"))
        return None
    text = original.decode("utf-8", errors="surrogateescape")
    start = text.find(AUTO_START)
    end = text.rfind(AUTO_END)
    if start < 0 and end < 0:
        return None
    if start < 0 or end < start:
        report.files.append(
            FileResult(str(path), "skipped", SKIP_MALFORMED_MARKERS, repo=_repo_of(path)),
        )
        return None
    inner = text[start + len(AUTO_START) : end]
    words = len(inner.split())
    repo = _repo_of(path)
    if is_pointer_block(inner):
        report.files.append(
            FileResult(str(path), "unchanged", "already a pointer", words, words, repo),
        )
        return None
    reason = _skip_reason(path)
    if reason:
        report.files.append(FileResult(str(path), "skipped", reason, words, 0, repo))
        return None
    match = STAMP.search(inner)
    if match is None:
        report.files.append(FileResult(str(path), "skipped", SKIP_NO_STAMP, words, 0, repo))
        return None
    return _Legacy(path, original, text, start, end + len(AUTO_END), inner, match.group(1))


def _skip_reason(path: Path) -> str:
    top = _git_top(path)
    if top is not None and (top / ".git").is_file():
        return SKIP_LINKED_WORKTREE
    spelled = str(path)
    if any(part in spelled for part in EXCLUDED_PATH_PARTS):
        return SKIP_EXCLUDED_PATH
    if path.is_symlink():
        return SKIP_SYMLINKED_FILE
    return ""


def _git_top(path: Path) -> Path | None:
    """Nearest ancestor directory holding a ``.git`` entry (a directory or a gitfile)."""
    for ancestor in path.parents:
        if os.path.lexists(ancestor / ".git"):
            return ancestor
    return None


def _repo_of(path: Path) -> str:
    top = _git_top(path)
    return str(top) if top is not None else "(no git repository)"


# ── migration ─────────────────────────────────────────────────────────


def _migrate_directory(
    directory: Path,
    legacy: list[_Legacy],
    report: MigrationReport,
    *,
    write: bool,
) -> None:
    ordered = sorted(legacy, key=lambda item: SOURCE_ORDER.index(item.path.name))
    source = ordered[0]
    source_text = _document_text(source)
    document = directory / CONTEXT_DOCUMENT_RELPATH
    document_state = "exists" if os.path.lexists(document) else "created"
    results: list[FileResult] = []
    for item in ordered:
        results.append(
            FileResult(
                str(item.path),
                "migrate",
                words_before=len(item.inner.split()),
                words_after=len(_inner(generate_context_pointer(item.stamp)).split()),
                repo=_repo_of(item.path),
                differing=item.inner.strip() != source.inner.strip(),
                document=document_state if item is source else "",
                document_path=str(document) if item is source else "",
            ),
        )
    if write:
        # The document first: a failure there leaves every instruction file untouched.
        try:
            if document_state == "created":
                _create_document(document, source_text.encode("utf-8", "surrogateescape"))
        except Exception as exc:
            for result in results:
                result.action, result.reason = "error", str(exc)
            report.files.extend(results)
            return
        for item, result in zip(ordered, results, strict=True):
            try:
                _replace_block(item)
            except Exception as exc:  # one file's failure must not stop the run
                result.action, result.reason = "error", str(exc)
    report.files.extend(results)


def _inner(block: str) -> str:
    return block.replace(AUTO_START, "").replace(AUTO_END, "")


def _document_text(source: _Legacy) -> str:
    """The block's inner text verbatim, minus the newline after START and before END."""
    inner = source.inner
    inner = inner.removeprefix("\n").removesuffix("\n")
    return inner + "\n"


def _replace_block(item: _Legacy) -> None:
    pointer = generate_context_pointer(item.stamp)
    updated = item.text[: item.start] + pointer + item.text[item.end_exclusive :]
    _atomic_replace(item.path, updated.encode("utf-8", "surrogateescape"), item.original)


# ── atomic file writes ────────────────────────────────────────────────


def _atomic_replace(path: Path, data: bytes, expected: bytes) -> None:
    """Replace ``path`` with ``data`` iff it still holds ``expected`` (temp file + rename)."""
    if path.read_bytes() != expected:
        raise RuntimeError(f"changed during migration: {path}")
    mode = stat.S_IMODE(path.stat().st_mode)
    temp = path.with_name(f".{path.name}.migrate-{secrets.token_hex(6)}")
    try:
        _write_new_file(temp, data, mode)
        temp.replace(path)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    _fsync_directory(path.parent)


def _create_document(document: Path, data: bytes) -> None:
    """Create ``document`` atomically; an existing one is never overwritten."""
    if document.parent.is_symlink():
        raise RuntimeError(f"docs directory is a symlink: {document.parent}")
    document.parent.mkdir(exist_ok=True)
    temp = document.with_name(f".{document.name}.migrate-{secrets.token_hex(6)}")
    try:
        _write_new_file(temp, data, 0o644)
        try:
            os.link(temp, document)
        except FileExistsError:
            return
    finally:
        temp.unlink(missing_ok=True)
    _fsync_directory(document.parent)


def _write_new_file(path: Path, data: bytes, mode: int) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(descriptor, view) :]
        os.fchmod(descriptor, mode)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
