"""Tests for the centralized atomization pipeline."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch


def test_atoms_dir_path():
    """atoms_dir() returns corpus_dir / data / atoms."""
    from organvm_engine.paths import atoms_dir, corpus_dir

    assert atoms_dir() == corpus_dir() / "data" / "atoms"


class TestPipelineDryRun:
    """Pipeline in dry-run mode computes results but writes nothing."""

    @patch("organvm_engine.plans.atomizer.atomize_all")
    def test_dry_run_no_files(self, mock_atomize, tmp_path):
        from organvm_engine.atoms.pipeline import run_pipeline
        from organvm_engine.plans.atomizer import AtomizeResult

        mock_atomize.return_value = AtomizeResult(
            tasks=[{"id": "t1", "status": "pending"}],
            plans_parsed=1,
            errors=[],
            archetype_counts={"checklist": 1},
            status_counts={"pending": 1},
        )

        result = run_pipeline(
            output_dir=tmp_path,
            skip_narrate=True,
            skip_link=True,
            dry_run=True,
        )

        assert result.atomize_count == 1
        assert result.plans_parsed == 1
        # No files written in dry-run
        assert not list(tmp_path.iterdir())

    @patch("organvm_engine.plans.atomizer.atomize_all")
    def test_dry_run_manifest_has_dry_run_flag(self, mock_atomize, tmp_path):
        from organvm_engine.atoms.pipeline import run_pipeline
        from organvm_engine.plans.atomizer import AtomizeResult

        mock_atomize.return_value = AtomizeResult(
            tasks=[], plans_parsed=0, errors=[],
            archetype_counts={}, status_counts={},
        )

        result = run_pipeline(
            output_dir=tmp_path, skip_narrate=True, skip_link=True, dry_run=True,
        )

        assert result.manifest["dry_run"] is True


class TestPipelineWrite:
    """Pipeline in write mode creates expected files."""

    @patch("organvm_engine.atoms.reconciler.reconcile_tasks")
    @patch("organvm_engine.atoms.reconciler.apply_verdicts")
    @patch("organvm_engine.plans.atomizer.atomize_all")
    def test_manifest_hashes_tasks_after_reconciliation(
        self, atomize, apply, reconcile, tmp_path, monkeypatch,
    ):
        import hashlib

        from organvm_engine.atoms.pipeline import run_pipeline
        from organvm_engine.plans.atomizer import AtomizeResult
        monkeypatch.setattr(
            "organvm_engine.plans.index.build_plan_index",
            lambda **kw: MagicMock(total_plans=0),
        )
        monkeypatch.setattr("organvm_engine.plans.index.index_to_json", lambda index: "{}")

        atomize.return_value = AtomizeResult(
            tasks=[{"id": "a", "status": "pending"}], plans_parsed=1,
            errors=[], archetype_counts={}, status_counts={},
        )
        reconcile.return_value = MagicMock(
            verdicts=[object()], likely_completed=1, partially_done=0,
        )
        apply.side_effect = lambda path, verdicts: path.write_text(
            '{"id":"a","status":"completed"}\n',
        )
        result = run_pipeline(
            output_dir=tmp_path, skip_narrate=True, skip_link=True,
            skip_research=True, dry_run=False,
        )
        actual = hashlib.sha256((tmp_path / "atomized-tasks.jsonl").read_bytes()).hexdigest()
        assert result.manifest["files"]["atomized-tasks.jsonl"]["sha256"] == actual

    @patch("organvm_engine.plans.atomizer.atomize_all")
    def test_write_creates_files(self, mock_atomize, tmp_path):
        from organvm_engine.atoms.pipeline import run_pipeline
        from organvm_engine.plans.atomizer import AtomizeResult

        mock_atomize.return_value = AtomizeResult(
            tasks=[{
                "id": "t1", "status": "pending", "task_type": "implement",
                "actionable": True,
                "source": {"file": "plan.md", "plan_title": "Test"},
                "project": {"slug": "test-proj", "organ": "META"},
                "agent": "claude",
            }],
            plans_parsed=1,
            errors=[],
            archetype_counts={"checklist": 1},
            status_counts={"pending": 1},
        )

        result = run_pipeline(
            output_dir=tmp_path,
            skip_narrate=True,
            skip_link=True,
            dry_run=False,
        )

        assert result.atomize_count == 1
        assert (tmp_path / "atomized-tasks.jsonl").exists()
        assert (tmp_path / "ATOMIZED-SUMMARY.md").exists()
        assert (tmp_path / "pipeline-manifest.json").exists()

    @patch("organvm_engine.plans.atomizer.atomize_all")
    def test_write_manifest_structure(self, mock_atomize, tmp_path):
        from organvm_engine.atoms.pipeline import run_pipeline
        from organvm_engine.plans.atomizer import AtomizeResult

        mock_atomize.return_value = AtomizeResult(
            tasks=[], plans_parsed=0, errors=[],
            archetype_counts={}, status_counts={},
        )

        run_pipeline(
            output_dir=tmp_path, skip_narrate=True, skip_link=True, dry_run=False,
        )

        manifest = json.loads((tmp_path / "pipeline-manifest.json").read_text())
        assert "generated" in manifest
        assert "counts" in manifest
        assert "files" in manifest
        assert "filters" in manifest
        required_counts = {"plans_parsed", "tasks", "prompts", "sessions", "threads", "links", "errors"}
        assert required_counts <= set(manifest["counts"].keys())


class TestPipelineQuality:
    """Pipeline manifest includes quality stats."""

    @patch("organvm_engine.plans.atomizer.atomize_all")
    def test_manifest_quality_stats(self, mock_atomize, tmp_path):
        from organvm_engine.atoms.pipeline import run_pipeline
        from organvm_engine.plans.atomizer import AtomizeResult

        mock_atomize.return_value = AtomizeResult(
            tasks=[{
                "id": "t1", "status": "pending", "task_type": "implement",
                "actionable": True,
                "source": {"file": "plan.md", "plan_title": "Test"},
                "project": {"slug": "test-proj", "organ": "META"},
                "agent": "claude",
            }],
            plans_parsed=1,
            errors=[],
            archetype_counts={"checklist": 1},
            status_counts={"pending": 1},
        )

        run_pipeline(
            output_dir=tmp_path,
            skip_narrate=True,
            skip_link=True,
            dry_run=False,
        )

        manifest = json.loads((tmp_path / "pipeline-manifest.json").read_text())
        assert "quality" in manifest
        q = manifest["quality"]
        assert "null_organ_tasks" in q
        assert "empty_fingerprint_prompts" in q
        assert "link_threshold" in q
        assert q["link_threshold"] == 0.30


class TestPipelineSkips:
    """Pipeline respects skip flags."""

    @patch("organvm_engine.plans.atomizer.atomize_all")
    def test_skip_narrate(self, mock_atomize, tmp_path):
        from organvm_engine.atoms.pipeline import run_pipeline
        from organvm_engine.plans.atomizer import AtomizeResult

        mock_atomize.return_value = AtomizeResult(
            tasks=[], plans_parsed=0, errors=[],
            archetype_counts={}, status_counts={},
        )

        result = run_pipeline(
            output_dir=tmp_path, skip_narrate=True, skip_link=True, dry_run=True,
        )

        assert result.narrate_count == 0
        assert result.sessions_processed == 0

    @patch("organvm_engine.plans.atomizer.atomize_all")
    def test_skip_link(self, mock_atomize, tmp_path):
        from organvm_engine.atoms.pipeline import run_pipeline
        from organvm_engine.plans.atomizer import AtomizeResult

        mock_atomize.return_value = AtomizeResult(
            tasks=[{"id": "t1"}], plans_parsed=1, errors=[],
            archetype_counts={}, status_counts={},
        )

        result = run_pipeline(
            output_dir=tmp_path, skip_narrate=True, skip_link=True, dry_run=True,
        )

        assert result.link_count == 0


class TestCLIPipeline:
    """CLI integration for atoms pipeline subcommand."""

    @patch("organvm_engine.plans.atomizer.atomize_all")
    def test_cli_pipeline_dry_run(self, mock_atomize, tmp_path, capsys):
        from organvm_engine.cli.atoms import cmd_atoms_pipeline
        from organvm_engine.plans.atomizer import AtomizeResult

        mock_atomize.return_value = AtomizeResult(
            tasks=[{"id": "t1"}], plans_parsed=1, errors=[],
            archetype_counts={}, status_counts={},
        )

        args = MagicMock()
        args.write = False
        args.output_dir = str(tmp_path)
        args.agent = None
        args.organ = None
        args.skip_narrate = True
        args.skip_link = True
        args.skip_research = True
        args.skip_reconcile = False
        args.research_dir = None
        args.threshold = 0.15

        ret = cmd_atoms_pipeline(args)

        assert ret == 0
        captured = capsys.readouterr()
        assert "[DRY RUN]" in captured.out
        assert "[1/7] Atomize" in captured.out
        assert "[2/7] Research" in captured.out


class TestPipelineReconcile:
    """Pipeline reconcile step persists verdicts into atomized-tasks.jsonl."""

    def test_pipeline_result_has_reconcile_fields(self):
        from organvm_engine.atoms.pipeline import PipelineResult

        r = PipelineResult()
        assert r.reconcile_completed == 0
        assert r.reconcile_partial == 0

    @patch("organvm_engine.plans.atomizer.atomize_all")
    def test_dry_run_skips_reconcile(self, mock_atomize, tmp_path):
        from organvm_engine.atoms.pipeline import run_pipeline
        from organvm_engine.plans.atomizer import AtomizeResult

        mock_atomize.return_value = AtomizeResult(
            tasks=[{"id": "t1", "status": "pending"}],
            plans_parsed=1, errors=[],
            archetype_counts={}, status_counts={},
        )

        result = run_pipeline(
            output_dir=tmp_path, dry_run=True,
            skip_narrate=True, skip_link=True,
        )

        assert result.reconcile_completed == 0
        assert result.reconcile_partial == 0

    @patch("organvm_engine.plans.atomizer.atomize_all")
    def test_skip_reconcile_flag(self, mock_atomize, tmp_path):
        from organvm_engine.atoms.pipeline import run_pipeline
        from organvm_engine.plans.atomizer import AtomizeResult

        mock_atomize.return_value = AtomizeResult(
            tasks=[{"id": "t1", "status": "pending"}],
            plans_parsed=1, errors=[],
            archetype_counts={}, status_counts={},
        )

        result = run_pipeline(
            output_dir=tmp_path, dry_run=False,
            skip_narrate=True, skip_link=True,
            skip_reconcile=True,
        )

        assert result.reconcile_completed == 0
        assert result.reconcile_partial == 0

    @patch("organvm_engine.plans.atomizer.atomize_all")
    def test_manifest_includes_reconcile_counts(self, mock_atomize, tmp_path):
        from organvm_engine.atoms.pipeline import run_pipeline
        from organvm_engine.plans.atomizer import AtomizeResult

        mock_atomize.return_value = AtomizeResult(
            tasks=[], plans_parsed=0, errors=[],
            archetype_counts={}, status_counts={},
        )

        result = run_pipeline(
            output_dir=tmp_path, dry_run=True,
            skip_narrate=True, skip_link=True,
        )

        counts = result.manifest["counts"]
        assert "reconcile_completed" in counts
        assert "reconcile_partial" in counts
        assert counts["reconcile_completed"] == 0
        assert counts["reconcile_partial"] == 0


def test_duplicate_write_does_not_activate_research(tmp_path, monkeypatch):
    import pytest

    from organvm_engine.atoms.pipeline import run_pipeline
    from organvm_engine.plans.atomizer import AtomizeResult, DuplicateTaskIdError

    research = tmp_path / 'research'
    research.mkdir()
    doc = research / 'doc.md'
    original = '---\nstatus: reference\n---\n# Research\n\n- [ ] Implement an example feature with useful details\n'
    doc.write_text(original)
    monkeypatch.setattr('organvm_engine.plans.atomizer.atomize_all', lambda **kw: AtomizeResult(
        tasks=[{'id': 'same'}, {'id': 'same'}], plans_parsed=1, errors=[],
        archetype_counts={}, status_counts={},
    ))
    with pytest.raises(DuplicateTaskIdError):
        run_pipeline(output_dir=tmp_path / 'output', research_dir=research,
                     skip_narrate=True, skip_link=True, dry_run=False)
    assert doc.read_text() == original


def test_cli_reports_duplicate_without_traceback(tmp_path, monkeypatch, capsys):
    import argparse

    from organvm_engine.cli.atoms import cmd_atoms_pipeline
    from organvm_engine.plans.atomizer import DuplicateTaskIdError

    def fail(**kwargs):
        raise DuplicateTaskIdError('duplicate task ID: a')
    monkeypatch.setattr('organvm_engine.atoms.pipeline.run_pipeline', fail)
    assert cmd_atoms_pipeline(argparse.Namespace(write=True)) != 0
    assert 'duplicate task ID' in capsys.readouterr().err


def test_missing_task_file_removes_stale_manifest_hash(tmp_path, monkeypatch):
    from organvm_engine.atoms import pipeline
    from organvm_engine.plans.atomizer import AtomizeResult

    monkeypatch.setattr('organvm_engine.plans.atomizer.atomize_all', lambda **kw: AtomizeResult(
        tasks=[{'id': 'a'}], plans_parsed=1, errors=[], archetype_counts={}, status_counts={},
    ))
    monkeypatch.setattr('organvm_engine.plans.index.build_plan_index', lambda **kw: MagicMock(total_plans=0))
    monkeypatch.setattr('organvm_engine.plans.index.index_to_json', lambda index: '{}')
    real_hash = pipeline._sha256
    def remove_after_hash(path):
        value = real_hash(path)
        if path.name == 'atomized-tasks.jsonl':
            path.unlink()
        return value
    monkeypatch.setattr(pipeline, '_sha256', remove_after_hash)
    result = pipeline.run_pipeline(output_dir=tmp_path, skip_narrate=True, skip_link=True,
                                   skip_reconcile=True, skip_research=True, dry_run=False)
    assert 'sha256' not in result.manifest['files']['atomized-tasks.jsonl']
    assert any(stage == 'hash-tasks' for stage, error in result.errors)


def test_skip_link_refuses_changed_linked_task(tmp_path, monkeypatch):
    import pytest

    from organvm_engine.atoms.pipeline import run_pipeline
    from organvm_engine.plans.atomizer import AtomizeResult

    monkeypatch.setattr('organvm_engine.plans.index.build_plan_index', lambda **kw: MagicMock(total_plans=0))
    monkeypatch.setattr('organvm_engine.plans.index.index_to_json', lambda index: '{}')

    old = {'id': 'a', 'source': {'file': 'p.md', 'line_start': 3}, 'raw_text': 'old'}
    new = {'id': 'a', 'source': {'file': 'p.md', 'line_start': 4}, 'raw_text': 'new'}
    task_path = tmp_path / 'atomized-tasks.jsonl'
    task_path.write_text(json.dumps(old) + '\n')
    (tmp_path / 'atom-links.jsonl').write_text(json.dumps({'task_id': 'a'}) + '\n')
    monkeypatch.setattr('organvm_engine.plans.atomizer.atomize_all', lambda **kw: AtomizeResult(
        tasks=[new], plans_parsed=1, errors=[], archetype_counts={}, status_counts={},
    ))
    with pytest.raises(ValueError, match='links'):
        run_pipeline(output_dir=tmp_path, skip_narrate=True, skip_link=True,
                     skip_research=True, dry_run=False)
    assert json.loads(task_path.read_text()) == old


def test_skip_link_rejects_ambiguous_repeated_tasks(tmp_path, monkeypatch):
    import hashlib

    import pytest

    from organvm_engine.atoms.pipeline import run_pipeline
    from organvm_engine.plans.atomizer import AtomizeResult

    source = {'file': 'p.md', 'line_start': 3}
    hierarchy = {'breadcrumb': 'Repeat'}
    base = hashlib.sha256(b'p.md|Repeat|Repeat').hexdigest()[:12]
    first = {'id': base, 'title': 'Repeat', 'source': source, 'hierarchy': hierarchy, 'raw_text': 'same'}
    second = dict(first, id='other', source={'file': 'p.md', 'line_start': 4})
    (tmp_path / 'atomized-tasks.jsonl').write_text(json.dumps(first) + '\n' + json.dumps(second) + '\n')
    (tmp_path / 'atom-links.jsonl').write_text(json.dumps({'task_id': base}) + '\n')
    monkeypatch.setattr('organvm_engine.plans.atomizer.atomize_all', lambda **kw: AtomizeResult(
        tasks=[first, second], plans_parsed=1, errors=[], archetype_counts={}, status_counts={},
    ))
    monkeypatch.setattr('organvm_engine.plans.index.build_plan_index', lambda **kw: MagicMock(total_plans=0))
    monkeypatch.setattr('organvm_engine.plans.index.index_to_json', lambda index: '{}')
    with pytest.raises(ValueError, match='links'):
        run_pipeline(output_dir=tmp_path, skip_narrate=True, skip_link=True,
                     skip_research=True, dry_run=False)


def test_successful_task_write_activates_research(tmp_path, monkeypatch):
    from organvm_engine.atoms.pipeline import run_pipeline
    from organvm_engine.plans.atomizer import AtomizeResult

    research = tmp_path / 'research'
    research.mkdir()
    doc = research / 'doc.md'
    doc.write_text('---\nstatus: reference\n---\n# Research\n\n- [ ] Implement an example feature with useful details\n')
    monkeypatch.setattr('organvm_engine.plans.atomizer.atomize_all', lambda **kw: AtomizeResult(
        tasks=[], plans_parsed=0, errors=[], archetype_counts={}, status_counts={},
    ))
    monkeypatch.setattr('organvm_engine.plans.index.build_plan_index', lambda **kw: MagicMock(total_plans=0))
    monkeypatch.setattr('organvm_engine.plans.index.index_to_json', lambda index: '{}')
    result = run_pipeline(output_dir=tmp_path / 'output', research_dir=research,
                          skip_narrate=True, skip_link=True, skip_reconcile=True, dry_run=False)
    assert not result.errors
    assert 'reference-activated' in doc.read_text()
    assert (tmp_path / 'output/atomized-tasks.jsonl').is_file()


def test_skip_link_rejects_ambiguous_existing_ids(tmp_path, monkeypatch):
    import pytest

    from organvm_engine.atoms.pipeline import run_pipeline
    from organvm_engine.plans.atomizer import AtomizeResult

    first = {'id': 'a', 'title': 'one'}
    second = {'id': 'a', 'title': 'two'}
    task_file = tmp_path / 'atomized-tasks.jsonl'
    task_file.write_text(json.dumps(first) + '\n' + json.dumps(second) + '\n')
    (tmp_path / 'atom-links.jsonl').write_text(json.dumps({'task_id': 'a'}) + '\n')
    monkeypatch.setattr('organvm_engine.plans.atomizer.atomize_all', lambda **kw: AtomizeResult(
        tasks=[second], plans_parsed=1, errors=[], archetype_counts={}, status_counts={},
    ))
    monkeypatch.setattr('organvm_engine.plans.index.build_plan_index', lambda **kw: MagicMock(total_plans=0))
    monkeypatch.setattr('organvm_engine.plans.index.index_to_json', lambda index: '{}')
    with pytest.raises(ValueError, match='links'):
        run_pipeline(output_dir=tmp_path, skip_narrate=True, skip_link=True,
                     skip_research=True, dry_run=False)
    assert len(task_file.read_text().splitlines()) == 2
