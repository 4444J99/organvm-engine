# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Core Python package for the ORGANVM eight-organ system: registry, governance, seed discovery, metrics, dispatch, git superproject management, context file sync, session analysis, plan atomization, prompt narrative extraction, and the unified `organvm` CLI.

## Commands

```bash
# Install (use the workspace venv at meta-organvm/.venv)
pip install -e ".[dev]"

# Test
pytest tests/ -v                              # all tests
pytest tests/test_registry.py -v              # one module
pytest tests/test_registry.py::test_name -v   # one test

# Lint
ruff check src/

# Typecheck
pyright
```

## Architecture

### Foundation modules

Every other module imports from these; change them carefully.

- **`organ_config.py`** — Single source of truth for organ key/directory/registry-key/GitHub-org mappings. The `ORGANS` dict maps CLI short keys (`"I"`, `"META"`, `"LIMINAL"`) to metadata. All organ lookups across the codebase derive from helper functions here (`organ_dir_map`, `organ_aliases`, `registry_key_to_dir`, etc.).

- **`paths.py`** — Resolves canonical filesystem paths (`workspace_root`, `corpus_dir`, `registry_path`, `governance_rules_path`, `soak_dir`, `atoms_dir`). Reads `ORGANVM_WORKSPACE_DIR` and `ORGANVM_CORPUS_DIR` env vars, falls back to `~/Workspace` conventions.

- **`domain.py`** — Content-based identity for atomic units. `domain_fingerprint()` produces a SHA256[:16] digest from tags + file refs. `domain_set()` builds prefixed sets for Jaccard similarity comparison. Used by both `atoms/` and `prompts/` to link tasks and prompts by content DNA.

- **`project_slug.py`** — Canonical project slug derivation (`meta-organvm/organvm-engine` form). Converts filesystem paths, plan directory names, and raw slugs to a normalized slash-separated format. Shared across `prompts/`, `plans/`, and `session/`.

### Domain modules (23)

| Module | Role |
|--------|------|
| `registry/` | Load/save/query/validate/update `registry-v2.json` |
| `governance/` | Promotion state machine, dependency graph validation, audit, blast-radius impact |
| `seed/` | Discover `seed.yaml` files across workspace, read them, build produces/consumes graph |
| `metrics/` | Calculate system metrics, propagate into markdown/JSON, timeseries, variable resolution |
| `dispatch/` | Event payload validation, routing, cascade |
| `git/` | Superproject init/sync, submodule status/drift, workspace reproduction |
| `contextmd/` | Auto-generate CLAUDE.md/GEMINI.md/AGENTS.md across all repos from templates |
| `omega/` | 17-criterion binary scorecard for system maturity |
| `ci/` | CI health triage from soak-test data |
| `deadlines/` | Parse deadlines from `rolling-todo.md` |
| `pitchdeck/` | HTML pitch deck generation per repo |
| `session/` | Multi-agent session transcript parsing (Claude, Gemini, Codex), plan auditing, prompt analysis |
| `plans/` | Plan file atomization, indexing, hygiene checks, overlap detection, and per-organ synthesis |
| `prompts/` | Prompt extraction, classification, narrative threading, and clipboard history analysis |
| `atoms/` | Cross-system linking pipeline: Jaccard matching tasks↔prompts, git reconciliation, per-organ rollups |
| `coordination/` | Multi-agent claims registry (punch-in/out), tool checkout line for concurrent command traffic |
| `distill/` | Operational pattern taxonomy, SOP-to-pattern coverage analysis, scaffold generation |
| `ecosystem/` | Product business profiles, competitive matrix, gap analysis, action generation |
| `prompting/` | Agent-specific prompting guidelines and provider standards |
| `sop/` | SOP/METADOC discovery, inventory audit, tiered resolver (T4→T3→T2 cascade) |
| `irf/` | Parse, query, AND write back INST-INDEX-RERUM-FACIENDARUM.md — the universal work registry. IRFItem dataclass, priority/domain/status filtering, parse-completeness diagnostics, and tooled mutations (`irf add` / `irf complete` / `irf stats --write`, dry-run by default, hardlink-inode-preserving) |
| `fossil/` | Living Stratigraphy — archaeological reconstruction of system history. Excavates git commits, classifies by Jungian archetype (8 types), generates epoch chronicles, captures intentions, detects drift, real-time witness hooks, testament bridge |
| `cli/` | One module per command group (24 modules), wired together in `cli/__init__.py` |

