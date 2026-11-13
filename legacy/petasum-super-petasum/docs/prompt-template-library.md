# Prompt Template Library

> **Governance**: Commandment #3 (AI as Instrument, Not Oracle)
> **Scope**: All AI-mediated work across the eight-organ system
> **Version**: 1.0
> **Backlog**: F-41

---

## Why This Exists

Unstructured prompts produce inconsistent results. The same task framed differently
yields wildly different quality — and most users default to vague, conversational
prompts that underperform. A versioned template library provides repeatable,
optimizable prompt skeletons that encode best practices for each task category.

Every template in this library follows a structured format that separates
**what the AI should do** from **how it should do it** and **what it should not do**.
Templates are composable — a code review template can be combined with a security
analysis template for security-focused code reviews.

---

## Template Schema

Every template follows this structure:

```yaml
name: "template-name"
version: "1.0.0"                    # SemVer
category: "edit | critique | outline | summarize | research | code-review | code-generate | analyze"
frameworks: ["CO-STAR", "RISEN"]    # Optional: named frameworks applied

role: "Who the AI acts as"
audience: "Who the output is for"
goal: "What the AI should achieve"
constraints:
  - "What the AI must not do"
  - "Boundaries on scope, length, or approach"
output_format: "Expected structure of the response"
self_check: "Instruction for the AI to verify its own output"
```

---

## Named Frameworks

### CO-STAR

A 6-element prompt framework for structured task framing:

| Element | Purpose | Example |
|---------|---------|---------|
| **C** — Context | Background information the AI needs | "This is a Python FastAPI service handling user authentication" |
| **O** — Objective | What the AI should accomplish | "Identify security vulnerabilities in the auth flow" |
| **S** — Style | Writing or analysis style | "Technical, precise, citing specific lines" |
| **T** — Tone | Emotional register | "Direct and professional, not alarmist" |
| **A** — Audience | Who will read the output | "Senior backend developer" |
| **R** — Response | Expected format | "Numbered list of findings with severity ratings" |

### RISEN

A 5-element framework emphasizing role and narrowing:

| Element | Purpose | Example |
|---------|---------|---------|
| **R** — Role | Who the AI should act as | "You are a senior security auditor" |
| **I** — Instructions | What to do | "Review this authentication module" |
| **S** — Steps | How to do it (ordered) | "1. Check input validation 2. Check token handling 3. Check error messages" |
| **E** — End goal | Success criteria | "A prioritized list of vulnerabilities with remediation steps" |
| **N** — Narrowing | Constraints and exclusions | "Focus only on auth — ignore unrelated code style issues" |

---

## Template Catalog

### 1. Edit

```yaml
name: "edit-clarity"
version: "1.0.0"
category: "edit"

role: "Professional editor specializing in technical writing"
audience: "The original author"
goal: "Revise the provided text for clarity, conciseness, and logical flow"
constraints:
  - "Preserve the author's voice and intent"
  - "Do not add new information or arguments"
  - "Do not change technical terminology"
  - "Flag passages that are ambiguous rather than guessing meaning"
output_format: "Revised text with inline comments explaining significant changes"
self_check: "Verify every change improves clarity without altering meaning"
```

### 2. Critique

```yaml
name: "critique-structured"
version: "1.0.0"
category: "critique"

role: "Critical reviewer with domain expertise"
audience: "The creator of the work"
goal: "Evaluate the provided work against explicit criteria and provide actionable feedback"
constraints:
  - "Separate observations (what you see) from judgments (what you think)"
  - "Provide specific examples for every criticism"
  - "Include at least one strength for every weakness identified"
  - "Do not rewrite — only identify issues and suggest directions"
output_format: |
  ## Strengths
  - [numbered list]
  ## Areas for Improvement
  - [numbered list with specific examples]
  ## Priority Actions
  - [top 3 most impactful changes]
self_check: "Verify every criticism includes a specific example and a constructive suggestion"
```

### 3. Outline

```yaml
name: "outline-hierarchical"
version: "1.0.0"
category: "outline"

role: "Structural thinker and information architect"
audience: "The author who will flesh out the outline"
goal: "Generate a hierarchical outline from the provided topic or thesis"
constraints:
  - "Maximum 3 levels of nesting"
  - "Each section heading should be self-explanatory"
  - "Include estimated word count or scope for each section"
  - "Do not write prose — headings and bullet points only"
output_format: |
  # Title
  ## Section 1 (~N words)
  - Key point A
    - Sub-point
  - Key point B
  ## Section 2 (~N words)
  ...
self_check: "Verify the outline covers the thesis completely and sections flow logically"
```

### 4. Summarize

```yaml
name: "summarize-preserve"
version: "1.0.0"
category: "summarize"

role: "Research analyst skilled in distillation"
audience: "Someone who needs the key points without reading the full text"
goal: "Condense the provided content while preserving all key points, arguments, and conclusions"
constraints:
  - "Do not add interpretation or opinion"
  - "Preserve the original structure and argument flow"
  - "Flag any ambiguities in the source material"
  - "Target length: 20-30% of original"
output_format: |
  ## Summary
  [condensed text]
  ## Key Points
  - [bulleted list of essential takeaways]
  ## Omitted Details
  - [what was left out and why]
self_check: "Verify every key argument from the original appears in the summary"
```

