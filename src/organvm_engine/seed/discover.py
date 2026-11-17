"""Discover seed.yaml files across the workspace."""

from pathlib import Path

from organvm_engine.organ_config import organ_org_dirs
from organvm_engine.paths import workspace_root

# Known org directories — derived from canonical organ_config
ORGAN_ORGS = organ_org_dirs()

# For backward compatibility with git modules
DEFAULT_WORKSPACE = workspace_root()


def discover_seeds(
    workspace: Path | str | None = None,
    orgs: list[str] | None = None,
) -> list[Path]:
    """Walk the workspace and find all seed.yaml files.

    Structure: ~/Workspace/<org>/<repo>/seed.yaml

    When a workspace-manifest.yaml exists at the workspace root and no
    explicit ``orgs`` list is provided, scanning is limited to the organs
    declared in the manifest. This enables partial checkouts for
    collaborators who only need a subset of the full system.

    Args:
        workspace: Root workspace directory. Defaults to ~/Workspace.
        orgs: List of org directory names to scan. Defaults to all 8 organs,
            or the manifest-declared subset if a workspace-manifest.yaml exists.

    Returns:
        Sorted list of paths to seed.yaml files found.
    """
    ws = Path(workspace) if workspace else workspace_root()

    # Determine which org directories to scan
    if orgs is not None:
        # Explicit orgs parameter always takes precedence
        scan_orgs = orgs
    else:
        # Check for workspace manifest to limit organ scanning
        from organvm_engine.organ_config import organ_dir_map
        from organvm_engine.seed.manifest import load_workspace_manifest, organs_in_manifest

        manifest = load_workspace_manifest(ws / "workspace-manifest.yaml")
        manifest_organs = organs_in_manifest(manifest)
        if manifest is not None:
            dir_map = organ_dir_map()
            scan_orgs = [dir_map[k] for k in manifest_organs if k in dir_map]
        else:
            scan_orgs = ORGAN_ORGS

    seeds: list[Path] = []
    for org_name in scan_orgs:
        org_dir = ws / org_name
        if not org_dir.is_dir():
            continue
        for repo_dir in sorted(org_dir.iterdir()):
            if not repo_dir.is_dir():
                continue
            seed_file = repo_dir / "seed.yaml"
            if seed_file.is_file():
                seeds.append(seed_file)

    return sorted(seeds)
