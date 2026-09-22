"""Workspace manifest — declares which organs are present in a partial checkout.

A workspace-manifest.yaml at the workspace root enables organ-scoped
workspaces for collaborators who only need a subset of the full system.

When present, discover_seeds() limits scanning to declared organs.
When absent, all organs are scanned (full-workspace behavior).

Manifest uses CLI short keys for organs (I, II, META, etc.) — the same
keys used by the `organvm` CLI and `organ_config.organ_dir_map()`.
"""

from __future__ import annotations

from pathlib import Path

from organvm_engine._stable_io import read_stable_regular_bytes


def load_workspace_manifest(path: Path | str) -> dict | None:
    """Load a workspace-manifest.yaml file.

    Args:
        path: Path to the manifest file.

    Returns:
        Parsed manifest dict, or None if the file doesn't exist.
    """
    manifest_path = Path(path)
    # Only an absent pathname means a full workspace. Unsafe existing inputs
    # must never broaden discovery to every organ.
    try:
        manifest_path.lstat()
    except FileNotFoundError:
        return None

    import yaml

    data = yaml.safe_load(read_stable_regular_bytes(manifest_path))
    if not isinstance(data, dict):
        raise ValueError(f"Workspace manifest must be a mapping: {manifest_path}")
    organs = data.get("organs_present")
    if not isinstance(organs, list) or any(not isinstance(organ, str) for organ in organs):
        raise ValueError(f"Workspace manifest requires organs_present strings: {manifest_path}")
    from organvm_engine.organ_config import organ_dir_map

    if any(organ not in organ_dir_map() for organ in organs):
        raise ValueError(f"Workspace manifest contains unknown organs: {manifest_path}")
    return data


def organs_in_manifest(manifest: dict | None) -> list[str]:
    """Return the list of organ short keys declared in the manifest.

    Returns empty list if manifest is None (full workspace).
    """
    if manifest is None:
        return []
    organs = manifest.get("organs_present")
    if isinstance(organs, list):
        return [str(o) for o in organs]
    return []


def is_partial_workspace(manifest: dict | None) -> bool:
    """Check if the workspace is declared as partial."""
    if manifest is None:
        return False
    return bool(manifest.get("partial", False))
