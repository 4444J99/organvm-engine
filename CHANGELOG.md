# Changelog

## Unreleased

- Public CLI surface inventory: `python -m organvm_engine.api_surface show|check|write` extracts
  the live `organvm` command tree, compares it with the committed baseline
  `docs/api/cli-surface.json`, and classifies drift as breaking or compatible; a test keeps the
  baseline current. Draft version policy in `docs/api/VERSIONING.md` (issue #194).
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
