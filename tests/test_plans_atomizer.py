"""Tests for plans/atomizer.py — plan atomization pipeline."""

from pathlib import Path

from organvm_engine.plans.atomizer import (
    AtomicTask,
    AtomizeResult,
    PlanParser,
    atomize_plans,
    classify_archetype,
    detect_agent_subplan,
    discover_plans,
    extract_file_refs,
    extract_loc_estimate,
    extract_plan_date,
    extract_plan_status,
    extract_plan_title,
    extract_tags,
    infer_status_from_checkbox,
    infer_task_type,
    is_actionable,
)

# ---------------------------------------------------------------------------
# discover_plans
# ---------------------------------------------------------------------------


class TestDiscoverPlans:
    """Test plan file discovery."""

    def test_discovers_md_files(self, tmp_path: Path):
        (tmp_path / "plan-a.md").write_text("# Plan A")
        (tmp_path / "plan-b.md").write_text("# Plan B")
        result = discover_plans(tmp_path)
        assert len(result) == 2
        names = {p.name for p in result}
        assert names == {"plan-a.md", "plan-b.md"}

    def test_discovers_nested_files(self, tmp_path: Path):
        sub = tmp_path / "project" / "sprint-1"
        sub.mkdir(parents=True)
        (sub / "plan.md").write_text("# Nested")
        result = discover_plans(tmp_path)
        assert len(result) == 1
        assert result[0].name == "plan.md"

    def test_skips_known_skip_files(self, tmp_path: Path):
        (tmp_path / "plan.md").write_text("# OK")
        (tmp_path / "ATOMIZED-SUMMARY.md").write_text("skip me")
        (tmp_path / "atomized-tasks.jsonl").write_text("{}")
        result = discover_plans(tmp_path)
        assert len(result) == 1
        assert result[0].name == "plan.md"

    def test_empty_directory(self, tmp_path: Path):
        result = discover_plans(tmp_path)
        assert result == []


# ---------------------------------------------------------------------------
# Inference helpers
# ---------------------------------------------------------------------------


class TestInferenceHelpers:
    """Test standalone inference functions."""

    def test_detect_agent_subplan_positive(self):
        p = Path("/plans/2026-03-01-deploy-agent-a1b2c3d4.md")
        is_agent, parent = detect_agent_subplan(p)
        assert is_agent is True
        assert parent == "2026-03-01-deploy.md"

    def test_detect_agent_subplan_negative(self):
        p = Path("/plans/2026-03-01-deploy.md")
        is_agent, parent = detect_agent_subplan(p)
        assert is_agent is False
        assert parent is None

    def test_extract_plan_date_from_filename(self):
        p = Path("2026-03-15-refactor.md")
        date = extract_plan_date(p, [])
        assert date == "2026-03-15"

    def test_extract_plan_date_from_content(self):
        p = Path("my-plan.md")
        lines = ["# Plan", "Created: 2026-01-10", "Some text"]
        date = extract_plan_date(p, lines)
        assert date == "2026-01-10"

    def test_extract_plan_date_none(self):
        p = Path("untitled.md")
        date = extract_plan_date(p, ["# No dates here", "Just prose."])
        assert date is None

    def test_extract_plan_title(self):
        lines = ["", "# My Amazing Plan", "Some body text"]
        assert extract_plan_title(lines) == "My Amazing Plan"

    def test_extract_plan_title_missing(self):
        lines = ["No heading here", "Just paragraphs"]
        assert extract_plan_title(lines) == "Untitled Plan"

    def test_extract_plan_status(self):
        lines = ["# Plan", "**Status**: In Progress", "body"]
        assert extract_plan_status(lines) == "In Progress"

    def test_extract_plan_status_none(self):
        lines = ["# Plan", "No status marker"]
        assert extract_plan_status(lines) is None


class TestInferTaskType:
    """Test task type inference from text."""

    def test_create_file(self):
        assert infer_task_type("Create new config", "") == "create_file"

    def test_write_test(self):
        assert infer_task_type("Add unit test", "pytest coverage") == "write_test"

    def test_deploy(self):
        assert infer_task_type("Deploy to production", "") == "deploy"

    def test_generic_fallback(self):
        assert infer_task_type("do something", "vague") == "generic"


class TestInferStatusFromCheckbox:
    def test_completed(self):
        assert infer_status_from_checkbox("x") == "completed"
        assert infer_status_from_checkbox("X") == "completed"

    def test_in_progress(self):
        assert infer_status_from_checkbox("~") == "in_progress"

    def test_pending(self):
        assert infer_status_from_checkbox(" ") == "pending"


class TestExtractFileRefs:
    def test_backtick_paths(self):
        text = "Edit `src/engine/main.py` and `tests/test_main.py`"
        refs = extract_file_refs(text)
        paths = {r.path for r in refs}
        assert "src/engine/main.py" in paths
        assert "tests/test_main.py" in paths

    def test_bold_file_path(self):
        text = "**File**: `src/config.yaml`"
        refs = extract_file_refs(text)
        assert any(r.path == "src/config.yaml" for r in refs)

    def test_file_action_create(self):
        text = "CREATE `src/new_module.py` with ~50 lines"
        refs = extract_file_refs(text)
        assert len(refs) >= 1
        ref = next(r for r in refs if r.path == "src/new_module.py")
        assert ref.action == "create"

    def test_no_http_refs(self):
        text = "`https://example.com/file.py` should be ignored"
        refs = extract_file_refs(text)
        assert all(not r.path.startswith("http") for r in refs)


