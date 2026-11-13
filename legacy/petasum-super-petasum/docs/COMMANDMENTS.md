# Organization Commandments

<a id="top"></a>

> *We will be at the forefront of society, guiding the automated world's businesses and workforce away from collapse or stagnation — towards ethical and meaningful solutions that facilitate the rapid evolution of advanced empowerment for both employers and employees — in the workforce and the lifeforce.*
>
> — ORGANVM North Star (see `meta-organvm/VISION.md`)

These commandments exist to make that vision enforceable. The principles below govern how we build, ship, and maintain — ensuring that automation amplifies human capability rather than eroding it, and that a system of 105 repositories remains coherent enough for one person to operate at institutional scale.

---

This document outlines the core principles and commandments that guide our organization-wide issue tracking and project management practices. These principles are inspired by best practices from leading open-source projects including Semgrep, TensorFlow, and Schema.org.

**All principles herein are derived from and subordinate to the meta-principle of logical consistency.** See [PRINCIPLE_CONFLICTS.md](PRINCIPLE_CONFLICTS.md) for the complete logic-first framework.

## Table of Contents
1. [Meta-Principle (Level 0)](#meta-principle-level-0)
2. [Core Principles](#core-principles)
3. [Application to Organization-Wide Issue Tracking](#application-to-organization-wide-issue-tracking)
4. [Contributing to These Principles](#contributing-to-these-principles)
5. [Logical Framework Reference](#logical-framework-reference)
6. [Original Inspiration Sources](#original-inspiration-sources)

[Back to Top](#top)

---

## Meta-Principle (Level 0)

### Logic & Logical Consistency
**The supreme principle from which all others derive.**

- All organizational decisions must be logically consistent
- When principles conflict, logical analysis determines resolution
- Contradictions are impermissible and must be resolved
- All principles below are valid insofar as they serve logical coherence

[Back to Top](#top)

## Core Principles

### From Semgrep Philosophy
*(Classified as Level 1-4 based on logical derivation)*

#### 1. Free & Open Source (Level 3: Community Principle)
**Logical Derivation**: Open source enables verification, which is a logical necessity for validating correctness.

- All organizational tools and templates should be freely available and open source
- Empower community involvement and collaboration
- No proprietary barriers to participation
- **Logic**: Closed systems cannot be independently verified; verification is required for logical confidence

#### 2. Privacy & Security First (Level 2: Operational Principle)
**Logical Derivation**: Security failures create logical impossibilities - compromised systems cannot reliably execute intended logic.

- Sensitive information should never leave your organization without explicit consent
- Keep code reviews, discussions, and data within appropriate security boundaries
- Default to secure practices in all workflows and automation
- **Logic**: Insecure systems are logically unreliable; reliability requires security

#### 3. Support Many Use Cases (Level 3: Community Principle)
**Logical Derivation**: Diverse use cases provide more data points for logical validation; flexibility is logically more robust than rigidity.

- Templates and workflows should be flexible and adaptable
- If a standard GitHub feature can accomplish something, we should support it
- Accommodate diverse team structures and project types
- **Logic**: Rigid systems fail when assumptions break; logical systems adapt to varied inputs

#### 4. Beginner-friendly & Human-readable (Level 3: Community Principle)
**Logical Derivation**: Clear communication is a logical necessity; ambiguity prevents verification and introduces errors.

- Documentation should be accessible to newcomers
- Templates should be self-explanatory with clear guidance
- Use plain language over jargon where possible
- **Logic**: Obscure communication creates logical barriers; clarity enables logical participation

#### 5. Deterministic & Reliable (Level 2: Operational Principle)
**Logical Derivation**: Determinism is a direct expression of logical consistency; same inputs must yield same outputs.

- Workflows should produce consistent, predictable results
- Automation should be reliable and fail gracefully
- Given the same inputs, expect the same outputs
- **Logic**: Non-determinism violates logical causality; reliable systems are logically necessary

#### 6. Safe Execution (Level 2: Operational Principle)
**Logical Derivation**: Unsafe execution creates unpredictable states; predictability is a logical requirement for reliable systems.

- No arbitrary code execution in templates or workflows
- Validate all inputs and outputs
- Use GitHub's native features and well-tested actions
- **Logic**: Arbitrary execution prevents logical verification; validation ensures logical soundness

#### 7. Performance Matters (Level 2: Operational Principle)
**Logical Derivation**: Poor performance creates logical limits - infinite time requirements are logically equivalent to impossibility.

- Keep processes efficient and fast
- Avoid unnecessary complexity
- Optimize for developer productivity
- **Logic**: Slow systems approach logical impossibility at scale; efficiency is a logical optimization

### From TensorFlow Principles
*(Classified as Level 1-4 based on logical derivation)*

#### 8. Quality Over Quantity (Level 2: Operational Principle)
**Logical Derivation**: Logical value maximization requires prioritizing high-impact contributions over volume.

- Each contribution should meaningfully improve the organization's processes
- Focus on high-impact changes rather than numerous small tweaks
- Prioritize maintainability and long-term value
- **Logic**: Many low-quality items create logical overhead; few high-quality items maximize logical value

#### 9. Community Collaboration (Level 3: Community Principle)
**Logical Derivation**: Diverse perspectives strengthen logical analysis through multiple validation paths.

- Foster open discussion and consensus-building
- Encourage cross-team collaboration
- Value diverse perspectives and experiences
- **Logic**: Multiple viewpoints reduce logical blind spots; collaboration enhances verification

#### 10. Transparency (Level 1: Foundational Principle)
**Logical Derivation**: Transparency is required for verification; hidden logic cannot be validated.

- All decisions and changes should be communicated openly
- Document the reasoning behind organizational policies
- Make processes visible and understandable to all
- **Logic**: Opaque systems cannot be logically verified; transparency enables logical scrutiny

#### 11. Backward Compatibility (Level 4: Stability Principle)
**Logical Derivation**: Logical respect for existing dependencies; stability enables predictability.

- Minimize breaking changes to existing workflows
- Provide migration paths when changes are necessary
- Consider the impact on all stakeholders before major changes
- **Logic**: Breaking changes create logical discontinuities; compatibility preserves logical chains

#### 12. Security & Privacy Standards (Level 2: Operational Principle)
**Logical Derivation**: Security is prerequisite for reliability; privacy is logical consequence of autonomy.

- Maintain high standards for data privacy and security
- Regularly review and update security practices
- Protect sensitive organizational information
- **Logic**: Compromised systems produce logically unreliable outputs; privacy protects logical autonomy

### From Schema.org Standards
*(Classified as Level 1-4 based on logical derivation)*

#### 13. Interoperability (Level 4: Stability Principle)
**Logical Derivation**: Logical systems must integrate; isolated systems create logical barriers.

- Ensure templates and workflows work across different teams and repositories
- Avoid team-specific or tool-specific assumptions
- Design for integration with existing tools and processes
- **Logic**: Non-interoperable systems create logical silos; integration enables logical flow

#### 14. Clarity & Precision (Level 1: Foundational Principle)
**Logical Derivation**: Ambiguity violates logical determinacy; precision is required for logical validity.

- Aim for clear, non-ambiguous definitions in all documentation
- Use consistent terminology across all templates
- Provide examples to illustrate concepts
- **Logic**: Ambiguous statements lack logical truth value; precision enables logical reasoning

#### 15. Inclusivity (Level 3: Community Principle)
**Logical Derivation**: Maximizing participant pool increases logical validation opportunities.

- Welcome contributions from all organization members
- Lower barriers to participation
- Support contributors at all skill levels
- **Logic**: Exclusion reduces available logical perspectives; inclusion maximizes verification power

#### 16. Stability (Level 4: Stability Principle)
**Logical Derivation**: Stable foundations enable reliable logical reasoning over time.

- Changes should not break existing issues or workflows
- Maintain stable interfaces and data structures
- Version major changes appropriately
- **Logic**: Unstable systems prevent long-term logical planning; stability enables logical prediction

### From Incident Lessons
*(Classified as Level 2 based on logical derivation)*

#### 17. Non-Destructive Autonomy (Level 2: Operational Principle)
**Logical Derivation**: Irreversible actions by autonomous agents violate predictability;
recoverability is a logical prerequisite for safe autonomy.

- Autonomous agents MUST NOT permanently delete files; use archival (`mv` to `.archive/`)
  or soft-delete (`trash`) instead of `rm`
- Files not tracked by version control require CRITICAL-level approval before any
  destructive operation
- Cleanup phases in agent plans MUST enumerate target files explicitly and await
  human confirmation before proceeding
- Audit logging of destructive operations MUST have a local fallback when the
  primary audit store is unavailable
- Source materials, prototypes, and design artifacts are classified as protected
  and require elevated permissions to modify or remove
- **Logic**: Permanent deletion creates irreversible state loss; logical systems
  require recoverability for error correction

#### 18. Bounded Autonomous Execution (Level 2: Operational Principle)
**Logical Derivation**: Unbounded autonomy in non-interactive agents violates predictability;
scope limits and rollback triggers are logical prerequisites for safe unattended operation.

- Non-interactive agents (background, scheduled, auto-sync) MUST declare a single-repo
  scope at session start; cross-repo writes are forbidden within a single session
- A mandatory dry-run pass MUST precede any write operations in non-interactive mode;
  the dry-run output is logged and diffed against the live run
- Token budget and wall-clock timeout MUST be declared at session start; exceeding
  either triggers immediate rollback of uncommitted changes
- Automatic rollback is triggered by: (1) git merge conflict, (2) CI failure on
  committed changes, (3) file write outside declared scope, (4) budget exceeded,
  (5) unhandled exception, (6) session timeout
- Cross-organ impulses discovered during execution MUST be captured as GitHub issues
  in the target repo, not acted upon directly
- Every non-interactive session MUST produce an audit record: session ID, agent name,
  repo path, start/end timestamps, files read, files written, rollback events
- See `docs/NON-INTERACTIVE-AGENT-SAFETY.md` for the full safety protocol and
  `agent--claude-smith` ScopeValidator (F-35) for code-level enforcement
- **Logic**: Unbounded agents create unpredictable state mutations; logical systems
  require bounded execution contexts for verifiable outcomes

[Back to Top](#top)

## Application to Organization-Wide Issue Tracking

These commandments apply to our organization-wide issue tracking practices in the following ways:

### Issue Templates
- **Beginner-friendly**: Templates include clear instructions and examples
- **Clarity**: Required fields are well-defined with validation
- **Flexibility**: Support multiple issue types (initiatives, incidents, RFCs)

### Workflows & Automation
- **Safe Execution**: Use only trusted GitHub Actions
- **Deterministic**: Workflows produce predictable results
- **Performance**: Optimize for fast execution and minimal overhead

### Documentation
- **Transparency**: All processes are fully documented
- **Inclusivity**: Documentation written for all skill levels
- **Interoperability**: Guidance works across different team structures

### Community Practices
- **Collaboration**: Encourage cross-team discussion on org-wide issues
- **Quality**: Focus on high-impact organizational initiatives
- **Backward Compatibility**: Maintain existing processes while improving

[Back to Top](#top)

## Contributing to These Principles

These commandments are living guidelines, **but all changes must pass logical scrutiny**. As our organization evolves, we should:

1. **Review through logic**: Assess whether principles remain logically sound and consistent
2. **Propose with reasoning**: Open discussions or RFCs with clear logical justification
3. **Share logical insights**: Document what works, what doesn't, and WHY (logical analysis)
4. **Stay logically principled**: Use logical reasoning to guide all decision-making
5. **Challenge inconsistencies**: Any principle that creates logical contradictions must be reformed
6. **Verify derivations**: Ensure all principles trace back to logical foundations

**Key requirement**: Any proposed principle must include its logical derivation and demonstrate consistency with the Level 0 meta-principle of logic.

[Back to Top](#top)

## Logical Framework Reference

For detailed information on conflict resolution and the logic-first hierarchy:
- See [PRINCIPLE_CONFLICTS.md](PRINCIPLE_CONFLICTS.md) for complete logical framework
- See [LOGIC_FRAMEWORK.md](LOGIC_FRAMEWORK.md) for philosophical and practical foundations

[Back to Top](#top)

## Original Inspiration Sources

These principles were inspired by (but logically analyzed and reorganized):
- [Semgrep Philosophy](https://semgrep.dev/docs/contributing/semgrep-philosophy)
- [TensorFlow Contributing Guidelines](https://github.com/tensorflow/tensorflow/blob/master/CONTRIBUTING.md)
- [Schema.org Community Guidelines](https://github.com/schemaorg/schemaorg)

---

*These commandments represent our commitment to building **logically consistent, effective, inclusive, and sustainable** organization-wide processes.*

**Remember: Logic is not one principle among many—it is the foundation upon which all others rest.**

[Back to Top](#top)
