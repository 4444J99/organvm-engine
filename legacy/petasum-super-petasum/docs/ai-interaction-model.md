# 4-Layer AI Interaction Model

> **Governance**: Commandment #2 (Privacy & Security First), #6 (Safe Execution)
> **Scope**: All AI-mediated work across the eight-organ system
> **Version**: 1.0

---

## Why This Exists

AI tools transform human work through a pipeline that is often invisible.
A writer pastes text into Claude; a developer runs Copilot on proprietary code;
an analyst feeds confidential data to ChatGPT. In each case, the original content
passes through multiple transformations — and at each stage, control, provenance,
and data sovereignty may be lost.

The 4-layer model makes this pipeline explicit so that every AI interaction
in ORGANVM can be reasoned about, classified, and governed.

---

## The Four Layers

```
┌─────────────────────────────────────────────────┐
│  Layer 4: REINTEGRATION                         │
│  AI output merged back into canonical source     │
│  Human review gate — no auto-merge              │
├─────────────────────────────────────────────────┤
│  Layer 3: TRANSFORMATION                        │
│  AI processes the projection (generate, edit,    │
│  critique, summarize, classify)                  │
├─────────────────────────────────────────────────┤
│  Layer 2: PROJECTION                            │
│  Content leaves the canonical store and enters   │
│  the AI context (prompt, upload, API call)        │
├─────────────────────────────────────────────────┤
│  Layer 1: SOURCE OF TRUTH                       │
│  Canonical content — git repos, vaults, local    │
│  files. The authoritative version.               │
└─────────────────────────────────────────────────┘
```

### Layer 1: Source of Truth

The canonical version of all content. This is the authoritative store.

- **Location**: Git repositories, local filesystem, encrypted vaults
- **Properties**: Version-controlled, auditable, owned by the author
- **Rule**: The source of truth is never the AI's output. AI output becomes
  part of the source only after passing through Layer 4 (reintegration).

### Layer 2: Projection

Content leaves the canonical store and enters an AI environment. This is
the moment data sovereignty is at risk.

- **Mechanism**: Copy-paste, API call, file upload, context window injection
- **Risk**: Once projected, the content may be logged, cached, or used for
  training by the AI provider (depending on provider policy and tier)
- **Controls**:
  - Apply data classification before projection (see `data-classification.md`)
  - Redact or pseudonymize sensitive content before projection
  - Route through local models for CONFIDENTIAL/REGULATED data
  - Log what was projected, to which provider, and when

### Layer 3: Transformation

The AI processes the projected content and produces output. The transformation
may be generative (new text), analytical (classification, summary), or
editorial (rewrite, critique).

- **Properties**: Non-deterministic, provider-dependent, potentially lossy
- **Risk**: AI may hallucinate, introduce errors, or subtly alter meaning
- **Controls**:
  - Treat all AI output as draft, never as authoritative
  - Multi-model verification for critical transformations (F-34)
  - Prompt versioning — same prompt should produce comparable results

### Layer 4: Reintegration

AI output is merged back into the source of truth. This is the most
critical gate — it determines what becomes canonical.

- **Rule**: No auto-merge. A human must review and approve the reintegration.
- **Mechanism**: PR review, manual copy, structured merge
- **Controls**:
  - Diff review: compare AI output against source before merging
  - Provenance annotation: record that content was AI-assisted
  - Quality gate: AI output must pass the same review standards as human work
  - Reintegration must follow the Score/Rehearse/Perform lifecycle (F-09)

---

## Data Flow Rules

### Rule 1: Classification Before Projection

Before any content enters Layer 2, determine its data classification
(PUBLIC, INTERNAL, CONFIDENTIAL, REGULATED). The classification determines
which AI providers are permitted. See `data-classification.md`.

### Rule 2: Local-Only for Sensitive Data

CONFIDENTIAL and REGULATED content MUST be projected only to local models
(Ollama). Cloud providers (Anthropic, OpenAI, Groq) are forbidden for
these classifications. This is enforced by the sensitivity-based router
in `agentic-titan/adapters/router.py` (F-24).

### Rule 3: Human Gate at Reintegration

No AI output may be merged into the source of truth without human review.
This applies to both interactive sessions (human reviews in real-time) and
non-interactive sessions (output queued for review per the safety protocol).

### Rule 4: Provenance Tracking

Every reintegration must record:
- Which AI tool/model produced the output
- What was projected (summary, not full content)
- When the interaction occurred
- Whether the output was used verbatim, edited, or rejected

---

## Interaction Patterns

### Pattern A: Interactive Writing

```
Source → [human selects excerpt] → Projection → [Claude edits] →
Transformation → [human reviews diff] → Reintegration
```

Classification: Typically INTERNAL or CONFIDENTIAL.
Route: Cloud for INTERNAL, Ollama for CONFIDENTIAL.

### Pattern B: Code Generation

```
Source → [agent reads codebase] → Projection → [LLM generates code] →
Transformation → [tests + lint + human review] → Reintegration (PR merge)
```

Classification: Typically INTERNAL (open source) or CONFIDENTIAL (proprietary).
Gate: CI must pass before reintegration.

### Pattern C: Document Analysis

```
Source → [full document projected] → Projection → [LLM summarizes/extracts] →
Transformation → [human verifies against source] → Reintegration
```

Classification: Depends on document content. Apply classification per-document.
Risk: Full projection means full exposure — use local models for sensitive docs.

### Pattern D: Non-Interactive Agent

```
Source → [agent auto-reads scope] → Projection → [LLM processes] →
Transformation → [dry-run + audit] → Reintegration (queued for review)
```

Classification: Determined at scheduling time per the safety protocol.
Gate: Mandatory dry-run pass. Human reviews before merge.

---

## Relationship to Other Governance

| Document | Relationship |
|----------|-------------|
| `data-classification.md` (F-37) | Defines the 4 tiers used in Layer 2 routing |
| `writing-vault-protocol.md` (F-38) | Defines the canonical storage for Layer 1 |
| `NON-INTERACTIVE-AGENT-SAFETY.md` | Constrains Layer 2-4 for unattended agents |
| `agentic-titan/adapters/router.py` | Code enforcement of Layer 2 routing (F-24) |
| `orchestration-start-here/docs/score-rehearse-perform.md` | Layer 4 lifecycle (F-09) |
| Commandment #2 | Privacy & Security First — foundational principle |
| Commandment #17 | Non-Destructive Autonomy — Layer 4 safety |
| Commandment #18 | Bounded Execution — Layer 2/3 scope limits |

---

## References

- **Data Classification**: `docs/data-classification.md` — per-tier controls
- **Writing Vault**: `docs/writing-vault-protocol.md` — canonical storage protocol
- **Safety Protocol**: `docs/NON-INTERACTIVE-AGENT-SAFETY.md` — agent constraints
- **Sensitivity Router**: `agentic-titan/adapters/router.py` — code enforcement
- **Commandments**: `COMMANDMENTS.md` — #2, #6, #17, #18
