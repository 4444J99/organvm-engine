# Prompt Anti-Pattern Catalog

> **Governance**: Commandment #3 (AI as Instrument, Not Oracle)
> **Scope**: All AI-mediated work across the eight-organ system
> **Version**: 1.0
> **Backlog**: F-71

---

## Why This Exists

Good prompts have templates (see `prompt-template-library.md`). Bad prompts also have
patterns — recurring mistakes that waste tokens, produce poor output, and create
false confidence. Naming these anti-patterns makes them recognizable and avoidable.

This catalog documents 12 named anti-patterns. Each entry includes a description of
the pattern, a concrete example showing what it looks like, and a fix describing
what to do instead.

---

## The Catalog

### 1. Context Dumping

**Description**: Pasting entire files, repositories, or large documents into a prompt
without focus or direction. The AI receives a wall of content with no guidance on
what matters.

**Example**:
> "Here's my entire codebase (47 files). Find the bug."

**Fix**: Provide only the relevant excerpts. State which file, function, or behavior
is problematic. Include the error message, expected behavior, and actual behavior.
If context is genuinely large, summarize and let the AI ask for specific files.

---

### 2. Overloading

**Description**: Asking multiple unrelated tasks in a single prompt. The AI attempts
to address all of them, doing none well.

**Example**:
> "Review this PR for security issues, also write the release notes, and can you
> suggest a better name for the project?"

**Fix**: One task per prompt. If tasks are related (e.g., review code then write
release notes based on the review), chain them sequentially with clear separation.

---

### 3. Ambiguity

**Description**: Requesting improvement without specifying dimensions. "Make it better"
is not actionable — better how? Clearer? Faster? More secure? Shorter?

**Example**:
> "Can you improve this function?"

**Fix**: Specify the improvement dimensions: "Improve this function's error handling —
it currently swallows exceptions silently. Add specific error types and meaningful
messages."

---

### 4. Leading

**Description**: Framing a question to push the AI toward a predetermined answer.
This turns the AI into a yes-machine instead of an analytical tool.

**Example**:
> "Don't you think using a microservices architecture would be better here?"

**Fix**: Ask open questions: "What architecture would you recommend for this system,
given these constraints? Compare at least two options with trade-offs."

---

### 5. Role Confusion

**Description**: Asking the AI to simultaneously be the architect, implementer,
reviewer, and tester. Each role has different objectives and constraints — mixing
them produces shallow output.

**Example**:
> "Design the system, write the code, review it for bugs, and write the tests."

**Fix**: Use one role per session or prompt. Architect first, then implement, then
review. The prompt template library (see `prompt-template-library.md`) provides
distinct templates for each role.

---

### 6. Infinite Iteration

**Description**: Endless "try again" loops without changing the prompt, context, or
constraints. If the first three attempts don't produce good output, the fourth
attempt with the same input won't either.

**Example**:
> "No, that's not right. Try again."
> "Still not what I want. Try again."
> "One more time."

**Fix**: Apply the Three-Prompt Rule. After three attempts: stop, diagnose
why the output doesn't match expectations, rewrite the prompt with better
constraints, provide an example of what good output looks like, or switch approach
entirely.

---

### 7. Premature Optimization

**Description**: Optimizing AI output for performance, elegance, or style before
verifying it is correct. A beautifully refactored function that produces wrong
results is worse than an ugly one that works.

**Example**:
> "Make this more elegant and idiomatic" (before testing it works)

**Fix**: Prove correctness first, then polish. Verify the output runs, passes tests,
and handles edge cases before requesting style improvements.

---

### 8. Trust Without Verify

**Description**: Accepting AI output without testing, reviewing, or understanding it.
The AI is confident — but confidence is not correctness.

**Example**:
> (Copies AI-generated code directly into production without reading it)

