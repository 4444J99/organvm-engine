# Personal AI Gateway Architecture

> **Governance**: Commandment #2 (Privacy & Security First), #6 (Safe Execution)
> **Scope**: All AI interactions originating from the ORGANVM workspace
> **Version**: 1.0
> **Backlog**: F-40

---

## Why This Exists

Every AI interaction involves data leaving local control and entering a third-party
context. Without a structured gateway, sensitive content leaks, costs accumulate
unmonitored, and prompt quality varies wildly between sessions. The AI gateway
centralizes these concerns into a single architectural chokepoint — a personal proxy
that classifies, routes, transforms, and audits every interaction before it reaches
an external model.

This document extends the 4-layer AI interaction model (see `ai-interaction-model.md`)
into an implementable 5-layer gateway architecture.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│  Layer 5: STORAGE                                       │
│  Interaction records, redaction mappings, audit trail    │
├─────────────────────────────────────────────────────────┤
│  Layer 4: POSTPROCESSOR                                 │
│  PII leak detection, hallucination flags, confidence    │
│  scoring, format normalization, output safety filters   │
├─────────────────────────────────────────────────────────┤
│  Layer 3: TRANSFORMER                                   │
│  Prompt template injection, role/audience/constraints   │
│  framing, model-specific formatting                     │
├─────────────────────────────────────────────────────────┤
│  Layer 2: ROUTER                                        │
│  Sensitivity-based model selection, provider failover,  │
│  cost optimization, rate limiting                       │
├─────────────────────────────────────────────────────────┤
│  Layer 1: PREPROCESSOR                                  │
│  Classification engine, redaction engine,               │
│  context preparation                                    │
└─────────────────────────────────────────────────────────┘
```

---

## Layer 1: Preprocessor

The preprocessor intercepts every outbound AI request before it leaves the local
environment. Three engines operate in sequence.

### Classification Engine

Applies the `DataClassification` enum from the data classification framework (see
`data-classification.md`) to determine the sensitivity tier of the input:

| Tier | Label | Action |
|------|-------|--------|
| T1 | Public | Pass through — no redaction required |
| T2 | Internal | Redact identifiers, apply pseudonymization |
| T3 | Confidential | Full redaction, local-model-only routing |
| T4 | Regulated | Block by default — requires explicit override with audit |

### Redaction Engine

Applies pseudonymization rules from the pseudonymization guidelines (see
`pseudonymization-guidelines.md`) to replace sensitive tokens with reversible
placeholders. Redaction mappings are stored in the vault (see
`writing-vault-protocol.md`) for later de-pseudonymization of AI output.

### Context Preparation

Assembles the final prompt payload:
- Strips irrelevant context to reduce token cost
- Attaches relevant project metadata (organ, repo, tier)
- Injects system-level instructions (e.g., "do not store this interaction")

---

## Layer 2: Router

The router selects the appropriate model and provider based on sensitivity tier,
task type, and cost constraints.

### Sensitivity-Based Model Selection

| Tier | Allowed Models | Rationale |
|------|---------------|-----------|
| T1 (Public) | Any (Claude, GPT, Gemini, local) | No data risk |
| T2 (Internal) | Claude (API, no training), GPT (API, no training) | API-only, training opt-out verified |
| T3 (Confidential) | Local models only (Ollama, llama.cpp) | Data never leaves machine |
| T4 (Regulated) | Blocked unless local + air-gapped | Requires explicit human approval |

### Provider Failover

Ordered failover chain per tier:
1. Primary provider (configured per-project)
2. Secondary provider (same tier eligibility)
3. Local fallback (always available for T1-T3)
4. Graceful failure with cached response suggestion

### Cost Optimization

- Track token usage per provider, per project, per session
- Route simple tasks (classification, formatting) to smaller/cheaper models
- Reserve large-context models for tasks that require them
- Monthly budget caps with warning thresholds

Reference: `agentic-titan/adapters/router.py` implements the model-agnostic adapter
pattern that this gateway extends.

---

## Layer 3: Transformer

The transformer shapes raw user intent into structured prompts optimized for the
selected model.

### Prompt Template Injection

Selects and populates a template from the prompt template library (see
`prompt-template-library.md`). Templates encode:
- **Role**: Who the AI should act as
- **Audience**: Who the output is for
- **Constraints**: What the AI must not do
- **Output format**: Expected structure of the response

### Model-Specific Formatting

Adapts prompt structure to model preferences:
- **Claude**: XML tags for structure, extended thinking for reasoning tasks
- **GPT**: Markdown formatting, system/user message separation
- **Local models**: Simplified prompts, reduced context windows

### Framing Injection

Appends governance-level instructions:
- Training opt-out declarations
- Data handling instructions
- Session scope boundaries (from explore vs production mode — see
  `explore-vs-production-modes.md`)

---

## Layer 4: Postprocessor

The postprocessor inspects AI output before it reaches the user or is incorporated
into any canonical artifact.

### PII Leak Detection

Scans AI output for:
- Personal identifiers that survived redaction
- Email addresses, phone numbers, API keys
- Names or locations that should have been pseudonymized
- Patterns matching the redaction mapping keys (indicating failed redaction)

### Hallucination Flags

Flags output that:
- References files, functions, or APIs that don't exist in the codebase
- Cites sources that cannot be verified
- Contains confident assertions about implementation details not present in context

### Confidence Scoring

Assigns a confidence score (0.0–1.0) based on:
- Consistency with provided context
- Specificity of the response
- Presence of hedging language vs. definitive claims

### Format Normalization

Converts AI output to the expected format:
- Code blocks with correct language tags
- Markdown structure matching project conventions
- Stripping of conversational preamble/postamble

### Output Safety Filters

Cross-reference with F-83 output safety requirements:
- Verify no secrets or credentials in generated code
- Check for common security anti-patterns in code output
- Flag outputs that suggest disabling security features

---

## Layer 5: Storage

Every interaction passing through the gateway produces a persistent record.

### Interaction Records

Stored using the AI interaction manifest template (see `ai-interaction-manifest.md`).
Each record captures: tool, model, classification tier, input/output summaries,
incorporation status, and session linkage.

### Redaction Mappings

Pseudonymization mappings stored in the vault (see `writing-vault-protocol.md`):
- Keyed by interaction ID
- Required for de-pseudonymizing AI output
- Retention follows data classification tier rules

### Audit Trail

Immutable append-only log of:
- Every routing decision (which model, why)
- Every redaction applied (what was replaced)
- Every postprocessor flag raised
- Every human override of a gateway decision

---

## Deployment Options

### Option A: Local Python Service

Minimal deployment — a Python CLI that wraps API calls:

```
gateway classify <input>     # Run preprocessor, print tier
gateway route <input>        # Full pipeline, interactive
gateway audit --last 50      # Review recent interactions
```

### Option B: FastAPI Service

Local HTTP service for integration with editors, scripts, and agents:

```
POST /v1/interact     → Full pipeline
GET  /v1/audit        → Interaction history
GET  /v1/health       → Service status + provider availability
```

### Option C: agentic-titan Integration

Embed the gateway as a middleware layer in the agentic-titan orchestration framework.
The `adapters/router.py` already implements model-agnostic routing — the gateway
layers (preprocessor, transformer, postprocessor, storage) wrap around the existing
adapter pattern.

---

## Cross-References

- `ai-interaction-model.md` — 4-layer conceptual model this gateway implements
- `data-classification.md` — Tier definitions (T1–T4)
- `pseudonymization-guidelines.md` — Redaction rules
- `writing-vault-protocol.md` — Vault storage for sensitive mappings
- `prompt-template-library.md` — Template injection source (F-41)
- `ai-interaction-manifest.md` — Interaction record format (F-43)
- `explore-vs-production-modes.md` — Mode-specific gateway behavior (F-42)
- `prompt-anti-patterns.md` — Anti-patterns the transformer should prevent (F-71)
