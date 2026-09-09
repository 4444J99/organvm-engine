"""Durable, machine-readable custody receipts for context synchronization."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import secrets
import stat
import subprocess
import sys
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

CONTEXT_SYNC_RECEIPT_SCHEMA = "organvm.context-sync-receipt.v1"
MAX_RECEIPT_INPUT_BYTES = 16_000_000
GIT_OBJECT_ID = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
SHA256_IDENTITY = re.compile(r"^sha256:[0-9a-f]{64}$")
RECEIPT_TRANSACTION_ALIAS = re.compile(
    r"^transaction-[0-9a-f]{48}\.(?:generated|rollback)$",
)


class ContextSyncReceiptError(RuntimeError):
    """Raised when a context receipt cannot bind all required local evidence."""


class ContextSyncReceiptPublicationError(ContextSyncReceiptError):
    """Receipt installation occurred; matching outputs must not be rolled back."""

    def __init__(self, message: str, path: Path, receipt_sha256: str) -> None:
        super().__init__(message)
        self.receipt_path = str(path)
        self.receipt_sha256 = receipt_sha256


def generator_git_identity(
    repository_root: Path | None = None,
    *,
    allowed_dirty_paths: Iterable[Path | str] = (),
) -> dict[str, str]:
    """Bind the generator to a clean exact Git commit and tree."""
    root = (repository_root or Path(__file__).resolve().parents[3]).resolve(strict=True)
    allowed: set[str] = set()
    for raw_path in allowed_dirty_paths:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = root / candidate
        try:
            allowed.add(candidate.resolve(strict=False).relative_to(root).as_posix())
        except ValueError:
            continue
    unexpected = [
        (status, paths)
        for status, paths in _git_status_entries(root)
        if not paths or any(path not in allowed for path in paths)
    ]
    if unexpected:
        raise ContextSyncReceiptError(
            "generator checkout has tracked or untracked changes; "
            "refusing to attest its HEAD",
        )
    commit = _git(root, "rev-parse", "HEAD")
    tree = _git(root, "rev-parse", f"{commit}^{{tree}}")
    if (
        not GIT_OBJECT_ID.fullmatch(commit)
        or not GIT_OBJECT_ID.fullmatch(tree)
        or len(commit) != len(tree)
    ):
        raise ContextSyncReceiptError("generator Git identity is malformed")
    return {"commit": commit, "tree": tree}


def _git_status_entries(root: Path) -> list[tuple[str, tuple[str, ...]]]:
    """Return NUL-safe porcelain entries, retaining both sides of renames."""
    try:
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "status",
                "--porcelain=v1",
                "-z",
                "--untracked-files=all",
            ],
            check=True,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ContextSyncReceiptError(
            f"cannot resolve generator Git status: {exc}",
        ) from exc
    records = completed.stdout.split(b"\0")
    entries: list[tuple[str, tuple[str, ...]]] = []
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        if len(record) < 4 or record[2:3] != b" ":
            raise ContextSyncReceiptError("generator Git status output is malformed")
        status = record[:2].decode("ascii", errors="strict")
        paths = [record[3:].decode("utf-8", errors="surrogateescape")]
        if "R" in status or "C" in status:
            if index >= len(records) or not records[index]:
                raise ContextSyncReceiptError("generator rename status is incomplete")
            paths.append(records[index].decode("utf-8", errors="surrogateescape"))
            index += 1
        entries.append((status, tuple(paths)))
    return entries


def build_context_sync_receipt(
    *,
    workspace: Path,
    registry_path: Path,
    seed_paths: Iterable[Path],
    remote_references: Iterable[dict[str, str]],
    output_paths: Iterable[Path],
    errors: Iterable[dict[str, str]],
    generator_identity: dict[str, str],
    expected_inputs: dict[str, Any] | None = None,
    expected_output_bindings: Iterable[dict[str, str | int]] | None = None,
    post_generator_identity: dict[str, str] | None = None,
    generated_at: datetime | None = None,
    sop_entries: Iterable[Any] = (),
    render_profile: str = "standard",
    invocation: dict[str, Any] | None = None,
    target_preimages: Iterable[dict[str, Any]] = (),
    workspace_identity: dict[str, int] | None = None,
    registry_validation_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a receipt from locally observable inputs and output bytes only."""
    bound_workspace_identity = _bound_workspace_identity(
        workspace,
        workspace_identity,
    )
    workspace = workspace.resolve(strict=True)
    identity = _validated_generator_identity(generator_identity)
    if post_generator_identity is not None:
        post_identity = _validated_generator_identity(post_generator_identity)
        if post_identity != identity:
            raise ContextSyncReceiptError(
                "generator Git identity changed during context synchronization",
            )
    inputs = bind_context_sync_inputs(
        workspace=workspace,
        registry_path=registry_path,
        seed_paths=seed_paths,
        sop_entries=sop_entries,
        render_profile=render_profile,
        invocation=invocation,
        target_preimages=target_preimages,
        workspace_identity=bound_workspace_identity,
        registry_validation_policy=registry_validation_policy,
    )
    if expected_inputs is not None and inputs != expected_inputs:
        raise ContextSyncReceiptError(
            "context sync input evidence changed during generation",
        )
    preflight_parent_identities = {
        str(binding.get("path", "")): binding.get("parent_identity")
        for binding in inputs.get("target_preimages", [])
        if isinstance(binding, dict) and binding.get("path")
    }
    outputs = sorted(
        (
            _output_binding(
                path,
                workspace,
                bound_workspace_identity,
                expected_parent_identity=preflight_parent_identities.get(
                    _portable_output_path(path, workspace),
                ),
            )
            for path in set(output_paths)
        ),
        key=lambda item: item["path"],
    )
    if expected_output_bindings is not None:
        expected_outputs = sorted(
            (dict(binding) for binding in expected_output_bindings),
            key=lambda item: item.get("path", ""),
        )
        if outputs != expected_outputs:
            raise ContextSyncReceiptError(
                "generated output changed before context receipt publication",
            )
    output_labels = {str(output["path"]) for output in outputs}
    references = sorted(
        (
            _bound_remote_reference(reference, output_labels)
            for reference in remote_references
        ),
        key=lambda item: (
            item.get("output_path", ""),
            item.get("direction", ""),
            item.get("repository", ""),
            item.get("ref", ""),
            item.get("path", ""),
        ),
    )
    error_records = [
        {
            "path": _portable_error_path(str(error.get("path", "")), workspace),
            "error": _portable_error_message(str(error.get("error", "")), workspace),
        }
        for error in errors
    ]
    if not outputs and not error_records:
        raise ContextSyncReceiptError("successful context sync receipt requires output bindings")
    timestamp = generated_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ContextSyncReceiptError("generated_at must be timezone-aware")

    return {
        "schema_version": CONTEXT_SYNC_RECEIPT_SCHEMA,
        "status": "failed" if error_records else "success",
        "generated_at": timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "generator": identity,
        "inputs": {
            **inputs,
        },
        "resolved_remote_references": references,
        "outputs": outputs,
        "errors": error_records,
        "claim_boundary": (
            "This receipt binds local generator/input/output bytes and rendered URLs only; "
            "it does not attest remote availability, branch existence, review, or publication."
        ),
    }


