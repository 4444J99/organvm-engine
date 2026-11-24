# Changelog

## Unreleased

- Release evidence for the 0.1.0 candidate (issue #195, steps 2–6):
  `organvm_engine.ci.release_evidence` builds the wheel + sdist, checks
  them against the exclusion list (private `organvm-ontologia` package,
  `psycopg`, `legacy/`, live-custody `receipts/`/`signatures/`, credential
  files), and writes a CycloneDX SBOM, `sha256sums.txt` and a provenance
  receipt under `docs/releases/0.1.0/`; `organvm_engine.ci.release_rollback`
  tests the rollback (install, uninstall, verify gone, reinstall from the
  sdist). The release workflow now generates this evidence on every build,
  attaches it to `v*` releases, smoke-tests the wheel on Python 3.11 and
  3.12, and runs the rollback test. Publication (step 7) and owner approval
  (step 8) are NOT done here: #192 is still open and publishing is the
  owner's call — the 0.1.0 candidate is verified, not shipped.
- Onboarding repair (issue #196): README and CONTRIBUTING now document the
  one install path (`pip install -e ".[dev]"`; there is no
  `requirements.txt`), every README CLI example is verified against the live
  CLI at main (registry/seed/governance/metrics/dispatch/context/docs forms
  all take an explicit `--registry` fixture path or `ORGANVM_WORKSPACE_DIR`,
  since the corpus defaults do not exist on a fresh machine), the canonical
  repository link is `4444J99/organvm-engine` (README, SECURITY.md
  advisories, CONTRIBUTING), and the stray `# Webhook test` lines are gone
  from README. New `docs/quickstart.md` (verified first-run walkthrough)
  and `docs/root-inventory.md` (34-entry root classification + relocation
  map); the dead `organvm-engine` gitlink is removed and the superseded
  `patch2.diff` is relocated to `docs/history/` with its landing evidence.
  `load_registry()` now fails closed with a diagnostic naming the missing
  registry path and the `--registry` / `ORGANVM_CORPUS_DIR` escape hatches
  instead of a bare traceback. CLAUDE.md's domain-module table is regenerated
  to the live 47 packages and `ecosystem.yaml` counts are corrected
  (47 modules, ~6,800 tests, 49 command groups).
- `organvm context sync` writes the full generated context to one generator-owned
  `docs/organvm-context.md` per directory (repo, organ, workspace) and leaves only a short
  pointer, with its `Last synced` stamp, between the `ORGANVM:AUTO` markers of `CLAUDE.md`,
  `GEMINI.md` and `AGENTS.md`, so agents that auto-load those files no longer carry the
  generated text. A legacy full block is migrated to the pointer on the next sync. The sync
  never creates or grows an instruction file: only one that already carries both markers
  receives the pointer (others are reported as `declined`), unless
  `--create-instruction-files` / `create_instruction_files=True` opts in. The
  receipted (`--receipt`) transaction layer covers the new file like any other output; its
  preflight creates a missing `docs/` first and a rollback removes it again. The changelog
  rollback understands whole-file records, and `contextmd.reader.read_generated_context`
  reads the document with a fallback to a legacy in-file block.
- Public CLI surface inventory: `python -m organvm_engine.api_surface show|check|write` extracts
  the live `organvm` command tree, compares it with the committed baseline
  `docs/api/cli-surface.json`, and classifies drift as breaking or compatible; a test keeps the
  baseline current. Draft version policy in `docs/api/VERSIONING.md` (issue #194).
- Workflow-ingest collector (`organvm ci workflow-inventory`, issue #190):
  the minimal trusted collector for the `ci/workflow_intelligence.py`
  `inventory()` / `drift()` primitives, which had zero production callers —
  it pins repository identity (API id vs the caller-pinned
  `--repository-id`) and revision, enumerates the workflow set from the
  pinned tree (a truncated listing fails the collection), verifies each
  file's bytes against Git object identity (contents blob SHA must equal
  the tree entry's), and hands the fetched files to the existing
  `inventory()`; CODEOWNERS and (optionally, `--registry`) tier/dependency
  data join with explicit unknowns, and `--restore-from` rebuilds a
  snapshot from a retained cycle artifact and compares digests. A new
  `.github/workflows/workflow-inventory.yml` (monthly schedule +
  `workflow_dispatch`) hosts the cycle and uploads the envelope as an
  artifact (90-day retention). Freshness budget: a snapshot is stale after
  35 days (one monthly cycle plus grace); at most 3 cycles are retained.
- Execution-evidence collector (`organvm ci evidence`, issue #189): the minimal trusted
  collector for the `ci/runtime_evidence.py` adapter — fetches one Actions run and its jobs
  pages through the environment-supplied token (`GITHUB_TOKEN`/`GH_TOKEN`, never minted,
  stored, or logged), evaluates them against caller-pinned expectations from a reviewed
  workflow contract (`tests/fixtures/ci_evidence/organvm-engine-ci-required-steps.json`),
  and reports `executed_pass` / `executed_failure` / `not_executed` / `pending` /
  `incomplete` without authorizing execution, a check, or a release. The September zero-step
  failure (run 34762163480) still reproduces as `not_executed` through the wired path, and
  the current main run (44909979065 at `1e4bec99`) reports `executed_pass` with its three
  required jobs on real runners.
- Tests are host-independent: `ORGANVM_*`/`LIMEN_GOV_*` env vars and the host's global
  git config/ignore no longer leak into the suite, and the exit-interview tests
  use a temp workspace pointing at the checkout under test instead of `~/Workspace`.
- `organvm governance promotion-queue`: read-only fleet view of every repo's next
  promotion step (ready / unverified / blocked), with blockers (invalid
  transition, missing `functional_class`, failing infrastructure mechanisms) and
  the most common causes. Repos without a local checkout are `unverified`, never
  `ready`. `organvm governance promote --dry-run` validates without emitting an
  EventSpine event or recording `promotion_history` (`execute_transition(dry_run=)`).
- Reader-mode documentation engine: canonical `project-record.yml` integrity
  validation, class-aware audience-route checks, seven-dimension repository
  audits, workspace discovery, and table/JSON/Markdown CLI reporting.
- Bind pilot, public, and retired deployment lifecycle states to at least one
  qualifying verified deployment assertion, with conservative retired-state
  support for verified current-unavailability evidence.
- Bind canonical and noncanonical delivery roles to an explicitly supplied
  checked-out repository identity, preventing Class D self-redirects.
- Executed 323-repository estate-audit notebook with privacy-bounded public
  outputs, reproducible input manifest, and first-wave rollout queue.
- Clarified canonical repository ownership versus the engine's historical
  meta-system functional placement.
- MCP tool layer (`organvm_engine.mcp`): pure, JSON-serializable wrappers
  exposing the five core CLIs (registry, governance, seed, metrics, dispatch)
  to the `organvm-mcp-server` without an MCP-SDK dependency. Includes a
  `MCP_TOOLS` manifest plus `list_tools()` / `call_tool()` for generic
  registration and dispatch.

## 0.1.0 (2026-02-17)

- Initial release: 5 modules (registry, governance, seed, metrics, dispatch)
- Unified CLI with `organvm` entry point
- Registry: load, save, query, validate, update
- Governance: state machine, dependency graph, full audit
- Seed: workspace discovery, YAML parsing, produces/consumes graph
- Metrics: calculator, propagator, timeseries from soak tests
- Dispatch: payload creation/validation, event routing, cascade planning
- 30+ tests with fixture data
