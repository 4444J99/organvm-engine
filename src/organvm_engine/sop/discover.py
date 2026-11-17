"""Discover SOP and METADOC files across the workspace."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from organvm_engine._stable_io import StableReadError, read_stable_regular_bytes
from organvm_engine.organ_config import ORGANS
from organvm_engine.paths import workspace_root

# All org directories including PERSONAL (4444J99).
# Use dict.fromkeys to deduplicate while preserving insertion order
# (LIMINAL and SIGMA_E share dir "4444J99").
ALL_ORG_DIRS = list(dict.fromkeys(v["dir"] for v in ORGANS.values()))

# Filename patterns (case-insensitive matching)
_SOP_PATTERNS = re.compile(
    r"^(SOP--|sop--|sop-|METADOC--|metadoc--|APPENDIX--|appendix--).*\.md$",
    re.IGNORECASE,
)

# Directory segments to skip entirely
_EXCLUDED_SEGMENTS = frozenset({
    "node_modules", ".venv", ".git", ".tox", "__pycache__",
    "ARCHIVE_RK01", "vault_backup", "zip_fossils",
})

# Directory names to skip at any depth within a repo
_EXCLUDED_ANY_DEPTH = frozenset({"archive"})

# Top-level directories under an org/repo to skip
_EXCLUDED_TOPLEVEL = frozenset({"intake"})

# Repo-level directories to skip entirely (e.g. meta-organvm/intake/)
_EXCLUDED_REPOS = frozenset({"intake"})


@dataclass
class SOPEntry:
    path: Path
    org: str
    repo: str
    filename: str
    title: str | None
    doc_type: str  # "SOP" | "METADOC" | "APPENDIX" | "SOP-SKILL" | "unknown"
    canonical: bool  # True if in praxis-perpetua/standards/
    has_canonical_header: bool  # True if starts with '> **Canonical location:**'
    scope: str = "unknown"  # "system" | "organ" | "repo" | "unknown"
    phase: str = "any"  # genesis | foundation | hardening | graduation | sustaining | any
    triggers: list[str] = field(default_factory=list)
    overrides: str | None = None
    complements: list[str] = field(default_factory=list)
    sop_name: str | None = None  # from frontmatter 'name' or derived from filename
    source_bytes: int | None = None
    source_sha256: str | None = None
    source_snapshot_attempted: bool = False


def _parse_frontmatter(path: Path) -> dict:
    """Extract YAML frontmatter from a markdown file.

    Looks for content between opening and closing '---' markers.
    Returns empty dict if no frontmatter found or on parse error.
    """
    text = _read_discovery_text(path)
    if text is None:
        return {}
    return _parse_frontmatter_text(text)


def _parse_frontmatter_text(text: str) -> dict:
    """Parse frontmatter from one already bound discovery snapshot."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    frontmatter: list[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            try:
                parsed = yaml.safe_load("\n".join(frontmatter)) or {}
            except yaml.YAMLError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        frontmatter.append(line)
    return {}


def _derive_sop_name(filename: str) -> str:
    """Derive a SOP name from a filename.

    'SOP--structural-integrity-audit.md' → 'structural-integrity-audit'
    'registry-update-protocol.md' → 'registry-update-protocol'
    """
    stem = Path(filename).stem
    # Strip SOP--, sop--, METADOC--, etc. prefixes
    return re.sub(r"^(SOP--|sop--|sop-|METADOC--|metadoc--|APPENDIX--|appendix--)", "", stem)


def _infer_scope(path: Path, workspace: Path) -> str:
    """Infer scope (system/organ/repo) from file location.

    - praxis-perpetua/standards/ → system
    - {org}/.sops/ (at org superproject level) → organ
    - {org}/{repo}/.sops/ → repo
    - Otherwise → unknown (legacy SOP, user should add frontmatter)
    """
    try:
        rel = path.relative_to(workspace)
    except ValueError:
        return "unknown"

    parts = rel.parts
    if len(parts) < 2:
        return "unknown"

    # system: praxis-perpetua/standards/
    if (
        len(parts) >= 4
        and parts[0] == "meta-organvm"
        and parts[1] == "praxis-perpetua"
        and parts[2] == "standards"
    ):
        return "system"

    # organ: {org}/.sops/foo.md (exactly 3 parts: org/.sops/file.md)
    if len(parts) == 3 and parts[1] == ".sops":
        return "organ"

    # repo: {org}/{repo}/.sops/foo.md (exactly 4 parts)
    if len(parts) == 4 and parts[2] == ".sops":
        return "repo"

    return "unknown"


