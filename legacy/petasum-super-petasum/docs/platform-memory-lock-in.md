# Platform Memory Lock-In

> **Governance**: Commandment #2 (Privacy & Security First), #13 (Interoperability), #17 (Non-Destructive Autonomy)
> **Scope**: All AI platform persistent memory used across the eight-organ system
> **Version**: 1.0
> **Backlog**: F-48

---

## Why This Exists

AI platforms increasingly offer persistent memory — context that survives across
sessions, shaping how the model responds to future interactions. This is useful:
it eliminates repetitive setup, enables continuity, and makes the AI feel like a
collaborator rather than a stateless function.

It is also a lock-in trap. When your working context, preferences, project
knowledge, and institutional memory live inside a platform's proprietary memory
system, switching providers means starting from zero. Worse, the memory is
often opaque — you cannot see exactly what the platform "remembers," cannot
export it in a structured format, and cannot audit it for stale or incorrect
information.

This document catalogs the risks and defines ORGANVM's mitigation strategy.

---

## Platform Memory Landscape

### ChatGPT Memory

- **Mechanism**: Persistent profile that accumulates facts across conversations.
  The model decides what to "remember" based on conversation content.
- **Visibility**: Partial — users can view stored memories in Settings, but the
  representation is summarized, not verbatim.
- **Export**: No structured export. Individual memories can be viewed and deleted,
  but there is no bulk export to a portable format.
- **Scope**: Global — memories apply to all conversations. No project-level
  isolation.
- **Control**: Users can delete individual memories or clear all. No granular
  editing of memory content.
- **Audit**: Difficult — no changelog of when memories were created or modified.

### Claude Memory (Projects)

- **Mechanism**: Project-scoped instructions and knowledge files. Users explicitly
  define what the model knows via project configuration.
- **Visibility**: Full — project instructions are authored by the user and visible
  at any time. MEMORY.md files are auto-maintained but readable.
- **Export**: Project instructions are text files. MEMORY.md is a Markdown file
  in the project configuration.
- **Scope**: Project-isolated — knowledge in one project does not leak to another.
- **Control**: Users have full editorial control over project instructions.
  MEMORY.md entries can be reviewed and pruned.
- **Audit**: Git-trackable when instructions are derived from version-controlled
  files (CLAUDE.md).

### Copilot Memory

- **Mechanism**: Varies by product (GitHub Copilot, Microsoft 365 Copilot).
  GitHub Copilot uses repository context and custom instructions. Microsoft 365
  Copilot uses organizational graph data.
- **Visibility**: Partial — repository context is visible, but organizational
  graph indexing is opaque.
- **Export**: Repository-based context is inherently exported (it is the repo).
  Organizational context is not exportable.
- **Scope**: Repository-scoped (GitHub Copilot) or organization-scoped (M365).
- **Control**: Limited — custom instructions file (`.github/copilot-instructions.md`)
  is user-controlled, but model behavior influenced by organizational data is not.

### Local Models (Ollama, llama.cpp)

- **Mechanism**: No persistent memory. Each session starts from scratch unless
  the user explicitly provides context.
- **Visibility**: Full — there is nothing hidden.
- **Export**: N/A.
- **Scope**: Session-only.
- **Control**: Total.

---

## Risk Analysis

### Risk 1: Vendor Lock-In

**Description**: Accumulated memory makes switching providers costly. The more
context a platform holds, the higher the switching cost.

**Severity**: High for teams that rely heavily on platform memory for institutional
knowledge. Low for teams that maintain external documentation.

**Mitigation**: Never allow platform memory to be the authoritative source for
any piece of institutional knowledge. Every fact that matters must exist in a
version-controlled file.

### Risk 2: Stale Context

**Description**: Platform memory accumulates over time but is rarely pruned.
Outdated facts (old project structures, deprecated APIs, former team members)
persist and silently degrade model responses.

**Severity**: Medium. Stale context causes subtle errors — the model gives
advice based on how things used to work, not how they work now.

**Mitigation**: Scheduled memory review (monthly). Delete or update entries
that reference deprecated systems. For ORGANVM: the `<!-- ORGANVM:AUTO:START -->`
blocks in CLAUDE.md files are auto-regenerated, preventing structural staleness.