### The atomization pipeline

The `atoms/`, `plans/`, and `prompts/` modules form a three-stage pipeline that can run independently or chained via `organvm atoms pipeline`:

1. **Atomize** (`plans/atomizer.py`) — Parse plan `.md` files into atomic tasks with tags, file refs, status, and project metadata. Discovers plans across `~/.claude/plans/`, `.gemini/plans/`, `.codex/plans/` in every workspace project.

2. **Narrate** (`prompts/narrator.py`) — Extract user prompts from session transcripts, classify them (`prompts/classifier.py`), assign domain fingerprints, and thread them into narrative episodes (`prompts/threading.py`).

3. **Link** (`atoms/linker.py`) — Jaccard-match atomized tasks against annotated prompts using `domain.py` domain sets. Produces `atom-links.jsonl`.

4. **Reconcile** (`atoms/reconciler.py`) — Cross-reference tasks against git commit history to detect completed work. Verdicts: `likely_completed`, `partially_done`, `stale`, `unknown`.

5. **Fanout** (`atoms/rollup.py`) — Aggregate centralized atom data into per-organ rollup JSON files in each organ superproject's `.atoms/` directory.

All pipeline outputs go to `corpus_dir/data/atoms/` with a `pipeline-manifest.json` tracking file hashes and counts.

### CLI dispatch pattern

`cli/__init__.py` builds an argparse tree with `build_parser()`. Commands with subcommands that are in the original tuple-dict (`registry`, `governance`, `seed`, `metrics`, etc.) dispatch via `{(command, subcommand): handler}`. Newer command groups (`session`, `plans`, `prompts`, `atoms`, `organism`, `irf`) use per-group inline dispatch dicts in explicit `if args.command == ...` branches. Top-level commands without subcommands (`status`, `deadlines`, `refresh`, `lint-vars`) dispatch via standalone `if` branches. Each CLI module exports `cmd_*` functions taking `argparse.Namespace` and returning `int`.

### Registry data safety

`registry/loader.py` → `save_registry()` refuses to write fewer than 50 repos to the production path. This prevents test fixtures from accidentally overwriting the real `registry-v2.json` (2,200+ lines).

### Test isolation

`tests/conftest.py` has an **autouse** fixture `_block_production_paths` that monkeypatches `paths._DEFAULT_WORKSPACE` and `loader._default_registry_path` to `/nonexistent/organvm-test-guard`. Every test runs in this sandbox — any test needing real file I/O must use `tmp_path` or `tests/fixtures/`. The `registry` fixture loads `fixtures/registry-minimal.json`.

## Key conventions

- **`src/` layout** — all imports are `from organvm_engine.X import Y`
- **No default exports** — CLI entry point is `organvm_engine.cli:main` (declared in `pyproject.toml`)
- **ruff config** — line-length 100, py311, rules: E/F/W/I/B/PTH/RET/SIM/COM/PL (see `pyproject.toml` for ignores)
- **pyright** — basic mode, py311
- **Commit prefixes** — `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`
- **Dry-run by default** — destructive CLI commands (`context sync`, `omega update`, `plans tidy`, `atoms pipeline`) default to `--dry-run=True` and require `--write` to execute

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `ORGANVM_WORKSPACE_DIR` | `~/Workspace` | Workspace root for all organ directories |
| `ORGANVM_CORPUS_DIR` | `<workspace>/meta-organvm/organvm-corpvs-testamentvm` | Path to corpus repo (registry, governance rules) |

<!-- ORGANVM:AUTO:START -->
## System Context (auto-generated — do not edit)

**Organ:** META-ORGANVM (Meta) | **Tier:** flagship | **Status:** GRADUATED
**Org:** `4444J99` | **Repo:** `organvm-engine`