def _should_skip(path: Path) -> bool:
    """Check if any path segment matches exclusion rules."""
    parts = path.parts
    for part in parts:
        if part in _EXCLUDED_SEGMENTS:
            return True
        # Skip vault backups by substring
        if "vault_backup" in part:
            return True
    return False


def _extract_title(path: Path) -> str | None:
    """Extract title from first heading line (first 10 lines)."""
    text = _read_discovery_text(path)
    if text is None:
        return None
    return _extract_title_text(text)


def _extract_title_text(text: str) -> str | None:
    for raw_line in text.splitlines()[:10]:
        line = raw_line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return None


def _has_canonical_header(path: Path) -> bool:
    """Check if file starts with canonical location blockquote."""
    text = _read_discovery_text(path)
    return _has_canonical_header_text(text) if text is not None else False


def _has_canonical_header_text(text: str) -> bool:
    first_line = text.splitlines()[0].strip() if text.splitlines() else ""
    return first_line.startswith("> **Canonical location:**")


def _read_discovery_text(path: Path) -> str | None:
    """Return one stable bounded SOP snapshot, or fail closed to no metadata."""
    payload = _read_discovery_payload(path)
    return payload.decode("utf-8", errors="replace") if payload is not None else None


def _read_discovery_payload(path: Path) -> bytes | None:
    """Return one stable bounded SOP byte snapshot, or fail closed."""
    try:
        return read_stable_regular_bytes(path)
    except StableReadError:
        return None


def _classify_doc_type(filename: str) -> str:
    lower = filename.lower()
    if lower.startswith(("sop--", "sop-")):
        return "SOP"
    if lower.startswith("metadoc--"):
        return "METADOC"
    if lower.startswith("appendix--"):
        return "APPENDIX"
    return "unknown"


def _is_in_praxis_standards(path: Path, workspace: Path) -> bool:
    """Check if path is under praxis-perpetua/standards/."""
    try:
        rel = path.relative_to(workspace)
        parts = rel.parts
        return (
            len(parts) >= 4
            and parts[0] == "meta-organvm"
            and parts[1] == "praxis-perpetua"
            and parts[2] == "standards"
        )
    except ValueError:
        return False


def discover_sops(
    workspace: Path | str | None = None,
    organ: str | None = None,
) -> list[SOPEntry]:
    """Walk the workspace and find all SOP/METADOC files.

    Args:
        workspace: Root workspace directory. Defaults to ~/Workspace.
        organ: If set, only scan this organ's directory (CLI key like "I", "META").

    Returns:
        Sorted list of SOPEntry objects.
    """
    ws = Path(workspace) if workspace else workspace_root()

    repo_identity = _repo_root_identity(ws)
    if repo_identity is not None:
        org_name, repo_name = repo_identity
        if organ and not _matches_organ_filter(org_name, organ):
            return []
        entries: list[SOPEntry] = []
        _scan_repo(ws, org_name, repo_name, ws, entries)
        _scan_sops_dir(ws, org_name, repo_name, ws / ".sops", entries)
        return sorted(entries, key=lambda e: (e.org, e.repo, e.filename))

    if organ:
        org_meta = ORGANS.get(organ.upper())
        if not org_meta:
            return []
        scan_dirs = [org_meta["dir"]]
    else:
        scan_dirs = ALL_ORG_DIRS

    entries: list[SOPEntry] = []

    for org_name in scan_dirs:
        org_dir = ws / org_name
        if not org_dir.is_dir():
            continue

        # Scan organ-level .sops/ directory (T3)
        _scan_sops_dir(ws, org_name, org_name, org_dir / ".sops", entries)

        for repo_dir in sorted(org_dir.iterdir()):
            if not repo_dir.is_dir():
                continue
            if repo_dir.name in _EXCLUDED_REPOS:
                continue
            # Walk the repo looking for SOP files
            _scan_repo(ws, org_name, repo_dir.name, repo_dir, entries)
            # Scan repo-level .sops/ directory (T4)
            _scan_sops_dir(ws, org_name, repo_dir.name, repo_dir / ".sops", entries)

    return sorted(entries, key=lambda e: (e.org, e.repo, e.filename))


