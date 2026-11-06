# Explore vs Production Modes

> **Governance**: Commandment #3 (AI as Instrument, Not Oracle), #5 (Discipline Over Drift)
> **Scope**: All AI-mediated work sessions across the eight-organ system
> **Version**: 1.0
> **Backlog**: F-42

---

## Why This Exists

Not all work has the same risk profile. A brainstorming session exploring architectural
options is fundamentally different from a session producing code that will ship to
production. Treating both identically leads to one of two failures: exploratory work
is stifled by governance overhead, or production work is exposed to the loose
practices of exploration.

Two modes resolve this: **Explore** for discovery and experimentation, **Production**
for verified, governed output. The boundary between them is explicit, auditable,
and never crossed without human review.

---

## Mode Definitions

### Explore Mode

**Purpose**: Discovery, experimentation, research, brainstorming, spike work.

| Property | Setting |
|----------|---------|
| Constraints | Loose — encourage divergent thinking |
| Variance | High — try multiple approaches |
| Temperature | Higher (0.7–1.0) for creative tasks |
| Git branches | Prefixed `spike/` or `explore/` |
| Merge to main | Never directly — requires promotion review |
| Session records | Breadcrumbs only (lightweight notes) |
| Governance checklist | Not required |
| Linked issues | Optional |
| Acceptance criteria | None — output is evaluated qualitatively |
| Output classification | Draft — not canonical until promoted |

**Typical Explore activities**:
- Researching a new library or framework
- Brainstorming feature approaches
- Prototyping a UI concept
- Exploring data with ad-hoc queries
- Testing prompt strategies
- Spiking a technical approach to assess feasibility

### Production Mode

**Purpose**: Shipping features, fixing bugs, writing documentation, any work that
will become canonical.

| Property | Setting |
|----------|---------|
| Constraints | Strict — follow all governance rules |
| Variance | Low — deterministic, reproducible |
| Temperature | Lower (0.0–0.3) for code, moderate for prose |
| Git branches | `feature/`, `fix/`, `docs/` prefixes |
| Merge to main | Via PR with review |
| Session records | Full AI interaction manifest (F-43) |
| Governance checklist | Required before merge |
| Linked issues | Required |
| Acceptance criteria | Defined before work begins |
| Output classification | Canonical upon merge |

**Typical Production activities**:
- Implementing a feature from a backlog item
- Fixing a reported bug
- Writing or updating documentation
- Refactoring code with test coverage
- Security patching
- Release preparation

---

## The Promotion Boundary

The most critical rule in the two-mode system:

> **Exploratory output is never merged directly into main.**

Promotion from Explore to Production follows this protocol:

1. **Review**: Human reviews all explore-mode output
2. **Assess**: Determine what (if anything) is worth keeping
3. **Extract**: Cherry-pick or rewrite valuable discoveries into a new production branch
4. **Govern**: Apply full production governance (tests, types, lint, review)
5. **Merge**: Standard PR process with linked issue

This prevents half-baked experimental code from contaminating production artifacts.
It also forces a deliberate decision point — the human must actively choose to
promote, not passively allow drift.

---

## Git Branch Conventions

### Explore Branches

```
spike/explore-vector-db-options
spike/prototype-dashboard-layout
explore/test-prompt-chaining
spike/2026-03-research-gateway
```

Explore branches:
- Are never merged to `main`
- May be deleted after extraction or retained for reference
- Do not require CI to pass (though it may run)
- Should include a brief `SPIKE.md` describing the goal and findings

### Production Branches

```
feature/ai-gateway-preprocessor
fix/redaction-engine-edge-case
docs/update-classification-tiers
refactor/simplify-router-logic
```

Production branches:
- Require linked issue
- Must pass CI
- Require PR review before merge
- Follow conventional commit messages

---

## Mode Selection Rules

### Default Mode

If no mode is explicitly declared, assume **Production mode**. This is the safe
default — it is better to over-govern than to under-govern.

### Declaring Mode

At the start of any AI-assisted work session, declare the mode:

- In Claude Code sessions: state "This is an explore/production session" at the start
- In conductor-managed sessions: the `session_type` field records the mode
- In git: the branch prefix (`spike/` vs `feature/`) signals the mode

### Switching Modes

Mode switches within a session are discouraged but sometimes necessary:

- **Explore to Production**: Stop. Create a new branch. Apply governance. Resume.
- **Production to Explore**: Stop. Create a `spike/` branch. Note the context switch.
  Do not continue production work in an explore branch.

Never mix modes in the same branch or the same commit.

---

## AI Configuration by Mode

### Temperature and Sampling

| Parameter | Explore | Production |
|-----------|---------|------------|
| Temperature | 0.7–1.0 | 0.0–0.3 |
| Top-p | 0.9–1.0 | 0.8–0.9 |
| Max tokens | Generous | Bounded to task |
| Stop sequences | None | Task-specific |

### Model Selection

| Task Type | Explore | Production |
|-----------|---------|------------|
| Brainstorming | Large creative model | N/A |
| Code generation | Any model for prototyping | Best available model with low temperature |
| Analysis | Varied — try multiple models | Consistent model for reproducibility |
| Simple tasks | Cheap/fast model | Cheap/fast model (same) |

### Prompt Style

| Element | Explore | Production |
|---------|---------|------------|
| Constraints | Minimal | Comprehensive |
| Output format | Flexible | Strict template |
| Self-check | Optional | Required |
| Examples | Optional | Recommended |

---

## Lifecycle Integration

The two-mode system maps to the Score/Rehearse/Perform lifecycle:

| Lifecycle Phase | Mode | Rationale |
|----------------|------|-----------|
| **Score** (planning) | Explore | Divergent thinking to identify approach |
| **Rehearse** (prototyping) | Explore → Production transition | Validate approach, then formalize |
| **Perform** (shipping) | Production | Strict governance, deterministic output |

See `score-rehearse-perform.md` for the full lifecycle model and
`conductor-playbook.md` for session management details.

---

## Anti-Patterns

| Anti-Pattern | Description | Fix |
|-------------|-------------|-----|
| Permanent spike | Explore branch that never gets promoted or deleted | Time-box spikes (max 1 week), then decide |
| Stealth production | Doing production work on an explore branch | Always use correct branch prefix |
| Explore theater | Declaring explore mode to avoid governance on production work | Mode is determined by intent, not convenience |
| Over-governed exploration | Applying full governance to brainstorming | Trust the mode separation — explore is meant to be loose |

---

## Cross-References

- `score-rehearse-perform.md` — Lifecycle phases that map to modes
- `conductor-playbook.md` — Session management and mode tracking
- `ai-gateway-architecture.md` — Gateway adjusts behavior based on mode (F-40)
- `ai-interaction-manifest.md` — Session records differ by mode (F-43)
- `prompt-template-library.md` — Template selection varies by mode (F-41)
- `prompt-anti-patterns.md` — Temperature Mismatch anti-pattern (F-71)
