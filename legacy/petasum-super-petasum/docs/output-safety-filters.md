# Output Safety Filters for AI Gateway

> **Governance**: Commandment #2 (Privacy & Security First), #6 (Safe Execution)
> **Scope**: Postprocessor layer of the AI gateway (Layer 4)
> **Version**: 1.0
> **Backlog**: F-83

---

## Why This Exists

The AI gateway's preprocessor (Layer 1) controls what goes *into* the AI. But
controlling input is insufficient — models hallucinate, inject unexpected content,
leak memorized data, and produce output that violates requested formats. The
postprocessor (Layer 4) must validate, sanitize, and annotate everything that
comes *out* before it re-enters the source of truth.

This document specifies a pipeline of six filter functions that operate on every
AI response before reintegration. Each filter returns one of three verdicts:
**pass** (output is safe), **warn** (output is flagged but forwarded), or
**block** (output is rejected and must be regenerated or manually reviewed).

Integration point: Layer 4 (Postprocessor) of the AI gateway architecture
defined in `ai-gateway-architecture.md` (F-40).

---

## Filter Pipeline Architecture

```
AI Response
    │
    ▼
┌──────────────────────┐
│  1. PII Detection    │ ──block──▶ Reject + log
│                      │ ──warn───▶ Flag + continue
├──────────────────────┤
│  2. Hallucination    │ ──warn───▶ Flag assertions
│     Flags            │
├──────────────────────┤
│  3. Confidence       │ ──warn───▶ Annotate score
│     Scoring          │
├──────────────────────┤
│  4. Format           │ ──block──▶ Reformat or reject
│     Normalization    │
├──────────────────────┤
│  5. Content Safety   │ ──block──▶ Reject + log
│                      │ ──warn───▶ Flag + continue
├──────────────────────┤
│  6. Provenance       │ ──pass───▶ Tag + continue
│     Markers          │
└──────────────────────┘
    │
    ▼
Validated Output → Layer 5 (Storage) → Reintegration
```

Each filter operates independently. A **block** from any filter halts the pipeline
and prevents reintegration. **Warn** flags are accumulated and surfaced to the
human reviewer. **Pass** verdicts are silent.

---

## Filter 1: PII Detection

**Purpose**: Detect personally identifiable information in AI output that was
not present in the input — hallucinated PII that could expose real individuals
or create liability.

### Detection Targets

| PII Type | Pattern | Example |
|---|---|---|
| Full names | Named entity recognition; common name patterns | "John Smith mentioned that..." |
| Email addresses | RFC 5322 pattern matching | "contact user@example.com" |
| Phone numbers | International format patterns (E.164, NANP) | "call +1-555-123-4567" |
| Physical addresses | Street address patterns with postal codes | "located at 123 Main St" |
| SSN/TIN | 9-digit patterns (NNN-NN-NNNN) | "SSN: 123-45-6789" |
| Credit card numbers | Luhn-valid 13-19 digit sequences | "card ending in 4242" |
| IP addresses | IPv4/IPv6 patterns | "server at 192.168.1.1" |

### Logic

```
for each PII_match in output:
    if PII_match exists in input:
        verdict = PASS  # User provided it; echo is expected
    else if PII_match is clearly synthetic/example:
        verdict = PASS  # "user@example.com" in a code sample
    else:
        verdict = BLOCK  # Hallucinated PII — reject
        log(severity=HIGH, type="hallucinated_pii", match=PII_match)
```

### Configuration

| Parameter | Default | Description |
|---|---|---|
| `pii_sensitivity` | `high` | Detection threshold: `low` (names only), `medium` (+ emails, phones), `high` (all types) |
| `allow_example_domains` | `true` | Pass PII in recognized example domains (example.com, test.org) |
| `block_on_first` | `true` | Block entire output on first hallucinated PII match |

### Verdict Mapping

| Condition | Verdict |
|---|---|
| No PII detected | **Pass** |
| PII detected but present in input | **Pass** |
| PII detected in example/synthetic context | **Pass** |
| Hallucinated PII (not in input, not synthetic) | **Block** |

---

## Filter 2: Hallucination Flags

**Purpose**: Identify assertions in AI output that cannot be verified against
the provided context, flagging them for human review.

### Detection Heuristics

