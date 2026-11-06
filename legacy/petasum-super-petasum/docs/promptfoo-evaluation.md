# Promptfoo Evaluation

> **Governance**: Commandment #5 (Deterministic & Reliable), #8 (Quality Over Quantity)
> **Scope**: CI/CD prompt testing for AI-mediated workflows across the eight-organ system
> **Version**: 1.0
> **Backlog**: F-45

---

## Why This Exists

AI-mediated workflows produce non-deterministic outputs. A prompt that works today
may regress tomorrow due to model updates, provider changes, or subtle template
drift. Without automated testing, these regressions go undetected until a human
notices degraded output — often too late.

Promptfoo is an open-source tool (300K+ users, MIT license) purpose-built for
testing LLM outputs in CI/CD pipelines. This document evaluates its fit for the
ORGANVM system, specifically for integration with agentic-titan and the prompt
template library (F-41).

---

## What Promptfoo Is

Promptfoo is a CLI and library for evaluating LLM outputs against defined
assertions. It operates on a simple model:

1. **Prompts**: The templates being tested (YAML or text files).
2. **Providers**: The LLM backends to test against (OpenAI, Anthropic, local, etc.).
3. **Test cases**: Input variables + expected output assertions.
4. **Assertions**: Declarative checks — contains, regex, similarity, JSON schema,
   LLM-as-judge, custom JavaScript functions.

Configuration is a single YAML file (`promptfooconfig.yaml`):

```yaml
prompts:
  - "Summarize the following text: {{text}}"

providers:
  - openai:gpt-4
  - anthropic:claude-sonnet

tests:
  - vars:
      text: "The quick brown fox jumps over the lazy dog."
    assert:
      - type: contains
        value: "fox"
      - type: llm-rubric
        value: "The summary is concise and accurate"
      - type: javascript
        value: "output.length < 200"
```

Run with `npx promptfoo eval` — outputs a pass/fail report suitable for CI.

---

## Key Features

### Assertion Library

- **Exact match**: `equals`, `contains`, `icontains`
- **Pattern match**: `regex`, `starts-with`, `not-contains`
- **Semantic**: `similar` (cosine similarity threshold), `llm-rubric` (LLM-as-judge)
- **Structural**: `is-json`, `is-valid-openapi`, `javascript` (custom function)
- **Safety**: `not-contains` for banned content, `moderation` for content policy
- **Cost/performance**: `cost`, `latency`, `perplexity`

### Multi-Provider Testing

Test the same prompt against multiple providers simultaneously. Critical for
ORGANVM's model-agnostic approach — ensures templates work across Anthropic,
OpenAI, and local models.

### Vulnerability Scanning

Built-in red-team module generates adversarial inputs:
- Prompt injection attempts
- Jailbreak patterns
- PII extraction probes
- Harmful content elicitation

### GitHub Actions Integration

```yaml
- name: Run prompt tests
  run: npx promptfoo eval --ci
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

The `--ci` flag outputs machine-readable results and exits non-zero on failure.

### Caching and Performance

- Response caching across runs (avoids re-calling LLMs for unchanged tests).
- Parallel provider execution.
- Configurable rate limiting per provider.

---

## Integration with ORGANVM

### agentic-titan Integration

agentic-titan defines prompt templates as part of its Agent Forge YAML DSL.
Promptfoo can test these templates as a CI step:

```
agentic-titan/
├── agents/
│   └── summarizer.yaml          # Agent definition with prompt template
├── tests/
│   └── prompts/
│       ├── promptfooconfig.yaml  # Promptfoo configuration
│       └── test-cases/
│           ├── summarizer.yaml   # Test cases for summarizer agent
│           └── classifier.yaml   # Test cases for classifier agent
```

CI pipeline addition:

```yaml
# In agentic-titan CI workflow
- name: Prompt regression tests
  run: npx promptfoo eval -c tests/prompts/promptfooconfig.yaml --ci
```

### Use Case: Template Validation (F-41)

The prompt template library defines reusable templates with variable slots.
Promptfoo validates that:
- Templates produce expected output structure
- Variable substitution works correctly
- Output quality meets minimum thresholds
- Templates work across target providers

### Use Case: Anti-Pattern Detection (F-71)

Promptfoo's assertion library can encode anti-patterns as negative tests:
- `not-contains: "As an AI language model"` — detect hedging
- `not-contains: "I cannot"` — detect refusal on valid inputs
- Custom JavaScript assertions for structural anti-patterns

### Use Case: Output Quality Gates (F-66)

LLM-as-judge assertions provide automated quality scoring:
- Factual accuracy against reference text
- Tone consistency with organ-aesthetic.yaml
- Completeness of required output sections

---

## Strengths

1. **Declarative**: Test cases are YAML — no code required for basic tests.
2. **CI-native**: Designed for pipeline integration from day one.
3. **Multi-provider**: Tests the same prompts across providers simultaneously.
4. **Extensible**: JavaScript assertions for custom logic.
5. **Active development**: Regular releases, responsive maintainers, growing ecosystem.
6. **Local-friendly**: Works with Ollama and other local providers.

---

## Weaknesses

1. **Learning curve**: YAML configuration can become complex for advanced test
   scenarios (nested assertions, conditional logic, dynamic test generation).
2. **Test maintenance overhead**: LLM outputs are inherently variable — assertions
   must be loose enough to avoid false failures but tight enough to catch real
   regressions. Finding this balance requires iteration.
3. **LLM-as-judge cost**: Semantic assertions that use an LLM to evaluate output
   add API cost and latency to CI runs.
4. **Non-determinism**: Even with temperature=0, LLM outputs vary across providers
   and model versions. Tests must account for acceptable variance.
5. **Limited state management**: Promptfoo tests individual prompt-response pairs.
   Multi-turn conversation testing and stateful agent workflows require additional
   scaffolding.

---

## Recommendation

**Adopt for flagship repos, evaluate ROI before system-wide rollout.**

### Phase 1: Flagship Adoption

Deploy Promptfoo in `agentic-titan` and `orchestration-start-here`:
- Define test cases for the 5-10 most critical prompt templates.
- Run as a non-blocking CI step initially (warn on failure, don't block merge).
- Collect data on false-positive rate and maintenance overhead.

### Phase 2: ROI Evaluation (after 2 months)

Assess:
- How many real regressions were caught?
- How many false positives required test updates?
- What is the per-run API cost for LLM-as-judge assertions?
- How much time does test maintenance consume?

### Phase 3: Conditional Rollout

If Phase 2 shows positive ROI:
- Extend to all repos with AI-mediated workflows.
- Promote to blocking CI step (merge requires green prompt tests).
- Integrate vulnerability scanning into security audit workflow.

If Phase 2 shows negative ROI:
- Retain for flagship repos only.
- Investigate alternative tools (DeepEval, Ragas) for comparison.

---

## References

- [`prompt-template-library.md`](prompt-template-library.md) — Prompt template library (F-41)
- [`prompt-anti-patterns.md`](prompt-anti-patterns.md) — Prompt anti-patterns (F-71)
- [Promptfoo documentation](https://www.promptfoo.dev/docs/) — Official docs
- [`ai-interaction-model.md`](ai-interaction-model.md) — CI integration context
