"""System context file sync — walks workspace, updates auto-generated sections.

The sync process:
1. Load registry + seeds once
2. Walk each organ directory looking for CLAUDE.md, GEMINI.md, and AGENTS.md files
3. For each file, inject or replace the auto-generated section
4. Optionally update the workspace-level context files

Preserves all manually-written content outside the AUTO markers.
"""

from __future__ import annotations

import difflib
import hashlib
import os
import re
import secrets
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from organvm_engine.contextmd import AUTO_END, AUTO_START
from organvm_engine.contextmd.generator import (
    generate_agents_section,
    generate_organ_section,
    generate_repo_section,
    generate_workspace_section,
    precompute_ammoi,
    resolve_agents_remote_references,
)

MAX_CONTEXT_OUTPUT_BYTES = 16_000_000
CUSTODY_TRANSACTION_ALIAS = re.compile(
    r"^transaction-[0-9a-f]{48}\.(?:generated|preimage|rollback)$",
)


class ContextCustodyPublicationError(RuntimeError):
    """A failed publication left a regular, CAS-bound effect at the public path."""

    def __init__(self, message: str, output_binding: dict[str, str | int]) -> None:
        super().__init__(message)
        self.output_binding = output_binding


def sync_all(
    workspace: Path | str | None = None,
    registry_path: str | None = None,
    dry_run: bool = False,
    organs: list[str] | None = None,
    additional_workspace_roots: list[Path] | None = None,
    receipt_path: Path | str | None = None,
) -> dict[str, Any]:
    """Sync auto-generated sections across all context files."""
    from organvm_engine.paths import additional_workspace_roots as resolve_additional_roots
    from organvm_engine.paths import registry_path as resolve_registry_path
    from organvm_engine.paths import workspace_root
    from organvm_engine.registry.loader import load_registry
    from organvm_engine.registry.validator import (
        capture_registry_validation_policy,
        validate_registry,
    )
    from organvm_engine.seed.discover import discover_seeds
    from organvm_engine.seed.reader import read_seed

    ws = Path(workspace).expanduser() if workspace else workspace_root()
    registry_source = (
        Path(registry_path).expanduser() if registry_path else resolve_registry_path()
    )
    extra_roots = (
        [Path(p).expanduser() for p in additional_workspace_roots]
        if additional_workspace_roots is not None
        else resolve_additional_roots(workspace=ws)
    )
    receipt_enabled = receipt_path is not None and not dry_run
    receipt_generated_at = (
        datetime.now(timezone.utc).replace(microsecond=0) if receipt_enabled else None
    )
    render_timestamp = (
        receipt_generated_at.strftime("%Y-%m-%dT%H:%M:%SZ")
        if receipt_generated_at is not None
        else None
    )
    render_profile = "receipted-core-v1" if receipt_enabled else "standard"
    receipt_expected_inputs: dict[str, Any] | None = None
    receipt_validation_policy = None
    receipt_workspace_identity: dict[str, int] | None = None
    captured_seed_payloads: dict[Path, bytes] = {}
    if receipt_enabled:
        assert receipt_path is not None
        receipt_target = Path(receipt_path).expanduser()
        if receipt_target.exists() or receipt_target.is_symlink():
            raise RuntimeError(f"receipt destination already exists: {receipt_target}")
        receipt_workspace_identity = _capture_custody_root_identity(ws)
        workspace_resolved = ws.resolve(strict=True)
        for root in extra_roots:
            if not root.exists():
                continue
            try:
                root.resolve(strict=True).relative_to(workspace_resolved)
            except ValueError as exc:
                raise RuntimeError(
                    "receipted context sync requires every output root to be inside "
                    f"the workspace: {root}",
                ) from exc

    # 1. Discover all seeds to have edge data
    seed_paths = discover_seeds(ws)
    for root in extra_roots:
        seed_paths.extend(discover_seeds(root))
        seed_paths.extend(_discover_flat_seeds(root))
    if receipt_enabled:
        seed_paths = sorted(
            set(seed_paths),
            key=_lexical_absolute,
        )
    if receipt_enabled:
        assert receipt_path is not None
        import json

        import yaml

        from organvm_engine.contextmd.receipt import capture_context_sync_inputs

        receipt_validation_policy = capture_registry_validation_policy()
        (
            receipt_expected_inputs,
            captured_registry_payload,
            captured_seed_payloads,
        ) = capture_context_sync_inputs(
            workspace=ws,
            registry_path=registry_source,
            seed_paths=seed_paths,
            workspace_identity=receipt_workspace_identity,
            registry_validation_policy=receipt_validation_policy.evidence(),
        )
        try:
            reg = json.loads(captured_registry_payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"cannot parse receipted registry input: {exc}") from exc
        if not isinstance(reg, dict):
            raise RuntimeError("receipted registry input is not a JSON mapping")
    else:
        reg = load_registry(registry_source)

    # Pre-flight: Validate registry before sync to prevent breaking 100+ files
    val_result = validate_registry(reg, policy=receipt_validation_policy)
    if not val_result.passed:
        raise RuntimeError(
            f"Registry validation failed. Refusing to sync context files.\n{val_result.summary()}",
        )

    if receipt_enabled:
        target_organs = organs or [str(key) for key in reg.get("organs", {})]
        organ_directory_map = _registry_organ_directory_map(reg, target_organs)
    else:
        from organvm_engine.git.superproject import REGISTRY_KEY_MAP

        organ_directory_map = REGISTRY_KEY_MAP
        target_organs = organs or list(organ_directory_map)

    all_seeds = []
    repo_to_seed = {}
    for p in seed_paths:
        try:
            if receipt_enabled:
                s = yaml.safe_load(captured_seed_payloads[p])
                if not isinstance(s, dict):
                    raise ValueError(f"seed.yaml at {p} is not a YAML mapping")
            else:
                s = read_seed(p)
            repo_identity = s.get("repo")
            if receipt_enabled and repo_identity in repo_to_seed:
                raise RuntimeError(
                    "receipted context sync rejects duplicate seed repository identity: "
                    f"{repo_identity}",
                )
            all_seeds.append(s)
            repo_to_seed[repo_identity] = s
        except Exception as exc:
            if receipt_enabled:
                raise RuntimeError(f"cannot receipt malformed seed input {p}: {exc}") from exc
            continue

    receipt_generator_identity: dict[str, str] | None = None
    if receipt_enabled:
        from organvm_engine.contextmd.receipt import generator_git_identity

        receipt_generator_identity = generator_git_identity()

    # 1b. Discover all SOPs for directive injection
    from organvm_engine.sop.discover import discover_sops
    from organvm_engine.sop.resolver import promotion_to_phase
    from organvm_engine.sop.resolver import resolve_all as resolve_all_sops

    all_sops = discover_sops(workspace=ws)
    for root in extra_roots:
        all_sops.extend(discover_sops(workspace=root))
        all_sops.extend(_discover_flat_sops(root))

    receipt_sop_inputs: dict[str, Any] | None = None
    if receipt_enabled:
        from organvm_engine.contextmd.receipt import bind_context_sync_sops

        receipt_sop_inputs = bind_context_sync_sops(all_sops, ws)
        stable_sops = discover_sops(workspace=ws)
        for root in extra_roots:
            stable_sops.extend(discover_sops(workspace=root))
            stable_sops.extend(_discover_flat_sops(root))
        if bind_context_sync_sops(stable_sops, ws) != receipt_sop_inputs:
            raise RuntimeError("SOP evidence changed while preparing receipted sync")
        all_sops = stable_sops

    # Pre-compute AMMOI once for all context files
    if not receipt_enabled:
        precompute_ammoi()

    updated = []
    created = []
    skipped = []
    errors = []
    changes = []
    expected_output_bindings: list[dict[str, str | int]] = []
    failed_output_paths: list[Path] = []
    target_preimages: list[dict[str, Any]] = []
    rendered_remote_references: list[dict[str, str]] = []

    if receipt_enabled:
        assert receipt_path is not None
        target_preimages = _preflight_context_outputs(
            workspace=ws,
            registry=reg,
            target_organs=target_organs,
            extra_roots=extra_roots,
            organ_directory_map=organ_directory_map,
            workspace_identity=receipt_workspace_identity,
        )
        receipt_target_absolute = _lexical_absolute(Path(receipt_path))
        output_targets = {
            _lexical_absolute(ws / str(binding["path"]))
            for binding in target_preimages
        }
        if receipt_target_absolute in output_targets:
            raise RuntimeError(
                "receipt destination collides with a generated context output: "
                f"{receipt_target_absolute}",
            )
        from organvm_engine.paths import PathConfig, context_changelog_path

        changelog_config = PathConfig(workspace_dir=workspace) if workspace else None
        changelog_target = _lexical_absolute(context_changelog_path(changelog_config))
        if receipt_target_absolute == changelog_target:
            raise RuntimeError(
                "receipt destination collides with the context changelog: "
                f"{receipt_target_absolute}",
            )
    target_preimage_map = {
        str(binding["path"]): binding for binding in target_preimages
    }

    for organ_key in target_organs:
        organ_dir_name = organ_directory_map.get(organ_key)
        if not organ_dir_name:
            continue

        organ_data = reg.get("organs", {}).get(organ_key, {})
        organ_path = ws / organ_dir_name

        if organ_path.is_dir():
            # 2. Sync organ-level context files
            for filename in ["CLAUDE.md", "GEMINI.md", "AGENTS.md"]:
                try:
                    organ_section = generate_organ_section(
                        organ_key,
                        reg,
                        all_seeds,
                        timestamp=render_timestamp,
                        include_live_context=not receipt_enabled,
                    )
                    res = _inject_section_result(
                        organ_path / filename,
                        organ_section,
                        dry_run,
                        custody_root=ws if receipt_enabled else None,
                        expected_input_bindings=(
                            target_preimage_map if receipt_enabled else None
                        ),
                        custody_root_identity=receipt_workspace_identity,
                    )
                    _record_sync_result(
                        res,
                        updated,
                        created,
                        skipped,
                        changes,
                        expected_output_bindings,
                        target_preimages,
                    )
                except Exception as e:
                    _record_sync_error(
                        e,
                        organ_path / filename,
                        errors,
                        expected_output_bindings,
                        failed_output_paths,
                    )

            # 3. Sync repo-level context files for the hierarchical workspace layout.
            for repo_entry in organ_data.get("repositories", []):
                repo_name = repo_entry.get("name")
                repo_path = organ_path / repo_name
                if not repo_path.is_dir():
                    continue
                _sync_repo_context_files(
                    repo_path=repo_path,
                    repo_entry=repo_entry,
                    organ_dir_name=organ_dir_name,
                    registry=reg,
                    repo_to_seed=repo_to_seed,
                    all_sops=all_sops,
                    dry_run=dry_run,
                    updated=updated,
                    created=created,
                    skipped=skipped,
                    changes=changes,
                    errors=errors,
                    rendered_remote_references=rendered_remote_references,
                    expected_output_bindings=expected_output_bindings,
                    failed_output_paths=failed_output_paths,
                    target_preimages=target_preimages,
                    target_preimage_map=target_preimage_map,
                    receipt_workspace_identity=receipt_workspace_identity,
                    receipt_workspace=ws if receipt_enabled else None,
                    render_timestamp=render_timestamp,
                    include_live_context=not receipt_enabled,
                    promotion_to_phase=promotion_to_phase,
                    resolve_all_sops=resolve_all_sops,
                )

        # 3b. Sync repo-level context files for additive flat workspace roots.
        for repo_entry in organ_data.get("repositories", []):
            repo_name = repo_entry.get("name")
            if not repo_name:
                continue
            for root in extra_roots:
                repo_path = root / repo_name
                if not repo_path.is_dir():
                    continue
                if organ_path.is_dir() and repo_path.resolve() == (organ_path / repo_name).resolve():
                    continue
                _sync_repo_context_files(
                    repo_path=repo_path,
                    repo_entry=repo_entry,
                    organ_dir_name=organ_dir_name,
                    registry=reg,
                    repo_to_seed=repo_to_seed,
                    all_sops=all_sops,
                    dry_run=dry_run,
                    updated=updated,
                    created=created,
                    skipped=skipped,
                    changes=changes,
                    errors=errors,
                    rendered_remote_references=rendered_remote_references,
                    expected_output_bindings=expected_output_bindings,
                    failed_output_paths=failed_output_paths,
                    target_preimages=target_preimages,
                    target_preimage_map=target_preimage_map,
                    receipt_workspace_identity=receipt_workspace_identity,
                    receipt_workspace=ws if receipt_enabled else None,
                    render_timestamp=render_timestamp,
                    include_live_context=not receipt_enabled,
                    promotion_to_phase=promotion_to_phase,
                    resolve_all_sops=resolve_all_sops,
                )

    # 4. Sync workspace-level context files
    for filename in ["CLAUDE.md", "GEMINI.md", "AGENTS.md"]:
        try:
            ws_section = generate_workspace_section(
                reg,
                all_seeds,
                timestamp=render_timestamp,
                include_live_context=not receipt_enabled,
            )
            res = _inject_section_result(
                ws / filename,
                ws_section,
                dry_run,
                custody_root=ws if receipt_enabled else None,
                expected_input_bindings=(
                    target_preimage_map if receipt_enabled else None
                ),
                custody_root_identity=receipt_workspace_identity,
            )
            _record_sync_result(
                res,
                updated,
                created,
                skipped,
                changes,
                expected_output_bindings,
                target_preimages,
            )
        except Exception as e:
            _record_sync_error(
                e,
                ws / filename,
                errors,
                expected_output_bindings,
                failed_output_paths,
            )

    result = {
        "updated": updated,
        "created": created,
        "skipped": skipped,
        "errors": errors,
        "dry_run": dry_run,
        "changes": changes,
        "changelog": changes,
        "receipt_path": None,
        "receipt_sha256": None,
    }

    if receipt_enabled:
        assert receipt_path is not None
        rediscovered_seed_paths = discover_seeds(ws)
        for root in extra_roots:
            rediscovered_seed_paths.extend(discover_seeds(root))
            rediscovered_seed_paths.extend(_discover_flat_seeds(root))
        rediscovered_seed_paths = sorted(
            set(rediscovered_seed_paths),
            key=_lexical_absolute,
        )
        if rediscovered_seed_paths != seed_paths:
            _raise_after_receipted_rollback(
                "seed evidence path set changed while preparing receipted sync",
                workspace=ws,
                target_preimages=target_preimages,
                expected_output_bindings=expected_output_bindings,
                workspace_identity=receipt_workspace_identity,
            )
        rediscovered_sops = discover_sops(workspace=ws)
        for root in extra_roots:
            rediscovered_sops.extend(discover_sops(workspace=root))
            rediscovered_sops.extend(_discover_flat_sops(root))
        if bind_context_sync_sops(rediscovered_sops, ws) != receipt_sop_inputs:
            _raise_after_receipted_rollback(
                "SOP evidence path set changed while preparing receipted sync",
                workspace=ws,
                target_preimages=target_preimages,
                expected_output_bindings=expected_output_bindings,
                workspace_identity=receipt_workspace_identity,
            )

        from organvm_engine.contextmd.receipt import (
            build_context_sync_receipt,
            write_context_sync_receipt,
        )

        assert receipt_generator_identity is not None
        assert receipt_expected_inputs is not None
        assert receipt_sop_inputs is not None
        assert receipt_validation_policy is not None
        bound_output_labels = {
            str(binding["path"]) for binding in expected_output_bindings
        }
        for missing_label in sorted(
            {str(binding["path"]) for binding in target_preimages}
            - bound_output_labels,
        ):
            errors.append(
                {
                    "path": str(ws / missing_label),
                    "error": "receipted target did not produce a bound output",
                },
            )
        output_paths = [
            Path(path)
            for path in (*updated, *created, *skipped, *failed_output_paths)
        ]
        invocation = {
            "organs": sorted(target_organs),
            "organ_directory_map": {
                key: organ_directory_map[key]
                for key in sorted(target_organs)
                if key in organ_directory_map
            },
            "additional_workspace_roots": sorted(
                _receipt_path_label(root, ws) for root in extra_roots
            ),
            "targets": sorted(str(binding["path"]) for binding in target_preimages),
        }
        receipt_expected_inputs.update(
            {
                "sops": receipt_sop_inputs,
                "render_profile": render_profile,
                "invocation": invocation,
                "target_preimages": sorted(
                    target_preimages,
                    key=lambda item: str(item.get("path", "")),
                ),
                "target_preimages_manifest_sha256": _canonical_receipt_digest(
                    target_preimages,
                ),
            },
        )
        post_generator_identity = generator_git_identity(
            allowed_dirty_paths=output_paths,
        )
        receipt = build_context_sync_receipt(
            workspace=ws,
            registry_path=registry_source,
            seed_paths=seed_paths,
            remote_references=rendered_remote_references,
            output_paths=output_paths,
            errors=errors,
            generator_identity=receipt_generator_identity,
            post_generator_identity=post_generator_identity,
            expected_inputs=receipt_expected_inputs,
            expected_output_bindings=expected_output_bindings,
            generated_at=receipt_generated_at,
            sop_entries=all_sops,
            render_profile=render_profile,
            invocation=invocation,
            target_preimages=target_preimages,
            workspace_identity=receipt_workspace_identity,
            registry_validation_policy=receipt_validation_policy.evidence(),
        )
        receipt_target = Path(receipt_path).expanduser()
        receipt_digest = write_context_sync_receipt(receipt_target, receipt)
        result["receipt_path"] = str(receipt_target)
        result["receipt_sha256"] = receipt_digest

    # Emit context sync event
    if not dry_run:
        if changes:
            import json
            import time

            from organvm_engine.paths import (
                PathConfig,
                context_changelog_path,
            )

            sync_timestamp = int(time.time())
            # Use explicit config based on the passed workspace, to support tests.
            config = PathConfig(workspace_dir=workspace) if workspace else None
            changelog_file = context_changelog_path(config)
            try:
                if not (config or PathConfig()).registry_path().is_file():
                    raise FileNotFoundError(
                        "canonical corpus registry is absent; skip context changelog",
                    )
                changelog_file.parent.mkdir(parents=True, exist_ok=True)
                with changelog_file.open("a", encoding="utf-8") as f:
                    for change in changes:
                        record = {
                            "timestamp": sync_timestamp,
                            "path": change["path"],
                            "action": change["action"],
                            "diff": change.get("diff", ""),
                            "old_section": change.get("old_section", ""),
                            "new_section": change.get("new_section", ""),
                        }
                        f.write(json.dumps(record) + "\n")
            except Exception:
                # Fallback or silent failure if no corpus repo exists in test envs
                pass

        try:
            from organvm_engine.pulse.emitter import emit_engine_event
            from organvm_engine.pulse.types import CONTEXT_SYNCED

            emit_engine_event(
                event_type=CONTEXT_SYNCED,
                source="contextmd",
                payload={
                    "updated_count": len(updated),
                    "created_count": len(created),
                    "changed_count": len(changes),
                    "error_count": len(errors),
                },
            )
        except Exception:
            pass

        # Emit to Testament Chain
        from organvm_engine.ledger.emit import testament_emit
        testament_emit(
            event_type="context.sync",
            source_organ="META-ORGANVM",
            source_repo="organvm-engine",
            actor="cli",
            payload={
                "updated": len(updated),
                "created": len(created),
                "changed": len(changes),
                "errors": len(errors),
            },
        )

    return result

