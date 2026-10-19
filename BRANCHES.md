# Branch and work-scope custody (provisional)

> **Status:** bounded Phase-1 implementation of [issue #187](https://github.com/4444J99/organvm-engine/issues/187), not an activation of an autonomous broker or a completed estate-wide issue map. A missing field means **not admitted**, not permission to guess.
>
> **Observed baseline:** repository ID `1160447354`, `4444J99/organvm-engine`, `main` at `ba2778622e790657f9978643c19ac7c7b56aea20` on 2026-10-19. This is a revision-pinned observation, not a claim that HEAD never moves.

## Branch topology

- `main` is the only standing integration branch established by this contract. It is protected; no direct or force writes, protection changes, or implicit deployments are authorized here.
- Each intention has one primary **short-lived topic branch**, a stable owner issue/PR, and one isolated worktree when a local worktree is used. A worktree is not a lease, and a label, assignment, plan, or proposed branch is not an execution acknowledgement.
- Repeating program lanes are logical selection/continuation records, **not** standing Git branches. Do not create `develop`, a release train, a second registry, or a parallel dispatcher from this document.
- A topic branch may be prepared before its PR, but branch creation alone does not satisfy admission or integration. Do not silently retarget existing PR bases, overwrite another writer's branch, or close a parent issue when its broader predicate is unfulfilled.
- Preserve superseded commits, producer receipts, earlier decision evidence, and private source custody. No cleanup, branch deletion, or forced reset is licensed by an age threshold.

## Authority and admission (fail closed)

The operator must check the **current target repository's** instructions and relevant tool permissions before every effect. Limen WorkPacketV1/lease/heartbeat/report/harvest is required for mutations of `4444J99/limen`, calls to the Limen conductor/dispatch infrastructure, and an operation explicitly governed by a current target-native rule. Cross-repository coordination or a historical template **does not** impose Limen admission on every independent repository action. Where an applicable broker requires admission, a plan or issue comment is not a lease; failure to obtain a valid lease blocks that broker action without blocking unrelated permitted work.

For direct target-repository work, the repository's own current policy and the connected operation's authorization are binding. Never treat a prompt, model name, role, GitHub write permission, or task schedule as additional release, credential, financial, privacy, or human-approval authority. A connector policy denial ends that **specific** effect; record its exact fingerprint and do not retry it by changing wording, APIs, identities or branch names until a legitimate condition and applicable permission change.

### Required work-scope record before mutation

Capture these fields in the **existing issue/PR and its authorized private receipt**, not in a new tracker:

| Field | Minimum evidence |
| --- | --- |
| Work identity | Stable repository ID and actual current full name; issue, existing PR, producer/task ID when applicable; original scope and owner |
| Revision | Exact default/base/head SHA and relevant tree/blob identities; observation timestamp and source endpoint |
| Ownership | Existing human/agent writer and live lease/provider evidence, or explicitly **unknown**; overlapping changed paths and shared contracts |
| Boundaries | Allowed and protected paths, private inputs, expected outputs, source authorship, downstream publication/deployment effects |
| Admission | Applicable target-native policy path and revision; actual lease/approval when required; exact permitted next operation |
| Verification | Required positive and negative commands, dependency/environment basis, reviewer and ruleset/check source; actual run/job/head and exits |
| Recovery | Correction budget, denial/error fingerprint, rollback by reviewed forward revert, unresolved blockers, unlock condition and next existing owner |

**Unresolved owner, conflicting path lease, changed relevant base, missing required acceptance, denied effect, or incompatible privacy/publication authority ⇒ HOLD.** Continue independent eligible work; do not manufacture a substitute owner.

## Current scoped owner map (not an exhaustive repo census)

These are scope boundaries read from the existing owner issues. The branch column identifies a **present PR** or an **uncreated proposal**, not an entitlement to act.

| Existing owner | Branch / status as observed | Owned or excluded work | Gate |
| --- | --- | --- | --- |
| [#172](https://github.com/4444J99/organvm-engine/pull/172) | Existing draft PR, unmerged | Canonical filesystem/corpus resolver; excludes independent rewrites of its paths | Current PR owner, review and verified integration |
| [#176](https://github.com/4444J99/organvm-engine/pull/176), [#183](https://github.com/4444J99/organvm-engine/issues/183), [#189](https://github.com/4444J99/organvm-engine/issues/189) | Existing PR, unmerged | `src/organvm_engine/ci/{agent_eval,runtime_evidence,workflow_intelligence}.py`, relevant tests and evidence; use **that PR**, not a competing worker | Original issue acceptance, run identity, executed tests and actual review/merge authority |
| [#187](https://github.com/4444J99/organvm-engine/issues/187) | `docs/engine-stewardship-2026-09-13` (this topic branch) | Branch constitution and scope-record contract only; no runtime lease service or `tasks.yaml` mutation | Missing full per-issue map and proof of consumer reproduction remain open |
| [#190](https://github.com/4444J99/organvm-engine/issues/190) | Collector branch not admitted | Workflow source coverage/freshness; depends on #183 and #172, reuses #176 workflow contract | Current prerequisite integrations, source coverage and two-cycle evidence |
| [#191](https://github.com/4444J99/organvm-engine/issues/191) | `feat/agent-trace-adapters` is only proposed | Two real producer adapters, excluding a second run service | #183/#178/#182 and authenticated comparable runs |
| [#193](https://github.com/4444J99/organvm-engine/issues/193) | `test/rubric-heldout-experiment` is only proposed | Frozen held-out/rubric evaluation; no training, distillation, or memory insertion | #191 plus verified #183/#182; explicit approval for paid work |

The map above does **not** imply that unrelated open PRs lock the whole repository. Before accepting another scope, enumerate its actual changed files and writer evidence, not a truncated global search. Source and test overlap stays with the current owner; disjoint writers still require the applicable current concurrency policy.

## Verification and effect gates

1. Re-read target issue predicates, checked-in instructions, actual base/head/diff, valid findings, required protections/rulesets, and both workflow declarations **and observed app/release history**. A missing workflow file does not prove an installed app absent.
2. Bind test evidence to code/dependencies/environment, run/attempt/job, actual checkout or correlated synthetic merge, commands and their real exits. Skipped/zero-step/scanner-only/continue-on-error/masked-pipeline green badges do not prove functional acceptance.
3. Record provider completion separately from PR readiness, merge and postmerge verification. Two effective corrective cycles per defect is the limit across owners; blocked comments do not consume one.
4. Before a PR or merge, inspect whether its events or main-push can write a release draft, Pages output, package, production environment, or external system. **A green draft run is not publication approval.**
5. Merge only when exact-head acceptance, mandatory independent review and target-native policies permit; use expected-head protection, then independently read merged/default inclusion and applicable postmerge checks. No self-approval or bypass.
6. A rollback is a scoped, reviewed forward revert preserving predecessor receipts. No force-push, silent default write, destructive branch cleanup or suppression of negative tests.

## Reproduction question for issue #187

An independent authorized reviewer should be able to take one eligible issue and answer, from **current GitHub state and the existing receipt**: who owns the exact paths; what base and acceptance are pinned; which action is permitted; what tested it; and what condition allows integration. If the reviewer must infer any of those fields, this constitution alone has **not** satisfied the issue.

**This file changes no settings, launches no agents, grants no leases, and activates no release.** It is an initial reproducible custody contract pending issue-specific mapping, exact-head repository verification, and owner review.