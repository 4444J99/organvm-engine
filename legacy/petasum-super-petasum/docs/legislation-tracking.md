# AI-Relevant Legislation Tracking

> **Governance**: Commandment #2 (Privacy & Security First), #12 (Security & Privacy Standards)
> **Scope**: Legislation affecting AI usage, data handling, and privacy across all organs
> **Version**: 1.0
> **Backlog**: F-73
> **Update Schedule**: Quarterly review

---

## Why This Exists

AI-related legislation is evolving rapidly across jurisdictions. A single-operator
system like ORGANVM might seem exempt from enterprise compliance burdens, but
several of these laws apply to any entity processing personal data or deploying
AI systems — regardless of size. Ignorance of a regulation is not a defense.

This document tracks legislation that could affect ORGANVM's AI practices, data
handling, or published output. Each entry includes the jurisdiction, key requirements,
penalties, effective dates, and specific ORGANVM relevance.

**Disclaimer**: This is a reference tracking document, not legal advice. Consult
qualified legal counsel for compliance obligations specific to your circumstances.

---

## Legislation Tracker

### EU AI Act (Regulation 2024/1689)

| Property | Detail |
|---|---|
| **Jurisdiction** | European Union (all member states) |
| **Effective Date** | Phased: Feb 2025 (prohibited practices), Aug 2025 (GPAI), Aug 2026 (high-risk) |
| **Status** | In force — phased implementation |

**Key Requirements**:
- **Article 50 — Transparency obligations**: AI-generated content must be marked as
  such when published. Deepfakes and synthetic text require disclosure
- **Risk classification**: AI systems categorized as unacceptable, high-risk, limited,
  or minimal risk. Most ORGANVM usage falls under minimal/limited risk (generative tools)
- **GPAI model obligations**: Providers of general-purpose AI models must document
  training data, publish model cards, and comply with copyright law
