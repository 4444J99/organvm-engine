# Pseudonymization and Redaction Guidelines

> **Governance**: Commandment #2 (Privacy & Security First)
> **Scope**: All CONFIDENTIAL and REGULATED content projected to AI tools
> **Version**: 1.0

---

## Why This Exists

When sensitive content must be projected to an AI (Layer 2 of the AI interaction
model), raw identifiers — names, organizations, locations, dates — create exposure
risk. Pseudonymization replaces real identifiers with consistent tokens, preserving
the content's structure and meaning while protecting the entities it references.

This document defines the token format, replacement rules, mapping management,
and validation procedures for pseudonymization in the ORGANVM system.

---

## Token Format

### Entity Types and Tokens

| Entity Type | Token Pattern | Examples |
|-------------|---------------|----------|
| Person | `[[PERSON_N]]` | `[[PERSON_1]]`, `[[PERSON_2]]` |
| Organization | `[[ORG_X]]` | `[[ORG_A]]`, `[[ORG_B]]` |
| Location | `[[LOCATION_N]]` | `[[LOCATION_1]]`, `[[LOCATION_2]]` |
| Date | `[[DATE_N]]` | `[[DATE_1]]`, `[[DATE_2]]` |
| Email | `[[EMAIL_N]]` | `[[EMAIL_1]]`, `[[EMAIL_2]]` |
| Phone | `[[PHONE_N]]` | `[[PHONE_1]]`, `[[PHONE_2]]` |
| Address | `[[ADDRESS_N]]` | `[[ADDRESS_1]]`, `[[ADDRESS_2]]` |
| Account/ID | `[[ACCOUNT_N]]` | `[[ACCOUNT_1]]`, `[[ACCOUNT_2]]` |
| Custom | `[[CUSTOM_label_N]]` | `[[CUSTOM_PROJECT_1]]` |

**Token rules:**
- Tokens use double brackets `[[ ]]` to avoid collision with markdown/code syntax
- Numeric suffixes are sequential per type within a document
- Letter suffixes (A, B, C) are used for organizations to distinguish from numeric IDs
- Tokens are case-sensitive: `[[PERSON_1]]` ≠ `[[person_1]]`
- The same real entity always maps to the same token within a session

---

## Replacement Rules

### What MUST Be Replaced

For CONFIDENTIAL content:
- Full names of real people
- Organization names (unless publicly known in the context)
- Email addresses
- Phone numbers
- Physical addresses
- Account numbers, IDs, credentials

For REGULATED content (all of the above, plus):
- Dates of birth, dates of service
- Geographic identifiers smaller than a state/province
- Any identifier that could be used for re-identification

### What SHOULD Be Replaced

- Job titles (if they identify a specific person in context)
- Relationships ("my brother" → "[[PERSON_2]]" if the relationship is identifying)
- Project names (if they reveal confidential business information)

### What Should NOT Be Replaced

- Generic role descriptions ("the CEO", "a developer")
- Public figures mentioned in public context
- Published company names in public analysis
- Technical terms, product names in public documentation
- Dates that are not personally identifying (publication dates, version dates)

---

## Quasi-Identifier Generalization

Some identifiers are not directly identifying but become identifying in
combination (quasi-identifiers). Apply generalization:

| Original | Generalized | Rule |
|----------|-------------|------|
| "age 34" | "age 30-39" | 10-year bands |
| "salary $87,500" | "salary $80K-$90K" | $10K bands |
| "born March 15, 1990" | "born Q1 1990" or `[[DATE_1]]` | Quarter or token |
| "lives in Brooklyn" | "lives in New York metro" or `[[LOCATION_1]]` | City-level or token |
| "Senior Staff Engineer at Google" | "senior engineer at [[ORG_A]]" | Generalize title, tokenize org |

---

## Metadata Stripping

Before projection to any AI, strip the following metadata:

- **File metadata**: Author, creation date, last modified by (in Office docs, PDFs)
- **EXIF data**: GPS coordinates, camera info, timestamps (in images)
- **Git metadata**: Committer email, author name (if projecting diffs)
- **Email headers**: Full headers contain IP addresses, routing info

**Tools:**
- `exiftool -all= photo.jpg` — strip EXIF
- `qpdf --linearize --replace-input doc.pdf` — strip PDF metadata
- `python-docx` — programmatic metadata removal for Word docs

---

