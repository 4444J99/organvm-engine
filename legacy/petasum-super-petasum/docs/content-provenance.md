# Content Provenance: C2PA and W3C PROV Evaluation

> **Governance**: Commandment #4 (Beginner-friendly & Human-readable), #10 (Transparency), #14 (Clarity & Precision)
> **Scope**: Provenance tracking for AI-assisted content across the eight-organ system
> **Version**: 1.0
> **Backlog**: F-47

---

## Why This Exists

When AI assists in creating content — code, documentation, analysis, design
decisions — the question of provenance becomes non-trivial. Who wrote this?
What did the AI contribute? What sources informed the output? What was the
human's role?

Without a provenance model, AI-assisted content exists in a trust vacuum. Readers
cannot assess how much editorial judgment went into a document. Auditors cannot
verify claims of human authorship. Future maintainers cannot trace why a decision
was made or what information it was based on.

Two standards address this problem from different angles: W3C PROV (data model for
provenance metadata) and C2PA (content credentials for media files). This document
evaluates both for ORGANVM's needs and recommends an implementation path.

---

## W3C PROV

### What It Is

The W3C Provenance Data Model (PROV) is a recommendation (2013) for representing
provenance information. It defines three core concepts:

- **Entity**: A thing with provenance — a document, dataset, code file, image.
- **Activity**: Something that happens — writing, transforming, reviewing, committing.
- **Agent**: Something that acts — a person, an AI model, an automated script.

Relationships connect these:
- `wasGeneratedBy`: Entity was produced by Activity.
- `wasAttributedTo`: Entity is attributed to Agent.
- `used`: Activity consumed an Entity.
- `wasDerivedFrom`: Entity was derived from another Entity.
- `wasAssociatedWith`: Activity was carried out by Agent.
- `actedOnBehalfOf`: Agent was directed by another Agent.

### Fit for ORGANVM

PROV maps cleanly to AI-assisted content workflows:

```
Entity: docs/provider-policy-tracking.md (v1.0)
  wasGeneratedBy: Activity: "drafting session 2026-03-08"
    wasAssociatedWith: Agent: "Claude Opus 4" (AI)
    wasAssociatedWith: Agent: "human author" (Human)
  wasDerivedFrom: Entity: "provider documentation" (source material)
  wasDerivedFrom: Entity: "data-classification.md" (referenced doc)
```

### Strengths

- Well-defined, W3C-standardized vocabulary.
- Serializable as JSON-LD, RDF, or plain JSON.
- Expressive enough to capture human-AI collaboration chains.
- Lightweight — can be embedded as frontmatter or sidecar files.

### Weaknesses

- No built-in verification (provenance claims are assertions, not proofs).
- Tooling ecosystem is academic — limited production-ready libraries.
- Overhead: full PROV records for every document may not justify the cost.

---

## C2PA

### What It Is

The Coalition for Content Provenance and Authenticity (C2PA) defines a standard
for embedding cryptographically signed "content credentials" (manifests) into
media files. Founded by Adobe, Microsoft, BBC, and others.

A C2PA manifest includes:
- **Claim**: What happened to the content (created, edited, AI-generated).
- **Assertions**: Specific metadata (tool used, AI model, edit actions).
- **Signature**: Cryptographic proof that the claim was made by a specific actor.
- **Ingredient list**: References to source content used in creation.

### Fit for ORGANVM

C2PA is primarily designed for images, video, and audio — binary media formats
where the manifest is embedded in the file itself. ORGANVM currently produces
mostly text (Markdown, code, YAML), where C2PA's embedding model does not
naturally apply.

### Strengths

- Cryptographic verification — provenance claims are signed, not just asserted.
- Industry adoption growing (Adobe Firefly, Microsoft Designer, Leica cameras).
- Addresses the "is this AI-generated?" question directly.

### Weaknesses

