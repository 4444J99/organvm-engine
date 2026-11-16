"""The generator writes docs/organvm-context.md and leaves only a pointer in instruction files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from organvm_engine.contextmd import AUTO_END, AUTO_START
from organvm_engine.contextmd.generator import (
    compose_context_document,
    generate_agents_section,
    generate_context_pointer,
    generate_repo_section,
)
from organvm_engine.contextmd.reader import is_pointer_block, read_generated_context
from organvm_engine.contextmd.sync import _inject_section_result, sync_all, sync_repo
from organvm_engine.registry.loader import load_registry

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
DOCUMENT = Path("docs") / "organvm-context.md"
T1 = "2026-11-16T10:00:00Z"
T2 = "2026-11-16T10:05:00Z"

EXPECTED_POINTER = (
    f"{AUTO_START}\n"
    "Generated system context (organ, edges, directives, task queue, density) is in "
    "`docs/organvm-context.md`.\n"
    "Read it when you need it; it is refreshed by `organvm context sync --write`. "
    f"*Last synced: {T1}*\n"
    f"{AUTO_END}"
)


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.setattr(
        "organvm_engine.contextmd.receipt.generator_git_identity",
        lambda *args, **kwargs: {"commit": "a" * 40, "tree": "b" * 40},
    )
    monkeypatch.setattr("organvm_engine.contextmd.sync.precompute_ammoi", lambda: None)
    monkeypatch.setattr(
        "organvm_engine.pulse.emitter.emit_engine_event", lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "organvm_engine.ledger.emit.testament_emit", lambda *args, **kwargs: None,
    )


@pytest.fixture
def registry():
    return load_registry(FIXTURES / "registry-minimal.json")


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "workspace"
    (root / "organvm-i-theoria" / "recursive-engine").mkdir(parents=True)
    return root


def repo_of(workspace: Path) -> Path:
    return workspace / "organvm-i-theoria" / "recursive-engine"


def run_sync(workspace: Path, **kwargs):
    return sync_all(
        workspace=workspace,
        registry_path=str(FIXTURES / "registry-minimal.json"),
        additional_workspace_roots=[],
        organs=["ORGAN-I"],
        **kwargs,
    )


def block_words(path: Path) -> int:
    text = path.read_text()
    block = text[text.index(AUTO_START) : text.index(AUTO_END) + len(AUTO_END)]
    return len(block.replace(AUTO_START, "").replace(AUTO_END, "").split())


# ── pointer text ──────────────────────────────────────────────────────


def test_pointer_text_is_exactly_the_decided_pointer():
    assert generate_context_pointer(T1) == EXPECTED_POINTER


def test_pointer_is_a_short_block_with_the_sync_stamp_inside_it():
    pointer = generate_context_pointer(T1)
    assert len(pointer.replace(AUTO_START, "").replace(AUTO_END, "").split()) <= 60
    inside = pointer.split(AUTO_START, 1)[1].split(AUTO_END, 1)[0]
    assert f"Last synced: {T1}" in inside
    assert is_pointer_block(inside)


# ── pointer written, full context in docs/organvm-context.md ──────────


def test_sync_repo_writes_the_document_and_only_a_pointer(tmp_path, registry):
    repo = tmp_path / "recursive-engine"
    repo.mkdir()
    for name in ("CLAUDE.md", "GEMINI.md", "AGENTS.md"):
        result = sync_repo(
            repo, "recursive-engine", "organvm-i-theoria", registry,
            filename=name, timestamp=T1, include_live_context=False,
        )
        assert (repo / name).read_text() == EXPECTED_POINTER + "\n"
        assert result["context_document"]["path"] == str(repo / DOCUMENT)

    document = (repo / DOCUMENT).read_text()
    assert document.splitlines()[0].startswith("<!-- GENERATED FILE")
    assert "## System Context (auto-generated" in document
    assert "## Agent Context (auto-generated" in document
    assert "`recursive-engine`" in document
    assert AUTO_START not in document
    assert AUTO_END not in document


def test_document_carries_every_agents_prompting_hint(tmp_path, registry):
    repo = tmp_path / "recursive-engine"
    repo.mkdir()
    sync_repo(repo, "recursive-engine", "organvm-i-theoria", registry, timestamp=T1)
    document = (repo / DOCUMENT).read_text()
    assert "**Prompting (Anthropic)**" in document
    assert "**Prompting (Google)**" in document


def test_sync_all_writes_a_document_and_pointers_at_every_level(workspace):
    result = run_sync(workspace)

    assert result["errors"] == []
    levels = [workspace, workspace / "organvm-i-theoria", repo_of(workspace)]
    for level in levels:
        assert (level / DOCUMENT).is_file()
        assert str(level / DOCUMENT) in result["created"]
        for name in ("CLAUDE.md", "GEMINI.md", "AGENTS.md"):
            text = (level / name).read_text()
            assert text.count(AUTO_START) == 1
            assert "docs/organvm-context.md" in text
            assert block_words(level / name) <= 60
    assert "## System Overview" in (workspace / DOCUMENT).read_text()
    assert "## Organ Map" in (workspace / "organvm-i-theoria" / DOCUMENT).read_text()
    assert "## System Context" in (repo_of(workspace) / DOCUMENT).read_text()
    assert "## Agent Context" in (repo_of(workspace) / DOCUMENT).read_text()


def test_dry_run_reports_the_document_and_each_pointer_without_writing(workspace):
    result = run_sync(workspace, dry_run=True)

    assert result["dry_run"] is True
    reported = set(result["created"]) | set(result["updated"])
    for level in (workspace, workspace / "organvm-i-theoria", repo_of(workspace)):
        assert str(level / DOCUMENT) in reported
        for name in ("CLAUDE.md", "GEMINI.md", "AGENTS.md"):
            assert str(level / name) in reported
    assert {change["path"] for change in result["changes"]} >= {
        str(repo_of(workspace) / DOCUMENT),
        str(repo_of(workspace) / "CLAUDE.md"),
    }
    assert not (workspace / "docs").exists()
    assert not (repo_of(workspace) / "docs").exists()
    assert not (repo_of(workspace) / "CLAUDE.md").exists()


# ── idempotency ───────────────────────────────────────────────────────


def test_second_run_with_a_later_timestamp_changes_nothing(tmp_path, registry):
    repo = tmp_path / "recursive-engine"
    repo.mkdir()
    sync_repo(
        repo, "recursive-engine", "organvm-i-theoria", registry,
        timestamp=T1, include_live_context=False,
    )
    before = {
        path.relative_to(repo): path.read_bytes() for path in repo.rglob("*") if path.is_file()
    }

    result = sync_repo(
        repo, "recursive-engine", "organvm-i-theoria", registry,
        timestamp=T2, include_live_context=False,
    )

    after = {
        path.relative_to(repo): path.read_bytes() for path in repo.rglob("*") if path.is_file()
    }
    assert result["action"] == "unchanged"
    assert result["context_document"]["action"] == "unchanged"
    assert after == before
    assert T2.encode() not in b"".join(after.values())


def test_sync_all_second_run_is_all_skipped(workspace):
    first = run_sync(workspace)
    second = run_sync(workspace)

    assert first["errors"] == [] and second["errors"] == []
    assert second["created"] == []
    assert second["updated"] == []
    assert len(second["skipped"]) == len(first["created"]) + len(first["updated"])


def test_pointer_stamp_moves_only_when_the_document_changes(tmp_path, registry):
    repo = tmp_path / "recursive-engine"
    repo.mkdir()
    sync_repo(
        repo, "recursive-engine", "organvm-i-theoria", registry,
        timestamp=T1, include_live_context=False,
    )
    seed = {"produces": [{"target": "repo-b", "artifact": "data"}]}

    result = sync_repo(
        repo, "recursive-engine", "organvm-i-theoria", registry, seed=seed,
        timestamp=T2, include_live_context=False,
    )

    assert result["context_document"]["action"] == "updated"
    assert result["action"] == "updated"
    pointer = (repo / "CLAUDE.md").read_text()
    assert f"Last synced: {T2}" in pointer
    assert f"Last synced: {T1}" not in pointer
    assert "repo-b" in (repo / DOCUMENT).read_text()
    assert "repo-b" not in pointer


# ── migration of a legacy full block ──────────────────────────────────


def test_a_file_with_a_legacy_full_block_is_migrated_to_the_pointer(workspace, registry):
    repo = repo_of(workspace)
    legacy = generate_repo_section(
        "recursive-engine", "organvm-i-theoria", registry, timestamp="2026-04-01T00:00:00Z",
    )
    (repo / "CLAUDE.md").write_text(
        f"# Recursive Engine\n\nManual intro.\n\n{legacy}\n## Keep This\n\nManual tail.\n",
    )
    (repo / "AGENTS.md").write_text(
        generate_agents_section(
            "recursive-engine", "organvm-i-theoria", registry, timestamp="2026-04-01T00:00:00Z",
        ),
    )
    assert block_words(repo / "CLAUDE.md") > 60

    result = run_sync(workspace)

    assert result["errors"] == []
    claude = (repo / "CLAUDE.md").read_text()
    assert "Manual intro." in claude
    assert "## Keep This" in claude and "Manual tail." in claude
    assert "### Edges" not in claude
    assert "Active Handoff Protocol" not in claude
    assert claude.count(AUTO_START) == 1
    assert block_words(repo / "CLAUDE.md") <= 60
    assert "### Edges" not in (repo / "AGENTS.md").read_text()
    assert "### Edges" in (repo / DOCUMENT).read_text()
    assert str(repo / "CLAUDE.md") in result["updated"]
    assert str(repo / DOCUMENT) in result["created"]


def test_a_failed_document_write_leaves_the_legacy_block_in_place(workspace, registry):
    repo = repo_of(workspace)
    legacy = generate_repo_section(
        "recursive-engine", "organvm-i-theoria", registry, timestamp="2026-04-01T00:00:00Z",
    )
    (repo / "CLAUDE.md").write_text(legacy + "\n")
    (repo / "docs").write_text("a file where the directory should be\n")

    result = run_sync(workspace)

    assert any(error["path"] == str(repo / DOCUMENT) for error in result["errors"])
    assert (repo / "CLAUDE.md").read_text() == legacy + "\n"
    assert not (repo / "GEMINI.md").exists()
    assert not (repo / "AGENTS.md").exists()


def test_whole_file_inject_ignores_only_the_sync_stamps(tmp_path):
    target = tmp_path / "doc.md"
    text = "# Title\n\nbody\n\n*Last synced: 2026-11-16T10:00:00Z*"
    assert _inject_section_result(target, text, whole_file=True)["action"] == "created"
    assert target.read_text() == text + "\n"

    later = text.replace("10:00:00", "11:00:00")
    assert _inject_section_result(target, later, whole_file=True)["action"] == "unchanged"
    assert target.read_text() == text + "\n"

    edited = later.replace("body", "changed body")
    result = _inject_section_result(target, edited, whole_file=True)
    assert result["action"] == "updated"
    assert result["change"]["whole_file"] is True
    assert target.read_text() == edited + "\n"


def test_whole_file_inject_replaces_hand_edits(tmp_path):
    target = tmp_path / "doc.md"
    target.write_text("hand written\n")
    result = _inject_section_result(target, "generated", whole_file=True)
    assert result["action"] == "updated"
    assert target.read_text() == "generated\n"


# ── custody: receipted sync covers the new file ───────────────────────


def test_receipted_sync_binds_the_document_like_any_other_output(workspace):
    first = run_sync(workspace, receipt_path=workspace / "receipt-1.json")
    second = run_sync(workspace, receipt_path=workspace / "receipt-2.json")

    receipt = json.loads((workspace / "receipt-1.json").read_text())
    again = json.loads((workspace / "receipt-2.json").read_text())
    label = "organvm-i-theoria/recursive-engine/docs/organvm-context.md"
    assert receipt["status"] == "success"
    outputs = {item["path"] for item in receipt["outputs"]}
    assert {label, "docs/organvm-context.md", "organvm-i-theoria/docs/organvm-context.md"} <= (
        outputs
    )
    preimages = {item["path"]: item for item in receipt["inputs"]["target_preimages"]}
    assert preimages[label]["state"] == "absent"
    assert set(preimages[label]["parent_identity"]) == {"device", "inode"}
    assert len(first["created"]) == 12
    assert second["created"] == [] and second["updated"] == []
    assert len(second["skipped"]) == 12
    assert receipt["outputs"] == again["outputs"]
    assert all(binding["state"] == "present" for binding in again["inputs"]["target_preimages"])
    assert all(item["journal_object"] == item["sha256"] for item in receipt["outputs"])


def test_receipted_sync_migrates_a_legacy_block_through_custody(workspace, registry):
    repo = repo_of(workspace)
    legacy = generate_repo_section(
        "recursive-engine", "organvm-i-theoria", registry, timestamp="2026-04-01T00:00:00Z",
    )
    (repo / "CLAUDE.md").write_text(f"# Manual\n\n{legacy}\n")

    result = run_sync(workspace, receipt_path=workspace / "receipt.json")

    receipt = json.loads((workspace / "receipt.json").read_text())
    assert receipt["status"] == "success"
    assert result["errors"] == []
    claude = (repo / "CLAUDE.md").read_text()
    assert claude.startswith("# Manual")
    assert "### Edges" not in claude
    assert "### Edges" in (repo / DOCUMENT).read_text()


def test_receipt_failure_restores_both_files_and_removes_the_created_directories(
    workspace, registry, monkeypatch,
):
    import organvm_engine.contextmd.receipt as receipt_mod

    repo = repo_of(workspace)
    legacy = generate_repo_section(
        "recursive-engine", "organvm-i-theoria", registry, timestamp="2026-04-01T00:00:00Z",
    )
    original = f"# Manual\n\n{legacy}\n".encode()
    (repo / "CLAUDE.md").write_bytes(original)

    def fail_receipt_write(*_args, **_kwargs):
        raise OSError("simulated receipt fsync failure")

    monkeypatch.setattr(receipt_mod, "write_context_sync_receipt", fail_receipt_write)

    with pytest.raises(RuntimeError, match="context sync receipt creation failed"):
        run_sync(workspace, receipt_path=workspace / "receipt.json")

    assert (repo / "CLAUDE.md").read_bytes() == original
    assert not (repo / DOCUMENT).exists()
    for level in (workspace, workspace / "organvm-i-theoria", repo):
        assert not (level / "docs").exists()
        assert not (level / "GEMINI.md").exists()
        assert not (level / "AGENTS.md").exists()
    assert not (workspace / "receipt.json").exists()


def test_receipt_failure_keeps_a_docs_directory_that_already_existed(
    workspace, monkeypatch,
):
    import organvm_engine.contextmd.receipt as receipt_mod

    repo = repo_of(workspace)
    (repo / "docs").mkdir()
    (repo / "docs" / "guide.md").write_text("human guide\n")

    def fail_receipt_write(*_args, **_kwargs):
        raise OSError("simulated receipt fsync failure")

    monkeypatch.setattr(receipt_mod, "write_context_sync_receipt", fail_receipt_write)

    with pytest.raises(RuntimeError, match="context sync receipt creation failed"):
        run_sync(workspace, receipt_path=workspace / "receipt.json")

    assert [path.name for path in (repo / "docs").iterdir()] == ["guide.md"]
    assert not (workspace / "docs").exists()


def test_receipted_preflight_failure_removes_directories_it_created(workspace):
    repo = repo_of(workspace)
    elsewhere = workspace.parent / "elsewhere"
    elsewhere.mkdir()
    (repo / "docs").symlink_to(elsewhere, target_is_directory=True)

    with pytest.raises(RuntimeError, match="cannot be a symlink"):
        run_sync(workspace, receipt_path=workspace / "receipt.json")

    assert not (workspace / "docs").exists()
    assert not (workspace / "organvm-i-theoria" / "docs").exists()
    assert list(elsewhere.iterdir()) == []
    assert not (workspace / "receipt.json").exists()


# ── readers ───────────────────────────────────────────────────────────


def test_changelog_records_mark_document_changes_as_whole_file(workspace):
    result = run_sync(workspace, dry_run=True)
    by_path = {change["path"]: change for change in result["changes"]}

    assert by_path[str(repo_of(workspace) / DOCUMENT)]["whole_file"] is True
    assert "whole_file" not in by_path[str(repo_of(workspace) / "CLAUDE.md")]


def _write_changelog(path: Path, records: list[dict]) -> None:
    path.write_text("".join(json.dumps(record) + "\n" for record in records))


def test_cli_rollback_deletes_a_created_document_and_restores_an_updated_one(
    tmp_path, monkeypatch,
):
    from organvm_engine.cli.context import cmd_context_rollback

    created = tmp_path / "created" / "organvm-context.md"
    created.parent.mkdir()
    created.write_text("# generated\n")
    updated = tmp_path / "updated.md"
    updated.write_text("new generated text\n")
    changelog = tmp_path / "changelog.jsonl"
    _write_changelog(
        changelog,
        [
            {
                "timestamp": 7, "path": str(created), "action": "created",
                "old_section": "", "whole_file": True,
            },
            {
                "timestamp": 7, "path": str(updated), "action": "updated",
                "old_section": "old generated text\n", "whole_file": True,
            },
        ],
    )
    monkeypatch.setattr("organvm_engine.paths.context_changelog_path", lambda *a, **k: changelog)

    assert cmd_context_rollback(argparse.Namespace(to="7")) == 0

    assert not created.exists()
    assert updated.read_text() == "old generated text\n"


def test_cli_rollback_restores_the_legacy_block_a_pointer_replaced(tmp_path, monkeypatch):
    from organvm_engine.cli.context import cmd_context_rollback

    legacy = f"{AUTO_START}\n## System Context\nlots of generated text\n{AUTO_END}"
    claude = tmp_path / "CLAUDE.md"
    claude.write_text(f"# Manual\n\n{generate_context_pointer(T1)}\n")
    changelog = tmp_path / "changelog.jsonl"
    _write_changelog(
        changelog,
        [{"timestamp": 9, "path": str(claude), "action": "updated", "old_section": legacy}],
    )
    monkeypatch.setattr("organvm_engine.paths.context_changelog_path", lambda *a, **k: changelog)

    assert cmd_context_rollback(argparse.Namespace(to="9")) == 0

    assert claude.read_text() == f"# Manual\n\n{legacy}\n"


def test_reader_prefers_the_document(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "organvm-context.md").write_text("# from the document\n")
    (tmp_path / "CLAUDE.md").write_text(f"{AUTO_START}\nlegacy text\n{AUTO_END}\n")

    assert read_generated_context(tmp_path) == "# from the document\n"


def test_reader_falls_back_to_a_legacy_block(tmp_path, registry):
    legacy = generate_repo_section(
        "recursive-engine", "organvm-i-theoria", registry, timestamp="2026-04-01T00:00:00Z",
    )
    (tmp_path / "CLAUDE.md").write_text(f"# Manual\n\n{legacy}\n")

    text = read_generated_context(tmp_path)

    assert text is not None
    assert "### Edges" in text
    assert AUTO_START not in text


def test_reader_skips_pointer_blocks_and_returns_none_without_content(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(generate_context_pointer(T1) + "\n")
    (tmp_path / "GEMINI.md").write_text("# no generated block at all\n")

    assert read_generated_context(tmp_path) is None


def test_reader_reads_a_migrated_directory_through_the_document(workspace):
    run_sync(workspace)
    text = read_generated_context(repo_of(workspace))

    assert text is not None
    assert text == (repo_of(workspace) / DOCUMENT).read_text()


def test_compose_context_document_strips_markers_and_leads_with_the_header():
    document = compose_context_document(
        "Title", [f"{AUTO_START}\n## One\n{AUTO_END}", f"{AUTO_START}\n## Two\n{AUTO_END}"],
    )

    assert document.splitlines()[0].startswith("<!-- GENERATED FILE")
    assert document.splitlines()[2] == "# Title"
    assert AUTO_START not in document and AUTO_END not in document
    assert "## One" in document and "## Two" in document