| Signal | Description | Weight |
|---|---|---|
| **Unsupported citations** | References to documents, papers, URLs not in context | High |
| **Specific statistics** | Precise numbers (percentages, dates, quantities) without source | High |
| **Named entities** | People, organizations, products not mentioned in input | Medium |
| **Causal claims** | "X causes Y" or "X leads to Y" without supporting evidence | Medium |
| **Historical claims** | "In [year], [event] happened" without source | Medium |
| **Absolute statements** | "Always", "never", "all", "none" without qualification | Low |

### Logic

```
for each assertion in output:
    evidence = search_context(assertion, input_context)
    if evidence.found:
        confidence = evidence.strength
    else:
        flag(assertion, reason="unsupported_by_context")
        confidence = LOW

    if count(flagged_assertions) > threshold:
        verdict = WARN
```

### Configuration

| Parameter | Default | Description |
|---|---|---|
| `flag_threshold` | `3` | Number of unsupported assertions before issuing WARN |
| `check_urls` | `true` | Validate that referenced URLs were in the input context |
| `check_citations` | `true` | Verify cited sources against provided context |

### Verdict Mapping

| Condition | Verdict |
|---|---|
| All assertions supported by context | **Pass** |
| 1-2 unsupported assertions | **Pass** (individual flags attached) |
| 3+ unsupported assertions | **Warn** (output forwarded with flags) |

**Note**: This filter never blocks — hallucination detection is inherently
heuristic. The human reviewer makes the final judgment.

---

## Filter 3: Confidence Scoring

**Purpose**: Assign a heuristic confidence score to AI output based on
observable signals, helping the human reviewer prioritize verification effort.

### Scoring Signals

| Signal | Effect on Confidence | Weight |
|---|---|---|
| **Hedging language** | Decreases ("might", "possibly", "I think", "it seems") | -10 per instance |
| **Certainty language** | Increases ("definitely", "always", "certainly") | +5 per instance (capped) |
| **Response length** | Very short responses for complex queries decrease confidence | Variable |
| **Self-contradiction** | Output contradicts itself | -30 per instance |
| **Refusal signals** | "I cannot", "I don't have information about" | Score = 0 (explicit uncertainty) |
| **Structured output** | Well-formatted, schema-compliant responses | +10 |
| **Code with comments** | Code blocks with explanatory comments | +5 |
| **Hallucination flags** | From Filter 2 | -15 per flag |

### Scoring Algorithm

```
base_score = 70  # Default confidence
adjustments = sum(signal_weights)
final_score = clamp(base_score + adjustments, 0, 100)

if final_score >= 80:
    label = "HIGH"
elif final_score >= 50:
    label = "MEDIUM"
elif final_score > 0:
    label = "LOW"
else:
    label = "UNCERTAIN"
```

### Configuration

| Parameter | Default | Description |
|---|---|---|
| `base_score` | `70` | Starting confidence before adjustments |
| `warn_threshold` | `40` | Score below which WARN is issued |
| `min_length_chars` | `50` | Responses shorter than this for non-trivial queries decrease confidence |

### Verdict Mapping

| Condition | Verdict |
|---|---|
| Score >= 50 | **Pass** (score attached as metadata) |
| Score 20-49 | **Warn** (low confidence — human review recommended) |
| Score < 20 | **Warn** (very low confidence — strong review recommended) |

**Note**: This filter never blocks. Confidence scoring is informational.

---

## Filter 4: Format Normalization

**Purpose**: Ensure AI output matches the requested format, correcting minor
deviations and rejecting outputs that cannot be salvaged.

### Supported Formats

| Requested Format | Validation | Auto-Correction |
|---|---|---|
| **Markdown** | Valid markdown syntax, heading hierarchy | Fix unclosed code blocks, normalize heading levels |
| **JSON** | Valid JSON, schema compliance if schema provided | Fix trailing commas, missing quotes on keys |
| **YAML** | Valid YAML, schema compliance if schema provided | Fix indentation (tabs → spaces) |
| **Code block** | Language tag present, parseable by language grammar | Wrap raw code in fenced blocks, add language tag |
| **Plain text** | No unexpected markup | Strip HTML/markdown if plain text requested |
| **Structured table** | Consistent column count, header row present | Pad short rows, normalize delimiters |

### Logic

