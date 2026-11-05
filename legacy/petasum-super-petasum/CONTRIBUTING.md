# Contributing to petasum-super-petasum

Thank you for your interest in contributing to this organization-wide issue tracking template repository!

## Logic-First Principles

**All contributions must align with our logic-first framework.**

Before contributing, please familiarize yourself with:
- [LOGIC_FRAMEWORK.md](LOGIC_FRAMEWORK.md) - Philosophical and practical foundations
- [PRINCIPLE_CONFLICTS.md](PRINCIPLE_CONFLICTS.md) - Conflict resolution and hierarchy
- [COMMANDMENTS.md](COMMANDMENTS.md) - Core principles with logical derivations

**Key requirement**: Any proposal must include logical reasoning. "I think this would be better" is insufficient; explain WHY through logical analysis.

## How to Use This Repository

This repository serves as a template for setting up organization-wide issue tracking infrastructure. There are two main ways to use it:

### 1. As a Template for Your Organization

1. Use this repository as a template to create your own `org-issues` repository
2. Customize the templates to fit your organization's needs
3. Configure the workflows with your organization's specific settings

### 2. Contributing Improvements

If you'd like to improve these templates for everyone:

1. Fork this repository
2. Create a feature branch (`git checkout -b feature/improve-templates`)
3. Make your changes
4. Ensure all YAML files are valid
5. Update the README if you're adding new features
6. Submit a pull request

## Template Customization Guidelines

When customizing these templates for your organization:

1. **Update placeholders**: Replace `your-org` with your actual organization name
2. **Adjust labels**: Modify the label names to match your organization's conventions
3. **Configure workflows**: Update the GitHub Actions workflow with your Project URL and secrets
4. **Modify fields**: Add or remove fields from issue templates based on your needs
5. **Update contact links**: Change URLs in `config.yml` to point to your organization's resources

## Code Quality

- All YAML files must be valid and properly formatted
- Follow GitHub's issue template and workflow syntax
- Test templates in a real repository before submitting PRs
- Document any new features or changes in the README
- **Adhere to the logic-first principles outlined in [COMMANDMENTS.md](COMMANDMENTS.md)**

### Logical Standards for Contributions

Every contribution should:

1. **Be logically justified**: Explain the reasoning, not just the change
2. **Maintain consistency**: Ensure no contradictions with existing principles
3. **Demonstrate soundness**: Valid reasoning from true premises
4. **Enable verification**: Provide clear, testable claims
5. **Document reasoning**: Make your logical chain transparent

### Example of Good Contribution Message

```
Problem: Current incident template lacks severity estimation guidance

Logical Analysis:
- Premise: Inconsistent severity labeling creates communication failures (observed)
- Premise: Communication failures delay incident response (causal link)
- Premise: Delayed response increases impact (empirical fact)
- Conclusion: Guidance improves severity consistency
- Therefore: Guidance reduces incident impact

Proposed Solution: Add severity matrix to incident template

Evidence: Similar matrices reduced mis-labeling by 60% in prior organizations (cite)

Logical Classification: Level 2 (Operational) - improves system reliability
```

### Example of Insufficient Contribution Message

```
"The incident template should have more fields because it would be better"
→ No logical reasoning
→ No evidence
→ Unclear benefit
→ Cannot evaluate logically
```

## Contribution Review Process

All contributions will be evaluated based on:

1. **Logical Soundness** (Level 0): Does the reasoning hold?
2. **Consistency** (Level 1): Does it contradict existing principles?
3. **Practical Value** (Level 2): Does it improve operational effectiveness?
4. **Community Impact** (Level 3): Does it enhance collaboration?
5. **Stability** (Level 4): Does it maintain compatibility?

If a contribution conflicts with existing principles, the conflict will be resolved using the framework in [PRINCIPLE_CONFLICTS.md](PRINCIPLE_CONFLICTS.md).

## Questions?

If you have questions about using these templates or the logic-first framework, please:
1. Review [LOGIC_FRAMEWORK.md](LOGIC_FRAMEWORK.md) first
2. Open a discussion with your specific logical question
3. Present your reasoning for community feedback

**Remember**: Questions framed with logical reasoning get better answers. Instead of "Should I do X?", ask "Given premises A, B, C, does X logically follow?"
