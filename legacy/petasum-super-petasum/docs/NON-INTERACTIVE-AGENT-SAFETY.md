# Non-Interactive Agent Safety Protocol

> **Governance**: Commandment #18 — Bounded Autonomous Execution
> **Scope**: All non-interactive agent sessions across the eight-organ system
> **Version**: 1.0

---

## Definitions

**Non-interactive agent**: Any agent session that runs without a human-in-the-loop
(HITL). This includes background agents, scheduled agents, auto-sync processes, and
any session where the human operator is not actively reviewing each action.

**Interactive agent**: A session where a human reviews and approves each significant
action before it proceeds (e.g., a Claude Code CLI session with the user present).

The constraints in this document apply **only to non-interactive sessions**. Interactive
sessions are governed by the standard session protocol (`orchestration-start-here/docs/session-protocol.md`).

---

## Scope Constraints

### One Repo Per Session

A non-interactive agent session MUST operate within a single repository directory.
The working directory is locked at session start and cannot change.

- The repo path is declared in the session manifest before execution begins
- File reads outside the repo are permitted (e.g., reading a shared config)
- File **writes** outside the declared repo scope trigger immediate rollback
- Code-level enforcement: `agent--claude-smith` ScopeValidator (F-35)

### Cross-Organ Impulse Protocol

When a non-interactive agent discovers work that belongs in a different repo or organ:

1. **Do not act** on the cross-repo work
2. **Capture** the impulse as a GitHub issue in the target repo
3. **Continue** with the current session's declared scope
4. **Log** the impulse in the session audit record

This prevents cascading writes across repos from a single unattended session.

---

## Mandatory Dry-Run

Before performing any write operations, non-interactive sessions MUST:

1. Execute a dry-run pass that simulates all planned changes
2. Log the dry-run output (files that would be created/modified/deleted)
3. Compare the dry-run plan against the session's declared scope
4. Abort if any planned writes fall outside scope

The dry-run is not optional. Skipping it violates Commandment #18.

---

## Budget Caps

Every non-interactive session declares at start:

- **Token budget**: Maximum LLM tokens (input + output) for the session
- **Wall-clock timeout**: Maximum elapsed time before forced termination

Exceeding either budget triggers:

1. Immediate halt of the agent's execution
2. Rollback of any uncommitted changes
3. Session marked as `failed` with budget-exceeded reason
4. Audit record updated with actual usage vs. declared budget

---

## Rollback Triggers

The following conditions trigger automatic rollback of uncommitted changes:

| # | Trigger | Severity |
|---|---------|----------|
| 1 | Git merge conflict detected | CRITICAL |
| 2 | CI failure on committed changes | HIGH |
| 3 | File write outside declared scope | CRITICAL |
| 4 | Token or time budget exceeded | HIGH |
| 5 | Unhandled exception | CRITICAL |
| 6 | Session timeout | HIGH |

**Rollback procedure:**
1. `git checkout -- .` to discard uncommitted changes
2. If commits were made, `git reset --soft HEAD~N` to unstage (preserve for review)
3. Log the rollback event with trigger reason
4. Update session status to `rolled_back`

---

## Audit Requirements

Every non-interactive session MUST produce an audit record containing:

| Field | Description |
|-------|-------------|
| `session_id` | Unique session identifier |
| `agent_name` | Name/ID of the agent |
| `agent_type` | `non-interactive` |
| `repo_path` | Declared working directory |
| `start_time` | ISO 8601 timestamp |
| `end_time` | ISO 8601 timestamp |
| `files_read` | List of files read during session |
| `files_written` | List of files created/modified |
| `rollback_events` | Any rollback triggers that fired |
| `cross_organ_impulses` | Issues created in other repos |
| `token_usage` | Actual tokens consumed |
| `exit_status` | `success`, `failed`, `rolled_back`, `timeout` |

The audit record format is defined in F-57 (Agent Run Logging Standard).
Until F-57 is implemented, a JSON file at `$SESSION_DIR/audit.json` is acceptable.

---

## Relationship to Other Governance

- **Commandment #17** (Non-Destructive Autonomy): Applies to all agents. #18 adds
  scope and budget constraints specific to non-interactive sessions.
- **Commandment #18** (Bounded Autonomous Execution): This document is the detailed
  protocol referenced by that commandment.
- **Amendment E** (Session Lifecycle Mandate): Non-interactive sessions follow a
  compressed lifecycle — FRAME and SHAPE occur at scheduling time, not runtime.
- **Amendment F** (Agent Coordination Visibility): Breadcrumbs are mandatory at
  session completion, including for non-interactive sessions.

---

## References

- `COMMANDMENTS.md` — Commandment #17 (Non-Destructive Autonomy), #18 (Bounded Autonomous Execution)
- `orchestration-start-here/docs/session-protocol.md` — Interactive session checklist
- `orchestration-start-here/docs/breadcrumb-protocol.md` — Breadcrumb format (F-06)
- `agent--claude-smith/src/core/scope-validator.ts` — Code-level enforcement (F-35)
- `orchestration-start-here/governance-rules.json` — Amendment F
