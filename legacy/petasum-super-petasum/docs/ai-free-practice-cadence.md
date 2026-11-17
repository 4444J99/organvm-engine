# AI-Free Practice Cadence

> **Governance**: Commandment #2 (Human Judgment as Final Authority)
> **Scope**: Personal skill maintenance for AI-augmented practitioners
> **Version**: 1.0
> **Backlog**: F-70

---

## Why This Exists

AI tools are force multipliers. They also create dependency. A developer who relies
on Copilot for every function signature gradually loses the ability to write code
from memory. An architect who asks Claude for every design decision stops developing
architectural intuition. A writer who delegates all first drafts to AI loses the
muscle memory of composition.

This is not speculation — it is the predictable consequence of outsourcing cognitive
work. The skills that make a human practitioner valuable are exactly the skills that
atrophy fastest when delegated: debugging intuition, architectural judgment, the
ability to evaluate whether AI output is correct.

The AI-free practice cadence is a deliberate, scheduled antidote: regular sessions
where AI tools are completely disabled, forcing direct engagement with the craft.

---

## The Cadence

### Weekly: 2–4 Hours of AI-Free Coding

**Frequency**: Every week, minimum 2 hours, target 4 hours.

**Rules**:
- No Copilot, no autocomplete, no AI chat
- No searching for AI-generated answers (Stack Overflow is fine; "ask ChatGPT" is not)
- IDE assistance (syntax highlighting, basic autocomplete from project symbols) is allowed
- Debugger, profiler, and standard tooling are allowed

**What to do**:
- Pick a task from the current backlog (not a contrived exercise)
- Work through it using only documentation, source code, and your own reasoning
- Note where you feel friction — those are the atrophy points

**What to track**:
- Time to completion vs. AI-assisted estimate
- Points where you reached for AI and had to stop yourself
- Errors you caught that AI might have masked

### Monthly: "From Scratch" Exercise

**Frequency**: Once per month, 1–2 hours.

**Rules**:
- Implement a pattern you use regularly — but from scratch, without AI
- No copy-pasting from previous implementations
- Reference documentation is allowed; reference code from your own repos is not

**Suggested exercises**:
- Implement a REST API endpoint with validation and error handling
- Write a parser for a simple grammar (JSON subset, CSV, YAML)
- Build a state machine for a workflow you've implemented before
- Implement a common data structure (LRU cache, trie, priority queue)
- Write a test suite for an existing module, without AI assistance
- Create a CLI tool with argument parsing and help text

**What to track**:
- Which patterns you remembered vs. had to look up
- Time to working implementation
- Code quality compared to AI-assisted output

### Quarterly: Skills Self-Assessment

**Frequency**: Once per quarter, 1 hour for assessment + reflection.

**Assess against baseline in four skill areas**:

| Skill Area | Assessment Method | Healthy Baseline |
|-----------|------------------|-----------------|
| Debugging | Time to diagnose and fix a non-trivial bug (from logs/debugger only) | Within 2x of pre-AI speed |
| Architecture | Design a system on paper before code — evaluate coherence | Clear, justified decisions without AI validation |
| Code review | Review a PR without AI — compare findings with AI review after | Catch 70%+ of what AI catches, plus context AI misses |
| Writing | Draft a spec or doc without AI — evaluate clarity | Coherent, structured, complete (even if slower) |

**Process**:
1. Perform each assessment exercise
2. Record results in a private log
3. Compare with previous quarter
4. If any area shows significant decline, increase AI-free time for that area

---

## Skill Area Exercises

### Debugging

**Exercise**: Reproduce and fix a bug using only logs, debugger, and reading code.

- Select a recently closed bug (or introduce one deliberately in a test environment)
- Diagnose root cause without asking AI for help
- Write the fix and verify with tests
- Time yourself — compare with your pre-AI debugging speed

**What atrophies**: Pattern recognition in stack traces, hypothesis formation,
systematic elimination of causes, reading code you didn't write.

### Architecture

**Exercise**: Design a system on paper or whiteboard before any code.

- Choose an upcoming feature or a hypothetical system
- Sketch components, data flow, interfaces, failure modes
- Make and justify technology choices
- Only after the design is complete, optionally ask AI to critique it

**What atrophies**: Trade-off reasoning, constraint identification, the ability to
hold a system in your head, experience-based judgment about what will and won't work.

### Code Review

**Exercise**: Review a PR without AI assistance, then compare.

- Select a non-trivial PR (your own or a colleague's)
- Review thoroughly: correctness, edge cases, security, style, design
- Write review comments
- After completing your review, run an AI-assisted review and compare
- Track what you caught that AI missed, and vice versa

**What atrophies**: Security intuition, edge case thinking, understanding of project
conventions, the ability to spot subtle logic errors.

### Writing

**Exercise**: Draft documentation or a specification without AI help.

- Choose a module or feature that needs documentation
- Write the full document: purpose, API, examples, edge cases
- Time yourself and assess the output for clarity and completeness
- Compare (after the fact) with an AI-generated version

**What atrophies**: The ability to organize information, explain complex concepts
clearly, anticipate reader questions, write concise prose.

---

## Tracking and Accountability

### Private Log Format

Keep a simple log (plain text, markdown, or journal):

```
## 2026-03-08 — AI-Free Session

Duration: 3 hours
Type: weekly coding
Task: Implement gateway preprocessor classification engine

Observations:
- Struggled with regex for PII detection — would normally ask AI
- Remembered the enum pattern from data-classification but had to re-read the spec
- Debugging took 40 minutes for an off-by-one — AI would have caught it instantly
- Final code quality: comparable to AI-assisted, took ~2x longer

Atrophy points:
- Regex composition (need more practice)
- Test fixture setup (usually delegated)
```

### Trends to Watch

- **Increasing time gap**: If AI-free sessions take progressively longer relative
  to AI-assisted work, atrophy is occurring
- **Reach frequency**: If you find yourself reaching for AI more often during
  AI-free sessions, dependency is growing
- **Error rate**: If AI-free code has significantly more bugs, verification skills
  are declining

---

## Integration with ORGANVM Governance

The AI-free cadence complements the broader governance framework:

- **Commandment #2** requires human judgment as final authority — but judgment
  requires maintained skill
- **Explore mode** (see `explore-vs-production-modes.md`) can be used for AI-free
  practice — branch prefix `practice/` for dedicated skill exercises
- **Production mode** benefits when the human reviewer can actually evaluate AI
  output quality — which requires the skills this cadence maintains

---

## Cross-References

- `COMMANDMENTS.md` — Commandment #2 (Human Judgment as Final Authority)
- `ai-interaction-model.md` — Understanding the layers where human skill matters
- `explore-vs-production-modes.md` — Mode separation supports practice sessions (F-42)
- `prompt-anti-patterns.md` — Trust Without Verify pattern (F-71)
