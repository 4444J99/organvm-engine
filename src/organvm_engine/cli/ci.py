"""CI triage, infrastructure audit, scaffold, and branch protection CLI commands."""

import argparse
import json


def _requested_scaffold_capabilities(args: argparse.Namespace) -> tuple[bool, bool, bool]:
    """Resolve lint/test/typecheck booleans from scaffold CLI flags."""
    requested_specific = bool(args.lint or args.test or args.typecheck)
    include_all = bool(args.all or not requested_specific)
    return (
        bool(args.lint or include_all),
        bool(args.test or include_all),
        bool(args.typecheck or include_all),
    )


def cmd_ci_scaffold(args: argparse.Namespace) -> int:
    """Generate CI workflow YAML for a repo (lint/test/typecheck steps)."""
    from pathlib import Path

    from organvm_engine.ci.scaffold import scaffold_repo

    repo_path = Path(args.path).resolve()
    if not repo_path.is_dir():
        print(f"Error: {repo_path} is not a directory")
        return 1

    repo_name = getattr(args, "name", None) or repo_path.name
    dry_run = not getattr(args, "write", False)
    lint, test, typecheck = _requested_scaffold_capabilities(args)

    result = scaffold_repo(
        repo_path=repo_path,
        repo_name=repo_name,
        lint=lint,
        test=test,
        typecheck=typecheck,
    )
    target = repo_path / ".github" / "workflows" / result.workflow_filename()

    if args.json:
        out = {
            "repo": result.repo_name,
            "stack": result.stack.value,
            "workflow_file": str(target),
        }
        if result.lint_yaml:
            out["lint_step"] = result.lint_yaml
        if result.test_yaml:
            out["test_step"] = result.test_yaml
        if result.typecheck_yaml:
            out["typecheck_step"] = result.typecheck_yaml
        out["combined"] = result.combined_yaml()
        print(json.dumps(out, indent=2))
        return 0

    combined = result.combined_yaml()
    if not combined:
        print(f"Stack: {result.stack.value}")
        print("No steps generated (unknown stack or no flags selected).")
        return 1

    if dry_run:
        print(f"# Stack detected: {result.stack.value}")
        print(f"# Would write to: {target}")
        print()
        print(combined)
    else:
        wf_dir = repo_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True, exist_ok=True)
        target.write_text(combined)
        print(f"Wrote {target}")

    return 0


def cmd_ci_protect(args: argparse.Namespace) -> int:
    """Generate branch protection commands for GRADUATED repos."""
    from organvm_engine.ci.protect import plan_branch_protection
    from organvm_engine.registry.loader import load_registry

    registry_path = getattr(args, "registry", None)
    registry = load_registry(registry_path)

    organ_filter = getattr(args, "organ", None)
    repo_filter = getattr(args, "repo", None)

    dry_run = not getattr(args, "execute", False)

    plan = plan_branch_protection(
        registry,
        organ_filter=organ_filter,
        repo_filter=repo_filter,
    )

    if args.json:
        print(json.dumps(plan.to_dict(), indent=2))
        return 0

    print(f"\n{plan.summary()}\n")

    if plan.repos and not dry_run:
        print("\nCommands to execute:")
        print("=" * 50)
        for cmd in plan.commands():
            print()
            print(cmd)
        print()

    if dry_run and plan.repos:
        print("\n[dry-run] Commands that would be generated:")
        for p in plan.repos:
            print(f"  gh api -X PUT repos/{p.org}/{p.repo_name}/branches/main/protection ...")

    return 0


def cmd_ci_triage(args: argparse.Namespace) -> int:
    from organvm_engine.ci.triage import triage

    report = triage()
    print(f"\n{report.summary()}\n")
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    return 0


def cmd_ci_audit(args: argparse.Namespace) -> int:
    """Run infrastructure audit (The Descent Protocol)."""
    from organvm_engine.ci.audit import run_infra_audit
    from organvm_engine.registry.loader import load_registry

    registry_path = getattr(args, "registry", None)
    registry = load_registry(registry_path)

    organ_filter = getattr(args, "organ", None)
    repo_filter = getattr(args, "repo", None)

    report = run_infra_audit(
        registry=registry,
        organ_filter=organ_filter,
        repo_filter=repo_filter,
    )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(f"\n{report.summary()}\n")

    # Exit non-zero if any repos are non-compliant
    return 0 if report.non_compliant_repos == 0 else 1


def cmd_ci_evidence(args: argparse.Namespace) -> int:
    """Collect one run's execution evidence and evaluate it (organvm-engine #189).

    Fetches the run and its jobs pages through the environment-supplied token
    (``GITHUB_TOKEN``/``GH_TOKEN``), evaluates them against caller-pinned
    expectations from the reviewed workflow contract, and prints the report.
    Exit 0 only when the decision is ``executed_pass``; 1 for any other
    decision; 2 when the input, contract, or fetch is invalid. The report
    never authorizes execution, a check, or a release.
    """
    from pathlib import Path

    from organvm_engine.ci import evidence_collector

    if "/" not in args.repo:
        print("Error: --repo must be OWNER/NAME")
        return 2
    owner, repo = args.repo.split("/", 1)
    try:
        required_steps, contract = evidence_collector.load_required_steps(
            Path(args.required_steps),
        )
        report = evidence_collector.collect_run_evidence(
            owner=owner,
            repo=repo,
            run_id=args.run_id,
            expected_repository_id=args.repository_id,
            expected_revision=args.revision,
            expected_workflow_id=args.workflow_id,
            expected_run_id=args.run_id,
            expected_attempt=args.attempt,
            required_steps=required_steps,
        )
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}")
        return 2

    report["contract"] = contract
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                                  encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"\nExecution evidence — {args.repo} run {args.run_id} "
              f"(attempt {args.attempt})\n")
        print(f"  Decision: {report['decision']}")
        print(f"  Jobs: {report['observed_job_count']}/{report['reported_job_count']} "
              f"(enumeration complete: {report['enumeration_complete']})")
        for job in report["jobs"]:
            print(f"    - {job['name']}: {job['state']} "
                  f"(runner {job.get('runner_id')}, "
                  f"executed {job['executed_required']}/{job['required_count']} required steps)")
        print(f"  Sources: {report['collection']['run_source']}")
        print(f"  Observed at: {report['collection']['observed_at']}")
        print("  Authorizes release: False; authorizes execution: False\n")
    return 0 if report["decision"] == "executed_pass" else 1


def cmd_ci_mandate(args: argparse.Namespace) -> int:
    """Verify CI workflow files exist on disk (mandate check)."""
    from organvm_engine.ci.mandate import verify_ci_mandate
    from organvm_engine.registry.loader import load_registry

    registry_path = getattr(args, "registry", None)
    registry = load_registry(registry_path)

    report = verify_ci_mandate(registry)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(f"\nCI Mandate — {report.has_ci}/{report.total} repos have workflows "
              f"({report.adherence_rate:.0%})\n")
        missing = report.missing_repos()
        if missing:
            print(f"  Missing CI ({len(missing)}):")
            for entry in missing:
                found = "" if entry.repo_path_found else " [NOT ON DISK]"
                print(f"    - {entry.organ}/{entry.repo_name}{found}")
        drift = report.drift_from_registry(registry)
        if drift:
            print(f"\n  Registry Drift ({len(drift)}):")
            for d in drift:
                print(f"    - {d['organ']}/{d['repo']}: "
                      f"registry={d['registry_says']}, disk={d['filesystem_says']}")
    print()
    return 0
