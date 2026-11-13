# Atom integrity and corpus discovery

Owner is the November 9 request in portfolio conversation 01a18468-ef06-7132-be5b-4e8fa4684859. Engine source is 4444J99/organvm-engine. Stored atom records and the manifest belong to 4444J99/organvm-corpvs-testamentvm.

1. Reproduce collisions, manifest mutation timing and corpus fallback. Inventory every affected reference before migration.
2. Add focused regression coverage for stable collision disambiguation before dependency wiring, manifest hashing after reconciliation and corpus discovery through the managed shelf.
3. Preserve the first existing ID in each collision group and assign deterministic source-line-derived IDs to subsequent records. Preserve all other fields and verify reference mappings and record counts.
4. Reconcile manifest evidence against actual bytes and explicitly retain missing inputs and previous recorded hashes. Preserve the prior manifest in Git history.
5. Verify focused tests, repeatable migration, record and reference integrity, and publish each owning repository through its merge protocol.

Verification observed three failing regression cases before implementation, then 164 focused path, parser, pipeline, link, research and rollup tests passing. Ruff checks passed. The managed shelf resolved the actual task file without environment overrides. The corpus migration verified all 18,448 records and 83,729 links, with 213 source-line ID mappings and available manifest hashes. The historical annotated prompts file is absent and 6,731 existing priority entries lack a task match.

The follow-up restored the private dependency read route using a repository-scoped read-only deploy key. Hosted checkout and spec-compliance rerun succeeded. Review fixes defer research activation until atomic task persistence, preserve linked task identity boundaries, distinguish colliding global plans, report duplicate IDs at the CLI, and remove stale hashes on missing files. Three existing Ruff findings in unrelated modules were simplified without changing their intended branches so the required CI lint can run. Regression cases reproduce each issue and focused suites pass.
