# Standards Alignment: NIST, ISO, and OWASP

> **Governance**: Commandment #2 (Privacy & Security First), #6 (Safe Execution), #12 (Security & Privacy Standards)
> **Scope**: Mapping ORGANVM safety practices to external regulatory and industry standards
> **Version**: 1.0
> **Backlog**: F-46

---

## Why This Exists

ORGANVM's governance framework was designed from first principles — logic-first
commandments, organ-level separation, promotion state machines. These internal
mechanisms are effective, but they exist in a vacuum unless mapped to the external
standards that regulators, auditors, and enterprise customers recognize.

This document maps ORGANVM safety practices to three authoritative frameworks:
**NIST AI RMF** (risk management), **ISO 42001** (AI management systems), and
**OWASP Top 10 for LLM Applications** (application security). The mapping serves
two purposes: validating that ORGANVM's controls are substantive rather than
incidental, and identifying gaps where additional controls are needed.

---

## NIST AI Risk Management Framework (AI 100-1)

The NIST AI RMF organizes AI risk management into four functions: **Map**,
**Measure**, **Manage**, and **Govern**. Each maps to existing ORGANVM structures.

### Map — Context and Risk Identification

> *"Establish the context to frame risks related to an AI system."*

| NIST Requirement | ORGANVM Implementation | Artifact |
|---|---|---|
| Identify intended use and stakeholders | Organ model defines scope per domain (Theoria = theory, Ergon = products, etc.) | `seed.yaml` per repo |
| Map interdependencies | Unidirectional dependency graph: I → II → III, validated by `validate-deps.py` | `governance-rules.json` Art. II |
| Identify data types and sensitivity | 4-tier data classification: PUBLIC → INTERNAL → CONFIDENTIAL → REGULATED | `data-classification.md` |
| Contextualize deployment environment | Per-repo stack declaration in seed.yaml, organ-aesthetic.yaml for identity | `seed.yaml`, `organ-aesthetic.yaml` |

**Gap**: No formal stakeholder impact assessment template. The organ model implies
stakeholders (Koinonia = community, Logos = public discourse) but does not document
impact pathways.

### Measure — Assessment and Metrics

> *"Employ quantitative, qualitative, or mixed-method tools to analyze, assess, benchmark, and monitor AI risk."*

| NIST Requirement | ORGANVM Implementation | Artifact |
|---|---|---|
| Define metrics for trustworthiness | Conductor's Scorecard tracks promotion readiness, CI health, coverage | `system-metrics.json` |
| Monitor system behavior | CI pipelines per repo, soak test monitoring, billing-lock detection | `.github/workflows/` |
| Test for bias and fairness | Not currently implemented — AI output is tool-assisted, not decision-making | — |
| Evaluate performance over time | Promotion state machine tracks maturity: LOCAL → CANDIDATE → GRADUATED | `registry-v2.json` |

**Gap**: No systematic bias testing. Current AI usage is generative (code, docs),
not predictive (hiring, scoring), so bias risk is lower but not zero — especially
for content generation in Logos (discourse) and Koinonia (community).

### Manage — Risk Response

> *"Allocate resources for risk response based on assessed risk."*

| NIST Requirement | ORGANVM Implementation | Artifact |
|---|---|---|
| Implement risk controls | governance-rules.json encodes dependency constraints, promotion gates | `governance-rules.json` |
| Define response actions | Data classification tiers determine redaction, routing, retention | `data-classification.md` |
| Maintain incident response | Security policy with vulnerability reporting | `SECURITY.md` |
| Document risk decisions | ADR (Architecture Decision Records) for significant decisions | `docs/adr/` |

**Gap**: No formal incident response playbook for AI-specific incidents (model
hallucination causing data loss, prompt injection breaching data classification).

### Govern — Organizational Commitment

> *"Cultivate and implement a culture of risk management."*

