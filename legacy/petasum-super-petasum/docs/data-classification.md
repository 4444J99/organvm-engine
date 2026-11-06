# 4-Tier Data Classification Policy

> **Governance**: Commandment #2 (Privacy & Security First), #12 (Security & Privacy Standards)
> **Scope**: All data processed by AI tools across the eight-organ system
> **Version**: 1.0

---

## Why This Exists

Without data classification, all content is treated identically — personal
journals get the same handling as public README files. This creates two failure
modes: over-restricting public content (slowing work) or under-protecting
sensitive content (risking exposure).

The 4-tier system assigns every piece of content a classification that
determines which AI environments it may enter, what redaction is required,
and how long interaction records are retained.

---

## Classification Tiers

### Tier 1: PUBLIC

Content that is already public or intended for publication.

| Property | Value |
|----------|-------|
| **AI providers** | All (cloud and local) |
| **Redaction** | None required |
| **Retention** | Provider default (no restriction) |
| **Audit** | Optional |
| **Examples** | Open source code, published READMEs, public documentation, blog posts |

### Tier 2: INTERNAL

Content that is not public but not sensitive. Exposure would be
inconvenient but not harmful.

| Property | Value |
|----------|-------|
| **AI providers** | All (cloud and local) |
| **Redaction** | Remove credentials, API keys, internal URLs |
| **Retention** | Provider default (no restriction) |
| **Audit** | Recommended |
| **Examples** | Draft documentation, internal notes, architecture discussions, non-sensitive code |

### Tier 3: CONFIDENTIAL

Content containing personal, proprietary, or commercially sensitive
information. Exposure could cause harm.

| Property | Value |
|----------|-------|
| **AI providers** | Local only (Ollama, local GGUF) |
| **Redaction** | Full PII redaction, pseudonymization required |
| **Retention** | Local only, no cloud retention |
| **Audit** | Required — log projection and reintegration |
| **Examples** | Personal writing, financial data, client information, credentials, proprietary algorithms |

### Tier 4: REGULATED

Content subject to legal, regulatory, or contractual obligations.
Exposure could create legal liability.

| Property | Value |
|----------|-------|
| **AI providers** | Local only (Ollama, local GGUF) |
| **Redaction** | Full PII redaction, pseudonymization, metadata stripping |
| **Retention** | Local only, encrypted at rest, defined retention period |
| **Audit** | Mandatory — full audit trail with timestamps |
| **Examples** | Health data, financial records, legal documents, data under NDA, GDPR-covered personal data |

---

## Classification Decision Tree

```
Is the content already public or intended for publication?
├── YES → PUBLIC
└── NO
    Does the content contain PII, credentials, or proprietary IP?
    ├── NO → INTERNAL
    └── YES
        Is the content subject to legal/regulatory obligations?
        ├── NO → CONFIDENTIAL
        └── YES → REGULATED
```

---

## Per-Tier Controls

### Minimum Redaction Requirements

| Tier | Credentials | PII | Internal URLs | Metadata |
|------|-------------|-----|---------------|----------|
| PUBLIC | Remove | N/A | N/A | N/A |
| INTERNAL | Remove | N/A | Remove | N/A |
| CONFIDENTIAL | Remove | Pseudonymize | Remove | Strip |
| REGULATED | Remove | Pseudonymize | Remove | Strip |

**Pseudonymization format**: Replace identifiers with tokens:
- People: `[[PERSON_1]]`, `[[PERSON_2]]`
- Organizations: `[[ORG_A]]`, `[[ORG_B]]`
- Locations: `[[LOCATION_1]]`
- Dates: Generalize to month/year or `[[DATE_1]]`

The mapping between tokens and real values is stored separately with
elevated access controls (see Writing Vault protocol, F-38).

### AI Provider Routing

| Tier | Anthropic | OpenAI | Groq | Ollama | Local GGUF |
|------|-----------|--------|------|--------|------------|
| PUBLIC | Yes | Yes | Yes | Yes | Yes |
| INTERNAL | Yes | Yes | Yes | Yes | Yes |
| CONFIDENTIAL | **No** | **No** | **No** | Yes | Yes |
| REGULATED | **No** | **No** | **No** | Yes | Yes |

This routing is enforced by the sensitivity-based router in
`agentic-titan/adapters/router.py` via the `DataClassification` enum (F-24).

### Retention Limits

| Tier | AI provider retention | Local retention | Interaction records |
|------|----------------------|-----------------|---------------------|
| PUBLIC | Provider default | No limit | Optional |
| INTERNAL | Provider default | No limit | 90 days recommended |
| CONFIDENTIAL | Prohibited | Project lifetime | Required, 1 year |
| REGULATED | Prohibited | Per regulation | Required, per regulation |

---

## Classification by ORGANVM Context

| Context | Default Classification | Override Possible? |
|---------|----------------------|-------------------|
| Open source code (PUBLIC_PROCESS+) | PUBLIC | No (already public) |
| Internal code (LOCAL/CANDIDATE) | INTERNAL | Yes → CONFIDENTIAL if contains secrets |
| Personal writing / journals | CONFIDENTIAL | Yes → REGULATED if contains others' PII |
| Financial records | REGULATED | No |
| Health/medical data | REGULATED | No |
| Client/customer data | REGULATED | No |
| Research transcripts | INTERNAL | Yes → CONFIDENTIAL if contains personal data |
| AI chat logs | INTERNAL | Yes → based on content discussed |

---

## Applying Classification

### Per-File Classification

For repos with mixed sensitivity, classify at the file or directory level:

```yaml
# .data-classification.yaml (optional, per-repo)
defaults:
  classification: internal

overrides:
  - path: "src/**"
    classification: internal
  - path: "data/personal/**"
    classification: confidential
  - path: "data/financial/**"
    classification: regulated
  - path: "docs/public/**"
    classification: public
```

### Per-Request Classification

When using the LLM router, pass the classification explicitly:

```python
from adapters.router import DataClassification, get_router

router = get_router()
response = await router.complete(
    messages,
    classification=DataClassification.CONFIDENTIAL,
)
```

### Per-Session Classification

Non-interactive agent sessions declare classification at scheduling time.
The safety protocol enforces the classification for the entire session.

---

## Relationship to Other Governance

| Document | Relationship |
|----------|-------------|
| `ai-interaction-model.md` (F-36) | Classification occurs at Layer 2 (projection) |
| `writing-vault-protocol.md` (F-38) | Vault stores CONFIDENTIAL/REGULATED content |
| `NON-INTERACTIVE-AGENT-SAFETY.md` | Agents inherit session-level classification |
| `agentic-titan/adapters/router.py` | `DataClassification` enum enforces routing (F-24) |
| Commandment #2 | Privacy & Security First |
| Commandment #12 | Security & Privacy Standards |

---

## References

- **AI Interaction Model**: `docs/ai-interaction-model.md` — 4-layer data flow
- **Writing Vault**: `docs/writing-vault-protocol.md` — secure storage protocol
- **Sensitivity Router**: `agentic-titan/adapters/router.py` — code enforcement
- **Pseudonymization**: F-39 (future) — detailed redaction guidelines
- **Commandments**: `COMMANDMENTS.md` — #2, #12