def bind_context_sync_inputs(
    *,
    workspace: Path,
    registry_path: Path,
    seed_paths: Iterable[Path],
    sop_entries: Iterable[Any] = (),
    render_profile: str = "standard",
    invocation: dict[str, Any] | None = None,
    target_preimages: Iterable[dict[str, Any]] = (),
    workspace_identity: dict[str, int] | None = None,
    registry_validation_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Bind exact registry and seed bytes for pre/post generation comparison."""
    bound_workspace_identity = _bound_workspace_identity(
        workspace,
        workspace_identity,
    )
    workspace = workspace.resolve(strict=True)
    registry = _file_binding(
        registry_path,
        label=_portable_input_path(registry_path, workspace),
    )
    seeds = sorted(
        (
            _file_binding(path, label=_portable_input_path(path, workspace))
            for path in set(seed_paths)
        ),
        key=lambda item: item["path"],
    )
    normalized_preimages = sorted(
        (dict(binding) for binding in target_preimages),
        key=lambda item: str(item.get("path", "")),
    )
    return {
        "registry": registry,
        "seeds": seeds,
        "seeds_manifest_sha256": _canonical_digest(seeds),
        "sops": _bind_sop_inputs(sop_entries, workspace),
        "render_profile": render_profile,
        "registry_validation_policy": _registry_validation_policy_evidence(
            registry_validation_policy,
        ),
        "invocation": _canonical_copy(invocation or {}),
        "target_preimages": normalized_preimages,
        "target_preimages_manifest_sha256": _canonical_digest(normalized_preimages),
        "workspace_identity": bound_workspace_identity,
        "runtime": _runtime_identity(),
    }


def capture_context_sync_inputs(
    *,
    workspace: Path,
    registry_path: Path,
    seed_paths: Iterable[Path],
    sop_entries: Iterable[Any] = (),
    render_profile: str = "standard",
    invocation: dict[str, Any] | None = None,
    target_preimages: Iterable[dict[str, Any]] = (),
    workspace_identity: dict[str, int] | None = None,
    registry_validation_policy: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], bytes, dict[Path, bytes]]:
    """Capture the exact bytes that a receipted sync must parse and bind."""
    bound_workspace_identity = _bound_workspace_identity(
        workspace,
        workspace_identity,
    )
    workspace = workspace.resolve(strict=True)
    registry, registry_payload = _read_bound_regular_file(
        registry_path.expanduser(),
        label=_portable_input_path(registry_path, workspace),
        maximum_bytes=MAX_RECEIPT_INPUT_BYTES,
        subject="receipt input",
    )
    seed_payloads: dict[Path, bytes] = {}
    seed_bindings: list[dict[str, str | int]] = []
    for path in set(seed_paths):
        expanded = path.expanduser()
        binding, payload = _read_bound_regular_file(
            expanded,
            label=_portable_input_path(expanded, workspace),
            maximum_bytes=MAX_RECEIPT_INPUT_BYTES,
            subject="receipt input",
        )
        seed_payloads[path] = payload
        seed_bindings.append(binding)
    seeds = sorted(seed_bindings, key=lambda item: item["path"])
    normalized_preimages = sorted(
        (dict(binding) for binding in target_preimages),
        key=lambda item: str(item.get("path", "")),
    )
    inputs = {
        "registry": registry,
        "seeds": seeds,
        "seeds_manifest_sha256": _canonical_digest(seeds),
        "sops": _bind_sop_inputs(sop_entries, workspace),
        "render_profile": render_profile,
        "registry_validation_policy": _registry_validation_policy_evidence(
            registry_validation_policy,
        ),
        "invocation": _canonical_copy(invocation or {}),
        "target_preimages": normalized_preimages,
        "target_preimages_manifest_sha256": _canonical_digest(normalized_preimages),
        "workspace_identity": bound_workspace_identity,
        "runtime": _runtime_identity(),
    }
    return inputs, registry_payload, seed_payloads


def _bind_sop_inputs(entries: Iterable[Any], workspace: Path) -> dict[str, Any]:
    """Bind both exact SOP source bytes and the semantic model used by rendering."""
    semantic_records: list[dict[str, Any]] = []
    document_paths: dict[str, Path] = {}
    document_snapshots: dict[str, dict[str, str | int] | None] = {}
    for entry in entries:
        path = Path(entry.path).expanduser()
        label = _portable_input_path(path, workspace)
        for field in ("org", "repo", "filename", "doc_type", "scope", "phase"):
            if not isinstance(getattr(entry, field), str):
                raise ContextSyncReceiptError(f"SOP metadata {field} must be a string: {label}")
        if entry.phase not in {"genesis", "foundation", "hardening", "graduation", "sustaining", "any"}:
            raise ContextSyncReceiptError(f"SOP metadata phase is unsupported: {label}")
        for field in ("title", "overrides", "sop_name"):
            value = getattr(entry, field)
            if value is not None and not isinstance(value, str):
                raise ContextSyncReceiptError(f"SOP metadata {field} must be a string or null: {label}")
        for field in ("triggers", "complements"):
            value = getattr(entry, field)
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                raise ContextSyncReceiptError(f"SOP metadata {field} must be a string list: {label}")
        record = {
            "path": label,
            "org": str(entry.org),
            "repo": str(entry.repo),
            "filename": str(entry.filename),
            "title": entry.title,
            "doc_type": str(entry.doc_type),
            "canonical": bool(entry.canonical),
            "has_canonical_header": bool(entry.has_canonical_header),
            "scope": str(entry.scope),
            "phase": str(entry.phase),
            "triggers": list(entry.triggers or []),
            "overrides": entry.overrides,
            "complements": list(entry.complements or []),
            "sop_name": entry.sop_name,
        }
        semantic_records.append(record)
        previous = document_paths.setdefault(label, path)
        if previous != path:
            raise ContextSyncReceiptError(
                f"distinct SOP inputs collapse to the same portable path: {label}",
            )
        snapshot: dict[str, str | int] | None = None
        if bool(getattr(entry, "source_snapshot_attempted", False)):
            source_bytes = getattr(entry, "source_bytes", None)
            source_sha256 = getattr(entry, "source_sha256", None)
            if (
                isinstance(source_bytes, bool)
                or not isinstance(source_bytes, int)
                or source_bytes < 0
                or not isinstance(source_sha256, str)
                or not SHA256_IDENTITY.fullmatch(source_sha256)
            ):
                raise ContextSyncReceiptError(
                    f"SOP source snapshot was not captured stably: {label}",
                )
            snapshot = {
                "path": label,
                "bytes": source_bytes,
                "sha256": source_sha256,
            }
        prior_snapshot = document_snapshots.setdefault(label, snapshot)
        if prior_snapshot != snapshot:
            raise ContextSyncReceiptError(
                f"SOP source snapshots disagree for one portable path: {label}",
            )
    semantic_records.sort(
        key=lambda item: (
            str(item["path"]),
            str(item["scope"]),
            str(item["phase"]),
            str(item["sop_name"] or ""),
            str(item["repo"]),
        ),
    )
    if len(semantic_records) != len(
        {json.dumps(record, sort_keys=True, separators=(",", ":")) for record in semantic_records},
    ):
        raise ContextSyncReceiptError("duplicate SOP generation inputs are ambiguous")
    documents: list[dict[str, str | int]] = []
    for label, path in document_paths.items():
        live_binding = _file_binding(path, label=label)
        snapshot = document_snapshots[label]
        if snapshot is not None and live_binding != snapshot:
            raise ContextSyncReceiptError(
                f"SOP source changed after semantic discovery: {label}",
            )
        documents.append(live_binding)
    documents.sort(key=lambda item: item["path"])
    return {
        "documents": documents,
        "entries": semantic_records,
        "manifest_sha256": _canonical_digest(
            {"documents": documents, "entries": semantic_records},
        ),
    }


def bind_context_sync_sops(
    entries: Iterable[Any],
    workspace: Path,
) -> dict[str, Any]:
    """Public pre/post binding for the resolved SOP generation snapshot."""
    return _bind_sop_inputs(entries, workspace.resolve(strict=True))


def _canonical_copy(value: Any) -> Any:
    """Reject non-JSON invocation data and return its canonical value copy."""
    try:
        return json.loads(json.dumps(value, sort_keys=True, separators=(",", ":")))
    except (TypeError, ValueError) as exc:
        raise ContextSyncReceiptError("receipt invocation is not canonical JSON") from exc


def _registry_validation_policy_evidence(
    policy: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return complete, versioned evidence for the enum policy actually used."""
    if policy is None:
        from organvm_engine.registry.validator import (
            capture_registry_validation_policy,
        )

        policy = capture_registry_validation_policy().evidence()
    evidence = _canonical_copy(policy)
    required = {
        "policy_version",
        "source_kind",
        "source_sha256",
        "statuses",
        "revenue_models",
        "revenue_statuses",
        "promotion_states",
        "tiers",
    }
    if not isinstance(evidence, dict) or set(evidence) != required:
        raise ContextSyncReceiptError(
            "registry validation policy evidence is incomplete",
        )
    if evidence["policy_version"] != "organvm.registry-validation-policy.v1":
        raise ContextSyncReceiptError(
            "registry validation policy version is unsupported",
        )
    if evidence["source_kind"] not in {"external-schema", "embedded-fallback"}:
        raise ContextSyncReceiptError(
            "registry validation policy source kind is unsupported",
        )
    if not isinstance(evidence["source_sha256"], str) or not SHA256_IDENTITY.fullmatch(
        evidence["source_sha256"],
    ):
        raise ContextSyncReceiptError(
            "registry validation policy source identity is malformed",
        )
    for key in (
        "statuses",
        "revenue_models",
        "revenue_statuses",
        "promotion_states",
        "tiers",
    ):
        values = evidence[key]
        if (
            not isinstance(values, list)
            or not values
            or any(not isinstance(value, str) or not value for value in values)
            or values != sorted(set(values))
        ):
            raise ContextSyncReceiptError(
                f"registry validation policy {key} is not a canonical string set",
            )
    return evidence


def _runtime_identity() -> dict[str, str]:
    """Bind parser/runtime versions that can affect deterministic input semantics."""
    import yaml

    return {
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "pyyaml_version": str(yaml.__version__),
        "byteorder": sys.byteorder,
    }


def _bound_remote_reference(
    reference: dict[str, str],
    output_labels: set[str],
) -> dict[str, str]:
    """Require each rendered URL record to name a bound generated output."""
    rendered = dict(reference)
    output_path = rendered.get("output_path", "")
    if output_path not in output_labels:
        raise ContextSyncReceiptError(
            "rendered remote reference is not bound to a receipted output: "
            f"{output_path or '<missing>'}",
        )
    return rendered


def write_context_sync_receipt(path: Path, receipt: dict[str, Any]) -> str:
    """Create a receipt from a bounded content-addressed custody object."""
    path = path.expanduser()
    payload = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if len(payload) > MAX_RECEIPT_INPUT_BYTES:
        raise ContextSyncReceiptError("receipt payload exceeds size limit")
    payload_digest = hashlib.sha256(payload).hexdigest()
    try:
        parent_fd, filename = _open_absolute_parent_no_follow(
            path,
            "receipt destination",
            create_parents=True,
        )
    except OSError as exc:
        raise ContextSyncReceiptError(
            f"cannot open receipt destination without following links: {path}",
        ) from exc
    cas_fd: int | None = None
    staging_name: str | None = None
    staging_status: os.stat_result | None = None
    installed = False
    try:
        try:
            os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise ContextSyncReceiptError(f"receipt destination already exists: {path}")
        _assert_absolute_parent_is_live(path, parent_fd, "receipt destination")
        cas_fd = _open_receipt_cas(path, parent_fd)
        _assert_absolute_parent_is_live(path, parent_fd, "receipt destination")
        _lock_receipt_cas(cas_fd)
        _reap_receipt_transactions(cas_fd)
        _ensure_receipt_cas_object(
            cas_fd,
            payload_digest,
            payload,
        )
        staging_name, staging_status = _create_receipt_staging(cas_fd, payload)
        _assert_absolute_parent_is_live(path, parent_fd, "receipt destination")
        os.link(
            staging_name,
            filename,
            src_dir_fd=cas_fd,
            dst_dir_fd=parent_fd,
            follow_symlinks=False,
        )
        installed = True
        # The public name now owns its link. Retire the private staging alias
        # before any durability work so later cleanup never has to rename,
        # unlink, or otherwise race the public receipt path.
        _remove_private_receipt_alias(
            cas_fd,
            staging_name,
            staging_status,
            None,
        )
        staging_name = None
        os.fsync(cas_fd)
        if not _installed_receipt_matches(
            parent_fd,
            filename,
            staging_status,
            payload,
        ):
            raise ContextSyncReceiptError(
                "receipt destination changed during publication",
            )
        _assert_absolute_parent_is_live(path, parent_fd, "receipt destination")
        os.fsync(parent_fd)
        _assert_absolute_parent_is_live(path, parent_fd, "receipt destination")
        if not _installed_receipt_matches(
            parent_fd,
            filename,
            staging_status,
            payload,
        ):
            raise ContextSyncReceiptError(
                "receipt destination changed during publication",
            )
        _assert_absolute_parent_is_live(path, parent_fd, "receipt destination")
        if not _installed_receipt_matches(
            parent_fd,
            filename,
            staging_status,
            payload,
        ):
            raise ContextSyncReceiptError(
                "receipt destination changed during publication",
            )
    except Exception as exc:
        if staging_name is not None and cas_fd is not None:
            with suppress(Exception):
                _preserve_and_remove_private_receipt_alias(cas_fd, staging_name)
        if installed:
            raise ContextSyncReceiptPublicationError(
                f"receipt installed; final durability or identity verification failed: {exc}",
                path,
                "sha256:" + payload_digest,
            ) from exc
        raise
    finally:
        active_error = sys.exc_info()[0] is not None
        close_error: OSError | None = None
        for descriptor in (cas_fd, parent_fd):
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError as exc:
                    close_error = close_error or exc
        # Attempt both closes without masking an already classified publication
        # failure. A cleanup-only error crossed the same install boundary.
        if close_error is not None and not active_error:
            if installed:
                raise ContextSyncReceiptPublicationError(
                    f"receipt installed; descriptor cleanup failed: {close_error}",
                    path,
                    "sha256:" + payload_digest,
                ) from close_error
            raise close_error
    return "sha256:" + payload_digest


def _open_receipt_cas(path: Path, receipt_parent_fd: int) -> int:
    """Open the SHA-256 CAS in Git administration storage or a safe fallback."""
    git_fd = _discover_git_admin_fd(path.parent)
    if git_fd is not None:
        try:
            _assert_absolute_parent_is_live(
                path,
                receipt_parent_fd,
                "receipt destination",
            )
            if os.fstat(git_fd).st_dev != os.fstat(receipt_parent_fd).st_dev:
                raise ContextSyncReceiptError(
                    "Git receipt custody CAS crosses a filesystem boundary",
                )
            root_fd = _open_or_create_directory_at(
                git_fd,
                "organvm-receipt-cas",
            )
            cas_fd = _open_cas_sha_directory(root_fd)
            if os.fstat(cas_fd).st_dev != os.fstat(receipt_parent_fd).st_dev:
                os.close(cas_fd)
                raise ContextSyncReceiptError(
                    "Git receipt custody CAS crosses a filesystem boundary",
                )
            return cas_fd
        finally:
            with suppress(OSError):
                os.close(git_fd)
    if _has_git_marker(path.parent):
        raise ContextSyncReceiptError(
            "containing Git administration directory is not safely discoverable",
        )
    root_fd = _open_or_create_directory_at(
        receipt_parent_fd,
        ".organvm-receipt-cas",
    )
    cas_fd = _open_cas_sha_directory(root_fd)
    if os.fstat(cas_fd).st_dev != os.fstat(receipt_parent_fd).st_dev:
        os.close(cas_fd)
        raise ContextSyncReceiptError(
            "receipt custody CAS crosses a filesystem boundary",
        )
    return cas_fd


def _has_git_marker(start: Path) -> bool:
    """Return whether a lexical ancestor contains any Git administration marker."""
    candidate = Path(os.path.normpath(str(start.expanduser().absolute())))
    while True:
        try:
            (candidate / ".git").lstat()
        except FileNotFoundError:
            pass
        else:
            return True
        if candidate == candidate.parent:
            return False
        candidate = candidate.parent


def _open_cas_sha_directory(root_fd: int) -> int:
    try:
        _assert_private_receipt_cas_directory(root_fd)
        cas_fd = _open_or_create_directory_at(root_fd, "sha256")
    finally:
        os.close(root_fd)
    try:
        _assert_private_receipt_cas_directory(cas_fd)
    except Exception:
        os.close(cas_fd)
        raise
    return cas_fd


def _assert_private_receipt_cas_directory(descriptor: int) -> None:
    """Require the transaction namespace to be an owner-private real directory."""
    status = os.fstat(descriptor)
    effective_uid = getattr(os, "geteuid", lambda: status.st_uid)()
    if (
        not stat.S_ISDIR(status.st_mode)
        or stat.S_IMODE(status.st_mode) & 0o077
        or status.st_uid != effective_uid
    ):
        raise ContextSyncReceiptError(
            "receipt custody CAS is not an owner-private directory",
        )


def _discover_git_admin_fd(start: Path) -> int | None:
    """Return a no-follow descriptor for the containing repository's Git dir."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--absolute-git-dir"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    raw = completed.stdout.strip()
    if not raw:
        return None
    candidate = Path(raw)
    if not candidate.is_absolute():
        return None
    try:
        descriptor, probe = _open_absolute_parent_no_follow(
            candidate / ".organvm-cas-probe",
            "Git administration directory",
        )
    except (OSError, ContextSyncReceiptError):
        return None
    if probe != ".organvm-cas-probe":
        os.close(descriptor)
        return None
    return descriptor


def _open_or_create_directory_at(parent_fd: int, name: str) -> int:
    """Open one real child directory, creating it descriptor-relatively."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        return os.open(name, flags, dir_fd=parent_fd)
    except FileNotFoundError:
        with suppress(FileExistsError):
            os.mkdir(name, mode=0o700, dir_fd=parent_fd)
        os.fsync(parent_fd)
        return os.open(name, flags, dir_fd=parent_fd)


def _lock_receipt_cas(cas_fd: int) -> None:
    """Serialize cooperating CAS writers without introducing lock pathnames."""
    try:
        import fcntl

        fcntl.flock(cas_fd, fcntl.LOCK_EX)
    except (ImportError, OSError) as exc:
        raise ContextSyncReceiptError("cannot lock receipt custody CAS") from exc


def _ensure_receipt_cas_object(
    cas_fd: int,
    digest: str,
    payload: bytes,
) -> os.stat_result:
    """Create or verify the sole immutable CAS object for these receipt bytes."""
    staging_name = f"transaction-{secrets.token_hex(24)}.rollback"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    try:
        existing = os.stat(digest, dir_fd=cas_fd, follow_symlinks=False)
    except FileNotFoundError:
        existing = None
    if existing is not None:
        if not _cas_object_matches(cas_fd, digest, existing, payload):
            raise ContextSyncReceiptError(
                f"receipt custody CAS object is corrupt: sha256:{digest}",
            ) from None
        return existing
    descriptor = os.open(staging_name, flags, 0o600, dir_fd=cas_fd)
    try:
        offset = 0
        while offset < len(payload):
            offset += os.write(descriptor, payload[offset:])
        os.fchmod(descriptor, 0o400)
        os.fsync(descriptor)
        status = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    try:
        os.link(
            staging_name, digest, src_dir_fd=cas_fd, dst_dir_fd=cas_fd,
            follow_symlinks=False,
        )
    except FileExistsError:
        installed = os.stat(digest, dir_fd=cas_fd, follow_symlinks=False)
        if not _cas_object_matches(cas_fd, digest, installed, payload):
            raise ContextSyncReceiptError(
                f"receipt custody CAS object is corrupt: sha256:{digest}",
            ) from None
        status = installed
    finally:
        with suppress(FileNotFoundError):
            os.unlink(staging_name, dir_fd=cas_fd)
    os.fsync(cas_fd)
    if not _cas_object_matches(cas_fd, digest, status, payload):
        raise ContextSyncReceiptError(
            f"receipt custody CAS object failed verification: sha256:{digest}",
        )
    return status


def _create_receipt_staging(
    cas_fd: int,
    payload: bytes,
) -> tuple[str, os.stat_result]:
    """Create a private publication inode distinct from the immutable CAS object."""
    name = f"transaction-{secrets.token_hex(24)}.generated"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(name, flags, 0o644, dir_fd=cas_fd)
    try:
        offset = 0
        while offset < len(payload):
            offset += os.write(descriptor, payload[offset:])
        os.fsync(descriptor)
        return name, os.fstat(descriptor)
    finally:
        os.close(descriptor)


def _remove_private_receipt_alias(
    cas_fd: int,
    name: str,
    expected_status: os.stat_result,
    expected_payload: bytes | None,
) -> None:
    """Remove one exact engine-owned alias from the locked private CAS."""
    if not RECEIPT_TRANSACTION_ALIAS.fullmatch(name):
        raise ContextSyncReceiptError(
            f"refusing to remove non-transaction receipt path: {name}",
        )
    status = os.stat(name, dir_fd=cas_fd, follow_symlinks=False)
    if (status.st_dev, status.st_ino) != (
        expected_status.st_dev,
        expected_status.st_ino,
    ) or (
        expected_payload is not None
        and not _installed_receipt_matches(
            cas_fd,
            name,
            expected_status,
            expected_payload,
        )
    ):
        raise ContextSyncReceiptError(
            f"private receipt transaction changed before cleanup: {name}",
        )
    os.unlink(name, dir_fd=cas_fd)


def _preserve_and_remove_private_receipt_alias(cas_fd: int, name: str) -> None:
    """CAS-bind the exact private bytes before removing their transaction alias."""
    status, payload = _read_receipt_cas_candidate(cas_fd, name)
    digest = hashlib.sha256(payload).hexdigest()
    _ensure_receipt_cas_object(cas_fd, digest, payload)
    _remove_private_receipt_alias(cas_fd, name, status, payload)
    os.fsync(cas_fd)


def _reap_receipt_transactions(cas_fd: int) -> None:
    """Bound and remove transaction aliases left by an interrupted writer."""
    for name in sorted(os.listdir(cas_fd)):
        if RECEIPT_TRANSACTION_ALIAS.fullmatch(name):
            _preserve_and_remove_private_receipt_alias(cas_fd, name)


def _cas_object_matches(
    cas_fd: int,
    name: str,
    expected_status: os.stat_result,
    expected_payload: bytes,
) -> bool:
    try:
        current = os.stat(name, dir_fd=cas_fd, follow_symlinks=False)
    except OSError:
        return False
    if (
        not stat.S_ISREG(current.st_mode)
        or stat.S_IMODE(current.st_mode) != 0o400
        or current.st_nlink != 1
        or (current.st_dev, current.st_ino)
        != (expected_status.st_dev, expected_status.st_ino)
    ):
        return False
    if not _installed_receipt_matches(
        cas_fd,
        name,
        expected_status,
        expected_payload,
    ):
        return False
    try:
        rebound = os.stat(name, dir_fd=cas_fd, follow_symlinks=False)
    except OSError:
        return False
    return (
        stat.S_ISREG(rebound.st_mode)
        and stat.S_IMODE(rebound.st_mode) == 0o400
        and rebound.st_nlink == 1
        and (rebound.st_dev, rebound.st_ino)
        == (expected_status.st_dev, expected_status.st_ino)
    )


def _installed_receipt_matches(
    parent_fd: int,
    filename: str,
    expected_status: os.stat_result,
    expected_payload: bytes,
) -> bool:
    """Return whether the live destination is still the exact installed inode."""
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    flags |= (
        getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    descriptor: int | None = None
    try:
        current = os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
        if (current.st_dev, current.st_ino) != (
            expected_status.st_dev,
            expected_status.st_ino,
        ):
            return False
        descriptor = os.open(filename, flags, dir_fd=parent_fd)
        before = os.fstat(descriptor)
        chunks: list[bytes] = []
        total = 0
        while chunk := os.read(descriptor, 128 * 1024):
            total += len(chunk)
            if total > len(expected_payload):
                return False
            chunks.append(chunk)
        after = os.fstat(descriptor)
        live = os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
    except OSError:
        return False
    finally:
        if descriptor is not None:
            os.close(descriptor)
    stable_fields = (
        "st_dev",
        "st_ino",
        "st_mode",
        "st_size",
        "st_mtime_ns",
        "st_ctime_ns",
    )
    return (
        (live.st_dev, live.st_ino) == (before.st_dev, before.st_ino)
        and all(
            getattr(before, field) == getattr(after, field)
            and getattr(before, field) == getattr(live, field)
            for field in stable_fields
        )
        and b"".join(chunks) == expected_payload
    )


def _read_receipt_cas_candidate(
    cas_fd: int,
    name: str,
) -> tuple[os.stat_result, bytes]:
    """Read one stable regular candidate already moved into the custody CAS."""
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    flags |= (
        getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    descriptor = os.open(name, flags, dir_fd=cas_fd)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ContextSyncReceiptError("receipt retirement candidate is not regular")
        chunks: list[bytes] = []
        total = 0
        while chunk := os.read(descriptor, 128 * 1024):
            total += len(chunk)
            if total > MAX_RECEIPT_INPUT_BYTES:
                raise ContextSyncReceiptError(
                    "receipt retirement candidate exceeds size limit",
                )
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    live = os.stat(name, dir_fd=cas_fd, follow_symlinks=False)
    stable_fields = (
        "st_dev",
        "st_ino",
        "st_mode",
        "st_size",
        "st_mtime_ns",
        "st_ctime_ns",
    )
    if total != before.st_size or any(
        getattr(before, field) != getattr(after, field)
        or getattr(before, field) != getattr(live, field)
        for field in stable_fields
    ):
        raise ContextSyncReceiptError(
            "receipt retirement candidate changed while being rebound",
        )
    return before, b"".join(chunks)


def _assert_absolute_parent_is_live(path: Path, opened_fd: int, subject: str) -> None:
    """Require the lexical parent path to retain the opened directory identity."""
    try:
        live_fd, live_filename = _open_absolute_parent_no_follow(path, subject)
    except OSError as exc:
        raise ContextSyncReceiptError(
            f"{subject} parent changed during publication",
        ) from exc
    try:
        opened = os.fstat(opened_fd)
        live = os.fstat(live_fd)
        if live_filename != path.name or (opened.st_dev, opened.st_ino) != (
            live.st_dev,
            live.st_ino,
        ):
            raise ContextSyncReceiptError(f"{subject} parent changed during publication")
    finally:
        os.close(live_fd)


def _git(root: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ContextSyncReceiptError(f"cannot resolve generator Git identity: {exc}") from exc
    return completed.stdout.strip()


def _validated_generator_identity(identity: dict[str, str]) -> dict[str, str]:
    commit = identity.get("commit", "")
    tree = identity.get("tree", "")
    if (
        not GIT_OBJECT_ID.fullmatch(commit)
        or not GIT_OBJECT_ID.fullmatch(tree)
        or len(commit) != len(tree)
    ):
        raise ContextSyncReceiptError(
            "generator identity requires exact commit and tree with matching-format Git object IDs",
        )
    return {"commit": commit, "tree": tree}


def _file_binding(path: Path, *, label: str) -> dict[str, str | int]:
    path = path.expanduser()
    return _bound_regular_file(
        path,
        label=label,
        maximum_bytes=MAX_RECEIPT_INPUT_BYTES,
        subject="receipt input",
    )


def _bound_workspace_identity(
    workspace: Path,
    expected: dict[str, int] | None,
) -> dict[str, int]:
    """Bind the workspace inode and reject a lexical-root replacement."""
    from organvm_engine.contextmd.sync import _capture_custody_root_identity

    try:
        actual = _capture_custody_root_identity(workspace.expanduser())
    except (OSError, RuntimeError) as exc:
        raise ContextSyncReceiptError(f"cannot bind receipted workspace: {exc}") from exc
    if expected is None:
        return actual
    if set(expected) != {"device", "inode"} or any(
        isinstance(expected[key], bool)
        or not isinstance(expected[key], int)
        or expected[key] < 0
        for key in ("device", "inode")
    ):
        raise ContextSyncReceiptError("receipted workspace identity is malformed")
    normalized = {"device": expected["device"], "inode": expected["inode"]}
    if normalized != actual:
        raise ContextSyncReceiptError("receipted workspace root changed after input binding")
    return normalized


def _output_binding(
    path: Path,
    workspace: Path,
    workspace_identity: dict[str, int] | None = None,
    *,
    expected_parent_identity: object = None,
) -> dict[str, str | int]:
    from organvm_engine.contextmd.sync import (
        _assert_custody_parent_is_live,
        _custody_object_name,
        _open_custody_journal,
        _open_custody_parent,
        _read_custody_payload,
    )

    try:
        parent_fd, filename, label = _open_custody_parent(
            path.expanduser(),
            workspace,
            expected_root_identity=workspace_identity,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        raise ContextSyncReceiptError(
            f"context output is missing or outside the receipted workspace: {path}",
        ) from exc
    try:
        if expected_parent_identity is not None:
            actual_parent = os.fstat(parent_fd)
            if expected_parent_identity != {
                "device": actual_parent.st_dev,
                "inode": actual_parent.st_ino,
            }:
                raise RuntimeError(
                    "context output parent changed after receipted preflight",
                )
        payload = _read_custody_payload(parent_fd, filename)
        _assert_custody_parent_is_live(
            parent_fd,
            filename,
            label,
            workspace,
            workspace_identity,
        )
        rebound_payload = _read_custody_payload(parent_fd, filename)
        _assert_custody_parent_is_live(
            parent_fd,
            filename,
            label,
            workspace,
            workspace_identity,
        )
        if rebound_payload != payload:
            raise RuntimeError("context output changed during receipt binding")
        if expected_parent_identity is not None and payload is not None:
            journal_fd = _open_custody_journal(
                workspace,
                label,
                parent_fd,
                workspace_identity,
                create=False,
            )
            try:
                object_name = _custody_object_name(payload)
                try:
                    object_before = os.stat(
                        object_name,
                        dir_fd=journal_fd,
                        follow_symlinks=False,
                    )
                except FileNotFoundError as exc:
                    raise RuntimeError(
                        "generated output changed or context custody object is missing/corrupt",
                    ) from exc
                if (
                    not stat.S_ISREG(object_before.st_mode)
                    or stat.S_IMODE(object_before.st_mode) != 0o400
                    or object_before.st_nlink != 1
                ):
                    raise RuntimeError(
                        "context custody object is not private and immutable",
                    )
                object_payload = _read_custody_payload(journal_fd, object_name)
                object_after = os.stat(
                    object_name,
                    dir_fd=journal_fd,
                    follow_symlinks=False,
                )
            finally:
                os.close(journal_fd)
            if (
                object_payload != payload
                or (object_after.st_dev, object_after.st_ino)
                != (object_before.st_dev, object_before.st_ino)
                or stat.S_IMODE(object_after.st_mode) != 0o400
                or object_after.st_nlink != 1
            ):
                raise RuntimeError(
                    "generated output changed or context custody object is missing/corrupt",
                )
    except (OSError, RuntimeError) as exc:
        raise ContextSyncReceiptError(f"cannot bind context output {path}: {exc}") from exc
    finally:
        os.close(parent_fd)
    if payload is None:
        raise ContextSyncReceiptError(f"context output is missing: {path}")
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    binding: dict[str, str | int] = {
        "path": label,
        "bytes": len(payload),
        "sha256": digest,
    }
    if expected_parent_identity is not None:
        binding["journal_object"] = digest
    return binding


def _portable_output_path(path: Path, workspace: Path) -> str:
    """Return an output label without resolving a potentially replaced parent."""
    absolute = _lexical_absolute(path)
    try:
        return absolute.relative_to(workspace).as_posix()
    except ValueError:
        return absolute.name


def _bound_regular_file(
    path: Path,
    *,
    label: str,
    subject: str,
    maximum_bytes: int | None = None,
) -> dict[str, str | int]:
    """Hash one stable regular-file descriptor without following its final link."""
    binding, _payload = _read_bound_regular_file(
        path,
        label=label,
        subject=subject,
        maximum_bytes=maximum_bytes,
    )
    return binding


def _read_bound_regular_file(
    path: Path,
    *,
    label: str,
    subject: str,
    maximum_bytes: int | None = None,
) -> tuple[dict[str, str | int], bytes]:
    """Read and bind stable bytes from a no-follow regular-file descriptor."""
    path = path.expanduser()
    parent_fd: int | None = None
    descriptor: int | None = None
    live_parent_fd: int | None = None
    try:
        parent_fd, filename = _open_absolute_parent_no_follow(path, subject)
        target_status = os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(target_status.st_mode):
            raise ContextSyncReceiptError(f"{subject} is not a regular file: {path}")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        flags |= (
            getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
        )
        descriptor = os.open(filename, flags, dir_fd=parent_fd)
    except ContextSyncReceiptError:
        if descriptor is not None:
            os.close(descriptor)
        if parent_fd is not None:
            os.close(parent_fd)
        raise
    except OSError as exc:
        if descriptor is not None:
            os.close(descriptor)
        if parent_fd is not None:
            os.close(parent_fd)
        raise ContextSyncReceiptError(f"cannot open {subject} {path}: {exc}") from exc
    try:
        assert descriptor is not None
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ContextSyncReceiptError(f"{subject} is not a regular file: {path}")
        if maximum_bytes is not None and before.st_size > maximum_bytes:
            raise ContextSyncReceiptError(f"{subject} exceeds size limit: {path}")
        digest = hashlib.sha256()
        chunks: list[bytes] = []
        byte_count = 0
        while chunk := os.read(descriptor, 128 * 1024):
            byte_count += len(chunk)
            if maximum_bytes is not None and byte_count > maximum_bytes:
                raise ContextSyncReceiptError(f"{subject} exceeds size limit: {path}")
            digest.update(chunk)
            chunks.append(chunk)
        after = os.fstat(descriptor)
        current = os.stat(filename, dir_fd=parent_fd, follow_symlinks=False)
        live_parent_fd, live_filename = _open_absolute_parent_no_follow(path, subject)
        opened_parent = os.fstat(parent_fd)
        live_parent = os.fstat(live_parent_fd)
        live_current = os.stat(
            live_filename,
            dir_fd=live_parent_fd,
            follow_symlinks=False,
        )
    except OSError as exc:
        raise ContextSyncReceiptError(
            f"{subject} path changed while it was being bound: {path}: {exc}",
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if parent_fd is not None:
            os.close(parent_fd)
        if live_parent_fd is not None:
            os.close(live_parent_fd)
    stable_fields = (
        "st_dev",
        "st_ino",
        "st_mode",
        "st_size",
        "st_mtime_ns",
        "st_ctime_ns",
    )
    if (
        byte_count != before.st_size
        or (current.st_dev, current.st_ino) != (before.st_dev, before.st_ino)
        or (live_current.st_dev, live_current.st_ino) != (before.st_dev, before.st_ino)
        or (opened_parent.st_dev, opened_parent.st_ino)
        != (live_parent.st_dev, live_parent.st_ino)
        or any(
            getattr(before, field) != getattr(after, field)
            or getattr(before, field) != getattr(current, field)
            or getattr(before, field) != getattr(live_current, field)
            for field in stable_fields
        )
    ):
        raise ContextSyncReceiptError(f"{subject} changed while it was being bound: {path}")
    return (
        {
            "path": label,
            "bytes": byte_count,
            "sha256": "sha256:" + digest.hexdigest(),
        },
        b"".join(chunks),
    )


def _open_absolute_parent_no_follow(
    path: Path,
    subject: str,
    *,
    create_parents: bool = False,
) -> tuple[int, str]:
    """Open an absolute path's parent one real directory at a time."""
    absolute = _lexical_absolute(path)
    if not absolute.name:
        raise ContextSyncReceiptError(f"{subject} path has no file name: {path}")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    anchor = absolute.anchor or os.sep
    parent_fd = os.open(anchor, flags)
    try:
        parts = absolute.parts[1:] if absolute.anchor else absolute.parts
        for component in parts[:-1]:
            try:
                child_fd = os.open(component, flags, dir_fd=parent_fd)
            except FileNotFoundError:
                if not create_parents:
                    raise
                with suppress(FileExistsError):
                    os.mkdir(component, mode=0o700, dir_fd=parent_fd)
                os.fsync(parent_fd)
                child_fd = os.open(component, flags, dir_fd=parent_fd)
            os.close(parent_fd)
            parent_fd = child_fd
    except Exception:
        os.close(parent_fd)
        raise
    return parent_fd, absolute.name


def _portable_input_path(path: Path, workspace: Path) -> str:
    resolved = _lexical_absolute(path)
    try:
        return resolved.relative_to(workspace).as_posix()
    except ValueError:
        return resolved.name


def _lexical_absolute(path: Path) -> Path:
    """Normalize dot segments without resolving any filesystem symlink."""
    return Path(os.path.normpath(str(path.expanduser().absolute())))


def _portable_error_path(value: str, workspace: Path) -> str:
    if not value:
        return ""
    path = Path(value).expanduser()
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.resolve().relative_to(workspace).as_posix()
    except ValueError:
        return path.name


def _portable_error_message(value: str, workspace: Path) -> str:
    return value.replace(str(workspace), ".")


def _canonical_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()