## Redaction Mapping

The mapping between tokens and real values is stored **separately** from the
pseudonymized content, with elevated access controls.

### Mapping Format

```yaml
# .redaction-map.yaml (NEVER committed to git, NEVER projected to AI)
version: "1.0"
session_id: "sess_abc123"
created: "2026-03-08T14:30:00Z"
classification: confidential

mappings:
  PERSON_1: "Jane Smith"
  PERSON_2: "John Doe"
  ORG_A: "Acme Corporation"
  ORG_B: "Widget Inc"
  LOCATION_1: "123 Main St, Springfield"
  DATE_1: "1990-03-15"
  EMAIL_1: "jane.smith@acme.com"
```

### Storage Rules

- Mapping files are stored in the Writing Vault (`~/Vault/.redaction-maps/`)
- File naming: `YYYY-MM-DD-session-slug.yaml`
- Never committed to git (add to `.gitignore`)
- Never projected to any AI tool
- Encrypted at rest (vault encryption covers this)
- Retention: same as the content's classification tier
- Access: owner only (or explicitly authorized reviewer)

### Reversal

To de-pseudonymize (restore original content):

```bash
# Simple token replacement (for review purposes only)
sed -e 's/\[\[PERSON_1\]\]/Jane Smith/g' \
    -e 's/\[\[ORG_A\]\]/Acme Corporation/g' \
    pseudonymized-doc.md > restored-doc.md
```

De-pseudonymized content inherits the original classification and must
not be projected to cloud AI providers if CONFIDENTIAL or REGULATED.

---

## Validation

### Pre-Projection Checklist

Before projecting pseudonymized content to an AI:

- [ ] All required entity types have been replaced (names, orgs, emails, etc.)
- [ ] Token numbering is consistent (same person = same token throughout)
- [ ] No residual identifiers remain (search for @, phone patterns, addresses)
- [ ] Quasi-identifiers are generalized
- [ ] Metadata is stripped
- [ ] Redaction mapping is saved in the vault
- [ ] Classification routing will enforce local-only if CONFIDENTIAL/REGULATED

### Post-Reintegration Checklist

After receiving AI output based on pseudonymized input:

- [ ] AI output uses tokens (not real names) — verify no leakage
- [ ] De-pseudonymize only the portions being reintegrated
- [ ] Human reviews the de-pseudonymized output before merging
- [ ] AI interaction record updated with projection summary

---

## Examples

### Example: Personal Writing Review

**Original (CONFIDENTIAL):**
> Sarah met David at the Blue Moon Café on March 15th. David works at
> Meridian Labs and lives on 42 Oak Street in Portland.

**Pseudonymized:**
> [[PERSON_1]] met [[PERSON_2]] at [[LOCATION_1]] on [[DATE_1]].
> [[PERSON_2]] works at [[ORG_A]] and lives on [[ADDRESS_1]].

**Mapping:**
```yaml
PERSON_1: "Sarah"
PERSON_2: "David"
LOCATION_1: "Blue Moon Café"
DATE_1: "March 15th"
ORG_A: "Meridian Labs"
ADDRESS_1: "42 Oak Street, Portland"
```

### Example: Code Review with Client Names

**Original (CONFIDENTIAL):**
```python
# Client: Acme Corp, contact: john@acme.com
client_name = "Acme Corporation"
api_endpoint = "https://api.acme.com/v2"
```

**Pseudonymized:**
```python
# Client: [[ORG_A]], contact: [[EMAIL_1]]
client_name = "[[ORG_A]]"
api_endpoint = "https://api.[[ORG_A_DOMAIN]]/v2"
```

---

## Relationship to Other Governance

| Document | Relationship |
|----------|-------------|
| `ai-interaction-model.md` (F-36) | Pseudonymization occurs at Layer 2 (projection) |
| `data-classification.md` (F-37) | Classification determines redaction requirements |
| `writing-vault-protocol.md` (F-38) | Redaction mappings stored in vault |
| Commandment #2 | Privacy & Security First |

---

## References

- **AI Interaction Model**: `docs/ai-interaction-model.md` — Layer 2 controls
- **Data Classification**: `docs/data-classification.md` — per-tier redaction requirements
- **Writing Vault**: `docs/writing-vault-protocol.md` — secure storage for mappings
- **Sensitivity Router**: `agentic-titan/adapters/router.py` — routing enforcement
