# AI Interaction Manifest Template

> **Governance**: Commandment #2 (Privacy & Security First), #4 (Provenance & Traceability)
> **Scope**: All AI interactions that produce artifacts incorporated into ORGANVM
> **Version**: 1.0
> **Backlog**: F-43

---

## Why This Exists

When AI output is incorporated into canonical artifacts — code, documentation,
analysis, design decisions — the provenance of that output must be recorded.
Without a manifest, there is no way to answer fundamental questions:

- Which model generated this code?
- Was confidential data shared during the interaction?
- Did the user consent to training on this exchange?
- Can this output be reproduced or audited?

The AI interaction manifest provides a lightweight, structured record for every
AI interaction that produces incorporated output. It is the "receipt" for
AI-generated work.

---

## Manifest Schema

```yaml
# AI Interaction Manifest v1.0
# One manifest per interaction or coherent session segment

interaction_id: "int_YYYYMMDD_NNN"          # Unique identifier (date + sequence)
date: "YYYY-MM-DDTHH:MM:SSZ"               # ISO 8601 timestamp (UTC)

# Tool and provider
tool: "claude-code | chatgpt | perplexity | ollama | copilot | gemini | custom"
provider: "anthropic | openai | google | local | perplexity"
model_version: "claude-opus-4-20250514 | gpt-4o | llama3.2:3b | gemini-2.5-pro"

# Data governance
classification: "public | internal | confidential | regulated"
training_consent: true | false              # Was this interaction eligible for model training?
retention_setting: "default | none | 30d"   # Provider-side retention policy applied

# Session context
purpose: "code-generation | analysis | writing | research | review | debugging | brainstorming"
mode: "explore | production"                # See explore-vs-production-modes.md

# Content summary (never paste full content — summaries only)
input_summary: "Brief description of what was shared with the AI"
output_summary: "Brief description of what was received from the AI"

# Incorporation tracking
output_incorporated: true | false           # Was AI output used in a canonical artifact?
incorporation_target: "repo/path/file.ext"  # Where was the output incorporated?
incorporation_method: "verbatim | adapted | inspired"  # How closely does the artifact match AI output?

# Linkage
session_id: "optional FSBP session ID"      # Link to conductor session if applicable
issue_ref: "org/repo#123"                   # Link to GitHub issue if applicable
gateway_trace_id: "optional gateway ID"     # Link to AI gateway audit log (F-40)
```

---

## Field Definitions

### interaction_id

Format: `int_YYYYMMDD_NNN` where NNN is a zero-padded sequence number for that day.

Example: `int_20260308_003` — the third logged interaction on March 8, 2026.

For multi-turn conversations logged as a single interaction, use the timestamp of
the first exchange.

### classification

Maps directly to the data classification tiers (see `data-classification.md`):

| Value | Tier | Meaning |
|-------|------|---------|
| `public` | T1 | No sensitive data shared |
| `internal` | T2 | Internal project data, pseudonymized identifiers |
| `confidential` | T3 | Confidential data — local models only |
| `regulated` | T4 | Regulated data — should not be in AI interactions |

### training_consent

Whether the interaction is eligible for the provider's model training:

- `true`: Default API behavior, provider may use for training
- `false`: Training opt-out verified (API with training exclusion, or local model)

Most professional API usage (Anthropic API, OpenAI API with opt-out) should be `false`.
Consumer-tier tools (ChatGPT free tier, Claude.ai free tier) are typically `true`.

### retention_setting

The data retention policy applied to this interaction on the provider side:

- `default`: Provider's standard retention (varies by provider and plan)
- `none`: Zero retention requested (ephemeral API calls)
- `30d`: 30-day retention window (common for abuse monitoring)

### incorporation_method

How closely the canonical artifact matches the AI output:

- `verbatim`: Output used as-is (or near-verbatim with minor edits)
- `adapted`: Output substantially modified before use
- `inspired`: Output informed the approach but the artifact was written independently

---

## Storage Rules

### Standard Interactions (T1–T2)

Store manifest files alongside project artifacts:

```
project-root/
├── .ai-manifests/
│   ├── int_20260308_001.yaml
│   ├── int_20260308_002.yaml
│   └── ...
├── src/
├── tests/
└── ...
```

The `.ai-manifests/` directory:
- Is committed to git (manifests are metadata, not secrets)
- Uses `.gitattributes` to mark as generated: `*.yaml linguist-generated=true`
- Is excluded from code coverage and lint rules

### Confidential Interactions (T3–T4)

Store manifest files in the vault (see `writing-vault-protocol.md`):
- Vault path: `vault/ai-manifests/YYYY-MM/`
- Manifests in the vault may reference redaction mapping IDs
- Never commit T3/T4 manifests to public repositories

### Retention

- Manifests are retained for the lifetime of the project
- Archived projects retain manifests in their archive
- Manifests for interactions where `output_incorporated: false` may be purged after
  90 days at the user's discretion

---

## When to Create a Manifest

### Required

- AI output is incorporated verbatim or adapted into a canonical artifact
- Confidential or regulated data was shared with an AI tool
- The interaction produced a significant design decision or architectural choice

### Optional

- Exploratory sessions (explore mode) that did not produce incorporated output
- Quick lookups or formatting tasks
- AI-assisted git commit messages (low provenance value)

### Not Required

- Autocomplete suggestions (too granular to track individually)
- Spell-check or grammar suggestions
- IDE-level AI features (hover documentation, symbol lookup)

---

## Example Manifest

```yaml
interaction_id: "int_20260308_001"
date: "2026-03-08T14:30:00Z"

tool: "claude-code"
provider: "anthropic"
model_version: "claude-opus-4-20250514"

classification: "internal"
training_consent: false
retention_setting: "none"

purpose: "code-generation"
mode: "production"

input_summary: "Provided AI gateway architecture spec and asked for FastAPI router implementation"
output_summary: "Received router.py with sensitivity-based model selection and provider failover"

output_incorporated: true
incorporation_target: "agentic-titan/adapters/gateway_router.py"
incorporation_method: "adapted"

session_id: "session_20260308_prod_gateway"
issue_ref: "organvm-iv-taxis/petasum-super-petasum#125"
```

---

## Bulk Logging

For sessions that produce many small interactions (e.g., iterative code development),
a single manifest covering the entire session is acceptable. Use the session start
time as the `date` and summarize the full session in `input_summary` and
`output_summary`.

---

## Cross-References

- `data-classification.md` — Classification tier definitions
- `writing-vault-protocol.md` — Vault storage for confidential manifests
- `ai-interaction-model.md` — Conceptual model for AI interactions
- `ai-gateway-architecture.md` — Gateway produces manifests automatically (F-40)
- `explore-vs-production-modes.md` — Mode field values (F-42)
- `pseudonymization-guidelines.md` — Redaction applied before interactions
