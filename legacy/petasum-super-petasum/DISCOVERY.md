# Discovery: organvm/petasum-super-petasum

**Discovered:** 2026-06-22 | **Verdict:** REAL VALUE — promoted to ranked tier

## Value Thesis

`petasum-super-petasum` is the **only working cross-organ governance CLI in the ORGANVM estate**: a Python package (`python -m src evaluate|audit|report --registry registry.json`) that ingests any registry JSON, runs CI health and documentation coverage checks across all organs, tracks promotion obligations via `ObligationTracker`, and emits structured markdown reports per-organ or system-wide. The `logic-rules.json` file encodes the entire five-level principle hierarchy (Logic → Foundational → Operational → Community → Stability, 16 principles with explicit logical derivations and conflict resolution protocol) as machine-readable JSON — making it directly importable by any governance agent that needs a decision framework rather than a prose document. The GitHub infrastructure kit (9 issue templates, 3 automated workflows, label taxonomy) is a second distinct asset: a copy-ready governance layer for any ORGAN that needs structured cross-repo issue routing. The highest latent value is the Python CLI wired to the live ORGANVM registry: pointing `python -m src report --registry registry-v2.json` at the actual estate would produce the first automated, machine-generated system health report across all 89 active repos — a capability no other ORGAN-IV repo currently provides.

## Highest Latent Value

**Cross-organ governance API** — `src/governance.py` + `src/tracker.py` + `src/report.py` form a real automation substrate. Any orchestration agent can `pip install -e .` and call `check_ci_health()`, `check_documentation_coverage()`, `GovernanceReport`, `ObligationTracker`, and `generate_system_report()` directly. The optional integration with `organvm_engine.governance.audit` (graceful fallback if not installed) makes this a first-class extension point for the engine layer.

## Best Concrete First Task

**Wire the CLI to the live registry and run it in CI.** Concretely: add a CI step that runs `python -m src report --registry <path-to-registry-v2.json> -o governance-report.md` and uploads the result as a workflow artifact. This proves the pipeline end-to-end and produces the first live governance snapshot of the full estate from this tool.