| NIST Requirement | ORGANVM Implementation | Artifact |
|---|---|---|
| Establish governance structures | COMMANDMENTS.md defines 13 principles in logical hierarchy | `COMMANDMENTS.md` |
| Define roles and responsibilities | Conductor role (human director), AI agents (generators), human review gates | `ai-interaction-model.md` |
| Ensure accountability | AI interaction manifest tracks human direction vs AI generation | F-43 |
| Maintain transparency | Open source default (Commandment #1), audit logging | `COMMANDMENTS.md` |

---

## ISO 42001: AI Management System

ISO 42001 follows the Annex SL structure common to all ISO management system
standards (ISO 9001, 27001, etc.). Each clause maps to ORGANVM structures.

### Clause 4: Context of the Organization

| ISO Requirement | ORGANVM Implementation |
|---|---|
| 4.1 Understanding the organization and its context | Eight-organ model defines organizational scope; `VISION.md` defines mission |
| 4.2 Understanding needs and expectations of interested parties | Organ separation: Koinonia (community needs), Logos (public discourse), Ergon (customer needs) |
| 4.3 Determining the scope of the AIMS | Scope = all AI-mediated work across 105 repos; defined in `ai-interaction-model.md` |
| 4.4 AI management system | COMMANDMENTS.md + governance-rules.json + data classification = management system |

### Clause 5: Leadership

| ISO Requirement | ORGANVM Implementation |
|---|---|
| 5.1 Leadership and commitment | Single-operator model: human is both leadership and practitioner |
| 5.2 AI policy | COMMANDMENTS.md (13 principles), PRINCIPLE_CONFLICTS.md (resolution framework) |
| 5.3 Organizational roles and responsibilities | Conductor role directs; AI generates volume; human reviews. No auto-merge policy |

### Clause 6: Planning

| ISO Requirement | ORGANVM Implementation |
|---|---|
| 6.1 Actions to address risks and opportunities | Data classification tiers, pseudonymization guidelines, redaction engine |
| 6.2 AI objectives and planning to achieve them | Promotion state machine: LOCAL → CANDIDATE → PUBLIC_PROCESS → GRADUATED |
| 6.3 Planning of changes | Score/Rehearse/Perform workflow; ADRs for architectural changes |

### Clause 7: Support

| ISO Requirement | ORGANVM Implementation |
|---|---|
| 7.1 Resources | seed.yaml declares per-repo resources, CI definitions, event subscriptions |
| 7.2 Competence | Skills collection (101 skills) provides domain-specific AI competence |
| 7.3 Awareness | CLAUDE.md files at workspace, organ, and project levels encode context |
| 7.4 Communication | Kerygma organ handles distribution; Logos handles discourse |
| 7.5 Documented information | registry-v2.json, governance-rules.json, seed.yaml contracts |

### Clause 8: Operation

| ISO Requirement | ORGANVM Implementation |
|---|---|
| 8.1 Operational planning and control | Frame/Shape/Build/Prove workflow with hard phase gates |
| 8.2 AI risk assessment | Preprocessor layer classifies and redacts before AI projection |
| 8.3 AI risk treatment | Sensitivity-based model routing (local-only for T3/T4) |
| 8.4 AI system impact assessment | Not formalized — partially covered by promotion criteria |

**Gap**: No formal AI system impact assessment (AISIA) procedure. ISO 42001 Annex B
requires documented impact assessments before deploying AI systems that affect
individuals.

### Clause 9: Performance Evaluation

| ISO Requirement | ORGANVM Implementation |
|---|---|
| 9.1 Monitoring, measurement, analysis, and evaluation | CI pipelines, system-metrics.json, Conductor's Scorecard |
| 9.2 Internal audit | Organ audit (`organ-audit.py`), registry health checks |
| 9.3 Management review | Session review protocol, session self-critique |

### Clause 10: Improvement

| ISO Requirement | ORGANVM Implementation |
|---|---|
| 10.1 Continual improvement | Promotion state machine enforces maturity progression |
| 10.2 Nonconformity and corrective action | Issue tracking (GitHub Issues), backlog management (FEATURE-BACKLOG.md) |

---

## OWASP Top 10 for LLM Applications (2025)

The OWASP LLM Top 10 identifies the most critical security risks in applications
that use large language models. ORGANVM's exposure is primarily through AI-assisted
development and content generation.

### LLM01: Prompt Injection

> *Attacker manipulates LLM via crafted inputs to cause unintended actions.*

| Risk | ORGANVM Control | Status |
|---|---|---|
| Direct prompt injection | Safety protocol in non-interactive agent safety guidelines | Implemented |
| Indirect injection via data | Pseudonymization prevents sensitive data from entering prompts | Implemented |
| System prompt extraction | System prompts (CLAUDE.md) are designed to be safe if exposed | Mitigated |

**Implementation**: `NON-INTERACTIVE-AGENT-SAFETY.md` defines agent boundaries.
Pseudonymization (`pseudonymization-guidelines.md`) ensures that even if injection
succeeds, the extracted data contains only tokens, not real identifiers.

### LLM02: Insecure Output Handling

> *Application trusts LLM output without validation, enabling downstream attacks.*

| Risk | ORGANVM Control | Status |
|---|---|---|
| Unvalidated code execution | No auto-merge policy; human review gate at Layer 4 (reintegration) | Implemented |
| Output containing injected content | Output safety filters in postprocessor layer | Planned (F-83) |
| Format/schema violations | Format normalization in postprocessor | Planned (F-83) |

**Implementation**: See `output-safety-filters.md` (F-83) for the postprocessor
filter pipeline specification.

### LLM03: Training Data Poisoning

> *Manipulation of training data to introduce vulnerabilities or bias.*

| Risk | ORGANVM Control | Status |
|---|---|---|
| Poisoned base models | Use established providers (Anthropic, OpenAI) with published training practices | Mitigated |
| Poisoned fine-tuned models | Local model management via Ollama; models sourced from verified publishers | Mitigated |
| Poisoned retrieval data | RAG sources are local git repos under version control | Mitigated |

**Note**: ORGANVM does not fine-tune models. Risk is limited to model selection
and RAG source integrity.

### LLM04: Model Denial of Service

> *Resource-intensive operations overwhelm the LLM, causing service degradation.*

| Risk | ORGANVM Control | Status |
|---|---|---|
| Token exhaustion | Cost optimization in router layer; monthly budget caps | Planned (F-40) |
| Recursive prompt loops | Agent timeout policies in agentic-titan | Implemented |

### LLM05: Supply Chain Vulnerabilities

> *Compromised components in the LLM supply chain.*

| Risk | ORGANVM Control | Status |
|---|---|---|
| Compromised model weights | Model provenance tracking (source, hash, version) | Partial |
| Malicious plugins/tools | MCP server inventory with scoped permissions | Implemented |
| Dependency confusion | Standard npm/pip lockfiles; Dependabot enabled | Implemented |

### LLM06: Sensitive Information Disclosure

> *LLM reveals confidential data in its responses.*

| Risk | ORGANVM Control | Status |
|---|---|---|
| Training data memorization | Use API-only providers with training opt-out | Mitigated |
| Context window leakage | Data classification gates what enters the context | Implemented |
| PII in output | PII detection in postprocessor output filters | Planned (F-83) |

**Implementation**: 4-tier data classification (`data-classification.md`) prevents
sensitive content from reaching cloud models. For local models, pseudonymization
(`pseudonymization-guidelines.md`) adds a second layer.

### LLM07: Insecure Plugin Design

> *Plugins grant excessive permissions or fail to validate inputs.*

| Risk | ORGANVM Control | Status |
|---|---|---|
| MCP server over-permissioning | Filesystem MCP scoped to workspace; memory MCP is ephemeral | Implemented |
| Tool execution without validation | Shell command validation in agent--claude-smith security layer | Implemented |

### LLM08: Excessive Agency

> *LLM-based systems take actions beyond intended scope.*

| Risk | ORGANVM Control | Status |
|---|---|---|
| Unauthorized file modifications | Write path validation in agent--claude-smith | Implemented |
| Uncontrolled external calls | No auto-deploy; human review required for all deployments | Implemented |
| Scope creep in agent tasks | Session phase gates (Frame/Shape/Build/Prove) constrain scope | Implemented |

### LLM09: Overreliance

> *Users trust LLM output without verification, leading to errors.*

| Risk | ORGANVM Control | Status |
|---|---|---|
| Uncritical acceptance of AI output | No auto-merge policy; human review gate mandatory | Implemented |
| Skill atrophy | AI-free practice cadence (F-70) maintains human competence | Planned (F-70) |
| False confidence | Confidence scoring in output filters flags uncertain outputs | Planned (F-83) |

### LLM10: Model Theft

> *Unauthorized access to proprietary LLM models.*

| Risk | ORGANVM Control | Status |
|---|---|---|
| API key exposure | 1Password secrets management; `op://` references in agent--claude-smith | Implemented |
| Model weight extraction | N/A — ORGANVM uses third-party models, not proprietary ones | N/A |

---

## Compliance Checklist for Agent Interactions

Use this checklist before deploying any new agent interaction pattern.

### Pre-Interaction

- [ ] **Data classified**: Input content has a tier assignment (PUBLIC/INTERNAL/CONFIDENTIAL/REGULATED)
- [ ] **Redaction applied**: CONFIDENTIAL and REGULATED content pseudonymized per `pseudonymization-guidelines.md`
- [ ] **Model selection validated**: Tier-appropriate model selected per routing rules
- [ ] **Prompt reviewed**: No sensitive data in system prompt or context injection
- [ ] **Scope defined**: Agent task has clear boundaries (session phase, file scope, action whitelist)

### During Interaction

- [ ] **Timeout configured**: Agent has a maximum execution time
- [ ] **Output monitored**: Streaming output checked for PII leakage
- [ ] **Cost tracked**: Token usage logged per interaction
- [ ] **Audit trail active**: Interaction recorded with timestamps and model identifiers

### Post-Interaction

- [ ] **Output validated**: Human review before reintegration into source of truth
- [ ] **PII scan completed**: Output scanned for hallucinated PII not present in input
- [ ] **Confidence assessed**: Low-confidence assertions flagged for verification
- [ ] **Format verified**: Output matches requested format and schema
- [ ] **Provenance marked**: AI-generated content tagged with generation metadata

### Periodic Review

- [ ] **Standards updated**: This document reviewed against latest NIST/ISO/OWASP versions (quarterly)
- [ ] **Gap analysis refreshed**: New gaps identified and added to backlog
- [ ] **Incident review**: Any AI-related incidents assessed against framework mappings
- [ ] **Legislation cross-reference**: Check `legislation-tracking.md` (F-73) for new requirements

---

## Gap Summary

| Gap | Framework | Priority | Backlog |
|---|---|---|---|
| No formal stakeholder impact assessment | NIST Map | Medium | — |
| No bias/fairness testing for AI output | NIST Measure | Low | — |
| No AI-specific incident response playbook | NIST Manage | Medium | — |
| No AI system impact assessment (AISIA) | ISO 42001 8.4 | Medium | — |
| Output safety filters not yet implemented | OWASP LLM02, LLM06, LLM09 | High | F-83 |
| AI gateway not yet implemented | OWASP LLM04 | High | F-40 |
| AI-free practice cadence not defined | OWASP LLM09 | Medium | F-70 |
| Model provenance tracking incomplete | OWASP LLM05 | Low | — |

---

## References

- [NIST AI Risk Management Framework (AI 100-1)](https://www.nist.gov/artificial-intelligence/ai-risk-management-framework)
- [ISO/IEC 42001:2023 — AI Management System](https://www.iso.org/standard/81230.html)
- [OWASP Top 10 for LLM Applications (2025)](https://owasp.org/www-project-top-10-for-large-language-model-applications/)
- COMMANDMENTS.md — organizational principles
- `data-classification.md` — 4-tier data classification policy
- `ai-interaction-model.md` — 4-layer interaction model
- `ai-gateway-architecture.md` — 5-layer gateway architecture (F-40)
- `output-safety-filters.md` — postprocessor filter pipeline (F-83)
- `pseudonymization-guidelines.md` — redaction and pseudonymization rules

---

*This document is a governance mapping, not a certification claim. ORGANVM is a
single-operator system; formal ISO/NIST certification is not pursued. The mapping
validates that internal controls are substantive and identifies areas for improvement.*
