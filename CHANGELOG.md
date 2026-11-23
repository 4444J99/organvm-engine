# Changelog

## Unreleased

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