**Fix**: Always run tests. Always review the code. If you can't explain what the
code does, you don't understand it well enough to ship it. See the AI-free practice
cadence (`ai-free-practice-cadence.md`) for maintaining the skills needed to verify.

---

### 9. Copy-Paste Blindness

**Description**: Copying AI-generated code into the project without reading or
understanding it. Related to Trust Without Verify, but specifically about the
mechanical act of pasting without comprehension.

**Example**:
> (Copies a 200-line function from AI chat into the codebase, commits, pushes)

**Fix**: Read every line before committing. Explain the code to yourself (or a
rubber duck). If any part is unclear, ask the AI to explain it — or better, figure
it out yourself.

---

### 10. Scope Creep via AI

**Description**: Using the ease of AI generation to expand scope beyond the original
task. "While you're at it" is the most dangerous phrase in AI-assisted development.

**Example**:
> "While you're implementing this API endpoint, also add caching, rate limiting,
> an admin dashboard, and a migration script."

**Fix**: Stick to the session scope. If new work surfaces, create new issues for it.
The conductor session model enforces scope — respect it. One task, one session,
one branch.

---

### 11. Temperature Mismatch

**Description**: Using creative/high-variance settings for tasks that require
determinism, or using deterministic settings for tasks that benefit from creativity.

**Example**:
> Using temperature=1.0 for generating a database migration script
> Using temperature=0.0 for brainstorming product names

**Fix**: Match temperature to mode. Production code and deterministic tasks use low
temperature (0.0–0.3). Brainstorming, naming, and creative exploration use higher
temperature (0.7–1.0). See `explore-vs-production-modes.md` for mode-specific
settings.

---

### 12. Model Mismatch

**Description**: Using expensive, high-capability models for simple tasks (formatting,
renaming, boilerplate) or cheap, limited models for complex tasks (architecture
review, security analysis, nuanced writing).

**Example**:
> Using claude-opus-4-20250514 to rename a variable across 5 files
> Using llama3.2:3b to review a security-critical authentication module

**Fix**: Right-size model selection to task complexity. The AI gateway architecture
(see `ai-gateway-architecture.md`) can automate this through sensitivity-based
routing, but manual selection should also follow this principle:

| Task Complexity | Recommended Model Tier |
|----------------|----------------------|
| Formatting, boilerplate, simple transforms | Small/fast (local or GPT-4o-mini) |
| Standard code generation, documentation | Mid-tier (Claude Sonnet, GPT-4o) |
| Architecture review, security analysis, complex reasoning | Top-tier (Claude Opus, GPT-4o) |
| Confidential data tasks | Local models only (any size) |

---

## Quick Reference Table

| # | Anti-Pattern | One-Line Fix |
|---|-------------|-------------|
| 1 | Context Dumping | Provide only relevant excerpts with clear focus |
| 2 | Overloading | One task per prompt |
| 3 | Ambiguity | Specify improvement dimensions |
| 4 | Leading | Ask open questions |
| 5 | Role Confusion | One role per session |
| 6 | Infinite Iteration | Three-Prompt Rule — stop, diagnose, rewrite |
| 7 | Premature Optimization | Prove correctness before polishing |
| 8 | Trust Without Verify | Always test, always review |
| 9 | Copy-Paste Blindness | Read and explain before committing |
| 10 | Scope Creep via AI | Stick to session scope |
| 11 | Temperature Mismatch | Match temperature to mode |
| 12 | Model Mismatch | Right-size model to task complexity |

---

## Cross-References

- `prompt-template-library.md` — Positive patterns that prevent anti-patterns (F-41)
- `explore-vs-production-modes.md` — Mode-specific settings for temperature and constraints (F-42)
- `ai-gateway-architecture.md` — Automated routing prevents Model Mismatch (F-40)
- `ai-free-practice-cadence.md` — Maintains skills needed to detect Trust Without Verify (F-70)
- `ai-interaction-manifest.md` — Logging interactions creates accountability (F-43)
