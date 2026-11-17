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


**Prompting (Google)**: context 1M tokens (Gemini 1.5 Pro), format: markdown, thinking: thinking mode (thinkingConfig)


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










## ⚡ Conductor OS Integration
This repository is a managed component of the ORGANVM meta-workspace.
- **Orchestration:** Use `conductor patch` for system status and work queue.
- **Lifecycle:** Follow the `FRAME -> SHAPE -> BUILD -> PROVE` workflow.
- **Governance:** Promotions are managed via `conductor wip promote`.
- **Intelligence:** Conductor MCP tools are available for routing and mission synthesis.