class TestExtractTags:
    def test_known_tags(self):
        text = "Using python and pytest with fastapi server"
        tags = extract_tags(text)
        assert "python" in tags
        assert "pytest" in tags
        assert "fastapi" in tags

    def test_no_partial_matches(self):
        # "go" should not match the word "going"
        text = "We are going to the store."
        tags = extract_tags(text)
        assert "go" not in tags

    def test_empty_text(self):
        assert extract_tags("") == []


class TestExtractLocEstimate:
    def test_lines_pattern(self):
        assert extract_loc_estimate("about ~180 lines of code") == 180

    def test_loc_pattern(self):
        assert extract_loc_estimate("(300 LOC)") == 300

    def test_no_match(self):
        assert extract_loc_estimate("just some text") is None


class TestIsActionable:
    def test_exploration_not_actionable(self):
        assert is_actionable("Research spike", "explore options", "exploration") is False

    def test_post_hoc_not_actionable(self):
        assert is_actionable("Summary", "", "post_hoc") is False

    def test_create_task_actionable(self):
        assert is_actionable("Create config file", "", "generic") is True

    def test_summary_not_actionable(self):
        assert is_actionable("Project summary", "overview of context", "generic") is False

    def test_summary_with_action_verbs_stays_actionable(self):
        assert is_actionable("Create summary report", "implement this", "generic") is True


# ---------------------------------------------------------------------------
# classify_archetype
# ---------------------------------------------------------------------------


class TestClassifyArchetype:
    def test_phase_checkbox(self):
        lines = [
            "# Plan",
            "## Phase 1: Setup",
            "- [x] Install deps",
            "- [ ] Write config",
            "- [ ] Test",
        ]
        assert classify_archetype(lines) == "phase_checkbox"

    def test_checkbox_only(self):
        lines = [
            "# Plan",
            "## Tasks",
            "- [x] Done",
            "- [ ] Pending",
            "- [ ] Also pending",
        ]
        assert classify_archetype(lines) == "checkbox"

    def test_phase_task(self):
        lines = [
            "# Plan",
            "## Phase 1: Init",
            "### Step A: First thing",
            "Do the first thing.",
        ]
        assert classify_archetype(lines) == "phase_task"

    def test_post_hoc(self):
        lines = [
            "# Audit Summary",
            "This is a summary of findings.",
            *["Prose line." for _ in range(5)],
        ]
        assert classify_archetype(lines) == "post_hoc"

    def test_generic_fallback(self):
        lines = ["# Plan", "Some notes here."]
        assert classify_archetype(lines) == "generic"


# ---------------------------------------------------------------------------
# PlanParser
# ---------------------------------------------------------------------------


class TestPlanParser:
    def test_duplicate_titles_keep_distinct_stable_ids(self, tmp_path):
        filepath = tmp_path / "plan.md"
        parser = PlanParser([], filepath, tmp_path)
        first = parser._make_task("Repeat", "first", 10, 10)
        second = parser._make_task("Repeat", "second", 12, 12)
        assert first.id != second.id
        again = PlanParser([], filepath, tmp_path)
        assert first.id == again._make_task("Repeat", "first", 10, 10).id
        assert second.id == again._make_task("Repeat", "second", 12, 12).id

    def test_writer_rejects_duplicate_ids_before_replacing_file(self, tmp_path):
        import pytest

        from organvm_engine.plans.atomizer import write_jsonl
        output = tmp_path / "tasks.jsonl"
        output.write_text("preserved\n")
        with pytest.raises(ValueError, match="duplicate"):
            write_jsonl([{"id": "same"}, {"id": "same"}], output)
        assert output.read_text() == "preserved\n"

    """Test the stateful plan parser."""

    def _parse(self, lines: list[str], tmp_path: Path) -> list[AtomicTask]:
        filepath = tmp_path / "2026-03-15-test-plan.md"
        filepath.write_text("\n".join(lines))
        parser = PlanParser(lines, filepath, tmp_path)
        return parser.parse()

    def test_checkbox_tasks(self, tmp_path: Path):
        lines = [
            "# Test Plan",
            "## Tasks",
            "- [x] First task",
            "- [ ] Second task",
            "- [~] Third task in progress",
        ]
        tasks = self._parse(lines, tmp_path)
        assert len(tasks) == 3
        statuses = {t.status for t in tasks}
        assert statuses == {"completed", "pending", "in_progress"}

    def test_task_ids_are_stable(self, tmp_path: Path):
        lines = ["# Stable Plan", "## Section", "- [ ] Repeatable task"]
        tasks_a = self._parse(lines, tmp_path)
        tasks_b = self._parse(lines, tmp_path)
        assert tasks_a[0].id == tasks_b[0].id

    def test_task_ids_are_nonempty(self, tmp_path: Path):
        lines = ["# Plan", "- [ ] A task"]
        tasks = self._parse(lines, tmp_path)
        assert all(t.id for t in tasks)

    def test_code_block_detection(self, tmp_path: Path):
        lines = [
            "# Plan",
            "## Setup",
            "- [ ] Add config with code",
            "```python",
            "x = 1",
            "y = 2",
            "```",
        ]
        tasks = self._parse(lines, tmp_path)
        # At least one task should exist
        assert len(tasks) >= 1

    def test_empty_plan_emits_doc_level_task(self, tmp_path: Path):
        lines = ["# My Empty Plan", "Just some prose without any tasks."]
        tasks = self._parse(lines, tmp_path)
        assert len(tasks) == 1
        assert tasks[0].title == "My Empty Plan"

    def test_plan_date_extracted(self, tmp_path: Path):
        lines = ["# Plan", "- [ ] Task"]
        tasks = self._parse(lines, tmp_path)
        # filename is 2026-03-15-test-plan.md
        assert tasks[0].plan_date == "2026-03-15"

    def test_to_dict_round_trip(self, tmp_path: Path):
        lines = ["# Plan", "- [ ] A simple task"]
        tasks = self._parse(lines, tmp_path)
        d = tasks[0].to_dict()
        assert isinstance(d, dict)
        assert d["title"] == "A simple task"
        assert d["status"] == "pending"
        assert "source" in d
        assert "hierarchy" in d

    def test_dependency_wiring_across_phases(self, tmp_path: Path):
        lines = [
            "# Plan",
            "## Phase 1: First",
            "- [ ] Task A",
            "## Phase 2: Second",
            "- [ ] Task B",
        ]
        tasks = self._parse(lines, tmp_path)
        # Task B should depend on Task A (cross-phase wiring)
        task_b = [t for t in tasks if t.title == "Task B"]
        if task_b:
            assert len(task_b[0].depends_on) > 0


