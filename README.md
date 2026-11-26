# organvm-engine

Core governance, registry, and orchestration engine for the organvm eight-organ system. Consolidates ~30 standalone scripts into a proper installable Python package.

## Install

```bash
pip install -e .          # users: the `organvm` CLI and library
pip install -e ".[dev]"   # contributors: plus pytest, ruff, pyright, nbformat
```

There is no `requirements.txt` in this repo — install from `pyproject.toml`
as above. The `organvm-ontologia` dependency is optional and not on PyPI; the
full suite documents it in [CONTRIBUTING.md](CONTRIBUTING.md) (CI pins a
commit in `.github/workflows/ci.yml`). Without it, the ontologia-bridge tests
fail at import, not on behavior.

## Verify a release

Versioned artifacts ship as GitHub Releases: [Releases](https://github.com/4444J99/organvm-engine/releases). To verify a release, install its wheel (not the source tree) and run the smoke commands:

```bash
pip install <wheel-url-from-the-release>
organvm --help
organvm --registry tests/fixtures/registry-minimal.json registry validate
```

The first real versioned release is cut by pushing a `v*` tag after the release workflow lands; until then the Releases page holds only the draft `v0.0.1` with no assets.

## CLI

Registry commands read the canonical `repo-registry.json` from the corpus repo
by default. On a machine without that checkout they fail with a diagnostic
naming the missing path — pass `--registry <path>` or set
`ORGANVM_CORPUS_DIR` to the corpus repo. Seed commands read
`ORGANVM_WORKSPACE_DIR` (default `~/Workspace`). The examples below use the
checked-in minimal registry fixture, so they run on a fresh clone; see
[docs/quickstart.md](docs/quickstart.md) for the full first-run walkthrough.

```bash
# Registry (against the minimal fixture; use your corpus registry in practice)
organvm --registry tests/fixtures/registry-minimal.json registry show organvm-engine
organvm --registry tests/fixtures/registry-minimal.json registry list --organ ORGAN-I --tier flagship
organvm --registry tests/fixtures/registry-minimal.json registry list --format json
organvm --registry tests/fixtures/registry-minimal.json registry validate

# Governance
organvm --registry tests/fixtures/registry-minimal.json governance check-deps
# `governance audit` needs the corpus governance rules as well, so it also
# requires ORGANVM_CORPUS_DIR to point at the corpus repo.

# Seed (ORGANVM_WORKSPACE_DIR must hold an <org>/<repo>/seed.yaml layout)
ORGANVM_WORKSPACE_DIR=/path/to/workspace organvm seed discover
ORGANVM_WORKSPACE_DIR=/path/to/workspace organvm seed validate
ORGANVM_WORKSPACE_DIR=/path/to/workspace organvm seed graph

# Metrics (writes system-metrics.json next to the registry file — point
# --registry at a copy if you do not want the checkout touched)
organvm --registry tests/fixtures/registry-minimal.json metrics calculate

# Dispatch
organvm dispatch validate tests/fixtures/dispatch-payload-minimal.json

# Context
organvm --registry tests/fixtures/registry-minimal.json context sync --dry-run
organvm context surfaces --json

# Reader-mode documentation
organvm docs audit . --format markdown
organvm docs audit --workspace /path/to/workspace --format json --output docs-audit.json
# `docs validate` needs a project record; this repo has none yet (the audit
# above reports it). The schema lives in-repo:
#   organvm docs validate project-record.yml \
#     --schema src/organvm_engine/documentation/schemas/project-record-v1.schema.json \
#     --actual-repository 4444J99/organvm-engine
```

The [2026-08-31 documentation estate audit](docs/audits/reader-mode-estate-audit.md)
shows how installation-scoped and search-scoped repository inventories are
normalized without publishing private repository identities.

## Library Usage

```python
from organvm_engine.registry import load_registry, find_repo, validate_registry
from organvm_engine.governance import validate_dependencies, run_audit
from organvm_engine.seed import discover_seeds, build_seed_graph
from organvm_engine.metrics import compute_metrics

# Pass an explicit path: the default is the corpus repo, which a fresh
# machine does not have (load_registry() with no argument raises a
# FileNotFoundError naming the missing path and the --registry escape hatch).
registry = load_registry("tests/fixtures/registry-minimal.json")
result = validate_registry(registry)
print(result.summary())
```

## Core modules

| Module | Purpose |
|--------|---------|
| `registry` | Load, query, validate, update canonical `repo-registry.json` |
| `governance` | Rules enforcement, state machine, dependency graph, audit |
| `seed` | Discover, parse, and graph seed.yaml files |
| `metrics` | Compute and propagate system-wide metrics |
| `dispatch` | Cross-organ event routing and cascade planning |
| `contextmd` | Sync AI context files and discover exported conversation-corpus surfaces |
| `documentation` | Validate canonical project records and audit reader-mode documentation across seven dimensions |
| `mcp` | JSON-serializable tool wrappers exposing the 5 core CLIs to `organvm-mcp-server` |

The full module inventory (47 packages under `src/organvm_engine/`) is in
[CLAUDE.md](CLAUDE.md#domain-modules).

## Repository authority and system role

The canonical GitHub authority is
[`4444J99/organvm-engine`](https://github.com/4444J99/organvm-engine). The engine
serves as a cross-organ operational backbone; its historical description as an
ORGAN VIII/meta-system component describes function, not current repository
ownership.