def _discover_flat_seeds(root: Path) -> list[Path]:
    """Find seed.yaml files in a flat root shaped as <root>/<repo>/seed.yaml."""
    if not root.is_dir():
        return []
    seeds = []
    for repo_dir in sorted(root.iterdir()):
        if not repo_dir.is_dir():
            continue
        seed_file = repo_dir / "seed.yaml"
        if seed_file.is_file():
            seeds.append(seed_file)
    return seeds


def _discover_flat_sops(root: Path) -> list:
    """Find SOPs in a flat root shaped as <root>/<repo>/..."""
    if not root.is_dir():
        return []

    from organvm_engine.sop.discover import _scan_repo, _scan_sops_dir

    entries = []
    for repo_dir in sorted(root.iterdir()):
        if not repo_dir.is_dir():
            continue
        _scan_repo(root.parent, root.name, repo_dir.name, repo_dir, entries)
        _scan_sops_dir(root.parent, root.name, repo_dir.name, repo_dir / ".sops", entries)
    return entries


def _sync_repo_context_files(
    *,
    repo_path: Path,
    repo_entry: dict[str, Any],
    organ_dir_name: str,
    registry: dict,
    repo_to_seed: dict,
    all_sops: list,
    dry_run: bool,
    updated: list[str],
    created: list[str],
    skipped: list[str],
    changes: list[dict[str, Any]] | None = None,
    errors: list[dict[str, str]],
    rendered_remote_references: list[dict[str, str]],
    expected_output_bindings: list[dict[str, str | int]],
    failed_output_paths: list[Path],
    target_preimages: list[dict[str, Any]],
    target_preimage_map: dict[str, dict[str, Any]],
    receipt_workspace_identity: dict[str, int] | None,
    receipt_workspace: Path | None,
    render_timestamp: str | None,
    include_live_context: bool,
    promotion_to_phase,
    resolve_all_sops,
) -> None:
    repo_name = repo_entry.get("name")
    if not repo_name:
        return

    org_name = repo_entry.get("org") or organ_dir_name
    promo_status = repo_entry.get("promotion_status", "LOCAL")
    repo_phase = promotion_to_phase(promo_status)
    repo_sops = resolve_all_sops(
        all_sops, repo=repo_name, organ=organ_dir_name, phase=repo_phase,
    )

    for filename in ["CLAUDE.md", "GEMINI.md"]:
        try:
            res = sync_repo(
                repo_path,
                repo_name,
                org_name,
                registry,
                repo_to_seed.get(repo_name),
                dry_run,
                filename=filename,
                sop_entries=repo_sops,
                custody_root=receipt_workspace,
                timestamp=render_timestamp,
                include_live_context=include_live_context,
                expected_input_bindings=(
                    target_preimage_map if receipt_workspace is not None else None
                ),
                custody_root_identity=receipt_workspace_identity,
            )
            _record_sync_result(
                res,
                updated,
                created,
                skipped,
                changes,
                expected_output_bindings,
                target_preimages,
            )
        except Exception as e:
            _record_sync_error(
                e,
                repo_path / filename,
                errors,
                expected_output_bindings,
                failed_output_paths,
            )

    try:
        agents_section = generate_agents_section(
            repo_name,
            org_name,
            registry,
            repo_to_seed.get(repo_name),
            timestamp=render_timestamp,
        )
        res = _inject_section_result(
            repo_path / "AGENTS.md",
            agents_section,
            dry_run,
            custody_root=receipt_workspace,
            expected_input_bindings=(
                target_preimage_map if receipt_workspace is not None else None
            ),
            custody_root_identity=receipt_workspace_identity,
        )
        _record_sync_result(
            res,
            updated,
            created,
            skipped,
            changes,
            expected_output_bindings,
            target_preimages,
        )
        if receipt_workspace is not None:
            output_binding = res.get("output_binding")
            if not isinstance(output_binding, dict):
                raise RuntimeError("receipted AGENTS output is missing its byte binding")
            output_label = str(output_binding["path"])
            for reference in resolve_agents_remote_references(
                repo_to_seed.get(repo_name),
                registry,
                default_owner=str(org_name),
            ):
                rendered_remote_references.append(
                    {**reference, "output_path": output_label},
                )
    except Exception as e:
        _record_sync_error(
            e,
            repo_path / "AGENTS.md",
            errors,
            expected_output_bindings,
            failed_output_paths,
        )


