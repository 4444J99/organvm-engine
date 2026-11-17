"""organvm context migrate-legacy: move legacy full blocks into docs/organvm-context.md."""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest

from organvm_engine.contextmd import AUTO_END, AUTO_START
from organvm_engine.contextmd.generator import generate_context_pointer
from organvm_engine.contextmd.migrate import migrate_legacy

DOCUMENT = Path("docs") / "organvm-context.md"
STAMP = "2026-04-01T08:30:00Z"
BODY = "## System Context (auto-generated — do not edit)\n\nA fairly long generated body.\n"


def legacy_block(body: str = BODY, stamp: str | None = STAMP) -> str:
    tail = f"\n*Last synced: {stamp}*\n" if stamp else "\n"
    return f"{AUTO_START}\n{body}{tail}{AUTO_END}"


def write_instruction(path: Path, block: str | None = None, *, around: bool = True) -> str:
    block = legacy_block() if block is None else block
    text = f"# Manual intro\n\n{block}\n\n## Keep this\n" if around else block
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return text


def verbatim(body: str = BODY, stamp: str | None = STAMP) -> str:
    inner = legacy_block(body, stamp).removeprefix(AUTO_START).removesuffix(AUTO_END)
    return inner.removeprefix("\n").removesuffix("\n") + "\n"


def tree(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".git" not in path.parts
    }


# ── the migration itself ──────────────────────────────────────────────


def test_block_text_moves_verbatim_and_the_pointer_keeps_the_blocks_own_stamp(tmp_path):
    repo = tmp_path / "repo"
    write_instruction(repo / "CLAUDE.md")

    report = migrate_legacy([repo], write=True)

    assert (repo / DOCUMENT).read_text() == verbatim()
    claude = (repo / "CLAUDE.md").read_text()
    assert claude == f"# Manual intro\n\n{generate_context_pointer(STAMP)}\n\n## Keep this\n"
    assert f"*Last synced: {STAMP}*" in claude
    (item,) = report.by_action("migrate")
    assert item.words_before == len(legacy_block().replace(AUTO_START, "").replace(AUTO_END, "").split())
    assert item.words_after == 29
    assert item.document == "created"
    assert not report.by_action("error")


def test_default_is_a_dry_run_that_changes_nothing(tmp_path):
    repo = tmp_path / "repo"
    write_instruction(repo / "CLAUDE.md")
    before = tree(tmp_path)

    report = migrate_legacy([repo])

    assert report.dry_run is True
    assert tree(tmp_path) == before
    (item,) = report.by_action("migrate")
    assert item.document == "created"


def test_document_comes_from_claude_then_agents_then_gemini(tmp_path):
    first = tmp_path / "a"
    second = tmp_path / "b"
    third = tmp_path / "c"
    write_instruction(first / "CLAUDE.md", legacy_block("claude body\n"))
    write_instruction(first / "AGENTS.md", legacy_block("agents body\n"))
    write_instruction(first / "GEMINI.md", legacy_block("gemini body\n"))
    write_instruction(second / "GEMINI.md", legacy_block("gemini body\n"))
    write_instruction(second / "AGENTS.md", legacy_block("agents body\n"))
    write_instruction(third / "GEMINI.md", legacy_block("gemini body\n"))

    migrate_legacy([tmp_path], write=True)

    assert (first / DOCUMENT).read_text() == verbatim("claude body\n")
    assert (second / DOCUMENT).read_text() == verbatim("agents body\n")
    assert (third / DOCUMENT).read_text() == verbatim("gemini body\n")


def test_siblings_with_different_text_are_reported_as_differing_and_still_get_the_pointer(
    tmp_path,
):
    repo = tmp_path / "repo"
    write_instruction(repo / "CLAUDE.md", legacy_block("shared body\n", "2026-04-01T00:00:00Z"))
    write_instruction(repo / "GEMINI.md", legacy_block("shared body\n", "2026-04-01T00:00:00Z"))
    write_instruction(repo / "AGENTS.md", legacy_block("agent only body\n", "2026-05-02T00:00:00Z"))

    report = migrate_legacy([repo], write=True)

    by_name = {Path(item.path).name: item for item in report.by_action("migrate")}
    assert by_name["CLAUDE.md"].differing is False
    assert by_name["GEMINI.md"].differing is False
    assert by_name["AGENTS.md"].differing is True
    assert by_name["CLAUDE.md"].document == "created"
    assert by_name["AGENTS.md"].document == ""
    assert "agent only body" not in (repo / DOCUMENT).read_text()
    # Each file's pointer keeps that file's own stamp.
    assert "Last synced: 2026-05-02T00:00:00Z" in (repo / "AGENTS.md").read_text()
    assert "Last synced: 2026-04-01T00:00:00Z" in (repo / "GEMINI.md").read_text()
    for name in ("CLAUDE.md", "GEMINI.md", "AGENTS.md"):
        assert "agent only body" not in (repo / name).read_text()


