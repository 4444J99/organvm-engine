"""Shared test fixtures for organvm-engine."""

import os
from pathlib import Path

import pytest

from organvm_engine.registry.loader import load_registry

FIXTURES = Path(__file__).parent / "fixtures"


def replace_with_nonregular(path: Path, kind: str, outside: Path) -> None:
    """Replace a regular fixture with a requested non-regular filesystem object."""
    path.unlink()
    if kind == "fifo":
        if not hasattr(os, "mkfifo"):
            pytest.skip("FIFO creation is unavailable")
        os.mkfifo(path)
    elif kind == "symlink":
        path.symlink_to(outside)
    elif kind == "directory":
        path.mkdir()
    else:  # pragma: no cover - callers use closed parametrizations
        raise AssertionError(f"unknown replacement kind: {kind}")


# Sentinel path that should never exist — any test accidentally resolving
# the production path will fail fast instead of silently corrupting data.
_BLOCKED = Path("/nonexistent/organvm-test-guard")

# Host-exported prefixes that must never reach a test (see _block_production_paths).
_HOST_ENV_PREFIXES = ("ORGANVM_", "LIMEN_GOV_")


@pytest.fixture(autouse=True)
def _block_production_paths(monkeypatch):
    """Redirect all production path defaults to /nonexistent.

    This autouse fixture ensures no test can accidentally read from or
    write to the real registry, governance rules, or corpus directory.
    Tests that need file I/O must use tmp_path or the FIXTURES directory.
    """
    import organvm_engine.paths as paths_mod
    import organvm_engine.registry.loader as loader_mod

    monkeypatch.setattr(paths_mod, "_DEFAULT_WORKSPACE", _BLOCKED)
    # corpus_dir() also probes the Code-root fallback; block it so the
    # content-based probe can never resolve the real corpus during tests.
    monkeypatch.setattr(paths_mod, "_DEFAULT_CODE_ROOT", _BLOCKED)
    monkeypatch.setattr(
        loader_mod, "_default_registry_path", lambda: _BLOCKED / "registry-v2.json",
    )
    # Block env vars that bypass _DEFAULT_WORKSPACE, ensuring tests never
    # touch production corpus/governance files.
    monkeypatch.delenv("ORGANVM_WORKSPACE_DIR", raising=False)
    monkeypatch.delenv("ORGANVM_CORPUS_DIR", raising=False)
    # Every other ORGANVM_* / LIMEN_GOV_* knob a host shell exports (for
    # example ORGANVM_ADDITIONAL_WORKSPACE_ROOTS) overrides the config files
    # and fixtures the tests build, so the suite would pass or fail by host.
    # Tests that exercise an override set it explicitly with monkeypatch.setenv.
    for name in [n for n in os.environ if n.startswith(_HOST_ENV_PREFIXES)]:
        monkeypatch.delenv(name, raising=False)
    # A relocated Codex corpus on the host must not leak into discovery tests.
    monkeypatch.delenv("CODEX_HOME", raising=False)


@pytest.fixture(autouse=True)
def _hermetic_git_config(monkeypatch, tmp_path_factory):
    """Keep the host's global git config and global ignore file out of tests.

    A host-wide excludes file (for example one that ignores ``*.tmp``) hides
    untracked files from ``git status`` inside throwaway repositories, so tests
    that assert on a dirty checkout would pass or fail by machine.
    """
    empty_xdg = tmp_path_factory.mktemp("xdg-config")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(empty_xdg))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.fixture
def engine_workspace(tmp_path):
    """A workspace whose ``meta-organvm/organvm-engine`` is this checkout.

    The exit-interview analyzers resolve V1 modules as
    ``<workspace>/meta-organvm/organvm-engine/src/organvm_engine/<module>``.
    Pointing a temp workspace at the checkout under test keeps those tests
    independent of where (or whether) the host keeps its own workspace tree.
    """
    organ_dir = tmp_path / "meta-organvm"
    organ_dir.mkdir()
    (organ_dir / "organvm-engine").symlink_to(Path(__file__).resolve().parents[1])
    return tmp_path


@pytest.fixture
def registry():
    return load_registry(FIXTURES / "registry-minimal.json")
