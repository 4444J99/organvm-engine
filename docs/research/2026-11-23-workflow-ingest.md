# Research evidence: workflow ingestion proves complete source coverage

Issue: #190 (parent #188; depends on #183 and canonical resolver #172).
Plan: issue comment 6978075819, treated as a one-take draft and re-verified
at main `53d00d00` before building. Owning implementation: this change.

## What was live

At main `53d00d00`, `ci/workflow_intelligence.py` (`inventory()` / `drift()`,
745 lines) had zero production callers: nothing in `src/` imported the
module, no CLI subcommand wired it, and
`.github/workflows/monthly-infrastructure-audit.yml` never called it. No
collector module existed anywhere in the 1,232-file tree, and no
freshness/retention budget was defined anywhere. #172 (canonical corpus
resolver: `registry/loader.py` + `repo-registry.json`) and #183 (the
false-evidence family, verified fixed and closed 2026-11-23) are the
preconditions this build stands on.

## What changed

New `ci/workflow_ingest.py` is the minimal trusted collector the plan calls
for. It pins identity first (the GitHub API repo id, verified against the
caller-pinned `--repository-id`; the OE id is `1160447354`), enumerates the
workflow set from the pinned tree (full recursive listing; a truncated
response fails the collection), fetches each file's bytes and verifies them
against Git object identity (contents blob SHA must equal the tree entry's
blob SHA), and hands the fetched files to the existing `inventory()` — the
analysis is wired, not duplicated. New `organvm ci workflow-inventory` is
the one narrow call site, with `--restore-from` for the restore proof.

## The budget, and why these numbers

- A snapshot is stale after **35 days**: the collection cycle runs on the
  1st of each month, so 35 days is one cycle plus grace. A snapshot older
  than that cannot be the latest cycle's output and must not be trusted as
  fresh.
- At most **3 cycles are retained**: `drift()` needs two snapshots and
  restore needs one spare. The workflow artifact retention is 90 days, the
  same as the monthly audit's.
- Enumeration completeness and analyzed-file coverage stay separate fields,
  exactly as `inventory()` returns them: `coverage` reads `complete` only
  when the enumeration is complete AND every expected path analyzed.

## What the counterexamples proved

- Transfer/rename: an API repo id that disagrees with the pin is rejected,
  not reinterpreted.
- Duplicate pages / stale revision: a contents blob SHA that disagrees with
  the tree entry is rejected.
- Rate/permission failure: an HTTP 403 fails the collection closed; no
  unauthenticated fetch is attempted, and a missing token fails before any
  fetch.
- Symlink/path escape: refused loudly — a trust-boundary event, not
  ordinary missing data.
- Partial data: a fetch 404 stays `unavailable` and an over-budget file
  stays `truncated` in the envelope; the snapshot never collapses either
  into success or deletion. `drift()` between two cycles reads a
  still-enumerated but un-fetchable path `unavailable_comparison`, and a
  path genuinely absent from a complete enumeration at a new revision
  `removed_from_enumeration` — the distinction #183's CE3 turns on.
- Partial restore: a retained file changed after the cycle breaks the
  digest match; `rebuild_snapshot()` re-runs `inventory()` on the retained
  files and compares digests, so the retained artifact is the evidence,
  not a second source of truth.
- Privacy-export: the envelope never contains the token.

## Deviations from the plan, recorded

1. The plan's step 1 names the canonical resolver (`loader.py` +
   `repo-registry.json`) as the source of stable repository identity. The
   registry carries no numeric GitHub id per entry, and the corpus repo is
   not checked out on a bare runner — so identity is pinned from the API
   repo object, and the registry is an *optional* join (`--registry`) for
   tier/dependency data only. When no registry is supplied, those fields
   record `unknown` with the reason instead of being invented. The
   registry's `tier` is recorded as-is; no criticality number is derived
   from it.
2. The plan's step 6 allows hosting the cycle in
   `monthly-infrastructure-audit.yml` or a new workflow. A new
   `.github/workflows/workflow-inventory.yml` (monthly schedule +
   `workflow_dispatch`) hosts it instead: the monthly audit requires the
   canonical registry, which is not available on a bare runner, and the
   inventory cycle must run standalone. Fixing the audit's registry
   dependency is separate work, not this issue's.
3. The plan's acceptance asks for two real collection-cycle artifacts "on
   default". Nothing may be pushed to default before merge (merges are
   Anthony's call), so the two observed cycles ran on the PR branch via
   `workflow_dispatch`; their run ids are recorded in the PR. The monthly
   schedule runs the cycle on default after merge.

## Observed cycles

Two `workflow-inventory` runs dispatched on the PR branch (run ids in the
PR body). Each uploaded a `workflow-inventory-<run_id>` artifact holding
the envelope + retained file bytes; `drift()` between the two snapshots and
the restore-from-artifact rebuild are both recorded in the PR.