```
if requested_format is specified:
    validation_result = validate(output, requested_format)

    if validation_result.valid:
        verdict = PASS
    elif validation_result.auto_correctable:
        output = auto_correct(output, validation_result.fixes)
        verdict = PASS  # Corrected output replaces original
        log(severity=INFO, type="format_auto_corrected", fixes=validation_result.fixes)
    else:
        verdict = BLOCK
        log(severity=MEDIUM, type="format_validation_failed", errors=validation_result.errors)
else:
    verdict = PASS  # No format constraint specified
```

### Configuration

| Parameter | Default | Description |
|---|---|---|
| `auto_correct` | `true` | Attempt automatic format correction before blocking |
| `strict_schema` | `false` | Require exact schema compliance (not just valid syntax) |
| `max_correction_ratio` | `0.2` | Block if more than 20% of output needs correction |

### Verdict Mapping

| Condition | Verdict |
|---|---|
| Output matches requested format | **Pass** |
| Minor format issues, auto-correctable | **Pass** (corrected) |
| Major format violations, not correctable | **Block** |
| No format specified | **Pass** |

---

## Filter 5: Content Safety

**Purpose**: Block harmful content and detect prompt injection attempts that
may have been embedded in the AI output.

### Detection Categories

#### Harmful Content

| Category | Detection Method | Verdict |
|---|---|---|
| Instructions for harm | Keyword + context analysis | **Block** |
| Hate speech / discrimination | Pattern matching + context | **Block** |
| Malicious code | Static analysis for known malware patterns, obfuscated payloads | **Block** |
| Social engineering | Urgency patterns, credential requests, impersonation | **Warn** |

#### Prompt Injection in Output

AI output can itself contain prompt injection — text designed to manipulate
downstream AI systems that process the output.

| Signal | Example | Verdict |
|---|---|---|
| System prompt override | "Ignore previous instructions and..." | **Block** |
| Role reassignment | "You are now a [different role]..." | **Block** |
| Instruction injection | "When you see this text, execute..." | **Block** |
| Hidden instructions | Zero-width characters, Unicode tricks, base64-encoded commands | **Block** |

### Logic

```
# Content safety check
for each content_violation in scan(output, harmful_patterns):
    if content_violation.severity == CRITICAL:
        verdict = BLOCK
        log(severity=CRITICAL, type="harmful_content", details=content_violation)
        return  # Immediate halt

    if content_violation.severity == MEDIUM:
        accumulate_warning(content_violation)

# Prompt injection check
for each injection_signal in scan(output, injection_patterns):
    verdict = BLOCK
    log(severity=HIGH, type="output_prompt_injection", details=injection_signal)
    return  # Immediate halt

if warnings.count > 0:
    verdict = WARN
else:
    verdict = PASS
```

### Configuration

| Parameter | Default | Description |
|---|---|---|
| `injection_detection` | `strict` | `strict` (block any signal), `moderate` (allow in code blocks), `off` |
| `content_safety_level` | `standard` | `strict`, `standard`, `permissive` |
| `allow_in_code_blocks` | `true` | Allow pattern matches inside fenced code blocks (they may be legitimate examples) |

### Verdict Mapping

| Condition | Verdict |
|---|---|
| No harmful content or injection signals | **Pass** |
| Medium-severity content concerns | **Warn** |
| Harmful content detected | **Block** |
| Prompt injection in output detected | **Block** |

---

## Filter 6: Provenance Markers

**Purpose**: Tag output sections to distinguish AI-generated content from
human-edited content, establishing provenance for copyright defense and
audit trails.

### Marker Format

Provenance markers are embedded as metadata, not visible inline content. They
use a structured annotation format stored alongside the output.

```json
{
  "provenance": {
    "generated_at": "2026-03-08T14:30:00Z",
    "model": "claude-opus-4-20250514",
    "provider": "anthropic",
    "session_id": "sess_abc123",
    "interaction_id": "int_def456",
    "filters_applied": ["pii", "hallucination", "confidence", "format", "safety", "provenance"],
    "confidence_score": 75,
    "warnings": [],
    "human_edited": false,
    "human_edit_timestamp": null
  }
}
```

### Tagging Rules