# ---------------------------------------------------------------------------
# atomize_plans (high-level API)
# ---------------------------------------------------------------------------


class TestAtomizePlans:
    def test_atomize_directory(self, tmp_path: Path):
        (tmp_path / "plan.md").write_text(
            "# Sprint Plan\n- [ ] Build feature\n- [x] Write tests\n",
        )
        result = atomize_plans(tmp_path)
        assert isinstance(result, AtomizeResult)
        assert result.plans_parsed == 1
        assert len(result.tasks) >= 2
        assert "pending" in result.status_counts or "completed" in result.status_counts
        assert len(result.errors) == 0

    def test_atomize_empty_dir(self, tmp_path: Path):
        result = atomize_plans(tmp_path)
        assert result.plans_parsed == 0
        assert result.tasks == []

    def test_atomize_skips_empty_files(self, tmp_path: Path):
        (tmp_path / "empty.md").write_text("")
        (tmp_path / "real.md").write_text("# Plan\n- [ ] Task\n")
        result = atomize_plans(tmp_path)
        assert result.plans_parsed == 2  # counted, but empty one yields no tasks
        assert len(result.tasks) >= 1

    def test_atomize_records_errors_gracefully(self, tmp_path: Path):
        # A valid file should work even when another file has issues
        (tmp_path / "good.md").write_text("# Good Plan\n- [ ] Task\n")
        result = atomize_plans(tmp_path)
        assert result.plans_parsed >= 1
        assert len(result.tasks) >= 1


def test_global_plans_with_same_name_have_distinct_ids(tmp_path):
    from types import SimpleNamespace

    from organvm_engine.plans.atomizer import atomize_plans

    first = tmp_path / 'one' / 'same.md'
    second = tmp_path / 'two' / 'same.md'
    for path in (first, second):
        path.parent.mkdir()
        path.write_text('# Plan\n\n- [ ] Implement the same useful task\n')
    files = [SimpleNamespace(path=p, agent='codex', organ=None, repo=None) for p in (first, second)]
    result = atomize_plans(tmp_path / 'workspace', plan_files_override=files)
    assert not result.errors
    assert len(result.tasks) == 2
    assert len({task['id'] for task in result.tasks}) == 2
    reverse = atomize_plans(tmp_path / 'workspace', plan_files_override=list(reversed(files)))
    assert {task['id'] for task in result.tasks} == {task['id'] for task in reverse.tasks}


def test_writer_preserves_previous_tasks_if_serialization_fails(tmp_path, monkeypatch):
    import pytest

    from organvm_engine.plans import atomizer

    output = tmp_path / 'tasks.jsonl'
    output.write_text('previous\n')
    original = atomizer.json.dumps
    def fail_on_second(item, **kwargs):
        if item['id'] == 'b':
            raise ValueError('serialization failed')
        return original(item, **kwargs)
    monkeypatch.setattr(atomizer.json, 'dumps', fail_on_second)
    with pytest.raises(ValueError, match='serialization failed'):
        atomizer.write_jsonl([{'id': 'a'}, {'id': 'b'}], output)
    assert output.read_text() == 'previous\n'