### 5. Research

```yaml
name: "research-synthesize"
version: "1.0.0"
category: "research"

role: "Research analyst with expertise in the relevant domain"
audience: "Decision-maker who needs synthesized findings"
goal: "Synthesize information on the provided topic from multiple angles"
constraints:
  - "Distinguish established facts from opinions and speculation"
  - "Cite sources or indicate when claims are unverifiable"
  - "Present competing perspectives fairly"
  - "Flag gaps in available information"
output_format: |
  ## Overview
  [topic context]
  ## Key Findings
  - [numbered findings with confidence level]
  ## Competing Perspectives
  - [perspective A vs. perspective B]
  ## Gaps and Unknowns
  - [what remains unclear]
  ## Recommendations
  - [actionable next steps]
self_check: "Verify all claims are attributed and competing views are represented"
```

### 6. Code Review

```yaml
name: "code-review-comprehensive"
version: "1.0.0"
category: "code-review"

role: "Senior software engineer conducting a thorough code review"
audience: "The code author"
goal: "Analyze the provided code for bugs, style issues, security vulnerabilities, and design concerns"
constraints:
  - "Cite specific line numbers or code snippets"
  - "Categorize findings by severity: critical, warning, suggestion"
  - "Do not rewrite the code — describe what should change and why"
  - "Focus on correctness first, style second"
output_format: |
  ## Critical Issues
  - [must fix before merge]
  ## Warnings
  - [should fix, potential problems]
  ## Suggestions
  - [style, readability, minor improvements]
  ## Security Notes
  - [any security-relevant observations]
self_check: "Verify every finding includes the specific code location and a clear rationale"
```

### 7. Code Generate

```yaml
name: "code-generate-spec"
version: "1.0.0"
category: "code-generate"

role: "Software engineer implementing a specification"
audience: "The developer who will maintain this code"
goal: "Produce working code that implements the provided specification"
constraints:
  - "Follow the project's existing code style and conventions"
  - "Include error handling for all failure modes"
  - "Add docstrings or comments explaining non-obvious logic"
  - "Do not import libraries not already in the project's dependencies"
  - "Include type hints (Python) or type annotations (TypeScript)"
output_format: |
  ```language
  [implementation]
  ```
  ## Design Decisions
  - [why this approach was chosen]
  ## Testing Notes
  - [how to test this code]
  ## Known Limitations
  - [what this implementation does not handle]
self_check: "Verify the code handles all edge cases in the specification and compiles/runs"
```

### 8. Analyze

```yaml
name: "analyze-patterns"
version: "1.0.0"
category: "analyze"

role: "Analyst skilled in pattern recognition and data interpretation"
audience: "The person who provided the content for analysis"
goal: "Extract patterns, themes, or structured data from the provided content"
constraints:
  - "Support claims with specific evidence from the content"
  - "Distinguish strong patterns (multiple occurrences) from weak signals (single occurrence)"
  - "Do not impose patterns that are not supported by the data"
  - "Quantify where possible (frequency, percentage, distribution)"
output_format: |
  ## Primary Patterns
  - [pattern name]: [description + evidence]
  ## Secondary Signals
  - [weaker patterns worth noting]
  ## Anomalies
  - [data points that don't fit any pattern]
  ## Visualization Suggestion
  - [how this data could be visualized]
self_check: "Verify every identified pattern has at least two supporting data points"
```

---

## Model-Specific Formatting Tips

### Claude (Anthropic)

- Use XML tags for structured sections: `<context>`, `<instructions>`, `<constraints>`
- Extended thinking mode benefits from explicit reasoning steps
- Responds well to "think step by step" for complex analysis
- Supports 200K context — safe to include substantial reference material

### GPT (OpenAI)

- Use markdown headings and bullet lists for structure
- System message for persistent role/constraints, user message for task
- JSON mode available for structured output — request it explicitly
- Shorter context window — be selective with included material

### Local Models (Ollama, llama.cpp)

- Simpler prompts perform better — reduce meta-instructions
- Shorter context windows — prioritize the most relevant content
- May need explicit output format examples rather than descriptions
- Temperature sensitivity varies by model — test before relying on defaults

---

## Versioning Rules

- Templates use SemVer: `MAJOR.MINOR.PATCH`
- **MAJOR**: Breaking change to template structure or intent
- **MINOR**: New optional fields or expanded guidance
- **PATCH**: Typo fixes, clarification without behavior change
- Old versions are retained in `docs/examples/prompt-templates/` for reference

---

## Cross-References

- `ai-interaction-model.md` — Conceptual model for AI interactions
- `ai-gateway-architecture.md` — Gateway transformer layer consumes these templates (F-40)
- `prompt-anti-patterns.md` — What these templates help you avoid (F-71)
- `explore-vs-production-modes.md` — Mode-specific template selection (F-42)
