# Repository Structure

```
petasum-super-petasum/
├── .github/
│   ├── DISCUSSION_TEMPLATE/
│   │   └── org-proposal.yml          # Discussion template for proposals
│   ├── ISSUE_TEMPLATE/
│   │   ├── config.yml                # Issue template chooser configuration
│   │   ├── org-incident.yml          # Template for org-wide incidents
│   │   ├── org-rfc.yml               # Template for RFCs
│   │   └── org-wide-initiative.yml   # Template for org-wide initiatives
│   └── workflows/
│       └── add-to-org-project.yml    # Auto-add issues to org Project
├── docs/
│   ├── QUICK_REFERENCE.md            # Quick reference guide
│   ├── STRUCTURE.md                  # This file - repository structure documentation
│   └── examples/
│       └── README.md                 # Usage examples
├── COMMANDMENTS.md                   # Organization principles and commandments
├── CONTRIBUTING.md                   # Contribution guidelines
├── README.md                         # Main documentation
├── SECURITY.md                       # Security policies
├── SETUP.md                          # Detailed setup guide
└── copilot-chat-response-transcript  # Original context document
```

## File Descriptions

### Templates

#### `.github/ISSUE_TEMPLATE/org-wide-initiative.yml`
Form template for creating organization-wide initiatives. Includes fields for:
- Summary and problem statement
- Scope definition
- Impacted repositories
- Owners and success criteria
- Timeline, risks, and communication plan

#### `.github/ISSUE_TEMPLATE/org-incident.yml`
Form template for tracking multi-repo incidents. Includes fields for:
- Severity level (SEV-1/2/3)
- Start time and detection method
- Impact assessment
- Mitigation status and timeline
- Follow-up action items

#### `.github/ISSUE_TEMPLATE/org-rfc.yml`
Form template for proposing cross-repo changes. Includes fields for:
- Summary and motivation
- Design approach and alternatives
- Affected repositories and teams
- Risk assessment and success metrics

#### `.github/ISSUE_TEMPLATE/config.yml`
Configures the issue template chooser with:
- Disabled blank issues
- Contact links for discussions, security, and support

#### `.github/DISCUSSION_TEMPLATE/org-proposal.yml`
Form template for early-stage proposals in GitHub Discussions

### Workflows

#### `.github/workflows/add-to-org-project.yml`
GitHub Actions workflow that:
- Triggers on issue open/label events
- Detects issues with `org-wide` label
- Automatically adds them to organization Project
- Requires `ORG_PROJECT_TOKEN` secret

### Documentation

#### `README.md`
Main documentation covering:
- Repository overview and purpose
- What's included
- Usage instructions for organizations
- Best practices and architecture recommendations

#### `SETUP.md`
Step-by-step setup guide including:
- Prerequisites
- Creating org Project
- Configuring PAT and secrets
- Updating configuration files
- Creating labels
- Testing and troubleshooting

#### `CONTRIBUTING.md`
Guidelines for:
- Using the repository as a template
- Contributing improvements
- Customization guidelines
- Code quality standards

#### `COMMANDMENTS.md`
Organization principles and commandments inspired by:
- Semgrep philosophy (privacy, open source, performance)
- TensorFlow principles (quality, collaboration, transparency)
- Schema.org standards (interoperability, clarity, inclusivity)
- Application to organization-wide issue tracking
- Living guidelines for continuous improvement

#### `SECURITY.md`
Security information including:
- How to report vulnerabilities
- Secure usage guidelines
- Secrets management
- Access control recommendations

#### `docs/QUICK_REFERENCE.md`
Quick reference covering:
- Template selection guide
- Label definitions
- Common commands
- Severity guidelines
- Triage processes

#### `docs/examples/README.md`
Practical examples including:
- Real-world scenarios
- Template usage examples
- Cross-linking patterns
- Workflow lifecycles
- Communication templates

## Data Flow

```
┌─────────────────────────────────────────────────────────┐
│ User Creates Issue                                       │
│ (Selects template: Initiative/Incident/RFC)             │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│ GitHub Applies Template                                  │
│ - Pre-fills fields                                       │
│ - Adds default labels (org-wide, initiative/incident...)│
│ - Sets title format                                      │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│ Workflow Triggered                                       │
│ on: issues (opened, labeled)                            │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│ Workflow Checks Labels                                   │
│ if: contains(labels, 'org-wide')                        │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│ Add to Organization Project                              │
│ - Uses ORG_PROJECT_TOKEN                                │
│ - Adds issue to specified project                       │
│ - Issue appears in project board                        │
└─────────────────────────────────────────────────────────┘
```

## Integration Points

### GitHub Features Used
- **Issues**: Primary tracking mechanism
- **Issue Templates (Forms)**: Structured issue creation
- **Labels**: Categorization and automation triggers
- **Projects (v2)**: Cross-repo tracking and visualization
- **Discussions**: Early-stage proposals and Q&A
- **GitHub Actions**: Automation workflows
- **Secrets**: Secure token storage

### External Integration Possibilities
- Slack/Teams notifications (add workflow)
- Status page updates (add workflow)
- Metrics dashboards (query via API)
- PagerDuty/Opsgenie (add workflow)
- Email notifications (built-in GitHub)

## Customization Points

Users should customize:
1. **Workflow file**: Update project URL and token name
2. **Config file**: Update organization name and URLs
3. **Templates**: Adjust fields to match processes
4. **Labels**: Align with existing label schema
5. **Documentation**: Add org-specific guidelines

## Labels Used

| Label | Auto-Applied | Trigger | Purpose |
|-------|--------------|---------|---------|
| `org-wide` | ✅ (by templates) | Workflow trigger | Marks cross-repo issues |
| `initiative` | ✅ (by template) | - | Long-term projects |
| `incident` | ✅ (by template) | - | Production issues |
| `rfc` | ✅ (by template) | - | Proposals |
| `epic` | ❌ (manual) | - | Large multi-phase work |
| `needs-triage` | ✅ (by templates) | - | Requires review |
| `sev-1/2/3` | ❌ (manual/dropdown) | - | Severity indicator |

## Required Secrets

| Secret | Scope | Permissions | Usage |
|--------|-------|-------------|-------|
| `ORG_PROJECT_TOKEN` | Organization | Projects: R/W, Issues: R/W | Add issues to org Project |

## Supported GitHub Plans

- ✅ GitHub Enterprise Cloud (full support)
- ✅ GitHub Enterprise Server (full support, version 3.0+)
- ✅ GitHub Team (Projects v2 available)
- ⚠️ GitHub Free (Projects available, but limited features)
