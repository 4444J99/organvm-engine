"""Centralized atomization pipeline: discover → atomize → narrate → link → index.

Chains the plan atomizer, prompt narrator, and cross-system linker into a
single pipeline that writes all outputs to a central directory.
"""

from __future__ import annotations

import datetime
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from organvm_engine.atoms.linker import AtomLink


@dataclass
class PipelineResult:
    """Aggregate result of the full pipeline run."""
    atomize_count: int = 0
    plans_parsed: int = 0
    research_docs_scanned: int = 0
    research_directives: int = 0
    narrate_count: int = 0
    noise_skipped: int = 0
    sessions_processed: int = 0
    thread_count: int = 0
    link_count: int = 0
    reconcile_completed: int = 0
    reconcile_partial: int = 0
    manifest: dict = field(default_factory=dict)
    errors: list[tuple[str, str]] = field(default_factory=list)
    links: list[AtomLink] = field(default_factory=list)


def _sha256(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def run_pipeline(
    output_dir: Path | None = None,
    agent: str | None = None,
    organ: str | None = None,
    skip_narrate: bool = False,
    skip_link: bool = False,
    skip_reconcile: bool = False,
    skip_research: bool = False,
    research_dir: Path | None = None,
    link_threshold: float = 0.30,
    dry_run: bool = True,
) -> PipelineResult:
    """Run the full atomization pipeline.

    Args:
        output_dir: Where to write outputs. Defaults to atoms_dir().
        agent: Filter by agent (claude/gemini/codex).
        organ: Filter by organ key.
        skip_narrate: Skip prompt narration step.
        skip_link: Skip cross-system linking step.
        skip_reconcile: Skip git-based reconciliation step.
        skip_research: Skip research activation step.
        research_dir: Path to research docs directory. Defaults to
            praxis-perpetua/research/ under the workspace.
        link_threshold: Minimum Jaccard similarity for links.
        dry_run: If True, compute results but don't write files.

    Returns:
        PipelineResult with counts and manifest.
    """
    from organvm_engine.atoms.summary import generate_link_summary
    from organvm_engine.paths import atoms_dir
    from organvm_engine.plans.atomizer import DuplicateTaskIdError, atomize_all
    from organvm_engine.plans.atomizer import write_jsonl as write_tasks_jsonl
    from organvm_engine.plans.summary import generate_summary
    from organvm_engine.prompts.summary import generate_narrative_summary

    if output_dir is None:
        output_dir = atoms_dir()

    result = PipelineResult()
    manifest: dict = {
        "generated": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        "dry_run": dry_run,
        "filters": {"agent": agent, "organ": organ},
        "files": {},
    }

    # Step 1: Atomize plans
    all_tasks: list[dict] = []
    try:
        atomize_result = atomize_all(agent=agent, organ=organ)
        all_tasks.extend(atomize_result.tasks)
        result.atomize_count = len(atomize_result.tasks)
        result.plans_parsed = atomize_result.plans_parsed
        result.errors.extend(("atomize", e) for _, e in atomize_result.errors)
    except Exception as e:
        result.errors.append(("atomize", str(e)))

    # Step 1b: Research activation (optional)
    research_result = None
    if not skip_research:
        try:
            from organvm_engine.atoms.research import activate_research

            r_dir = research_dir
            if r_dir is None:
                from organvm_engine.paths import workspace_root as _ws
                r_dir = _ws() / "meta-organvm" / "praxis-perpetua" / "research"

            if r_dir.is_dir():
                research_result = activate_research(
                    r_dir,
                    mark_activated=False,
                )
                result.research_docs_scanned = research_result.docs_scanned
                result.research_directives = research_result.total_directives
                all_tasks.extend(research_result.tasks)
                result.errors.extend(
                    ("research", e) for _, e in research_result.errors
                )
        except Exception as e:
            result.errors.append(("research", str(e)))

    # Write combined task output (plans + research directives)
    result.atomize_count = len(all_tasks)
    if not dry_run and (skip_link or skip_narrate):
        links_path = output_dir / "atom-links.jsonl"
        tasks_path = output_dir / "atomized-tasks.jsonl"
        if links_path.exists():
            if not tasks_path.exists():
                raise ValueError("Cannot retain links without their original task file")
            with links_path.open(encoding="utf-8") as f:
                linked_ids = {json.loads(line)["task_id"] for line in f if line.strip()}
            old_tasks = {}
            with tasks_path.open(encoding="utf-8") as f:
                for task in map(json.loads, f):
                    task_id = task["id"]
                    if task_id in linked_ids:
                        if task_id in old_tasks:
                            raise ValueError("Cannot retain links for duplicate existing task IDs")
                        old_tasks[task_id] = task
            new_tasks = {task["id"]: task for task in all_tasks if task["id"] in linked_ids}
            base_ids: dict[str, list[str]] = {}
            for task in all_tasks:
                source = task.get("source", {}).get("file")
                title = task.get("title")
                breadcrumb = task.get("hierarchy", {}).get("breadcrumb")
                if source and title and breadcrumb:
                    base = hashlib.sha256(f"{source}|{breadcrumb}|{title}".encode()).hexdigest()[:12]
                    base_ids.setdefault(base, []).append(task["id"])
            if any(len(ids) > 1 and linked_ids.intersection(ids) for ids in base_ids.values()):
                raise ValueError("Cannot retain links for ambiguous repeated tasks")
            fields = ("title", "source", "hierarchy", "raw_text", "agent")
            if old_tasks.keys() != new_tasks.keys() or any(
                any(old_tasks[key].get(field) != new_tasks[key].get(field) for field in fields)
                for key in old_tasks
            ):
                raise ValueError("Cannot retain links when linked task identities have changed")
    try:
        if not dry_run:
            output_dir.mkdir(parents=True, exist_ok=True)
            tasks_path = output_dir / "atomized-tasks.jsonl"
            write_tasks_jsonl(all_tasks, tasks_path)
            if research_result is not None:
                from organvm_engine.atoms.research import mark_doc_activated

                for path in research_result.activation_candidates:
                    try:
                        mark_doc_activated(path)
                    except Exception as e:
                        result.errors.append(("research-activate", f"{path}: {e}"))
            manifest["files"]["atomized-tasks.jsonl"] = {
                "count": len(all_tasks),
                "sha256": _sha256(tasks_path),
            }

            summary = generate_summary(all_tasks, result.plans_parsed)
            summary_path = output_dir / "ATOMIZED-SUMMARY.md"
            summary_path.write_text(summary, encoding="utf-8")
    except DuplicateTaskIdError:
        raise
    except Exception as e:
        result.errors.append(("write-tasks", str(e)))

    # Step 2: Narrate prompts
    narrate_result = None
    if not skip_narrate:
        try:
            from organvm_engine.prompts.narrator import narrate_prompts
            from organvm_engine.prompts.narrator import write_jsonl as write_prompts_jsonl

            narrate_result = narrate_prompts(agent=agent)
            result.narrate_count = len(narrate_result.prompts)
            result.noise_skipped = narrate_result.noise_skipped
            result.sessions_processed = narrate_result.sessions_processed
            result.thread_count = narrate_result.thread_count
            result.errors.extend(("narrate", e) for _, e in narrate_result.errors)

            if not dry_run:
                prompts_path = output_dir / "annotated-prompts.jsonl"
                write_prompts_jsonl(narrate_result.prompts, prompts_path)
                manifest["files"]["annotated-prompts.jsonl"] = {
                    "count": len(narrate_result.prompts),
                    "sha256": _sha256(prompts_path),
                }

                summary = generate_narrative_summary(narrate_result)
                summary_path = output_dir / "NARRATIVE-SUMMARY.md"
                summary_path.write_text(summary, encoding="utf-8")
        except Exception as e:
            result.errors.append(("narrate", str(e)))

    # Step 3: Link tasks to prompts
    if not skip_link and result.atomize_count > 0 and result.narrate_count > 0:
        try:
            from organvm_engine.atoms.linker import compute_links

            tasks_path = output_dir / "atomized-tasks.jsonl"
            prompts_path = output_dir / "annotated-prompts.jsonl"

            if dry_run:
                # In dry-run, files don't exist on disk — skip file-based linking
                result.link_count = 0
            elif tasks_path.exists() and prompts_path.exists():
                links = compute_links(
                    tasks_path, prompts_path, threshold=link_threshold,
                )
                result.links = links
                result.link_count = len(links)

                links_path = output_dir / "atom-links.jsonl"
                with links_path.open("w", encoding="utf-8") as f:
                    for link in links:
                        f.write(json.dumps(link.to_dict(), ensure_ascii=False) + "\n")
                manifest["files"]["atom-links.jsonl"] = {
                    "count": len(links),
                    "sha256": _sha256(links_path),
                }

                link_summary = generate_link_summary(links, link_threshold)
                link_summary_path = output_dir / "LINK-SUMMARY.md"
                link_summary_path.write_text(link_summary, encoding="utf-8")
        except Exception as e:
            result.errors.append(("link", str(e)))

    # Step 4: Reconcile tasks against git history
    if not skip_reconcile and not dry_run and result.atomize_count > 0:
        try:
            from organvm_engine.atoms.reconciler import apply_verdicts, reconcile_tasks
            from organvm_engine.paths import workspace_root

            tasks_path = output_dir / "atomized-tasks.jsonl"
            if tasks_path.exists():
                rec_result = reconcile_tasks(tasks_path, workspace_root())
                apply_verdicts(tasks_path, rec_result.verdicts)
                result.reconcile_completed = rec_result.likely_completed
                result.reconcile_partial = rec_result.partially_done
        except Exception as e:
            result.errors.append(("reconcile", str(e)))

    # Step 5: Write plan index
    if not dry_run:
        try:
            from organvm_engine.plans.index import build_plan_index, index_to_json

            index = build_plan_index(agent=agent, organ=organ)
            index_path = output_dir / "plan-index.json"
            index_path.write_text(index_to_json(index), encoding="utf-8")
            manifest["files"]["plan-index.json"] = {
                "count": index.total_plans,
            }
        except Exception as e:
            result.errors.append(("index", str(e)))

    # Step 5: Compute quality stats
    null_organ_tasks = 0
    empty_fp_prompts = 0
    if not dry_run:
        tasks_path = output_dir / "atomized-tasks.jsonl"
        if tasks_path.exists():
            with tasks_path.open(encoding="utf-8") as f:
                for raw in f:
                    line = raw.strip()
                    if not line:
                        continue
                    t = json.loads(line)
                    organ = t.get("project", {}).get("organ")
                    if not organ or organ in ("_root", None):
                        null_organ_tasks += 1
        prompts_path = output_dir / "annotated-prompts.jsonl"
        if prompts_path.exists():
            with prompts_path.open(encoding="utf-8") as f:
                for raw in f:
                    line = raw.strip()
                    if not line:
                        continue
                    p = json.loads(line)
                    fp = p.get("domain_fingerprint", "")
                    if not fp or fp.startswith("e3b0c44298fc"):
                        empty_fp_prompts += 1

    manifest["quality"] = {
        "null_organ_tasks": null_organ_tasks,
        "empty_fingerprint_prompts": empty_fp_prompts,
        "link_threshold": link_threshold,
    }

    # Reconciliation may have rewritten task statuses after the first hash.
    if not dry_run and "atomized-tasks.jsonl" in manifest["files"]:
        try:
            manifest["files"]["atomized-tasks.jsonl"]["sha256"] = _sha256(
                output_dir / "atomized-tasks.jsonl",
            )
        except OSError as e:
            manifest["files"]["atomized-tasks.jsonl"].pop("sha256", None)
            result.errors.append(("hash-tasks", str(e)))

    # Step 6: Write manifest
    manifest["counts"] = {
        "plans_parsed": result.plans_parsed,
        "research_docs_scanned": result.research_docs_scanned,
        "research_directives": result.research_directives,
        "tasks": result.atomize_count,
        "prompts": result.narrate_count,
        "noise_skipped": result.noise_skipped,
        "sessions": result.sessions_processed,
        "threads": result.thread_count,
        "links": result.link_count,
        "reconcile_completed": result.reconcile_completed,
        "reconcile_partial": result.reconcile_partial,
        "errors": len(result.errors),
    }

    if not dry_run:
        manifest_path = output_dir / "pipeline-manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    result.manifest = manifest
    return result