- **Text-unfriendly**: Designed for binary media. No standard embedding for
  Markdown, source code, or YAML files.
- **PKI overhead**: Requires certificate management for signing.
- **Premature for ORGANVM**: The system does not yet produce media content at
  scale. Adopting C2PA now would be infrastructure without payoff.

---

## ORGANVM Implementation: Lightweight PROV

Rather than adopting either standard wholesale, ORGANVM already has the building
blocks of a provenance system. The recommendation is to formalize what exists
using PROV-inspired metadata.

### Existing Provenance Infrastructure

| ORGANVM Component | PROV Concept | Role |
|-------------------|-------------|------|
| Git commit history | Activity chain | Each commit = an activity with timestamp, author, message |
| AI interaction manifests (F-43) | Agent records | Each manifest records model, provider, token count, human role |
| `seed.yaml` produces/consumes edges | Entity derivation | Declares what each repo produces and what it depends on |
| SYLLABUS.md cited sources | Entity references | Traces content back to source material |
| `Co-Authored-By` commit trailers | Agent attribution | Credits both human and AI in version history |

### Provenance Chain Example

A typical AI-assisted document goes through this chain:

```
1. Human writes prompt (Agent: human, Activity: prompting)
   └─ uses: source material, existing docs, SYLLABUS references

2. AI generates draft (Agent: Claude Opus 4, Activity: generation)
   └─ uses: prompt, model training, context window contents

3. Human reviews and edits (Agent: human, Activity: review)
   └─ uses: AI draft, domain knowledge, governance rules

4. Commit to git (Activity: commit)
   └─ generates: versioned file entity
   └─ attributed to: human (author) + AI (co-author)
   └─ associated with: AI interaction manifest (F-43)
```

### Proposed Metadata Format

Add a `provenance` block to AI interaction manifests:

```yaml
provenance:
  model: "W3C PROV (lightweight)"
  entities:
    - id: "docs/content-provenance.md"
      version: "1.0"
      wasGeneratedBy: "session-2026-03-08-governance-docs"
      wasDerivedFrom:
        - "provider documentation (external)"
        - "data-classification.md"
        - "ai-interaction-model.md"
  activities:
    - id: "session-2026-03-08-governance-docs"
      type: "drafting"
      startedAt: "2026-03-08T00:00:00Z"
  agents:
    - id: "claude-opus-4"
      type: "ai"
      role: "drafter"
    - id: "human-author"
      type: "human"
      role: "director, reviewer"
```

### Implementation Phases

**Phase 1 (now)**: Continue using existing infrastructure — git history,
`Co-Authored-By` trailers, AI interaction manifests. No new tooling required.

**Phase 2 (when F-43 manifests are operational)**: Add PROV-inspired `provenance`
blocks to manifests. Lightweight, no cryptographic signing.

**Phase 3 (when media content is produced)**: Evaluate C2PA for images, diagrams,
and generated media. Only adopt when there is actual media content to sign.

---

## Decision

**Implement lightweight PROV-inspired metadata. Defer full C2PA until media
content is produced at scale.**

Rationale:
- ORGANVM's content is overwhelmingly text-based. C2PA adds PKI overhead
  without addressing the primary use case.
- Git commit history already provides a strong activity chain. Formalizing it
  with PROV vocabulary adds semantic clarity without new infrastructure.
- AI interaction manifests (F-43) are the natural carrier for provenance metadata.
- The cost of premature C2PA adoption (certificate management, tooling integration)
  exceeds the benefit for a text-first system.

---

## References

- [`writing-vault-protocol.md`](writing-vault-protocol.md) — Writing vault protocol (F-38)
- [`ai-interaction-manifest.md`](ai-interaction-manifest.md) — AI interaction manifest (F-43)
- [W3C PROV Overview](https://www.w3.org/TR/prov-overview/) — W3C Provenance standard
- [C2PA Specification](https://c2pa.org/specifications/) — Content Credentials standard