def sync_repo(
    repo_path: Path,
    repo_name: str,
    org: str,
    registry: dict,
    seed: dict | None = None,
    dry_run: bool = False,
    filename: str = "CLAUDE.md",
    sop_entries: list | None = None,
    custody_root: Path | None = None,
    timestamp: str | None = None,
    include_live_context: bool = True,
    expected_input_bindings: dict[str, dict[str, Any]] | None = None,
    custody_root_identity: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Sync a single repo's context file."""
    agent = filename.replace(".md", "").lower() if filename else None
    section = generate_repo_section(
        repo_name,
        org,
        registry,
        seed,
        sop_entries=sop_entries,
        agent=agent,
        repo_path=str(repo_path),
        timestamp=timestamp,
        include_live_context=include_live_context,
    )
    file_path = repo_path / filename
    res = _inject_section_result(
        file_path,
        section,
        dry_run,
        custody_root=custody_root,
        expected_input_bindings=expected_input_bindings,
        custody_root_identity=custody_root_identity,
    )
    return {
        "path": res["path"],
        "action": res["action"],
        "dry_run": dry_run,
        "change": res.get("change"),
        "output_binding": res.get("output_binding"),
        "input_binding": res.get("input_binding"),
    }


def _inject_section(file_path: Path, new_section: str, dry_run: bool = False) -> str:
    """Inject or replace the auto-generated section in a markdown file."""
    return _inject_section_result(file_path, new_section, dry_run)["action"]


def _inject_section_result(
    file_path: Path,
    new_section: str,
    dry_run: bool = False,
    custody_root: Path | None = None,
    expected_input_bindings: dict[str, dict[str, Any]] | None = None,
    custody_root_identity: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Inject or replace the auto-generated section and describe the generated diff."""
    import re

    custody: tuple[str, str] | None = None
    existing_payload: bytes | None = None
    parent_identity: dict[str, int] | None = None
    if custody_root is not None:
        parent_fd, filename, output_label = _open_custody_parent(
            file_path,
            custody_root,
            expected_root_identity=custody_root_identity,
        )
        try:
            existing_payload = _read_custody_payload(parent_fd, filename)
            parent_identity = _custody_parent_identity(parent_fd)
        finally:
            os.close(parent_fd)
        custody = (filename, output_label)
        content = (
            existing_payload.decode("utf-8")
            if existing_payload is not None
            else None
        )
    else:
        content = file_path.read_text() if file_path.exists() else None

    input_binding: dict[str, Any] | None = None
    if custody is not None:
        _filename, output_label = custody
        assert parent_identity is not None
        if existing_payload is None:
            input_binding = {
                "path": output_label,
                "state": "absent",
                "parent_identity": parent_identity,
            }
        else:
            input_binding = {
                **_payload_binding(output_label, existing_payload),
                "state": "present",
                "parent_identity": parent_identity,
            }
        if expected_input_bindings is not None:
            expected_input = expected_input_bindings.get(output_label)
            if expected_input is None:
                raise RuntimeError(
                    f"context target was not bound during preflight: {output_label}",
                )
            if input_binding != expected_input:
                raise RuntimeError(
                    f"context target changed after receipted preflight: {output_label}",
                )

    if content is None:
        action = "created"
        rendered = new_section + "\n"
        change = _build_change_record(file_path, action, "", new_section)
    else:
        action, rendered, change = _render_existing_context(
            file_path,
            content,
            new_section,
            re,
        )

    if not dry_run and action != "unchanged":
        payload = rendered.encode("utf-8")
        if custody is not None and len(payload) > MAX_CONTEXT_OUTPUT_BYTES:
            raise RuntimeError(
                "generated context output exceeds receipted size limit: "
                f"{output_label}",
            )
        if custody is not None:
            assert custody_root is not None
            parent_fd, filename, output_label = _open_custody_parent(
                file_path,
                custody_root,
                expected_root_identity=custody_root_identity,
            )
            if custody != (filename, output_label):
                os.close(parent_fd)
                raise RuntimeError(f"context output identity changed: {file_path}")
            try:
                _require_preflight_parent_identity(
                    parent_fd,
                    output_label,
                    expected_input_bindings,
                )
                _write_custody_payload(
                    parent_fd,
                    filename,
                    payload,
                    create_only=content is None,
                    expected_preimage=existing_payload,
                    custody_root=custody_root,
                    output_label=output_label,
                    custody_root_identity=custody_root_identity,
                )
            finally:
                os.close(parent_fd)
        else:
            file_path.write_text(rendered)

    output_binding = None
    if custody is not None and not dry_run:
        assert custody_root is not None
        expected_payload = rendered.encode("utf-8")
        parent_fd, filename, output_label = _open_custody_parent(
            file_path,
            custody_root,
            expected_root_identity=custody_root_identity,
        )
        try:
            _require_preflight_parent_identity(
                parent_fd,
                output_label,
                expected_input_bindings,
            )
            actual_payload = _read_custody_payload(parent_fd, filename)
            if actual_payload != expected_payload:
                raise RuntimeError(
                    f"generated context output changed before binding: {file_path}",
                )
            assert actual_payload is not None
            if action == "unchanged":
                _bind_unchanged_custody_payload(
                    parent_fd=parent_fd,
                    filename=filename,
                    payload=actual_payload,
                    custody_root=custody_root,
                    output_label=output_label,
                    custody_root_identity=custody_root_identity,
                )
        finally:
            os.close(parent_fd)
        output_binding = _payload_binding(output_label, actual_payload)
    return {
        "path": str(file_path),
        "action": action,
        "dry_run": dry_run,
        "change": change,
        "output_binding": output_binding,
        "input_binding": input_binding,
    }


def _render_existing_context(
    file_path: Path,
    content: str,
    new_section: str,
    re_module,
) -> tuple[str, str, dict[str, Any] | None]:
    """Render an existing context file without performing filesystem writes."""
    original_content = content

    # Pre-emptive strike: remove redundant handoff blocks that were previously stacked
    # outside the auto-managed block. This heals files from the non-idempotent bug.
    # We remove ALL instances from the existing content; the new sync will re-inject
    # exactly one instance inside the AUTO markers.
    # We stop before the next header, the AUTO_END marker, or end of string.
    handoff_pattern = (
        r"\n+## Active Handoff Protocol.*?(?=\n+##|"
        + re_module.escape(AUTO_END)
        + r"|$)"
    )
    content = re_module.sub(handoff_pattern, "", content, flags=re_module.DOTALL)

    # Heal stale error lines injected without AUTO markers (pre-fix accumulation)
    error_pattern = r"\n*<!-- ERROR: (?:Organ|Repo) '[^']+' not found -->"
    content = re_module.sub(error_pattern, "", content)

    # Clean up any trailing whitespace left by the removal
    content = content.strip()

    if AUTO_START in content and AUTO_END in content:
        # Replace existing section. Using greedy match '.*' instead of '.*?' to ensure
        # that if multiple START/END blocks exist, the entire range is collapsed.
        pattern = re_module.escape(AUTO_START) + r".*" + re_module.escape(AUTO_END)
        match = re_module.search(pattern, content, flags=re_module.DOTALL)
        old_section = match.group(0) if match else ""
        new_content = re_module.sub(
            pattern,
            new_section,
            content,
            flags=re_module.DOTALL,
        )
        healing_changed_content = content != original_content.strip()
        if new_content == content and not healing_changed_content:
            return "unchanged", original_content, None
        timestamp_pattern = (
            r"(?m)^\*Last synced: "
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\*$"
        )
        if (
            not healing_changed_content
            and re_module.sub(timestamp_pattern, "*Last synced: <semantic>*", new_content)
            == re_module.sub(timestamp_pattern, "*Last synced: <semantic>*", content)
        ):
            return "unchanged", original_content, None
        return (
            "updated",
            new_content,
            _build_change_record(file_path, "updated", old_section, new_section),
        )

    # Append to end
    rendered = content.rstrip() + "\n\n" + new_section + "\n"
    return (
        "updated",
        rendered,
        _build_change_record(file_path, "updated", "", new_section),
    )


def _capture_custody_root_identity(custody_root: Path) -> dict[str, int]:
    """Capture the real workspace directory identity through a no-follow fd."""
    root = custody_root.resolve(strict=True)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(root, flags)
    try:
        opened = os.fstat(descriptor)
        live = root.stat(follow_symlinks=False)
        if not stat.S_ISDIR(opened.st_mode) or (
            opened.st_dev,
            opened.st_ino,
        ) != (live.st_dev, live.st_ino):
            raise RuntimeError("receipted workspace changed while binding its root")
        return {"device": opened.st_dev, "inode": opened.st_ino}
    finally:
        os.close(descriptor)


def _open_custody_parent(
    file_path: Path,
    custody_root: Path,
    *,
    expected_root_identity: dict[str, int] | None = None,
) -> tuple[int, str, str]:
    """Open a contained, symlink-free output parent for descriptor-relative I/O."""
    root = custody_root.resolve(strict=True)
    lexical_target = file_path.absolute()
    if ".." in file_path.parts:
        raise RuntimeError(f"context output contains a parent traversal: {file_path}")
    try:
        lexical_relative = lexical_target.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(
            f"context output is outside the receipted workspace: {lexical_target}",
        ) from exc
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    root_status = root.stat(follow_symlinks=False)
    parent_fd = os.open(root, flags)
    opened_root_status = os.fstat(parent_fd)
    if (opened_root_status.st_dev, opened_root_status.st_ino) != (
        root_status.st_dev,
        root_status.st_ino,
    ):
        os.close(parent_fd)
        raise RuntimeError("receipted workspace changed while opening its root")
    if expected_root_identity is not None and (
        opened_root_status.st_dev,
        opened_root_status.st_ino,
    ) != (
        expected_root_identity.get("device"),
        expected_root_identity.get("inode"),
    ):
        os.close(parent_fd)
        raise RuntimeError("receipted workspace root changed after input binding")
    try:
        for component in lexical_relative.parts[:-1]:
            try:
                child_fd = os.open(component, flags, dir_fd=parent_fd)
            except OSError as exc:
                raise RuntimeError(
                    "context output parent is not a real in-workspace directory: "
                    f"{component}",
                ) from exc
            os.close(parent_fd)
            parent_fd = child_fd
        try:
            target_status = os.stat(
                lexical_target.name,
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            target_status = None
        if target_status is not None and stat.S_ISLNK(target_status.st_mode):
            raise RuntimeError(f"context output cannot be a symlink: {file_path}")
    except Exception:
        os.close(parent_fd)
        raise
    return parent_fd, lexical_target.name, lexical_relative.as_posix()


def _preflight_context_outputs(
    *,
    workspace: Path,
    registry: dict,
    target_organs: list[str],
    extra_roots: list[Path],
    organ_directory_map: dict[str, str],
    workspace_identity: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Reject unsafe targets and bind every preimage before the first write."""
    targets = [workspace / name for name in ("CLAUDE.md", "GEMINI.md", "AGENTS.md")]
    for organ_key in target_organs:
        organ_name = organ_directory_map.get(organ_key)
        if not _safe_path_component(organ_name):
            if organ_name:
                raise RuntimeError(f"invalid organ directory component: {organ_name}")
            continue
        assert isinstance(organ_name, str)
        organ_path = workspace / organ_name
        if organ_path.is_dir():
            targets.extend(
                organ_path / name for name in ("CLAUDE.md", "GEMINI.md", "AGENTS.md")
            )
        organ_data = registry.get("organs", {}).get(organ_key, {})
        for repo_entry in organ_data.get("repositories", []):
            repo_name = repo_entry.get("name")
            if not _safe_path_component(repo_name):
                if repo_name:
                    raise RuntimeError(f"invalid repository path component: {repo_name}")
                continue
            candidates = [organ_path / repo_name]
            candidates.extend(root / repo_name for root in extra_roots)
            for repo_path in candidates:
                if not repo_path.is_dir():
                    continue
                targets.extend(
                    repo_path / name
                    for name in ("CLAUDE.md", "GEMINI.md", "AGENTS.md")
                )
    bindings: list[dict[str, Any]] = []
    for target in sorted(set(targets), key=_lexical_absolute):
        parent_fd, filename, label = _open_custody_parent(
            target,
            workspace,
            expected_root_identity=workspace_identity,
        )
        try:
            payload = _read_custody_payload(parent_fd, filename)
            parent_identity = _custody_parent_identity(parent_fd)
        finally:
            os.close(parent_fd)
        if payload is None:
            bindings.append(
                {
                    "path": label,
                    "state": "absent",
                    "parent_identity": parent_identity,
                },
            )
        else:
            bindings.append(
                {
                    **_payload_binding(label, payload),
                    "state": "present",
                    "parent_identity": parent_identity,
                },
            )
    return bindings


def _raise_after_receipted_rollback(
    message: str,
    *,
    workspace: Path,
    target_preimages: list[dict[str, Any]],
    expected_output_bindings: list[dict[str, str | int]],
    workspace_identity: dict[str, int] | None,
) -> None:
    """Restore every published context target before reporting late input drift."""
    try:
        _restore_receipted_context_outputs(
            workspace=workspace,
            target_preimages=target_preimages,
            expected_output_bindings=expected_output_bindings,
            workspace_identity=workspace_identity,
        )
    except Exception as exc:
        raise RuntimeError(f"{message}; context output rollback failed: {exc}") from exc
    raise RuntimeError(message)


def _restore_receipted_context_outputs(
    *,
    workspace: Path,
    target_preimages: list[dict[str, Any]],
    expected_output_bindings: list[dict[str, str | int]],
    workspace_identity: dict[str, int] | None,
) -> None:
    """Restore preflight bytes without overwriting a concurrent public edit."""
    preimages = {str(binding["path"]): binding for binding in target_preimages}
    outputs = {str(binding["path"]): binding for binding in expected_output_bindings}
    for label in reversed(sorted(outputs)):
        preimage = preimages[label]
        output = outputs[label]
        target = workspace / label
        parent_fd, filename, opened_label = _open_custody_parent(
            target,
            workspace,
            expected_root_identity=workspace_identity,
        )
        try:
            if opened_label != label:
                raise RuntimeError(f"context rollback target identity changed: {label}")
            _require_preflight_parent_identity(parent_fd, label, preimages)
            current_payload = _read_custody_payload(parent_fd, filename)
            if current_payload is None or _payload_binding(label, current_payload) != output:
                raise RuntimeError(
                    f"context output changed before transaction rollback: {label}",
                )
            if preimage.get("state") == "present":
                if _payload_binding(label, current_payload).get("sha256") == preimage.get(
                    "sha256",
                ):
                    continue
                original_payload = _read_preimage_from_custody(
                    workspace=workspace,
                    output_label=label,
                    parent_fd=parent_fd,
                    preimage=preimage,
                    workspace_identity=workspace_identity,
                )
                _write_custody_payload(
                    parent_fd,
                    filename,
                    original_payload,
                    create_only=False,
                    expected_preimage=current_payload,
                    custody_root=workspace,
                    output_label=label,
                    custody_root_identity=workspace_identity,
                )
            else:
                _remove_created_custody_output(
                    parent_fd=parent_fd,
                    filename=filename,
                    payload=current_payload,
                    custody_root=workspace,
                    output_label=label,
                    custody_root_identity=workspace_identity,
                )
        finally:
            os.close(parent_fd)


def _read_preimage_from_custody(
    *,
    workspace: Path,
    output_label: str,
    parent_fd: int,
    preimage: dict[str, Any],
    workspace_identity: dict[str, int] | None,
) -> bytes:
    """Read and verify the immutable object created for an overwritten preimage."""
    digest = preimage.get("sha256")
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        raise RuntimeError(f"context preimage is missing its digest: {output_label}")
    object_name = f"sha256-{digest.removeprefix('sha256:')}.object"
    journal_fd = _open_custody_journal(
        workspace,
        output_label,
        parent_fd,
        workspace_identity,
    )
    try:
        _lock_custody_journal(journal_fd)
        payload = _read_custody_payload(journal_fd, object_name)
    finally:
        os.close(journal_fd)
    if payload is None or _payload_binding(output_label, payload).get("sha256") != digest:
        raise RuntimeError(f"context preimage custody object is unavailable: {output_label}")
    return payload


def _remove_created_custody_output(
    *,
    parent_fd: int,
    filename: str,
    payload: bytes,
    custody_root: Path,
    output_label: str,
    custody_root_identity: dict[str, int] | None,
) -> None:
    """Retire one transaction-created public file through the custody journal."""
    source_fd: int | None = None
    capture_name: str | None = None
    capture_identity: tuple[int, int] | None = None
    journal_fd = _open_custody_journal(
        custody_root,
        output_label,
        parent_fd,
        custody_root_identity,
    )
    try:
        _lock_custody_journal(journal_fd)
        _reap_custody_transactions(journal_fd)
        _assert_custody_parent_is_live(
            parent_fd,
            filename,
            output_label,
            custody_root,
            custody_root_identity,
        )
        source_fd = os.open(filename, _custody_read_flags(), dir_fd=parent_fd)
        opened = os.fstat(source_fd)
        if not stat.S_ISREG(opened.st_mode) or (
            _read_open_custody_payload(source_fd, filename) != payload
        ):
            raise RuntimeError(f"context output changed before removal: {output_label}")
        _ensure_custody_object(journal_fd, payload)
        live = os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
        if (live.st_dev, live.st_ino) != (opened.st_dev, opened.st_ino):
            raise RuntimeError(f"context output identity changed before removal: {output_label}")
        capture_name = f"transaction-{secrets.token_hex(24)}.rollback"
        os.rename(
            filename,
            capture_name,
            src_dir_fd=parent_fd,
            dst_dir_fd=journal_fd,
        )
        capture_status = os.stat(
            capture_name,
            dir_fd=journal_fd,
            follow_symlinks=False,
        )
        capture_identity = (capture_status.st_dev, capture_status.st_ino)
        captured_payload = _read_custody_payload(journal_fd, capture_name)
        if capture_identity != (opened.st_dev, opened.st_ino) or captured_payload != payload:
            _restore_journal_capture(
                parent_fd,
                journal_fd,
                filename,
                capture_name,
                capture_identity,
                captured_payload,
            )
            capture_name = None
            raise RuntimeError(f"context output changed at rollback boundary: {output_label}")
        os.fsync(parent_fd)
        _remove_private_journal_alias(
            journal_fd,
            capture_name,
            capture_identity,
            payload,
        )
        capture_name = None
        os.fsync(journal_fd)
    except Exception:
        if capture_name is not None and capture_identity is not None:
            captured_payload = _read_custody_payload(journal_fd, capture_name)
            _restore_journal_capture(
                parent_fd,
                journal_fd,
                filename,
                capture_name,
                capture_identity,
                captured_payload,
            )
        raise
    finally:
        if source_fd is not None:
            os.close(source_fd)
        os.close(journal_fd)


def _safe_path_component(value: object) -> bool:
    """Return whether registry-driven path input is exactly one safe basename."""
    return (
        isinstance(value, str)
        and value not in {"", ".", ".."}
        and "/" not in value
        and "\\" not in value
        and Path(value).name == value
    )


def _registry_organ_directory_map(
    registry: dict[str, Any],
    organ_keys: list[str] | None = None,
) -> dict[str, str]:
    """Derive receipted output roots only for the selected registry organs."""
    mapping: dict[str, str] = {}
    claimed: dict[str, str] = {}
    registry_organs = registry.get("organs", {})
    selected_keys = list(registry_organs) if organ_keys is None else organ_keys
    for raw_key in selected_keys:
        if raw_key not in registry_organs:
            continue
        organ = registry_organs[raw_key]
        key = str(raw_key)
        candidates = {
            value
            for value in (
                organ.get("directory"),
                organ.get("dir"),
                organ.get("github_org"),
                organ.get("org"),
            )
            if _safe_path_component(value)
        }
        candidates.update(
            repo.get("org")
            for repo in organ.get("repositories", [])
            if _safe_path_component(repo.get("org"))
        )
        if len(candidates) != 1:
            raise RuntimeError(
                "receipted context sync requires one registry-bound directory "
                f"for {key}; found {sorted(candidates)}",
            )
        directory = candidates.pop()
        assert isinstance(directory, str)
        previous = claimed.setdefault(directory, key)
        if previous != key:
            raise RuntimeError(
                "receipted context sync rejects a shared organ directory: "
                f"{directory} ({previous}, {key})",
            )
        mapping[key] = directory
    return mapping


def _read_custody_payload(parent_fd: int, filename: str) -> bytes | None:
    """Read one stable regular output through its already validated parent."""
    flags = _custody_read_flags()
    try:
        descriptor = os.open(filename, flags, dir_fd=parent_fd)
    except FileNotFoundError:
        return None
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise RuntimeError(f"context output is not a regular file: {filename}")
        chunks: list[bytes] = []
        total = 0
        while chunk := os.read(descriptor, 128 * 1024):
            total += len(chunk)
            if total > MAX_CONTEXT_OUTPUT_BYTES:
                raise RuntimeError(f"context output exceeds size limit: {filename}")
            chunks.append(chunk)
        after = os.fstat(descriptor)
        current = os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
    finally:
        os.close(descriptor)
    stable_fields = (
        "st_dev",
        "st_ino",
        "st_mode",
        "st_size",
        "st_mtime_ns",
        "st_ctime_ns",
    )
    if (
        total != before.st_size
        or (current.st_dev, current.st_ino) != (before.st_dev, before.st_ino)
        or any(
            getattr(before, field) != getattr(after, field)
            or getattr(before, field) != getattr(current, field)
            for field in stable_fields
        )
    ):
        raise RuntimeError(f"context output changed while reading: {filename}")
    return b"".join(chunks)


def _custody_read_flags() -> int:
    """Return no-follow, nonblocking flags for an untrusted regular-file read."""
    return (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )


def _custody_parent_identity(parent_fd: int) -> dict[str, int]:
    """Return the stable directory identity used by an output binding."""
    status = os.fstat(parent_fd)
    if not stat.S_ISDIR(status.st_mode):
        raise RuntimeError("context output parent is not a directory")
    return {"device": status.st_dev, "inode": status.st_ino}


def _require_preflight_parent_identity(
    parent_fd: int,
    output_label: str,
    expected_input_bindings: dict[str, dict[str, Any]] | None,
) -> None:
    """Require an output parent to match its preflight inode, even if absent."""
    if expected_input_bindings is None:
        return
    expected = expected_input_bindings.get(output_label)
    if expected is None:
        raise RuntimeError(
            f"context target was not bound during preflight: {output_label}",
        )
    expected_parent = expected.get("parent_identity")
    if expected_parent != _custody_parent_identity(parent_fd):
        raise RuntimeError(
            f"context output parent changed after receipted preflight: {output_label}",
        )


def _bind_unchanged_custody_payload(
    *,
    parent_fd: int,
    filename: str,
    payload: bytes,
    custody_root: Path,
    output_label: str,
    custody_root_identity: dict[str, int] | None,
) -> None:
    """Durably CAS-bind a pre-existing output without rewriting public bytes."""
    journal_fd = _open_custody_journal(
        custody_root,
        output_label,
        parent_fd,
        custody_root_identity,
    )
    try:
        _lock_custody_journal(journal_fd)
        _reap_custody_transactions(journal_fd)
        _assert_custody_parent_is_live(
            parent_fd,
            filename,
            output_label,
            custody_root,
            custody_root_identity,
        )
        if _read_custody_payload(parent_fd, filename) != payload:
            raise RuntimeError(
                f"unchanged context output changed before CAS binding: {output_label}",
            )
        _ensure_custody_object(journal_fd, payload)
        os.fsync(journal_fd)
    finally:
        os.close(journal_fd)


def _write_custody_payload(
    parent_fd: int,
    filename: str,
    payload: bytes,
    *,
    create_only: bool,
    expected_preimage: bytes | None,
    custody_root: Path,
    output_label: str,
    custody_root_identity: dict[str, int] | None = None,
) -> None:
    """Install bytes through a bounded, content-addressed custody journal.

    Cooperating writers serialize through the private journal lock. Observed
    regular replacements within ``MAX_CONTEXT_OUTPUT_BYTES`` are restored and
    CAS-bound. An uncooperative non-regular or oversized replacement injected
    in the final public-name syscall is retained privately when possible and
    aborts the operation; it can never produce a success receipt. Once generated
    bytes have become public, failure handling never mutates that public name.
    """
    source_fd: int | None = None
    journal_fd = _open_custody_journal(
        custody_root,
        output_label,
        parent_fd,
        custody_root_identity,
    )
    staging_name: str | None = None
    staging_identity: tuple[int, int] | None = None
    backup_name: str | None = None
    backup_identity: tuple[int, int] | None = None
    published = False
    try:
        _lock_custody_journal(journal_fd)
        _reap_custody_transactions(journal_fd)
        _assert_custody_parent_is_live(
            parent_fd,
            filename,
            output_label,
            custody_root,
            custody_root_identity,
        )
        if not create_only:
            if expected_preimage is None:
                raise RuntimeError(
                    f"context update is missing its expected preimage: {filename}",
                )
            source_flags = _custody_read_flags()
            source_fd = os.open(filename, source_flags, dir_fd=parent_fd)
            if not stat.S_ISREG(os.fstat(source_fd).st_mode):
                raise RuntimeError(f"context output is not a regular file: {filename}")
            if _read_open_custody_payload(source_fd, filename) != expected_preimage:
                raise RuntimeError(f"context output changed after rendering: {filename}")
            _ensure_custody_object(journal_fd, expected_preimage)

        generated_object = _ensure_custody_object(journal_fd, payload)
        staging_name, staging_identity = _create_custody_staging(
            journal_fd,
            payload,
            source_fd,
        )

        if create_only:
            _assert_custody_parent_is_live(
                parent_fd,
                filename,
                output_label,
                custody_root,
                custody_root_identity,
            )
        else:
            assert source_fd is not None
            assert expected_preimage is not None
            if _read_open_custody_payload(source_fd, filename) != expected_preimage:
                raise RuntimeError(f"context output changed before replacement: {filename}")
            current = os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
            opened = os.fstat(source_fd)
            if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
                raise RuntimeError(
                    f"context output identity changed before replacement: {filename}",
                )
            _assert_custody_parent_is_live(
                parent_fd,
                filename,
                output_label,
                custody_root,
                custody_root_identity,
            )
            backup_name = f"transaction-{secrets.token_hex(24)}.preimage"
            os.rename(
                filename,
                backup_name,
                src_dir_fd=parent_fd,
                dst_dir_fd=journal_fd,
            )
            backup_status = os.stat(
                backup_name,
                dir_fd=journal_fd,
                follow_symlinks=False,
            )
            backup_identity = (backup_status.st_dev, backup_status.st_ino)
            backup_payload = _read_custody_payload(journal_fd, backup_name)
            if backup_identity != (opened.st_dev, opened.st_ino) or (
                backup_payload != expected_preimage
            ):
                _restore_journal_capture(
                    parent_fd,
                    journal_fd,
                    filename,
                    backup_name,
                    backup_identity,
                    backup_payload,
                )
                backup_name = None
                raise RuntimeError(
                    f"context output changed at commit boundary: {filename}",
                )

        os.link(
            staging_name,
            filename,
            src_dir_fd=journal_fd,
            dst_dir_fd=parent_fd,
            follow_symlinks=False,
        )
        published = True
        # Retire the only private transaction alias immediately. From this point
        # onward the public name is never renamed or unlinked during cleanup.
        assert staging_identity is not None
        _remove_private_journal_alias(
            journal_fd,
            staging_name,
            staging_identity,
            None,
        )
        staging_name = None
        os.fsync(journal_fd)
        _assert_custody_parent_is_live(
            parent_fd,
            filename,
            output_label,
            custody_root,
            custody_root_identity,
        )
        os.fsync(parent_fd)
        _assert_custody_parent_is_live(
            parent_fd,
            filename,
            output_label,
            custody_root,
            custody_root_identity,
        )
        live = os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
        if staging_identity != (live.st_dev, live.st_ino) or (
            _read_custody_payload(parent_fd, filename) != payload
        ):
            raise RuntimeError(f"context output changed after installation: {filename}")

        if backup_name is not None and backup_identity is not None:
            _remove_private_journal_alias(
                journal_fd,
                backup_name,
                backup_identity,
                expected_preimage,
            )
            backup_name = None
        os.fsync(journal_fd)
        # The object itself is content-addressed, reused, and lives outside the
        # visible worktree whenever a Git admin directory is available.
        assert generated_object == _custody_object_name(payload)
    except Exception as publication_error:
        cleanup_error: Exception | None = None
        published_binding: dict[str, str | int] | None = None
        if published:
            try:
                published_binding = _bind_live_custody_effect(
                    parent_fd,
                    filename,
                    output_label,
                    journal_fd,
                )
            except Exception as exc:
                cleanup_error = RuntimeError(
                    "uncooperative non-regular or oversized context replacement "
                    "remains at the public path and cannot be receipted",
                )
                cleanup_error.__cause__ = exc
            if backup_name is not None and backup_identity is not None:
                try:
                    assert expected_preimage is not None
                    _remove_private_journal_alias(
                        journal_fd,
                        backup_name,
                        backup_identity,
                        expected_preimage,
                    )
                except Exception as exc:
                    if cleanup_error is None:
                        cleanup_error = exc
                else:
                    backup_name = None
        elif backup_name is not None and backup_identity is not None:
            try:
                backup_payload = _read_custody_payload(journal_fd, backup_name)
                _restore_journal_capture(
                    parent_fd,
                    journal_fd,
                    filename,
                    backup_name,
                    backup_identity,
                    backup_payload,
                )
            except Exception as exc:
                cleanup_error = RuntimeError(
                    "uncooperative non-regular or oversized context replacement "
                    "was retained in the private custody journal; no success "
                    "receipt was emitted",
                )
                cleanup_error.__cause__ = exc
            else:
                backup_name = None
        if staging_name is not None and staging_identity is not None:
            try:
                _remove_private_journal_alias(
                    journal_fd,
                    staging_name,
                    staging_identity,
                    None,
                )
            except Exception as exc:
                if cleanup_error is None:
                    cleanup_error = exc
        if cleanup_error is not None:
            raise cleanup_error from publication_error
        if published_binding is not None:
            raise ContextCustodyPublicationError(
                "context publication failed after a CAS-bound output became public",
                published_binding,
            ) from publication_error
        raise
    finally:
        if source_fd is not None:
            os.close(source_fd)
        os.close(journal_fd)


def _custody_object_name(payload: bytes) -> str:
    return f"sha256-{hashlib.sha256(payload).hexdigest()}.object"


def _ensure_custody_object(journal_fd: int, payload: bytes) -> str:
    """Create or verify one immutable content-addressed journal object."""
    name = _custody_object_name(payload)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(name, flags, 0o600, dir_fd=journal_fd)
    except FileExistsError:
        status = os.stat(name, dir_fd=journal_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(status.st_mode)
            or stat.S_IMODE(status.st_mode) != 0o400
            or status.st_nlink != 1
        ):
            raise RuntimeError(f"custody object mode is not immutable: {name}") from None
        existing = _read_custody_payload(journal_fd, name)
        if existing != payload:
            raise RuntimeError(
                f"custody object digest collision or corruption: {name}",
            ) from None
        return name
    try:
        offset = 0
        while offset < len(payload):
            offset += os.write(descriptor, payload[offset:])
        os.fchmod(descriptor, 0o400)
        os.fsync(descriptor)
        created = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    os.fsync(journal_fd)
    live = os.stat(name, dir_fd=journal_fd, follow_symlinks=False)
    if (
        (live.st_dev, live.st_ino) != (created.st_dev, created.st_ino)
        or stat.S_IMODE(live.st_mode) != 0o400
        or live.st_nlink != 1
        or _read_custody_payload(journal_fd, name) != payload
    ):
        raise RuntimeError(f"custody object changed during publication: {name}")
    return name


def _create_custody_staging(
    journal_fd: int,
    payload: bytes,
    source_fd: int | None,
) -> tuple[str, tuple[int, int]]:
    """Create a private transaction inode separate from the durable CAS object."""
    name = f"transaction-{secrets.token_hex(24)}.generated"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(name, flags, 0o644, dir_fd=journal_fd)
    try:
        if source_fd is not None:
            _copy_custody_metadata(source_fd, descriptor)
        else:
            os.fchmod(descriptor, 0o644)
        offset = 0
        while offset < len(payload):
            offset += os.write(descriptor, payload[offset:])
        os.fsync(descriptor)
        status = os.fstat(descriptor)
        return name, (status.st_dev, status.st_ino)
    finally:
        os.close(descriptor)


def _remove_private_journal_alias(
    journal_fd: int,
    name: str,
    expected_identity: tuple[int, int],
    expected_payload: bytes | None,
) -> None:
    """Remove an engine-private random alias after CAS-backed verification.

    The journal directory is a private capability namespace. Concurrent writers
    are supported on public output names, but mutation of a 192-bit transaction
    alias inside that private directory is outside the custody threat contract.
    ``expected_payload=None`` is reserved for a generated staging alias whose
    immutable payload object was already made durable; identity-only retirement
    prevents a public in-place edit from poisoning the private transaction queue.
    """
    if not CUSTODY_TRANSACTION_ALIAS.fullmatch(name):
        raise RuntimeError(f"refusing to remove non-transaction custody path: {name}")
    status = os.stat(name, dir_fd=journal_fd, follow_symlinks=False)
    if (status.st_dev, status.st_ino) != expected_identity:
        raise RuntimeError(f"private custody alias identity changed: {name}")
    if expected_payload is not None and (
        _read_custody_payload(journal_fd, name) != expected_payload
    ):
        raise RuntimeError(f"private custody alias bytes changed: {name}")
    os.unlink(name, dir_fd=journal_fd)


def _reap_custody_transactions(journal_fd: int) -> None:
    """CAS-bind and remove private aliases left by an interrupted writer."""
    for name in sorted(os.listdir(journal_fd)):
        if not CUSTODY_TRANSACTION_ALIAS.fullmatch(name):
            continue
        payload = _read_custody_payload(journal_fd, name)
        if payload is None:
            continue
        status = os.stat(name, dir_fd=journal_fd, follow_symlinks=False)
        identity = (status.st_dev, status.st_ino)
        _ensure_custody_object(journal_fd, payload)
        _remove_private_journal_alias(journal_fd, name, identity, payload)
    os.fsync(journal_fd)


def _lock_custody_journal(journal_fd: int) -> None:
    """Serialize cooperating custody writers through the opened CAS directory."""
    try:
        import fcntl

        fcntl.flock(journal_fd, fcntl.LOCK_EX)
    except (ImportError, OSError) as exc:
        raise RuntimeError("cannot lock context custody journal") from exc


def _bind_live_custody_effect(
    parent_fd: int,
    filename: str,
    output_label: str,
    journal_fd: int,
) -> dict[str, str | int] | None:
    """CAS-bind a stable regular public effect without mutating its pathname."""
    payload = _read_custody_payload(parent_fd, filename)
    if payload is None:
        return None
    _ensure_custody_object(journal_fd, payload)
    return _payload_binding(output_label, payload)


def _restore_journal_capture(
    parent_fd: int,
    journal_fd: int,
    filename: str,
    capture_name: str,
    capture_identity: tuple[int, int],
    capture_payload: bytes | None,
) -> bool:
    """Make a captured concurrent value live again, without overwriting a name."""
    if capture_payload is None:
        raise RuntimeError(f"custody recovery capture is missing: {capture_name}")
    _ensure_custody_object(journal_fd, capture_payload)
    try:
        os.link(
            capture_name,
            filename,
            src_dir_fd=journal_fd,
            dst_dir_fd=parent_fd,
            follow_symlinks=False,
        )
    except FileExistsError:
        restored = False
    else:
        restored = True
    _remove_private_journal_alias(
        journal_fd,
        capture_name,
        capture_identity,
        capture_payload,
    )
    return restored


def _open_custody_journal(
    custody_root: Path,
    output_label: str,
    output_parent_fd: int,
    custody_root_identity: dict[str, int] | None,
    *,
    create: bool = True,
) -> int:
    """Open a same-device CAS in the nearest real Git admin directory."""
    root = custody_root.resolve(strict=True)
    target_parent = (root / Path(output_label)).parent
    candidate = target_parent
    while True:
        git_admin = candidate / ".git"
        try:
            git_status = git_admin.lstat()
        except FileNotFoundError:
            git_status = None
        if git_status is not None:
            git_fd = _open_git_admin_directory(
                git_admin,
                git_status,
                custody_root,
                custody_root_identity,
            )
            if git_fd is None:
                raise RuntimeError(
                    f"cannot bind Git admin directory for custody journal: {git_admin}",
                )
            try:
                if (
                    os.fstat(git_fd).st_dev == os.fstat(output_parent_fd).st_dev
                ):
                    return _open_or_create_journal_directory(git_fd, create=create)
            finally:
                os.close(git_fd)
            raise RuntimeError(
                "Git admin custody journal crosses a filesystem boundary",
            )
        if candidate == root:
            break
        candidate = candidate.parent

    # Non-Git workspaces have no status surface to dirty. Keep a single hidden,
    # content-addressed fallback at the workspace root (or output parent mount).
    root_fd, _name, _label = _open_custody_parent(
        root / ".journal-anchor",
        custody_root,
        expected_root_identity=custody_root_identity,
    )
    if os.fstat(root_fd).st_dev != os.fstat(output_parent_fd).st_dev:
        os.close(root_fd)
        root_fd = os.dup(output_parent_fd)
    try:
        return _open_or_create_journal_directory(
            root_fd,
            directory_name=".organvm-context-cas",
            create=create,
        )
    finally:
        os.close(root_fd)


def _open_or_create_journal_directory(
    base_fd: int,
    *,
    directory_name: str = "organvm-context-cas",
    create: bool = True,
) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    if create:
        try:
            os.mkdir(directory_name, 0o700, dir_fd=base_fd)
        except FileExistsError:
            pass
        else:
            os.fsync(base_fd)
    try:
        journal_fd = os.open(directory_name, flags, dir_fd=base_fd)
    except OSError as exc:
        raise RuntimeError("context custody journal is not a real directory") from exc
    if os.fstat(journal_fd).st_dev != os.fstat(base_fd).st_dev:
        os.close(journal_fd)
        raise RuntimeError("context custody journal crosses a filesystem boundary")
    journal_status = os.fstat(journal_fd)
    if stat.S_IMODE(journal_status.st_mode) != 0o700 or (
        hasattr(os, "geteuid") and journal_status.st_uid != os.geteuid()
    ):
        os.close(journal_fd)
        raise RuntimeError("context custody journal is not private to this user")
    return journal_fd


def _open_git_admin_directory(
    git_path: Path,
    git_status: os.stat_result,
    custody_root: Path,
    custody_root_identity: dict[str, int] | None,
) -> int | None:
    """Open a real Git admin directory, including linked-worktree gitfiles."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    if stat.S_ISDIR(git_status.st_mode):
        descriptor, _name, _label = _open_custody_parent(
            git_path / ".journal-anchor",
            custody_root,
            expected_root_identity=custody_root_identity,
        )
        return descriptor
    if not stat.S_ISREG(git_status.st_mode) or git_status.st_size > 4096:
        return None
    read_flags = _custody_read_flags()
    descriptor = os.open(git_path, read_flags)
    try:
        before = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (git_status.st_dev, git_status.st_ino):
            raise RuntimeError("Git admin gitfile changed during journal binding")
        payload = b""
        while chunk := os.read(descriptor, 4096 - len(payload) + 1):
            payload += chunk
            if len(payload) > 4096:
                raise RuntimeError("Git admin gitfile exceeds size limit")
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    live_gitfile = git_path.lstat()
    stable_fields = (
        "st_dev",
        "st_ino",
        "st_mode",
        "st_size",
        "st_mtime_ns",
        "st_ctime_ns",
    )
    if len(payload) != before.st_size or any(
        getattr(before, field) != getattr(after, field)
        or getattr(before, field) != getattr(live_gitfile, field)
        for field in stable_fields
    ):
        raise RuntimeError("Git admin gitfile changed during journal binding")
    try:
        line = payload.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise RuntimeError("Git admin gitfile is not UTF-8") from exc
    if not line.startswith("gitdir: "):
        return None
    raw_admin = Path(line.removeprefix("gitdir: "))
    admin = raw_admin if raw_admin.is_absolute() else git_path.parent / raw_admin
    admin = admin.resolve(strict=True)
    live = admin.stat(follow_symlinks=False)
    admin_fd = os.open(admin, flags)
    opened_admin = os.fstat(admin_fd)
    if not stat.S_ISDIR(opened_admin.st_mode) or (
        opened_admin.st_dev,
        opened_admin.st_ino,
    ) != (live.st_dev, live.st_ino):
        os.close(admin_fd)
        raise RuntimeError("Git admin directory changed during journal binding")
    return admin_fd


def _assert_custody_parent_is_live(
    parent_fd: int,
    filename: str,
    output_label: str,
    custody_root: Path,
    custody_root_identity: dict[str, int] | None = None,
) -> None:
    """Require an opened output parent to remain at its bound workspace path."""
    live_target = custody_root / Path(output_label)
    live_fd, live_filename, live_label = _open_custody_parent(
        live_target,
        custody_root,
        expected_root_identity=custody_root_identity,
    )
    try:
        opened = os.fstat(parent_fd)
        live = os.fstat(live_fd)
        if (
            live_filename != filename
            or live_label != output_label
            or (opened.st_dev, opened.st_ino) != (live.st_dev, live.st_ino)
        ):
            raise RuntimeError(
                f"context output parent moved outside custody: {output_label}",
            )
    finally:
        os.close(live_fd)


def _read_open_custody_payload(descriptor: int, filename: str) -> bytes:
    """Read and bind an already opened output without trusting its path again."""
    os.lseek(descriptor, 0, os.SEEK_SET)
    before = os.fstat(descriptor)
    chunks: list[bytes] = []
    total = 0
    while chunk := os.read(descriptor, 128 * 1024):
        total += len(chunk)
        if total > MAX_CONTEXT_OUTPUT_BYTES:
            raise RuntimeError(f"context output exceeds size limit: {filename}")
        chunks.append(chunk)
    after = os.fstat(descriptor)
    stable_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    if total != before.st_size or any(
        getattr(before, field) != getattr(after, field) for field in stable_fields
    ):
        raise RuntimeError(f"context output changed while reading: {filename}")
    return b"".join(chunks)


def _copy_custody_metadata(source_fd: int, target_fd: int) -> None:
    """Preserve mode and extended ACL/xattr metadata on atomic replacement."""
    os.fchmod(target_fd, stat.S_IMODE(os.fstat(source_fd).st_mode))
    if not all(hasattr(os, name) for name in ("listxattr", "getxattr", "setxattr")):
        return
    attributes = os.listxattr(source_fd)
    for name in attributes:
        value = os.getxattr(source_fd, name)
        os.setxattr(target_fd, name, value)


def _payload_binding(path: str, payload: bytes) -> dict[str, str | int]:
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    return {
        "path": path,
        "bytes": len(payload),
        "sha256": digest,
        "journal_object": digest,
    }


def _receipt_path_label(path: Path, workspace: Path) -> str:
    """Return a deterministic lexical label for an in-workspace invocation root."""
    absolute = _lexical_absolute(path)
    root = _lexical_absolute(workspace)
    try:
        relative = absolute.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(f"receipt invocation root is outside workspace: {path}") from exc
    return relative.as_posix() or "."


def _lexical_absolute(path: Path) -> Path:
    """Normalize dot segments without resolving any filesystem symlink."""
    return Path(os.path.normpath(str(path.expanduser().absolute())))


def _canonical_receipt_digest(bindings: list[dict[str, Any]]) -> str:
    """Digest target preimages using the receipt's canonical JSON encoding."""
    import json

    ordered = sorted(bindings, key=lambda item: str(item.get("path", "")))
    payload = json.dumps(
        ordered,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _record_sync_result(
    res: dict[str, Any],
    updated: list[str],
    created: list[str],
    skipped: list[str],
    changes: list[dict[str, Any]] | None,
    output_bindings: list[dict[str, str | int]] | None = None,
    input_bindings: list[dict[str, Any]] | None = None,
) -> None:
    """Route an injection result into sync counters and changelog entries."""
    action = res["action"]
    path = res["path"]
    if action == "created":
        created.append(path)
    elif action == "updated":
        updated.append(path)
    else:
        skipped.append(path)

    change = res.get("change")
    if change and changes is not None:
        changes.append(change)
    binding = res.get("output_binding")
    if isinstance(binding, dict) and output_bindings is not None:
        output_bindings.append(binding)
    input_binding = res.get("input_binding")
    if isinstance(input_binding, dict) and input_bindings is not None:
        previous = next(
            (
                item
                for item in input_bindings
                if item.get("path") == input_binding.get("path")
            ),
            None,
        )
        if previous is None:
            raise RuntimeError(
                "context target was not bound during receipted preflight: "
                f"{input_binding.get('path')}",
            )
        if previous != input_binding:
            raise RuntimeError(
                "context target preimage changed after receipted preflight: "
                f"{input_binding.get('path')}",
            )


def _record_sync_error(
    error: Exception,
    path: Path,
    errors: list[dict[str, str]],
    output_bindings: list[dict[str, str | int]],
    failed_output_paths: list[Path],
) -> None:
    """Record a failure and retain any regular CAS-bound publication effect."""
    errors.append({"path": str(path), "error": str(error)})
    if not isinstance(error, ContextCustodyPublicationError):
        return
    output_bindings.append(error.output_binding)
    failed_output_paths.append(path)


def _build_change_record(
    file_path: Path,
    action: str,
    old_section: str,
    new_section: str,
) -> dict[str, Any]:
    """Build a compact changelog record for one generated context section."""
    old_lines = old_section.splitlines()
    new_lines = new_section.splitlines()
    diff_lines = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"{file_path}:before",
            tofile=f"{file_path}:after",
            lineterm="",
        ),
    )
    added = sum(
        1
        for line in diff_lines
        if line.startswith("+") and not line.startswith("+++")
    )
    removed = sum(
        1
        for line in diff_lines
        if line.startswith("-") and not line.startswith("---")
    )

    return {
        "path": str(file_path),
        "action": action,
        "added_lines": added,
        "removed_lines": removed,
        "before_hash": _section_hash(old_section),
        "after_hash": _section_hash(new_section),
        "diff": "\n".join(diff_lines),
        "old_section": old_section,
        "new_section": new_section,
    }


def _section_hash(section: str) -> str | None:
    if not section:
        return None
    return hashlib.sha256(section.encode("utf-8")).hexdigest()[:12]