### Edges
- **Produces** → `ORGAN-IV, META-ORGANVM`: governance-policy
- **Produces** → `ORGAN-IV, META-ORGANVM`: registry
- **Produces** → `META-ORGANVM`: metrics
- **Produces** → `META-ORGANVM`: omega-scorecard
- **Produces** → `ORGAN-I, ORGAN-II, ORGAN-III, ORGAN-IV, ORGAN-V, ORGAN-VI, ORGAN-VII, META-ORGANVM`: context-files
- **Produces** → `META-ORGANVM`: session-analysis
- **Produces** → `META-ORGANVM`: plan-atoms
- **Produces** → `META-ORGANVM`: prompt-narratives
- **Produces** → `META-ORGANVM`: atom-links
- **Produces** → `META-ORGANVM`: testament-artifacts
- **Produces** → `META-ORGANVM`: ci-reports
- **Produces** → `META-ORGANVM`: pitch-decks
- **Produces** → `META-ORGANVM`: ecosystem-profiles
- **Produces** → `META-ORGANVM`: fossil-record
- **Produces** → `ALL`: witness-hooks
- **Consumes** ← `META-ORGANVM`: registry
- **Consumes** ← `META-ORGANVM`: schema
- **Consumes** ← `META-ORGANVM`: governance-rules
- **Consumes** ← `META-ORGANVM`: soak-data
- **Consumes** ← `META-ORGANVM`: seed-files
- **Consumes** ← `META-ORGANVM`: session-transcripts
- **Consumes** ← `META-ORGANVM`: plan-files

### Siblings in Meta
`.github`, `organvm-corpvs-testamentvm`, `alchemia-ingestvm`, `schema-definitions`, `system-dashboard`, `organvm-mcp-server`, `praxis-perpetua`, `stakeholder-portal`, `materia-collider`, `organvm-ontologia`, `vigiles-aeternae--agon-cosmogonicum`, `cvrsvs-honorvm`, `custodia-securitatis`

### Governance
- *Standard ORGANVM governance applies*

*Last synced: 2026-10-24T14:40:54Z*

## Active Handoff Protocol

If `.conductor/active-handoff.md` exists, **READ IT FIRST** before doing any work.
It contains constraints, locked files, conventions, and completed work from the
originating agent. You MUST honor all constraints listed there.

Handoff files should include metadata at the top:
- `created_at`: UTC ISO-8601 timestamp
- `expires_at`: UTC ISO-8601 timestamp, normally within 48h of creation

If the handoff says "CROSS-VERIFICATION REQUIRED", your self-assessment will
NOT be trusted. A different agent will verify your output against these constraints.

## Session Review Protocol

At the end of each session that produces or modifies files:
1. Run `organvm session review --latest` to get a session summary
2. Check for unimplemented plans: `organvm session plans --project .`
3. Export significant sessions: `organvm session export <id> --slug <slug>`
4. Run `organvm prompts distill --dry-run` to detect uncovered operational patterns

Transcripts are on-demand (never committed):
- `organvm session transcript <id>` — conversation summary
- `organvm session transcript <id> --unabridged` — full audit trail
- `organvm session prompts <id>` — human prompts only


## System Library

Plans: 269 indexed | Chains: 5 available | SOPs: 81 active
Discover: `organvm plans search <query>` | `organvm chains list` | `organvm sop lifecycle`
Library: `meta-organvm/praxis-perpetua/library/`


## Active Directives

