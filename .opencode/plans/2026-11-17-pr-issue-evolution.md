# PR / Issue Evolution Report — `organvm-engine`

**Date:** 2026-11-17  
**Stream:** B (PR / Issue Evolution) of the Autonomous Ecosystem Retirement & Enrichment plan  
**Method:** full remote inventory via `gh` (all states), heuristic supersession detection, local git/oss evidence. Machine-readable evidence: `.opencode/plans/stream-b/2026-11-17-pr-issue-data.json`  
**Staging run:** `09_Engineering/custody-staging/run-20261117-104235-session-retirement/`

> Supersession links below are **evidence-backed candidates**, not licensed merges. No remote PR was closed and no history was rewritten by this pass. Destructive actions are listed as ready-to-run commands for the owner or the orchestration stream.

## 1. Repository state

| Field | Value |
|---|---|
| Local path | `/Volumes/Archive4T/Projects/organvm-engine` |
| GitHub remote | `4444J99/organvm-engine` |
| Upstream archived | no |
| Default branch (remote) | main |
| Local branch | `main` |
| Dirty files | 0 |
| Linked worktrees | 1 (canonical checkout) |
| Last commit | 2026-11-17T08:18:44 — feat(contextmd): guard sync file creation and add migrate-legacy comma |
| Plan surfaces | .codex/plans, .claude/plans |

## 2. PR inventory

| Metric | Count |
|---|---|
| PRs (all states) | 124 |
| Merged | 96 |
| Open | 1 |
| Closed unmerged | 27 |

Closed-unmerged classification:

| Class | Count |
|---|---|
| producer retired (Limen/Jules) | 16 |
| superseded (rewrite series) | 7 |
| closed without successor | 4 |

## 3. Evolution decisions (old → new)

| Old PR | Old title | Successor | Basis |
|---|---|---|---|
| #86 | chore(deps): bump the all-actions group across 1 directory with 2 update | #145 | superseded (rewrite series) |
| #99 | [limen LIMEN-060] feat: implement MCP tool wrappers for all 5 organvm CL | #112 | superseded (rewrite series) |
| #101 | [limen LIMEN-049] feat: handoff staleness detection and workspace-wide h | #117 | superseded (rewrite series) |
| #105 | [limen LIMEN-050] feat: context sync diff/changelog between runs | #120 | superseded (rewrite series) |
| #125 | [limen LIMEN-065] feat: exit interview testimony for documentation-only  | #134 | superseded (rewrite series) |
| #126 | [limen LIMEN-048] feat: SOP staleness detection cross-reference SOPs aga | #143 | superseded (rewrite series) |
| #127 | [limen LIMEN-070] network: R3 kinship mirror research — community identi | #131 | superseded (rewrite series) |

### Repo-level absorptions

| Archived source | Lives now at | Evidence |
|---|---|---|
| 4444J99/cvrsvs-honorvm (archived upstream) | this repo, `legacy/` | commit 175210b `chore(legacy): import scrubbed snapshot of cvrsvs-honorvm (#219)` |

## 4. Items marked archived

- **96 merged PRs** — resolved, no action; history is the archive.
- **7 closed-unmerged PRs with a traced successor** — archived as superseded; each row in §3 is a complete old → new mapping.
- **16 Limen/Jules PRs closed without successor** — archived by producer retirement. Limen is retired by standing rule; these branches have no surviving producer and no merge path.
- **4 PRs closed without a traced successor** — archived as abandoned. Titles are retained in the evidence file in case a later re-cut needs the original scope.

## 5. Open PR triage

| PR | Title | State | Idle | Recommended action |
|---|---|---|---|---|
| #214 | chore(deps): bump actions/checkout from 4.4.0 to 7.0.1 in the all- | ready | -1d | keep |

## 6. Issues

| Metric | Count |
|---|---|
| Issues (all states) | 113 |
| Open | 43 |
| Open and idle > 45 days | 28 |

Most common labels on open issues: `CI/CD` (2), `P1:important` (3), `P2:standard` (4), `chore` (2), `cross-repo` (2), `descent-protocol` (3), `domain:testament` (3), `effort:large` (3).

Longest-idle open issues (sample):

| Issue | Title | Idle |
|---|---|---|
| #55 | feat: Ring 4 — external chain anchoring (Base L2 / Celestia) | 121d |
| #42 | Submit conference talk proposals — omega #14 pathway | 121d |
| #54 | feat: Stakeholder Portal /testament/ route | 112d |
| #49 | feat: testament sonic bridge — OSC to alchemical-synthesizer | 112d |
| #41 | Fix soak-test LaunchAgent — gh CLI auth fails under launchd | 112d |
| #200 | [distribution] Which audience, search journeys and feedback loops fit Engine's | 64d |
| #199 | [operations] Which cost, access, dependency, legal and privacy obligations bel | 64d |
| #198 | [operations] Can Engine detect failure, recover data and support users without | 64d |

## 7. Follow-up flags

- Only open PR is a dependabot bump; the rest of the backlog is issues (43 open).

## 8. Provenance and limits

- PR/issue inventory: `gh pr list`/`gh issue list --state all` for `4444J99/organvm-engine`, captured 2026-11-17.
- Supersession classes: explicit `supersedes #N` in title; dependency retry (same package + directory, newer bump merged); rewrite series (identical title stem, later PR merged); producer retirement (Limen/Jules branch, no successor); otherwise abandoned.
- Heuristic limit: a title-stem match can link two genuinely different changes. Treat §3 as a review queue, not as settled provenance.
- No remote mutation was performed: no PR closed, no issue closed, no branch deleted.