- **High-risk AI**: Strict requirements for AI in employment, education, critical
  infrastructure (not directly applicable to ORGANVM's current use)

**Penalties**: Up to 35M EUR or 7% of global annual turnover for prohibited practices;
15M EUR or 3% for other violations.

**ORGANVM Relevance**:
- Art. 50 transparency: All AI-generated content published via Logos (discourse) or
  Kerygma (distribution) organs must include AI disclosure
- ORGANVM is a user of GPAI models, not a provider — provider obligations fall on
  Anthropic, OpenAI, etc.
- If ORGANVM products (Organ III) incorporate AI features, they may trigger limited-risk
  transparency obligations
- Cross-reference: `standards-alignment.md` (F-46) maps to NIST/ISO frameworks

---

### New York SHIELD Act (S5575B)

| Property | Detail |
|---|---|
| **Jurisdiction** | New York, United States |
| **Effective Date** | March 2020 |
| **Status** | In force |

**Key Requirements**:
- Requires "reasonable safeguards" for private information of New York residents
- Covers computerized data including name + SSN, driver's license, financial account
  numbers, biometric data, email + password
- Administrative, technical, and physical safeguards required
- Breach notification within reasonable time to affected individuals and NY AG

**Penalties**: Up to $5,000 per violation; no cap on total liability. AG enforcement.

**ORGANVM Relevance**:
- If any ORGANVM product (Organ III) processes data of NY residents, SHIELD Act applies
- Data classification framework (`data-classification.md`) satisfies "reasonable
  safeguards" requirement for Tier 3/4 data
- Pseudonymization practices exceed minimum requirements

---

### Tennessee ELVIS Act (SB 1493)

| Property | Detail |
|---|---|
| **Jurisdiction** | Tennessee, United States |
| **Effective Date** | July 2024 |
| **Status** | In force |

**Key Requirements**:
- Extends right of publicity to AI-generated voice and likeness
- Prohibits unauthorized use of AI to replicate a person's voice, image, or likeness
  without consent
- Applies to commercial uses including advertising, merchandise, and digital content
- Criminal and civil penalties for violations

**Penalties**: Civil damages + injunctive relief; criminal penalties for willful violations.

**ORGANVM Relevance**:
- Organ II (Poiesis) generative art and performance systems must not generate content
  that replicates real individuals' likeness or voice without consent
- AI-generated voices in audio engineering or music composition must use synthetic
  voices, not cloned voices of real people
- Low risk for code/documentation generation (Organs I, III, IV)

---

### HIPAA (Health Insurance Portability and Accountability Act)

| Property | Detail |
|---|---|
| **Jurisdiction** | United States (Federal) |
| **Effective Date** | 1996 (Privacy Rule 2003, Security Rule 2005) |
| **Status** | In force — HHS rulemaking on AI and PHI ongoing |

**Key Requirements**:
- Protects Protected Health Information (PHI) — individually identifiable health data
- Covered entities and business associates must implement administrative, physical,
  and technical safeguards
- Minimum necessary standard: only access/disclose the minimum PHI needed
- AI processing of PHI requires same protections as any electronic PHI processing
- Breach notification to HHS, affected individuals, and media (for large breaches)

**Penalties**: $100–$50,000 per violation; up to $1.5M per year for same violation type.
Criminal penalties for knowing violations.

**ORGANVM Relevance**:
- Currently low relevance — ORGANVM does not process health data
- If any Organ III product handles health-adjacent data, HIPAA becomes immediately
  relevant
- Data classification Tier 4 (REGULATED) already covers health data handling rules
- AI tools must never process PHI via cloud providers — local-only per T4 rules

---

### FERPA (Family Educational Rights and Privacy Act)

| Property | Detail |
|---|---|
| **Jurisdiction** | United States (Federal) |
| **Effective Date** | 1974 (amended multiple times) |
| **Status** | In force — ED guidance on AI and education records pending |

**Key Requirements**:
- Protects education records of students at institutions receiving federal funding
- Requires consent before disclosing personally identifiable information from
  education records
- "School official" exception allows disclosure to officials with "legitimate
  educational interests" — debated for AI tools
- AI tools processing student data may need to be classified as "school officials"
  under institutional policies

**Penalties**: Loss of federal funding (institutional); no direct monetary penalties
on individuals, but institutions face enforcement actions.

**ORGANVM Relevance**:
- Organ VI (Koinonia) includes educational components (reading groups, salons, learning)
- If Koinonia handles student records or operates in educational contexts, FERPA applies
- AI tools used in educational contexts must not transmit student data to cloud providers
  without institutional authorization
- Data classification Tier 4 covers educational records

---

### CCPA/CPRA (California Consumer Privacy Act / California Privacy Rights Act)

| Property | Detail |
|---|---|
| **Jurisdiction** | California, United States |
| **Effective Date** | CCPA: Jan 2020; CPRA amendments: Jan 2023 |
| **Status** | In force — CPPA rulemaking on automated decision-making ongoing |

**Key Requirements**:
- Consumers have right to know, delete, opt-out of sale/sharing of personal information
- CPRA added: right to correct, right to limit use of sensitive personal information
- Applies to businesses meeting revenue/data volume thresholds (>$25M revenue, >100K
  consumers, >50% revenue from selling data)
- **Automated decision-making**: CPRA gives consumers right to opt out of profiling
  and automated decision-making; regulations pending
- AI systems using personal information must comply with data minimization and purpose
  limitation

**Penalties**: $2,500 per unintentional violation; $7,500 per intentional violation.
Private right of action for data breaches.

**ORGANVM Relevance**:
- Revenue thresholds likely not met for single-operator system currently
- If any Organ III product processes California consumer data, CCPA/CPRA applies
  regardless of business size for certain categories
- Data classification and pseudonymization practices align with CCPA/CPRA principles
- Automated decision-making provisions relevant if any product uses AI for decisions
  affecting consumers

---

### Colorado AI Act (SB 24-205)

| Property | Detail |
|---|---|
| **Jurisdiction** | Colorado, United States |
| **Effective Date** | February 2026 |
| **Status** | Enacted — pre-implementation |

**Key Requirements**:
- First comprehensive US state AI law targeting algorithmic discrimination
- Applies to "high-risk AI systems" — those making consequential decisions in
  employment, education, financial services, housing, insurance, healthcare,
  government services, legal services
- Deployers must: complete impact assessments, implement risk management policies,
  provide consumer notice, allow human appeal
- Developers must: provide documentation, disclose training data, report known risks
- Annual impact assessment and public disclosure requirements

**Penalties**: AG enforcement under Colorado Consumer Protection Act; no private right
of action. Affirmative defense available for compliance with recognized AI risk
management frameworks (NIST AI RMF).

**ORGANVM Relevance**:
- Currently low relevance — ORGANVM does not deploy high-risk AI in covered categories
- If any Organ III product makes consequential decisions (hiring, lending, insurance),
  Colorado AI Act applies
- NIST AI RMF alignment (`standards-alignment.md`, F-46) provides affirmative defense
- Impact assessment framework partially covered by ISO 42001 mapping

---

### Illinois BIPA (Biometric Information Privacy Act)

| Property | Detail |
|---|---|
| **Jurisdiction** | Illinois, United States |
| **Effective Date** | 2008 |
| **Status** | In force — most litigated biometric privacy law in the US |

**Key Requirements**:
- Regulates collection, use, storage, and disclosure of biometric identifiers
  (fingerprints, voiceprints, facial geometry, iris scans, retina scans)
- Requires informed written consent before collection
- Requires published retention and destruction schedules
- Prohibits sale, lease, or trade of biometric data
- Private right of action — individuals can sue directly

**Penalties**: $1,000 per negligent violation; $5,000 per intentional/reckless
violation. Private right of action (no need for AG involvement). Per-scan accrual
upheld by IL Supreme Court.

**ORGANVM Relevance**:
- If any Organ II (Poiesis) system processes biometric data (facial recognition in
  generative art, voiceprints in audio engineering), BIPA applies
- If any Organ III product collects biometric data from Illinois residents, strict
  consent requirements apply
- AI models that process facial images or voice recordings trigger BIPA obligations
- Currently low relevance if no biometric data is processed

---

## Legislation Summary Matrix

| Legislation | Jurisdiction | Data Type | AI-Specific? | ORGANVM Risk | Key Deadline |
|---|---|---|---|---|---|
| EU AI Act | EU | All | Yes | Medium | Aug 2025 (GPAI), Aug 2026 (high-risk) |
| NY SHIELD Act | New York | PII | No | Low | In force |
| TN ELVIS Act | Tennessee | Likeness/voice | Partially | Low | In force |
| HIPAA | US Federal | PHI | No | Low (currently) | In force |
| FERPA | US Federal | Education records | No | Low (currently) | In force |
| CCPA/CPRA | California | Consumer PI | Partially | Low (currently) | In force |
| Colorado AI Act | Colorado | Consequential decisions | Yes | Low (currently) | Feb 2026 |
| Illinois BIPA | Illinois | Biometric data | No | Low (currently) | In force |

---

## Cross-Reference to ORGANVM Controls

| Requirement Category | ORGANVM Control | Document |
|---|---|---|
| Data classification | 4-tier classification system | `data-classification.md` |
| PII protection | Pseudonymization and redaction | `pseudonymization-guidelines.md` |
| AI transparency | AI interaction manifests | F-43 |
| Risk management | NIST AI RMF mapping | `standards-alignment.md` (F-46) |
| Output safety | Postprocessor filter pipeline | `output-safety-filters.md` (F-83) |
| Copyright compliance | Case law tracking | `copyright-case-law.md` (F-72) |
| Human oversight | No auto-merge, human review gates | `ai-interaction-model.md` |
| Breach response | Security policy | `SECURITY.md` |

---

## Quarterly Review Checklist

- [ ] Check for new AI-specific legislation in tracked jurisdictions (EU, US federal, key states)
- [ ] Review status of pending regulations (Colorado AI Act implementation, CPRA automated decision-making rules)
- [ ] Update effective dates and status for tracked legislation
- [ ] Assess whether any Organ III products have entered regulated categories
- [ ] Cross-reference with `copyright-case-law.md` (F-72) for related legal developments
- [ ] Update risk assessments based on ORGANVM's evolving scope
- [ ] Check for enforcement actions or notable cases under tracked legislation
- [ ] Verify ORGANVM controls still align with current requirements

---

## References

- [EU AI Act — Official Text](https://eur-lex.europa.eu/eli/reg/2024/1689/oj)
- [NY SHIELD Act (S5575B)](https://www.nysenate.gov/legislation/bills/2019/s5575)
- [Tennessee ELVIS Act (SB 1493)](https://wapp.capitol.tn.gov/apps/BillInfo/Default.aspx?BillNumber=SB1493)
- [HIPAA — HHS Summary](https://www.hhs.gov/hipaa/index.html)
- [FERPA — ED Summary](https://www2.ed.gov/policy/gen/guid/fpco/ferpa/index.html)
- [CCPA/CPRA — CA AG Summary](https://oag.ca.gov/privacy/ccpa)
- [Colorado AI Act (SB 24-205)](https://leg.colorado.gov/bills/sb24-205)
- [Illinois BIPA (740 ILCS 14)](https://www.ilga.gov/legislation/ilcs/ilcs3.asp?ActID=3004)
- `standards-alignment.md` (F-46) — NIST/ISO/OWASP alignment
- `copyright-case-law.md` (F-72) — copyright case law tracking
- `data-classification.md` — 4-tier data classification policy