### Risk 3: Privacy Exposure

**Description**: Persistent memory may contain sensitive information —
credentials mentioned in conversation, personal details, internal project
names. This data persists in a system the user does not fully control.

**Severity**: High for ChatGPT (global memory, no project isolation). Low for
Claude Projects (user-controlled, project-scoped).

**Mitigation**: Never discuss credentials, tokens, or secrets in AI conversations.
Use environment variables and secret managers. Review stored memories quarterly
for accidental sensitive content.

### Risk 4: Inconsistent Behavior

**Description**: Memory-influenced responses vary based on accumulated context.
Two users asking the same question get different answers because their memory
profiles differ. This makes behavior unpredictable and debugging difficult.

**Severity**: Medium. Particularly problematic for teams where multiple people
interact with the same platform.

**Mitigation**: Use explicit project instructions (CLAUDE.md, copilot-instructions)
rather than accumulated conversation memory. Explicit instructions are
deterministic — everyone with the same file gets the same behavior.

### Risk 5: Opaque Decision Influence

**Description**: The model's behavior is influenced by memory the user cannot
fully inspect. There is no way to know exactly how a stored memory affected a
specific response.

**Severity**: Low-medium. Mostly a transparency concern, but can cause real
confusion when the model makes unexpected assumptions.

**Mitigation**: Prefer platforms with explicit, user-authored memory (Claude
Projects) over platforms with implicit, model-managed memory (ChatGPT Memory).

---

## ORGANVM Mitigation Strategy

### Principle: Provider-Independent Context

All institutional knowledge must exist in version-controlled, provider-independent
files. Platform memory is a performance optimization (faster context loading),
not a source of truth.

### Implementation

| Context Type | Authoritative Source | Platform Mirror |
|-------------|---------------------|-----------------|
| Project structure | `seed.yaml`, `registry-v2.json` | CLAUDE.md auto-generated blocks |
| Coding standards | `CLAUDE.md` (per-repo) | Loaded as project instructions |
| Session memory | `MEMORY.md` (per-project, git-tracked) | Claude auto-memory (derived) |
| Workflow knowledge | SOPs in `orchestration-start-here/` | Referenced in project instructions |
| Personal preferences | `~/.claude/CLAUDE.md` | Loaded globally by Claude Code |

### Monthly Export Protocol

1. **Review platform memory**: Check ChatGPT memories, Claude project MEMORY.md
   files, and any other platform-specific memory stores.
2. **Reconcile with local files**: Ensure every valuable fact in platform memory
   is also captured in a version-controlled file.
3. **Prune stale entries**: Delete platform memories that reference deprecated
   systems, old project structures, or outdated decisions.
4. **Verify provider independence**: Confirm that if all platform memory were
   deleted today, the project could continue with only local files.

### Migration Strategy

If switching AI providers:

1. All project context is in CLAUDE.md / seed.yaml / MEMORY.md files — these
   are Markdown, not platform-specific.
2. Convert CLAUDE.md to the new provider's instruction format (typically
   trivial — most accept Markdown).
3. MEMORY.md content becomes initial context for the new provider's memory
   system.
4. SOPs and governance docs are provider-agnostic by design.
5. Total migration effort: hours, not weeks — because the source of truth
   is local.

---

## Decision

**Use project-separated memory. Never rely on platform memory as single source
of truth. Maintain monthly export discipline.**

The goal is not to avoid platform memory — it is genuinely useful for session
continuity and reduced prompt engineering. The goal is to ensure that platform
memory is always a derivative of version-controlled files, never the other way
around. If the platform disappears tomorrow, nothing of value is lost.

---

## References

- [`data-classification.md`](data-classification.md) — Data classification tiers
- [`writing-vault-protocol.md`](writing-vault-protocol.md) — Workspace write policy context
- [`provider-policy-tracking.md`](provider-policy-tracking.md) — Provider data handling policies (F-44)
- [`ai-interaction-model.md`](ai-interaction-model.md) — Interaction routing model
