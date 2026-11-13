# AI Provider Policy Tracking

> **Governance**: Commandment #2 (Privacy & Security First), #10 (Transparency)
> **Scope**: All external AI provider interactions across the eight-organ system
> **Version**: 1.0
> **Backlog**: F-44
> **Review Cadence**: Quarterly (next: 2026-Q3)

---

## Why This Exists

AI providers change their data handling policies frequently and inconsistently.
A model that did not train on API inputs last quarter may start doing so this
quarter. A consumer tier that once offered opt-out may remove that option. An
enterprise agreement that guaranteed data isolation may add exceptions in updated
terms of service.

Without a living comparison table, practitioners either assume all providers
behave the same (dangerous) or check policies ad-hoc (unreliable). This document
centralizes provider policy tracking so that data classification decisions
(see `data-classification.md`) and interaction routing (see `ai-interaction-model.md`)
are grounded in current facts rather than stale assumptions.

---

## Provider Policy Comparison

| Provider | Training Default | Opt-Out Method | Retention | Enterprise Tier | Last Policy Change | Last Verified |
|----------|-----------------|----------------|-----------|-----------------|-------------------|---------------|
| **OpenAI (ChatGPT)** | Yes — consumer inputs train models | Settings > Data Controls > toggle off | 30 days (abuse monitoring) | ChatGPT Enterprise/Team: no training | 2024-12 (default opt-in retained) | 2026-03 |
| **OpenAI (API)** | No — API inputs do not train by default | N/A (already off) | 30 days (abuse monitoring), 0 with zero-retention endpoint | API usage never trains unless explicitly opted in | 2023-03 (API default changed to no-train) | 2026-03 |
| **Anthropic (Claude)** | No — does not train on inputs by default | N/A (already off) | 90 days (safety, unless enterprise) | Enterprise: custom retention, zero-retention available | 2025-10 (policy reversal on feedback usage — feedback no longer used for training without explicit consent) | 2026-03 |
| **Google (Gemini Consumer)** | Yes — consumer inputs may train models | Gemini Apps Activity toggle in Google Account | 18 months (Gemini Apps Activity) | N/A (consumer tier) | 2024-06 (Gemini Apps Activity introduced) | 2026-03 |
| **Google (Vertex AI)** | No — enterprise inputs do not train | N/A (already off) | Customer-controlled | Full data isolation, HIPAA/SOC2 available | 2023-06 (Vertex AI data governance launched) | 2026-03 |
| **Microsoft (Copilot Consumer)** | Yes — consumer interactions may improve services | Limited — privacy settings in Microsoft Account | Not publicly specified | N/A (consumer tier) | 2024-09 (Copilot rebrand, policy update) | 2026-03 |
| **Microsoft (Azure OpenAI)** | No — customer data not used for training | N/A (already off) | 30 days (abuse monitoring), 0 with approved exemption | Full data isolation, managed by Azure compliance | 2023-06 (Azure OpenAI GA data policy) | 2026-03 |
| **Meta (Llama)** | N/A — open weights, self-hosted | N/A (no external data flow) | N/A (local) | N/A (self-hosted) | 2024-07 (Llama 3.1 license update) | 2026-03 |
| **Mistral** | No — API inputs do not train by default | N/A (already off) | 30 days (API), longer for La Plateforme free tier | Enterprise: custom retention | 2024-09 (La Plateforme policy update) | 2026-03 |
| **Local (Ollama)** | N/A — fully local, no external calls | N/A | N/A — no external retention | N/A | N/A | 2026-03 |

---

## Detailed Provider Notes

### OpenAI

**Two distinct regimes.** The API and ChatGPT operate under different data policies.
This is the single most important distinction to understand — code that calls the
OpenAI API does not train models, but the same prompt typed into ChatGPT does (unless
opted out).