def _repo_root_identity(path: Path) -> tuple[str, str] | None:
    """Return ``(org, repo)`` when *path* itself is a repo root."""
    if any((path / org_dir).is_dir() for org_dir in ALL_ORG_DIRS):
        return None
    if not (path / "seed.yaml").is_file() and not (path / ".sops").is_dir():
        return None

    org_name = path.parent.name
    repo_name = path.name
    seed_path = path / "seed.yaml"
    if seed_path.is_file():
        try:
            data = yaml.safe_load(read_stable_regular_bytes(seed_path)) or {}
        except (StableReadError, yaml.YAMLError):
            data = {}
        if isinstance(data, dict):
            seed_org = data.get("org") or data.get("organ")
            seed_repo = data.get("repo")
            if isinstance(seed_org, str) and seed_org:
                org_name = seed_org
            if isinstance(seed_repo, str) and seed_repo:
                repo_name = seed_repo
    return org_name, repo_name


def _matches_organ_filter(org_name: str, organ: str) -> bool:
    org_meta = ORGANS.get(organ.upper())
    if org_meta:
        return org_meta["dir"] == org_name
    return org_name == organ


def _scan_repo(
    workspace: Path,
    org_name: str,
    repo_name: str,
    repo_dir: Path,
    entries: list[SOPEntry],
) -> None:
    """Recursively scan a repo directory for SOP files."""
    for item in _walk_safe(repo_dir):
        if not item.is_file():
            continue
        if not _SOP_PATTERNS.match(item.name):
            continue
        if _should_skip(item):
            continue

        # Skip excluded directories
        try:
            rel_to_repo = item.relative_to(repo_dir)
            parts_lower = [p.lower() for p in rel_to_repo.parts]
            # Skip intake/ at repo top level
            if parts_lower and parts_lower[0] in _EXCLUDED_TOPLEVEL:
                continue
            # Skip archive/ at any depth
            if any(p in _EXCLUDED_ANY_DEPTH for p in parts_lower):
                continue
        except ValueError:
            continue

        entries.append(_build_entry(item, workspace, org_name, repo_name))


def _scan_sops_dir(
    workspace: Path,
    org_name: str,
    repo_name: str,
    sops_dir: Path,
    entries: list[SOPEntry],
) -> None:
    """Scan a .sops/ directory for SOP-skill files.

    Any .md file in .sops/ is treated as an SOP-skill regardless of filename.
    """
    if not sops_dir.is_dir():
        return
    try:
        for item in sorted(sops_dir.iterdir()):
            if item.is_file() and item.suffix == ".md":
                entries.append(_build_entry(
                    item, workspace, org_name, repo_name, doc_type_override="SOP-SKILL",
                ))
    except PermissionError:
        pass


def _build_entry(
    item: Path,
    workspace: Path,
    org_name: str,
    repo_name: str,
    doc_type_override: str | None = None,
) -> SOPEntry:
    """Build a fully-enriched SOPEntry from a file path."""
    source_payload = _read_discovery_payload(item)
    text = (
        source_payload.decode("utf-8", errors="replace")
        if source_payload is not None
        else None
    )
    fm = _parse_frontmatter_text(text) if text is not None else {}
    scope_from_fm = fm.get("scope")
    scope = scope_from_fm if scope_from_fm in ("system", "organ", "repo") else _infer_scope(
        item, workspace,
    )
    sop_name = fm.get("name") or _derive_sop_name(item.name)
    phase = fm.get("phase", "any")

    return SOPEntry(
        path=item,
        org=org_name,
        repo=repo_name,
        filename=item.name,
        title=_extract_title_text(text) if text is not None else None,
        doc_type=doc_type_override or _classify_doc_type(item.name),
        canonical=_is_in_praxis_standards(item, workspace),
        has_canonical_header=(
            _has_canonical_header_text(text) if text is not None else False
        ),
        scope=scope,
        phase=phase,
        triggers=fm.get("triggers") or [],
        overrides=fm.get("overrides"),
        complements=fm.get("complements") or [],
        sop_name=sop_name,
        source_bytes=len(source_payload) if source_payload is not None else None,
        source_sha256=(
            "sha256:" + hashlib.sha256(source_payload).hexdigest()
            if source_payload is not None
            else None
        ),
        source_snapshot_attempted=True,
    )


def _walk_safe(root: Path) -> list[Path]:
    """Walk directory tree, skipping excluded segments."""
    results: list[Path] = []
    try:
        for item in sorted(root.iterdir()):
            if item.name in _EXCLUDED_SEGMENTS:
                continue
            if item.name.startswith("."):
                continue
            if "vault_backup" in item.name:
                continue
            if item.name.lower() in _EXCLUDED_ANY_DEPTH:
                continue
            if item.is_file():
                results.append(item)
            elif item.is_dir():
                results.extend(_walk_safe(item))
    except PermissionError:
        pass
    return results
