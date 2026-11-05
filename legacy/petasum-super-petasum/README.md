[![ORGAN-IV: Taxis](https://img.shields.io/badge/ORGAN--IV-Taxis-e65100?style=flat-square)](https://github.com/organvm-iv-taxis)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue?style=flat-square)](LICENSE)

# Petasum Super Petasum

[![CI](https://github.com/organvm-iv-taxis/petasum-super-petasum/actions/workflows/ci.yml/badge.svg)](https://github.com/organvm-iv-taxis/petasum-super-petasum/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-pending-lightgrey)](https://github.com/organvm-iv-taxis/petasum-super-petasum)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/organvm-iv-taxis/petasum-super-petasum/blob/main/LICENSE)
[![Organ IV](https://img.shields.io/badge/Organ-IV%20Taxis-10B981)](https://github.com/organvm-iv-taxis)
[![Status](https://img.shields.io/badge/status-active-brightgreen)](https://github.com/organvm-iv-taxis/petasum-super-petasum)
[![Shell](https://img.shields.io/badge/lang-Shell-informational)](https://github.com/organvm-iv-taxis/petasum-super-petasum)


**Hat on a hat, galerum super galerum, quidquid superat, ad abundantiam, et cetera.**

A logic-first governance framework and cross-repository issue orchestration system for multi-organ organizations. Petasum provides the structural backbone that keeps distributed repositories, teams, and decision processes logically coherent as they scale.

---

## Table of Contents

- [Product Overview](#product-overview)
- [Orchestration Philosophy](#orchestration-philosophy)
- [The Logic-First Framework](#the-logic-first-framework)
- [Technical Architecture](#technical-architecture)
- [Installation and Quick Start](#installation-and-quick-start)
- [Features](#features)
- [Cross-Organ Orchestration](#cross-organ-orchestration)
- [Governance Model](#governance-model)
- [Relationship to Agentic Titan](#relationship-to-agentic-titan)
- [Repository Structure](#repository-structure)
- [Lifecycle and Roadmap](#lifecycle-and-roadmap)
- [Related Work](#related-work)
- [Contributing](#contributing)
- [License](#license)
- [Author](#author)

---

## Product Overview

### Why "Petasum"?

The petasum (or petasus) is the broad-brimmed winged hat of Hermes, the Greek messenger god who moved freely between realms --- conducting souls, carrying messages, and translating between divine and mortal domains. In the ORGAN system, Petasum Super Petasum occupies an analogous role: it is the governance layer that sits atop other governance layers, the orchestration of orchestration, the hat upon the hat.

The Latin phrase *galerum super galerum* --- hat upon hat --- is not decorative self-reference. It describes a real architectural pattern: **meta-governance**. When an organization spans eight organs, each with its own repositories, workflows, and decision cadences, the coordination problem is not merely technical but epistemological. You need a system that governs how governance itself operates. That is what Petasum provides.

### What This Repository Contains

Petasum Super Petasum is a **template repository** and **living governance specification** for organization-wide GitHub infrastructure. It ships:

1. **A logic-first decision framework** --- a five-level principle hierarchy (Logic > Foundational > Operational > Community > Stability) with formal conflict resolution rules, logical derivation chains for every principle, and a documented escalation protocol.

2. **Organization-wide issue templates** --- structured GitHub Issue forms for cross-repository initiatives, multi-service incidents, and RFCs, all grounded in the logic-first framework.

3. **Automated workflows** --- GitHub Actions that route issues to organization projects, notify affected repositories of cross-cutting concerns, and enforce labeling conventions.

4. **A comprehensive implementation roadmap** --- six phases from foundation through continuous evolution, with gate reviews, success criteria, measurement frameworks, and risk mitigation strategies.

5. **A self-critique and audit trail** --- including a comprehensive critique document, principle conflict matrix, and implementation checklist that tracks adoption across the lifecycle.

### The Problem It Solves

As distributed organizations grow, three coordination failures recur with monotonous regularity:

- **Principle collisions**: Team A optimizes for speed; Team B optimizes for security. Neither is wrong, but without a hierarchy, every cross-team decision becomes a political negotiation rather than a logical resolution.
- **Issue fragmentation**: A vulnerability affects twelve repositories. Without centralized tracking, each team discovers it independently, patches it differently, and nobody validates cross-repo consistency.
- **Governance drift**: Early-stage organizations operate on implicit norms. As they scale, those norms diverge per team until the organization is running multiple incompatible governance models simultaneously.

Petasum addresses all three by establishing logic as the supreme meta-principle from which all other organizational principles derive, then providing the templates, workflows, and processes to operationalize that commitment at scale.

---

## Orchestration Philosophy

### Logic as Meta-Principle

Most governance frameworks begin with a list of values and ask teams to balance them. This approach guarantees conflict, because values without a hierarchy produce irresolvable disputes. Petasum takes a different approach: it establishes **logic and logical consistency as the foundational principle** from which all other principles are derived.

This is not an aesthetic preference. Logic is the only self-justifying principle. To argue against logic, you must use logic --- making any such argument self-defeating. Every other organizational value (transparency, security, inclusivity, performance) requires a *reason* to adopt it, and reasons are logical arguments. Logic is the ground on which all other principles stand.

### The Hierarchy of Principles

Petasum organizes all governance principles into five levels, each logically derived from the level above:

| Level | Category | Examples | Logical Basis |
|-------|----------|----------|---------------|
| 0 | **Meta-Principle** | Logic and Logical Consistency | Self-justifying; required for all reasoning |
| 1 | **Foundational** | Transparency, Clarity, Verifiability | Direct logical necessities (hidden logic cannot be validated) |
| 2 | **Operational** | Security, Performance, Determinism, Quality | Derived from logical analysis of effective systems |
| 3 | **Community** | Open Source, Inclusivity, Collaboration | Derived from logical analysis of sustainable cooperation |
| 4 | **Stability** | Backward Compatibility, Interoperability | Derived from logical analysis of sustainable evolution |

When principles at the same level conflict, the framework resolves them through logical analysis of which option better serves the higher-level principle. When principles at different levels conflict, the higher-level principle prevails. This eliminates the "but what about..." paralysis that afflicts value-pluralist governance models.

### Governance as Infrastructure

Petasum treats governance decisions with the same rigor that software engineering applies to infrastructure decisions. Every principle has a logical derivation. Every conflict type has a resolution protocol. Every decision is documented with premises, reasoning, and conclusions. This is not bureaucracy --- it is the organizational equivalent of type safety. Catching contradictions early, in the governance layer, is cheaper than discovering them at deployment time.

---

## The Logic-First Framework

### Core Documents

The framework is specified across four interconnected documents, each serving a distinct function:

**[LOGIC_FRAMEWORK.md](./docs/LOGIC_FRAMEWORK.md)** --- The philosophical and practical foundation. Covers why logic is self-justifying, the three laws of classical logic (identity, non-contradiction, excluded middle), key inference rules (modus ponens, modus tollens, hypothetical syllogism), common logical fallacies to avoid, and advanced topics including modal logic, temporal logic, deontic logic, and Godelian limits. This is the document you read once and reference thereafter.

**[COMMANDMENTS.md](./docs/COMMANDMENTS.md)** --- Sixteen organizational principles classified by hierarchy level, each with an explicit logical derivation. Drawn from analysis of Semgrep, TensorFlow, and Schema.org governance models, then restructured through the logic-first lens. Principles include Free and Open Source (Level 3), Privacy and Security First (Level 2), Deterministic and Reliable (Level 2), Clarity and Precision (Level 1), and Stability (Level 4), among others.

**[PRINCIPLE_CONFLICTS.md](./docs/PRINCIPLE_CONFLICTS.md)** --- The conflict resolution matrix. Defines seven conflict types (Principle vs Logic, Same-Level, Different-Level, Interpretation Dispute, Pragmatic vs Ideal, Short-term vs Long-term, Incomplete Information) and provides resolution approaches and outcome criteria for each. Includes precedent case studies: Security vs Ease of Use, Performance vs Feature Completeness, and Backward Compatibility vs Technical Debt.

**[LIFECYCLE_ROADMAP.md](./docs/LIFECYCLE_ROADMAP.md)** --- The six-phase implementation plan from Foundation (Weeks 1--2) through Evolution (Year 2+). Each phase has objectives, tasks, deliverables, success criteria, and gate reviews with named decision authorities. The roadmap also specifies a measurement framework (leading and lagging indicators), risk mitigation strategies, and a continuous improvement loop.

### The Seven-Step Decision Method

When making any decision under the Petasum framework:

1. **State the question clearly** --- What exactly are we deciding? What are the success criteria?
2. **Identify relevant premises** --- What facts do we know? What assumptions are we making? Are the assumptions justified?
3. **List possible conclusions** --- What are the options? Are there options we have not considered?
4. **Apply logical reasoning** --- Which conclusions follow from the premises? Which options violate logical principles?
5. **Verify consistency** --- Does this conclusion contradict established facts or create new contradictions?
6. **Test completeness** --- Have we considered all relevant factors? What are we potentially missing?
7. **Document the chain** --- Record premises, reasoning, and conclusion to enable future verification.

This method applies equally to architectural decisions, incident triage, hiring, sprint planning, and cross-organ coordination.

---

## Technical Architecture

### Issue Routing System

Petasum implements a label-driven routing architecture using GitHub's native issue infrastructure:

```
User Creates Issue (selects template)
        |
        v
GitHub Applies Template
  - Pre-fills structured fields
  - Auto-applies labels (org-wide, initiative/incident/rfc, needs-triage)
  - Sets title format
        |
        v
Workflow Triggered (on: issues [opened, labeled])
        |
        v
Label Detection
  - org-wide    --> Add to Organization Project
  - cross-repo  --> Parse body for repo references, post coordination comment
  - all-repos   --> Notify all repository maintainers
        |
        v
Organization Project Board
  - Triage view (by priority)
  - Repository view (by affected repos)
  - Status view (by progress)
  - Team view (by ownership)
```

### Workflow Specifications

**add-to-org-project.yml** --- Triggers on issue open and label events. Detects the `org-wide` label. Adds the issue to the organization-level GitHub Project using the `actions/add-to-project@v1` action. Requires an `ORG_PROJECT_TOKEN` secret with Projects read/write and Issues read/write permissions.

**cross-repo-notifications.yml** --- Triggers on label events for `cross-repo` or `all-repos` labels. Parses the issue body for repository references (pattern: `owner/repo`). Posts a structured coordination comment listing referenced repositories, actions for maintainers, and linking syntax. Uses `actions/github-script@v7` for the GitHub API interaction.

**org-issue-notifications.yml** --- Triggers when the `org-wide` label is applied. Posts a comment with priority classification and next steps. Generates a notification summary for stakeholders.

### Label Taxonomy

The labeling system is defined in `.github/labels.yml` and organized into four categories:

| Category | Labels | Purpose |
|----------|--------|---------|
| **Type** | `org-wide`, `security`, `process`, `infrastructure`, `documentation`, `dependency` | Classify the nature of the issue |
| **Priority** | `urgent`, `high-priority`, `medium-priority`, `low-priority` | Drive triage ordering |
| **Status** | `needs-triage`, `in-progress`, `blocked`, `waiting-feedback`, `ready-to-implement` | Track workflow state |
| **Impact** | `breaking-change`, `cross-repo`, `all-repos` | Trigger cross-repository coordination |

### Issue Templates

Three form-based templates (`.yml` format, not markdown) enforce structured data entry:

- **Organization-Wide Initiative** (`org-wide-initiative.yml`) --- For cross-repository initiatives. Fields: summary, problem statement, scope, impacted repositories, owners, success criteria, timeline, risks, communication plan. Auto-labels: `org-wide`, `initiative`, `epic`, `needs-triage`.

- **Organization-Wide Incident** (`org-incident.yml`) --- For multi-service incidents. Fields: severity (SEV-1/2/3 dropdown), start time, detection method, impact assessment, mitigation status, timeline, follow-up actions. Auto-labels: `org-wide`, `incident`, `needs-triage`.

- **RFC** (`org-rfc.yml`) --- For cross-repository proposals. Fields: summary, motivation, design approach, alternatives, affected repos/teams, risks, success metrics. Auto-labels: `org-wide`, `rfc`, `needs-triage`.

A redirect template (`redirect-to-org-repo.yml`) is provided for installation in other repositories, directing users to file organization-wide issues in the central Petasum repository.

---

## Installation and Quick Start

### Option A: Use as a Template

Click **"Use this template"** on the repository page to create a new repository with the full Petasum structure. Then customize:

1. Update `.github/workflows/add-to-org-project.yml` with your organization's Project URL.
2. Update `.github/ISSUE_TEMPLATE/config.yml` with your organization name and discussion URLs.
3. Create the labels defined in `.github/labels.yml` in your repository settings.
4. Create a Fine-Grained Personal Access Token with Projects (R/W) and Issues (R/W) permissions.
5. Add the token as an organization secret named `ORG_PROJECT_TOKEN`.
6. Enable GitHub Discussions if desired.

### Option B: Copy Files Manually

```bash
git clone https://github.com/organvm-iv-taxis/petasum-super-petasum.git
cp -r petasum-super-petasum/.github your-org-repo/
cp petasum-super-petasum/docs/COMMANDMENTS.md your-org-repo/
cp petasum-super-petasum/docs/LOGIC_FRAMEWORK.md your-org-repo/
cp petasum-super-petasum/docs/PRINCIPLE_CONFLICTS.md your-org-repo/
```

### Option C: Install the Redirect Template Only

If you only need to redirect users from a specific repository to your central issue tracker:

```bash
curl -o .github/ISSUE_TEMPLATE/redirect-to-org-repo.yml \
  https://raw.githubusercontent.com/organvm-iv-taxis/petasum-super-petasum/main/.github/ISSUE_TEMPLATE/redirect-to-org-repo.yml
```

### Filing Your First Issue

1. Navigate to the [Issues tab](../../issues).
2. Click **New Issue**.
3. Select a template: Organization-Wide Issue, Security Concern, or Process Improvement.
4. Fill out all required fields. The template will guide you.
5. Submit. The workflow will automatically route the issue to the organization project.

### When to Use This Repository

**File issues here when:**
- The issue affects two or more repositories.
- It is an organization-wide security concern.
- It requires cross-team coordination or governance decisions.
- It concerns organization-wide infrastructure, processes, or policies.

**File in the specific repository when:**
- The issue affects only that repository.
- It is a feature request or bug report scoped to one project.

---

## Features

### Logic-First Decision Framework
All governance decisions are grounded in a five-level principle hierarchy with formal conflict resolution. No more "it depends" --- every conflict type has a documented resolution path. Sixteen principles, each with explicit logical derivation, cover the full spectrum from foundational transparency to operational security to community inclusivity.

### Structured Issue Templates
Form-based GitHub Issue templates with field validation, dropdown selections, and automatic label application. Three templates cover the primary cross-org coordination patterns: initiatives, incidents, and RFCs. Structured data entry reduces ambiguity and enables automation.

### Automated Cross-Repository Coordination
GitHub Actions workflows detect organization-wide issues, add them to project boards, and notify affected repositories. The cross-repo notification system parses issue bodies for repository references and posts structured coordination comments with linking syntax.

### Comprehensive Labeling System
A four-category label taxonomy (Type, Priority, Status, Impact) provides consistent classification across the organization. Labels serve double duty as automation triggers and human-readable status indicators.

### Six-Phase Implementation Roadmap
From Foundation through Evolution, each phase has defined objectives, deliverables, success criteria, gate reviews, and named decision authorities. The roadmap includes a measurement framework with leading and lagging indicators, risk mitigation strategies, and a continuous improvement loop.

### Conflict Resolution Protocols
Seven conflict types with explicit resolution approaches. Standard resolution (90% of cases) applies the hierarchy directly. Complex escalation convenes a logic review, requires formal logical arguments from each position, and synthesizes a superior solution. All resolutions are documented as precedent.

### Self-Critique and Audit Trail
The repository includes a comprehensive critique document that identifies ten major blind spots, ten critical shatter points, and twenty actionable recommendations. This is governance that audits itself.

### Scalability Guidance
Explicit guidance on when this framework is appropriate (20+ repositories, 5+ teams, complex coordination needs) and when simpler alternatives suffice (single team, fewer than 10 repos, existing tools that work). Honest scoping prevents over-engineering.

---

## Cross-Organ Orchestration

### The ORGAN System Context

Petasum Super Petasum operates within ORGAN-IV (Taxis), the orchestration and governance organ of an eight-organ creative-institutional system:

| Organ | Domain | GitHub Organization |
|-------|--------|-------------------|
| I | Theory (epistemology, recursion, ontology) | [organvm-i-theoria](https://github.com/organvm-i-theoria) |
| II | Art (generative, performance, experiential) | [organvm-ii-poiesis](https://github.com/organvm-ii-poiesis) |
| III | Commerce (SaaS, B2B, B2C products) | [organvm-iii-ergon](https://github.com/organvm-iii-ergon) |
| IV | Orchestration (governance, routing) | [organvm-iv-taxis](https://github.com/organvm-iv-taxis) |
| V | Public Process (essays, building in public) | [organvm-v-logos](https://github.com/organvm-v-logos) |
| VI | Community (salons, reading groups) | [organvm-vi-koinonia](https://github.com/organvm-vi-koinonia) |
| VII | Marketing (POSSE distribution, announcements) | [organvm-vii-kerygma](https://github.com/organvm-vii-kerygma) |
| VIII | Meta (umbrella org) | [meta-organvm](https://github.com/meta-organvm) |

### How Petasum Routes Between Organs

The ORGAN system enforces a no-back-edges dependency constraint: information flows I to II to III only; ORGAN-III cannot depend on ORGAN-II. Petasum operates at the orchestration layer (ORGAN-IV), which sits outside this linear dependency chain. It provides:

- **Cross-organ issue tracking**: When a governance decision affects multiple organs (for example, a new licensing policy for ORGAN-III commercial repos that also applies to ORGAN-II creative repos), Petasum is where the issue lives.
- **Conflict resolution across organ boundaries**: When ORGAN-I's theoretical principles collide with ORGAN-III's commercial constraints, the logic-first hierarchy provides a resolution framework that does not privilege either organ.
- **Coordination without coupling**: Petasum enables organs to coordinate on shared concerns (security policies, naming conventions, CI/CD standards) without creating runtime dependencies between them.

### Issue Flow Across Organs

```
ORGAN-I discovers a dependency conflict
        |
        v
Files issue in petasum-super-petasum (org-wide template)
        |
        v
Workflow adds to ORGAN-IV project board
        |
        v
Cross-repo notification identifies affected ORGAN-II and ORGAN-III repos
        |
        v
Maintainers in each organ create linked issues in their repos
        |
        v
Resolution coordinated via central Petasum issue
        |
        v
Decision documented with logical reasoning chain
```

---

## Governance Model

### Decision Authority

Petasum defines explicit decision authorities for each lifecycle phase:

- **Phase 0 (Foundation)**: Executive Leadership Team or designated Project Sponsor
- **Phase 1 (Awareness)**: Program Manager + Steering Committee
- **Phase 2 (Adoption)**: Program Manager + Pilot Team Leads
- **Phase 3 (Integration)**: Steering Committee + Organization Leadership
- **Phase 4 (Maturation)**: Governance Council + Executive Sponsor

Each gate review requires a written rationale for the go/no-go decision. This prevents governance by inertia.

### Escalation Protocols

**Standard Resolution** (90% of conflicts): Apply the principle hierarchy. If the conflict is between different levels, the higher level prevails. If same level, analyze which position better serves the higher-level principle. Document reasoning.

**Complex Escalation** (10% of conflicts): Convene a logic review with affected stakeholders. Each position must present a formal logical case. Collaboratively identify fallacies, contradictions, and gaps. Seek a synthesized solution that transcends the initial positions. If synthesis fails, return to Level 0 (Logic prevails). Update the framework if new insights emerge.

### Discourse Standards

All organizational discussions under the Petasum framework require:

- Clear logical reasoning, not assertion
- Explicit identification of assumptions
- Welcoming logical critique as a feature, not a threat
- Updating views when logic demands it
- Acknowledging "I don't know" when appropriate

Prohibited: arguments from authority without reasoning, emotional manipulation, personal attacks, intentional ambiguity, refusal to engage with logical criticism.

---

## Relationship to Agentic Titan

[Agentic Titan](https://github.com/organvm-iv-taxis/agentic-titan) is the flagship repository of ORGAN-IV. Where Agentic Titan provides the runtime orchestration layer --- AI agent coordination, task routing, and execution management --- Petasum Super Petasum provides the governance substrate on which that orchestration operates.

The relationship is complementary:

| Dimension | Agentic Titan | Petasum Super Petasum |
|-----------|--------------|----------------------|
| **Scope** | Runtime agent orchestration | Governance and decision frameworks |
| **Artifacts** | Code, APIs, agent configurations | Templates, workflows, policy documents |
| **Decisions** | Which agent handles which task | Which principle prevails in a conflict |
| **Time horizon** | Milliseconds to minutes | Weeks to years |
| **Users** | AI agents and their operators | Humans making organizational decisions |

Petasum defines the principles; Agentic Titan operationalizes them. If Agentic Titan is the nervous system, Petasum is the constitution.

---

## Repository Structure

```
petasum-super-petasum/
├── .github/
│   ├── CODEOWNERS                           # Repository ownership
│   ├── CONTRIBUTING.md                      # Contribution guidelines
│   ├── DISCUSSIONS.md                       # Discussion setup guide
│   ├── DISCUSSION_TEMPLATE/
│   │   └── org-proposal.yml                 # Proposal discussion template
│   ├── ISSUE_TEMPLATE/
│   │   ├── annual-principles-audit.yml      # Annual governance review
│   │   ├── config.yml                       # Template chooser config
│   │   ├── org-incident.yml                 # Multi-service incident
│   │   ├── org-rfc.yml                      # Cross-repo RFC
│   │   ├── org-wide-initiative.yml          # Cross-repo initiative
│   │   ├── organization-wide-issue.yml      # General org-wide issue
│   │   ├── process-improvement.yml          # Process improvement
│   │   ├── redirect-to-org-repo.yml         # Redirect for other repos
│   │   └── security-concern.yml             # Security issues
│   ├── PROJECTS.md                          # Project configuration guide
│   ├── QUICK_START.md                       # Quick start guide
│   ├── REDIRECT_TEMPLATE_USAGE.md           # Redirect template docs
│   ├── labels.yml                           # Label definitions
│   └── workflows/
│       ├── add-to-org-project.yml           # Auto-add to project board
│       ├── cross-repo-notifications.yml     # Cross-repo coordination
│       └── org-issue-notifications.yml      # Org-wide notifications
├── docs/
│   ├── QUICK_REFERENCE.md                   # Daily reference guide
│   ├── STRUCTURE.md                         # Repo structure docs
│   └── examples/
│       └── README.md                        # Usage examples
├── CHANGELOG.md                             # Version history
├── COMMANDMENTS.md                          # 16 principles + derivations
├── COMPREHENSIVE_CRITIQUE.md                # Self-assessment and audit
├── CONTRIBUTING.md                          # How to contribute
├── IMPLEMENTATION_CHECKLIST.md              # Lifecycle tracking
├── LICENSE                                  # MIT License
├── LIFECYCLE_ROADMAP.md                     # Six-phase implementation plan
├── LOGIC_FRAMEWORK.md                       # Philosophical foundation
├── PRINCIPLE_CONFLICTS.md                   # Conflict resolution matrix
├── README.md                                # This document
├── SECURITY.md                              # Security policies
└── SETUP.md                                 # Technical setup guide
```

---

## Lifecycle and Roadmap

### Current Status

Petasum is at **v1.0.0** with all core documentation complete. The logic-first framework documents (LOGIC_FRAMEWORK, COMMANDMENTS, PRINCIPLE_CONFLICTS, LIFECYCLE_ROADMAP) are stable and ready for organizational adoption. Several governance documents identified in the implementation checklist (GOVERNANCE.md, ESCALATION_GUIDE.md, METRICS.md) remain to be created.

### Implementation Phases

| Phase | Timeline | Focus | Gate Criteria |
|-------|----------|-------|--------------|
| **0: Foundation** | Weeks 1--2 | Core docs, leadership alignment, champion training | All docs complete, leadership go-ahead |
| **1: Awareness** | Weeks 3--4 | Organization-wide introduction, learning resources | 90% awareness, 50% understanding |
| **2: Adoption** | Weeks 5--8 | Pilot teams, process integration, tooling | Pilots effective, challenges solvable |
| **3: Integration** | Weeks 9--16 | Org-wide rollout, workflow embedding, culture | 50%+ unprompted framework use |
| **4: Maturation** | Months 5--12 | Optimization, edge case mastery, institutionalization | Self-sustaining, governance board |
| **5: Evolution** | Year 2+ | Center of excellence, research, ecosystem | External recognition, AI integration |

### Measurement Framework

**Adoption metrics**: Weekly active users (target >80%), decisions documented with reasoning (target >70%), meetings using logical structure (target >60%).

**Quality metrics**: Decision reversal rate (target <10% from baseline), conflicts resolved via framework (target >80%), logical fallacies in documentation (target <5%).

**Impact metrics**: Employee satisfaction (+15% from baseline), time-to-decision for complex decisions (-25%), customer satisfaction (+10%).

---

## Related Work

Petasum's governance model draws from and extends several established frameworks:

- **[Semgrep Philosophy](https://semgrep.dev/docs/contributing/semgrep-philosophy)** --- Source of principles around open source, privacy-first, determinism, safe execution, and performance. Restructured through the logic-first hierarchy.
- **[TensorFlow Contributing Guidelines](https://github.com/tensorflow/tensorflow/blob/master/CONTRIBUTING.md)** --- Source of quality-over-quantity, community collaboration, transparency, and backward compatibility principles.
- **[Schema.org Community Guidelines](https://github.com/schemaorg/schemaorg)** --- Source of interoperability, clarity, inclusivity, and stability principles.

The logic-first meta-principle itself is informed by classical logic (Aristotle's three laws), modal and temporal logic traditions, and Godel's incompleteness theorems as a check on framework hubris.

---

## Contributing

Contributions are welcome, but all proposed changes must pass logical scrutiny.

### How to Contribute

1. **Read the framework**: Understand [LOGIC_FRAMEWORK.md](./docs/LOGIC_FRAMEWORK.md) and [COMMANDMENTS.md](./docs/COMMANDMENTS.md) before proposing changes.
2. **Open a discussion or RFC**: For significant changes, use the RFC issue template or start a Discussion.
3. **Include logical reasoning**: Every proposal must include its logical derivation and demonstrate consistency with the Level 0 meta-principle.
4. **Challenge inconsistencies**: If you find a logical error in any document, you are obligated to point it out. We are obligated to correct it.

### What You Can Improve

- **Templates**: Suggest improvements to issue templates (field clarity, validation rules, new template types).
- **Workflows**: Propose automation improvements or new workflow patterns.
- **Documentation**: Keep documentation current, fix errors, improve clarity.
- **Framework**: Propose new principles (with logical derivation), refine conflict resolution protocols, or challenge existing principles.
- **Tooling**: Build or improve logic-supporting tools (fallacy detection, decision tree generators, conflict resolution wizards).

See [CONTRIBUTING.md](CONTRIBUTING.md) for full contribution guidelines.

---

## License

This project is licensed under the [MIT License](LICENSE).

The MIT License was chosen because open source enables verification (Level 3 Community Principle: Free and Open Source), and verification is a logical necessity for validating correctness. Closed systems cannot be independently verified; verification is required for logical confidence.

---

## Author

**[@4444j99](https://github.com/4444j99)**

Part of the [ORGAN-IV: Taxis](https://github.com/organvm-iv-taxis) orchestration organ within the [ORGAN system](https://github.com/meta-organvm) --- an eight-organ creative-institutional architecture coordinating theory, art, commerce, orchestration, public process, community, marketing, and meta-governance across distributed GitHub organizations.

<!-- SYSTEM-NAV-START -->

---

<sub>[Portfolio](https://4444j99.github.io/portfolio/) · [System Directory](https://4444j99.github.io/portfolio/directory/) · [ORGAN IV · Taxis](https://organvm-iv-taxis.github.io/) · Part of the <a href="https://4444j99.github.io/portfolio/directory/">ORGANVM eight-organ system</a></sub>

<!-- SYSTEM-NAV-END -->