- **ChatGPT (consumer)**: Inputs train models by default. Opt-out available via
  Settings > Data Controls > "Improve the model for everyone." Opting out disables
  conversation history. ChatGPT Team/Enterprise plans never train.
- **API**: Inputs never train models. Zero-retention endpoint available for
  sensitive workloads. 30-day abuse monitoring retention applies to all API calls.
- **Policy history**: Prior to March 2023, API data could be used for training.
  Policy changed after enterprise pushback.

### Anthropic

- Default: inputs not used for training.
- **October 2025 policy reversal**: Anthropic previously used thumbs-up/thumbs-down
  feedback to improve models. After public scrutiny, they reversed this — feedback
  is no longer used for training without explicit consent.
- Enterprise plans offer zero-retention and custom data handling agreements.
- Claude Projects (memory) is project-scoped and does not leak between projects.

### Google

**Two distinct regimes** (similar to OpenAI's split).

- **Gemini Consumer**: Inputs may train models. Controlled via Gemini Apps Activity
  in Google Account settings. 18-month retention for activity data.
- **Vertex AI**: Enterprise-grade. Customer data is not used for training. Full
  data isolation with customer-managed encryption keys available.
- **Caution**: Google's privacy policies are notoriously complex. Cross-product
  data sharing within Google's ecosystem is not always transparent.

### Microsoft

**Two distinct regimes.**

- **Copilot Consumer**: Interactions may improve Microsoft services. Limited
  opt-out controls. Policy is less clearly documented than Azure.
- **Azure OpenAI**: Customer data is not used for training. 30-day abuse
  monitoring retention with approved exemption for zero-retention. Azure
  compliance certifications (SOC2, HIPAA, FedRAMP) apply.

### Meta (Llama)

Open-weights model — fundamentally different from hosted providers. No data
leaves the local environment. The policy concern is the Llama license itself
(community vs. commercial use thresholds), not data handling.

- Llama 3.1+ license: free for organizations with <700M monthly active users.
- No telemetry in the model weights.
- Security responsibility shifts entirely to the operator.

### Mistral

- API inputs do not train by default.
- La Plateforme free tier may have different retention than paid tiers.
- Enterprise agreements available for custom retention.
- Relatively young company — policy history is short but clean.

### Local (Ollama)

- No external network calls. All inference is local.
- No retention concerns beyond local disk.
- No provider policy — the operator is the policy.
- Recommended for TIER-1 (RESTRICTED) and TIER-2 (CONFIDENTIAL) data per
  `data-classification.md`.

---

## ORGANVM Routing Implications

Based on this policy table, the AI interaction model routes data as follows:

| Data Tier | Permitted Providers | Rationale |
|-----------|-------------------|-----------|
| TIER-1 (RESTRICTED) | Local only (Ollama) | No external exposure permitted |
| TIER-2 (CONFIDENTIAL) | Local, enterprise API with zero-retention | Requires contractual data isolation |
| TIER-3 (INTERNAL) | Any API tier (not consumer chat) | API default no-train is sufficient |
| TIER-4 (PUBLIC) | Any provider including consumer tiers | No sensitivity concern |

---

## Update Protocol

1. **Quarterly review**: Check each provider's current terms of service and data
   handling documentation.
2. **Event-driven updates**: Any public announcement of policy change triggers an
   immediate update (do not wait for quarterly cycle).
3. **Verification**: Each row includes a "Last Verified" date. If a provider's
   verification date is >6 months old, treat the entry as potentially stale.
4. **Changelog**: Record all updates in the table below.

### Change Log

| Date | Provider | Change | Source |
|------|----------|--------|--------|
| 2026-03 | All | Initial table created | Provider documentation review |

---

## References

- [`data-classification.md`](data-classification.md) — 4-tier data classification policy
- [`ai-interaction-model.md`](ai-interaction-model.md) — 4-layer AI interaction model
- [`ai-gateway-architecture.md`](ai-gateway-architecture.md) — Gateway routing architecture