| Scope | Phase | Name | Description |
|-------|-------|------|-------------|
| repo | any | cli-module-pattern | cli-module-pattern |
| system | any | prompting-standards | Prompting Standards |
| system | any | research-standards-bibliography | APPENDIX: Research Standards Bibliography |
| system | any | phase-closing-and-forward-plan | METADOC: Phase-Closing Commemoration & Forward Attack Plan |
| system | any | research-standards | METADOC: Architectural Typology & Research Standards |
| system | any | sop-ecosystem | METADOC: SOP Ecosystem — Taxonomy, Inventory & Coverage |
| system | any | autonomous-content-syndication | SOP: Autonomous Content Syndication (The Broadcast Protocol) |
| system | any | autopoietic-systems-diagnostics | SOP: Autopoietic Systems Diagnostics (The Mirror of Eternity) |
| system | any | background-task-resilience | background-task-resilience |
| system | any | cicd-resilience-and-recovery | SOP: CI/CD Pipeline Resilience & Recovery |
| system | any | community-event-facilitation | SOP: Community Event Facilitation (The Dialectic Crucible) |
| system | any | context-window-conservation | context-window-conservation |
| system | any | conversation-to-content-pipeline | SOP — Conversation-to-Content Pipeline |
| system | any | cross-agent-handoff | SOP: Cross-Agent Session Handoff |
| system | any | cross-channel-publishing-metrics | SOP: Cross-Channel Publishing Metrics (The Echo Protocol) |
| system | any | data-migration-and-backup | SOP: Data Migration and Backup Protocol (The Memory Vault) |
| system | any | document-audit-feature-extraction | SOP: Document Audit & Feature Extraction |
| system | any | domain-architecture-and-dns | SOP: Domain Architecture & DNS Governance (The Concentric Circles) |
| system | any | dynamic-lens-assembly | SOP: Dynamic Lens Assembly |
| system | any | essay-publishing-and-distribution | SOP: Essay Publishing & Distribution |
| system | any | formal-methods-applied-protocols | SOP: Formal Methods Applied Protocols |
| system | any | formal-methods-master-taxonomy | SOP: Formal Methods Master Taxonomy (The Blueprint of Proof) |
| system | any | formal-methods-tla-pluscal | SOP: Formal Methods — TLA+ and PlusCal Verification (The Blueprint Verifier) |
| system | any | generative-art-deployment | SOP: Generative Art Deployment (The Gallery Protocol) |
| system | any | markdown-hygiene-and-linting | SOP: Markdown Hygiene and Linting |
| system | any | market-gap-analysis | SOP: Full-Breath Market-Gap Analysis & Defensive Parrying |
| system | any | mcp-server-fleet-management | SOP: MCP Server Fleet Management (The Server Protocol) |
| system | any | multi-agent-swarm-orchestration | SOP: Multi-Agent Swarm Orchestration (The Polymorphic Swarm) |
| system | any | network-testament-protocol | SOP: Network Testament Protocol (The Mirror Protocol) |
| system | any | open-source-licensing-and-ip | SOP: Open Source Licensing and IP (The Commons Protocol) |
| system | any | performance-interface-design | SOP: Performance Interface Design (The Stage Protocol) |
| system | any | pitch-deck-rollout | SOP: Pitch Deck Generation & Rollout |
| system | any | polymorphic-agent-testing | SOP: Polymorphic Agent Testing (The Adversarial Protocol) |
| system | any | promotion-and-state-transitions | SOP: Promotion & State Transitions |
| system | any | public-private-classification | SOP: Public/Private Classification |
| system | any | recursive-study-feedback | SOP: Recursive Study & Feedback Loop (The Ouroboros) |
| system | any | repo-onboarding-and-habitat-creation | SOP: Repo Onboarding & Habitat Creation |
| system | any | research-backend-routing | SOP: Research Backend Routing |
| system | any | research-to-implementation-pipeline | SOP: Research-to-Implementation Pipeline (The Gold Path) |
| system | any | security-and-accessibility-audit | SOP: Security & Accessibility Audit |
| system | any | session-as-seed | SOP: Session-as-Seed (The Black-Hole Geometry of Sessions) |
| system | any | session-self-critique | session-self-critique |
| system | any | smart-contract-audit-and-legal-wrap | SOP: Smart Contract Audit and Legal Wrap (The Ledger Protocol) |
| system | any | source-evaluation-and-bibliography | SOP: Source Evaluation & Annotated Bibliography (The Refinery) |
| system | any | stranger-test-protocol | SOP: Stranger Test Protocol |
| system | any | strategic-foresight-and-futures | SOP: Strategic Foresight & Futures (The Telescope) |
| system | any | styx-pipeline-traversal | SOP: Styx Pipeline Traversal (The 7-Organ Transmutation) |
| system | any | system-dashboard-telemetry | SOP: System Dashboard Telemetry (The Panopticon Protocol) |
| system | any | the-descent-protocol | the-descent-protocol |
| system | any | the-membrane-protocol | the-membrane-protocol |
| system | any | theoretical-concept-versioning | SOP: Theoretical Concept Versioning (The Epistemic Protocol) |
| system | any | theory-to-concrete-gate | theory-to-concrete-gate |
| system | any | triangulation-protocol | triangulation-protocol |
| system | any | typological-hermeneutic-analysis | SOP: Typological & Hermeneutic Analysis (The Archaeology) |
| unknown | any | SOP-001-vector-pipeline-activation | SOP-001: Vector Pipeline Activation |
| unknown | any | cicd-resilience | SOP: CI/CD Pipeline Resilience & Recovery |
| unknown | any | corpus-ontology-instantiation | SOP: Corpus Ontology Instantiation |
| unknown | any | ira-grade-norming | SOP: Diagnostic Inter-Rater Agreement (IRA) Grade Norming |
| unknown | any | ira-grade-norming | ira-grade-norming |
| unknown | any | SOP-GENESIS-TEMPLATE | SOP: Genesis Template (SPEC-023) |
| unknown | any | SOP-TRIADIC-REVIEW-PROTOCOL | Triadic Review Protocol (TRP) |