| Content State | `human_edited` | Evidence |
|---|---|---|
| Raw AI output, not yet reviewed | `false` | Provenance record only |
| AI output reviewed and approved without changes | `false` (add `human_reviewed: true`) | Review timestamp |
| AI output modified by human | `true` | Git diff showing human edits |
| Human-written content | N/A — no provenance marker | Git authorship |

### Logic

```
# Always runs, always passes
provenance_record = create_provenance(
    model=model_used,
    provider=provider_used,
    session=current_session,
    filters=filters_applied,
    confidence=confidence_score,
    warnings=accumulated_warnings
)

attach_metadata(output, provenance_record)
store_provenance(provenance_record, interaction_log)

verdict = PASS  # Provenance marking never blocks
```

### Integration with Copyright Defense

Provenance markers support the evidence preservation strategy defined in
`copyright-case-law.md` (F-72):

1. **Model attribution**: Records which model generated the content
2. **Human direction evidence**: Session ID links to AI interaction manifest (F-43)
   showing human prompts and creative direction
3. **Edit tracking**: `human_edited` flag combined with git history demonstrates
   human creative contribution
4. **Temporal evidence**: Timestamps establish when AI generation occurred vs
   when human editing occurred

---

## Pipeline Configuration

### Global Settings

```yaml
output_safety_filters:
  enabled: true
  fail_mode: "block"         # "block" halts on any BLOCK; "warn" downgrades to WARN
  log_level: "info"          # "debug", "info", "warn", "error"
  log_destination: "local"   # "local" (filesystem), "structured" (JSON log)
  max_output_size_kb: 500    # Block outputs exceeding this size

  filters:
    pii_detection:
      enabled: true
      sensitivity: "high"
      block_on_first: true

    hallucination_flags:
      enabled: true
      flag_threshold: 3

    confidence_scoring:
      enabled: true
      base_score: 70
      warn_threshold: 40

    format_normalization:
      enabled: true
      auto_correct: true
      strict_schema: false

    content_safety:
      enabled: true
      injection_detection: "strict"
      content_safety_level: "standard"

    provenance_markers:
      enabled: true
      # Cannot be disabled — provenance is always recorded
```

### Per-Tier Overrides

| Tier | PII Sensitivity | Content Safety | Injection Detection |
|---|---|---|---|
| T1 (Public) | `medium` | `standard` | `moderate` |
| T2 (Internal) | `high` | `standard` | `strict` |
| T3 (Confidential) | `high` | `strict` | `strict` |
| T4 (Regulated) | `high` | `strict` | `strict` |

---

## Implementation Notes

### Pipeline Execution Order

The filter order is intentional:
1. **PII Detection** first — reject hallucinated PII before any further processing
2. **Hallucination Flags** second — identify unsupported claims early
3. **Confidence Scoring** third — uses hallucination flag count as input
4. **Format Normalization** fourth — structural validation after content validation
5. **Content Safety** fifth — detect harmful content and injection
6. **Provenance Markers** last — annotate the validated output

### Performance Considerations

- PII detection and content safety are the most computationally expensive filters
- For streaming responses, filters can operate on chunks (PII, safety) or require
  full output (hallucination, confidence, format)
- Provenance marking adds negligible overhead
- Target: < 200ms total filter pipeline latency for non-streaming responses

### Error Handling

- If a filter itself fails (exception, timeout), default to **warn** verdict
  with error metadata attached
- Never silently pass — a failed filter must be logged
- Pipeline continues on filter failure unless `fail_mode` is `"strict"`

### Testing Strategy

- Unit tests per filter with known-good and known-bad inputs
- Integration tests for full pipeline with realistic AI outputs
- Adversarial tests: crafted outputs designed to bypass each filter
- Regression tests: outputs that previously triggered false positives/negatives

---

## References

- `ai-gateway-architecture.md` (F-40) — 5-layer gateway architecture (integration point)
- `pseudonymization-guidelines.md` — token format for PII replacement
- `data-classification.md` — tier definitions governing per-tier filter configuration
- `copyright-case-law.md` (F-72) — copyright defense strategy using provenance markers
- `standards-alignment.md` (F-46) — OWASP LLM02 (Insecure Output Handling) mapping
- COMMANDMENTS.md — Commandment #2 (Privacy & Security First), #6 (Safe Execution)
- F-43 — AI interaction manifests (linked via provenance session IDs)