def test_an_existing_document_is_never_overwritten(tmp_path):
    repo = tmp_path / "repo"
    write_instruction(repo / "CLAUDE.md")
    (repo / "docs").mkdir()
    (repo / DOCUMENT).write_text("hand-curated document\n")

    report = migrate_legacy([repo], write=True)

    assert (repo / DOCUMENT).read_text() == "hand-curated document\n"
    assert "docs/organvm-context.md" in (repo / "CLAUDE.md").read_text()
    assert AUTO_START in (repo / "CLAUDE.md").read_text()
    (item,) = report.by_action("migrate")
    assert item.document == "exists"


def test_second_run_is_idempotent(tmp_path):
    repo = tmp_path / "repo"
    write_instruction(repo / "CLAUDE.md")
    write_instruction(repo / "AGENTS.md", legacy_block("agents\n"))
    migrate_legacy([repo], write=True)
    after_first = tree(tmp_path)

    report = migrate_legacy([repo], write=True)

    assert tree(tmp_path) == after_first
    assert report.by_action("migrate") == []
    assert len(report.by_action("unchanged")) == 2


# ── skip rules ────────────────────────────────────────────────────────


def test_files_in_a_linked_git_worktree_are_skipped(tmp_path):
    worktree = tmp_path / "wt"
    write_instruction(worktree / "CLAUDE.md")
    (worktree / ".git").write_text("gitdir: /elsewhere/.git/worktrees/wt\n")
    before = tree(tmp_path)

    report = migrate_legacy([tmp_path], write=True)

    assert tree(tmp_path) == before
    (item,) = report.by_action("skipped")
    assert item.reason == "linked-worktree"


def test_relative_path_inside_a_linked_worktree_is_skipped(tmp_path, monkeypatch):
    worktree = tmp_path / "wt"
    write_instruction(worktree / "sub" / "CLAUDE.md")
    (worktree / ".git").write_text("gitdir: /elsewhere/.git/worktrees/wt\n")
    before = tree(tmp_path)
    monkeypatch.chdir(worktree / "sub")

    report = migrate_legacy(["."], write=True)

    assert tree(tmp_path) == before
    (item,) = report.by_action("skipped")
    assert item.reason == "linked-worktree"


def test_a_normal_git_checkout_is_migrated_and_grouped_under_its_top_level(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    write_instruction(repo / "sub" / "dir" / "CLAUDE.md")

    report = migrate_legacy([tmp_path])

    (item,) = report.by_action("migrate")
    assert item.repo == str(repo)


@pytest.mark.parametrize(
    "parts",
    [
        ("custody-staging", "x"),
        ("a", "session-corpus", "lifecycle"),
        ("receipts",),
        ("legacy", "old"),
    ],
)
def test_excluded_path_parts_are_skipped(tmp_path, parts):
    target = tmp_path.joinpath("root", *parts)
    write_instruction(target / "CLAUDE.md")
    before = tree(tmp_path)

    report = migrate_legacy([tmp_path], write=True)

    assert tree(tmp_path) == before
    (item,) = report.by_action("skipped")
    assert item.reason == "excluded-path"


def test_relative_excluded_path_is_skipped(tmp_path, monkeypatch):
    write_instruction(tmp_path / "receipts" / "CLAUDE.md")
    before = tree(tmp_path)
    monkeypatch.chdir(tmp_path)

    report = migrate_legacy([Path("receipts/CLAUDE.md")], write=True)

    assert tree(tmp_path) == before
    (item,) = report.by_action("skipped")
    assert item.reason == "excluded-path"


def test_symlinked_directories_are_not_descended_and_are_listed(tmp_path):
    real = tmp_path / "real"
    write_instruction(real / "CLAUDE.md")
    scan = tmp_path / "scan"
    scan.mkdir()
    (scan / "link").symlink_to(real, target_is_directory=True)
    before = tree(tmp_path)

    report = migrate_legacy([scan], write=True)

    assert tree(tmp_path) == before
    assert report.files == []
    assert report.skipped_directories == [str(scan / "link")]


def test_an_explicit_symlinked_directory_argument_is_skipped(tmp_path):
    real = tmp_path / "real"
    write_instruction(real / "CLAUDE.md")
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)

    report = migrate_legacy([link], write=True)

    assert report.skipped_directories == [str(link)]
    assert AUTO_START in (real / "CLAUDE.md").read_text()
    assert "docs/organvm-context.md" not in (real / "CLAUDE.md").read_text()