Linked skills: SOP-TRIADIC-REVIEW-PROTOCOL, cicd-resilience-and-recovery, continuous-learning-agent, evaluation-to-growth, genesis-dna, multi-agent-workforce-planner, promotion-and-state-transitions, quality-gate-baseline-calibration, repo-onboarding-and-habitat-creation, session-self-critique, structural-integrity-audit, the-membrane-protocol, triple-reference


**Prompting (Anthropic)**: context 200K tokens, format: XML tags, thinking: extended thinking (budget_tokens)


## Ecosystem Status

- **delivery**: 2/2 live, 0 planned
- **content**: 0/2 live, 1 planned
- **community**: 1/1 live, 0 planned

Run: `organvm ecosystem show organvm-engine` | `organvm ecosystem validate --organ META`


## External Mirrors (Network Testament)

- **technical** (1): yaml/pyyaml

Convergences: 0 | Run: `organvm network map --repo organvm-engine` | `organvm network suggest`


## Atomization Pipeline

Run `organvm atoms pipeline --write && organvm atoms fanout --write` to generate task queue.


## System Density (auto-generated)

AMMOI: 25% | Edges: 0 | Tensions: 0 | Clusters: 0 | Adv: 0 | Events(24h): 4365
Structure: 8 organs / 150 repos / 1654 components (depth 17) | Inference: 0% | Organs: META-ORGANVM:64%, ORGAN-I:53%, ORGAN-II:48%, ORGAN-III:55% +5 more
Last pulse: 2026-10-24T14:40:53 | Δ24h: vacuum | Δ7d: vacuum


## Dialect Identity (Trivium)

**Dialect:** SELF_WITNESSING | **Classical Parallel:** The Eighth Art | **Translation Role:** The Witness — proves all translations compose without loss

Strongest translations: I (formal), IV (structural), V (analogical)

Scan: `organvm trivium scan META <OTHER>` | Matrix: `organvm trivium matrix` | Synthesize: `organvm trivium synthesize`


## Logos Documentation Layer

**Status:** MISSING | **Symmetry:** 0.5 (GHOST)

Nature demands a documentation counterpart. This formation maintains its narrative record in `docs/logos/`.

### The Tetradic Counterpart
- **[Telos (Idealized Form)](../docs/logos/telos.md)** — The dream and theoretical grounding.
- **[Pragma (Concrete State)](../docs/logos/pragma.md)** — The honest account of what exists.
- **[Praxis (Remediation Plan)](../docs/logos/praxis.md)** — The attack vectors for evolution.
- **[Receptio (Reception)](../docs/logos/receptio.md)** — The account of the constructed polis.

### Alchemical I/O
- **[Source & Transmutation](../docs/logos/alchemical-io.md)** — Narrative of inputs, process, and returns.

- **[Public Essay](https://organvm-v-logos.github.io/public-process/)** — System-wide narrative entry.

*Compliance: Implementation exists without record.*

<!-- ORGANVM:AUTO:END -->