def test_a_symlinked_instruction_file_is_skipped(tmp_path):
    target = tmp_path / "elsewhere" / "CLAUDE.md"
    write_instruction(target)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "CLAUDE.md").symlink_to(target)
    before = target.read_text()

    report = migrate_legacy([repo], write=True)

    assert target.read_text() == before
    assert (repo / "CLAUDE.md").is_symlink()
    (item,) = report.by_action("skipped")
    assert item.reason == "symlinked-file"


def test_broken_symlink_and_symlink_to_pointer_are_skipped_without_error(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "CLAUDE.md").symlink_to(tmp_path / "does-not-exist")
    pointer_target = tmp_path / "elsewhere" / "AGENTS.md"
    write_instruction(pointer_target, generate_context_pointer(STAMP))
    (repo / "AGENTS.md").symlink_to(pointer_target)

    report = migrate_legacy([repo], write=True)

    assert not report.by_action("error")
    assert not report.by_action("unchanged")
    assert [item.reason for item in report.by_action("skipped")] == [
        "symlinked-file",
        "symlinked-file",
    ]


def test_non_regular_instruction_file_such_as_fifo_is_skipped_without_blocking(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    os.mkfifo(repo / "CLAUDE.md")

    report = migrate_legacy([repo], write=True)

    assert not report.by_action("error")
    (item,) = report.by_action("skipped")
    assert item.reason == "non-regular-file"


def test_blocks_without_a_stamp_or_with_broken_markers_are_skipped(tmp_path):
    no_stamp = tmp_path / "a"
    write_instruction(no_stamp / "CLAUDE.md", f"{AUTO_START}\n<!-- ERROR: Repo 'x' not found -->\n{AUTO_END}")
    broken = tmp_path / "b"
    broken.mkdir()
    (broken / "CLAUDE.md").write_text(f"# x\n{AUTO_START}\nno end\n")
    before = tree(tmp_path)

    report = migrate_legacy([tmp_path], write=True)

    assert tree(tmp_path) == before
    assert {item.reason for item in report.by_action("skipped")} == {
        "no-last-synced-stamp",
        "malformed-markers",
    }


def test_files_without_any_block_are_ignored(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# plain\n")

    report = migrate_legacy([tmp_path], write=True)

    assert report.files == []


# ── arguments and atomicity ───────────────────────────────────────────


def test_explicit_files_and_directories_are_accepted(tmp_path):
    one = tmp_path / "one"
    two = tmp_path / "two"
    write_instruction(one / "AGENTS.md", legacy_block("agents\n"))
    write_instruction(two / "CLAUDE.md")
    (two / "notes.md").write_text(legacy_block())

    report = migrate_legacy([one / "AGENTS.md", two, two / "notes.md"], write=True)

    assert (one / DOCUMENT).read_text() == verbatim("agents\n")
    assert (two / DOCUMENT).read_text() == verbatim()
    assert (two / "notes.md").read_text() == legacy_block()
    assert len(report.by_action("migrate")) == 2


def test_replacement_is_atomic_and_keeps_the_file_mode(tmp_path):
    repo = tmp_path / "repo"
    write_instruction(repo / "CLAUDE.md")
    (repo / "CLAUDE.md").chmod(0o640)
    inode_before = (repo / "CLAUDE.md").stat().st_ino

    migrate_legacy([repo], write=True)

    assert stat.S_IMODE((repo / "CLAUDE.md").stat().st_mode) == 0o640
    assert (repo / "CLAUDE.md").stat().st_ino != inode_before  # replaced, not rewritten in place
    leftovers = [path.name for path in repo.rglob("*") if ".migrate-" in path.name]
    assert leftovers == []


def test_a_file_changed_during_migration_is_not_overwritten(tmp_path, monkeypatch):
    import organvm_engine.contextmd.migrate as migrate_mod

    repo = tmp_path / "repo"
    write_instruction(repo / "CLAUDE.md")
    real = migrate_mod._replace_block

    def edit_then_replace(item):
        (repo / "CLAUDE.md").write_text("CONCURRENT USER EDIT\n")
        return real(item)

    monkeypatch.setattr(migrate_mod, "_replace_block", edit_then_replace)

    report = migrate_legacy([repo], write=True)

    assert (repo / "CLAUDE.md").read_text() == "CONCURRENT USER EDIT\n"
    (item,) = report.by_action("error")
    assert "changed during migration" in item.reason


def test_a_failed_document_write_leaves_every_instruction_file_untouched(tmp_path):
    repo = tmp_path / "repo"
    text = write_instruction(repo / "CLAUDE.md")
    (repo / "docs").write_text("a file where the directory should be\n")

    report = migrate_legacy([repo], write=True)

    assert (repo / "CLAUDE.md").read_text() == text
    assert [item.action for item in report.files] == ["error"]


def test_no_registry_or_environment_is_needed(tmp_path, monkeypatch):
    for name in list(os.environ):
        if name.startswith("ORGANVM_"):
            monkeypatch.delenv(name)
    repo = tmp_path / "repo"
    write_instruction(repo / "GEMINI.md")

    migrate_legacy([repo], write=True)

    assert (repo / DOCUMENT).is_file()


# ── CLI ───────────────────────────────────────────────────────────────


def run_cli(monkeypatch, capsys, *argv: str) -> tuple[int, str]:
    from organvm_engine.cli import main

    monkeypatch.setattr(sys, "argv", ["organvm", "context", "migrate-legacy", *argv])
    code = main()
    return code, capsys.readouterr().out


def test_cli_reports_a_dry_run_by_repository_with_totals(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    write_instruction(repo / "CLAUDE.md")
    write_instruction(repo / "AGENTS.md", legacy_block("agents\n"))
    worktree = tmp_path / "wt"
    write_instruction(worktree / "CLAUDE.md")
    (worktree / ".git").write_text("gitdir: x\n")

    code, out = run_cli(monkeypatch, capsys, str(tmp_path))

    assert code == 0
    assert "[DRY RUN]" in out
    assert "would M" in out
    assert f"{repo}: 2 files," in out
    assert "linked-worktree: 1 files" in out
    assert "Would migrate: 2 files" in out
    assert not (repo / DOCUMENT).exists()


def test_cli_write_applies_and_json_is_machine_readable(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    write_instruction(repo / "CLAUDE.md")

    code, out = run_cli(monkeypatch, capsys, "--write", str(repo))
    assert code == 0 and "Migrated: 1 files" in out
    assert (repo / DOCUMENT).is_file()

    code, out = run_cli(monkeypatch, capsys, "--json", str(repo))
    payload = json.loads(out)
    assert code == 0 and payload["dry_run"] is True
    assert [item["action"] for item in payload["files"]] == ["unchanged"]


def test_cli_exits_non_zero_when_a_write_fails(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    write_instruction(repo / "CLAUDE.md")
    (repo / "docs").write_text("blocking file\n")

    code, out = run_cli(monkeypatch, capsys, "--write", str(repo))

    assert code == 1
    assert "Errors: 1" in out
    assert "docs created" not in out
    assert "words " not in out.splitlines()[2]


def test_nonexistent_path_records_an_error_and_exits_non_zero(tmp_path, monkeypatch, capsys):
    missing = tmp_path / "does-not-exist"

    report = migrate_legacy([missing])
    (item,) = report.by_action("error")
    assert "does not exist" in item.reason

    code, out = run_cli(monkeypatch, capsys, str(missing))
    assert code == 1
    assert "Errors: 1" in out
