# Setup Guide

This guide will help you set up organization-wide issue tracking using the templates in this repository.

## Prerequisites

- A GitHub organization account
- Admin access to create repositories and organization Projects
- Ability to create Personal Access Tokens

## Setup Steps

### 1. Create Your org-issues Repository

```bash
# Option A: Use this repository as a template
# Click "Use this template" on GitHub

# Option B: Fork this repository
# Click "Fork" on GitHub

# Option C: Copy files manually
git clone https://github.com/ivi374forivi/petasum-super-petasum.git
cd petasum-super-petasum
cp -r .github your-org-issues-repo/
```

### 2. Create Organization Project (Projects v2)

1. Go to your organization page on GitHub
2. Click on "Projects" tab
3. Click "New project"
4. Choose "Board" or "Table" view
5. Add custom fields:
   - **Status**: Select field (Backlog, Ready, In Progress, Done)
   - **Priority**: Select field (High, Medium, Low)
   - **Owner**: Text field
   - **Target date**: Date field
6. Copy the Project URL (e.g., `https://github.com/orgs/your-org/projects/1`)

### 3. Create Personal Access Token (PAT)

1. Go to GitHub Settings → Developer settings → Personal access tokens → Fine-grained tokens
2. Click "Generate new token"
3. Name: `Org Project Automation`
4. Expiration: Choose appropriate duration
5. Resource owner: Select your organization
6. Repository access: "All repositories" or specific repos
7. Permissions:
   - Repository permissions → Issues: Read and write
   - Organization permissions → Projects: Read and write
8. Generate and copy the token

### 4. Add Token as Organization Secret

1. Go to your organization Settings → Secrets and variables → Actions
2. Click "New organization secret"
3. Name: `ORG_PROJECT_TOKEN`
4. Value: Paste your PAT
5. Repository access: Choose which repos can use this secret

### 5. Update Configuration Files

#### Update workflow file (`.github/workflows/add-to-org-project.yml`):

```yaml
# Replace this line:
project-url: https://github.com/orgs/your-org/projects/1

# With your actual project URL:
project-url: https://github.com/orgs/acme-corp/projects/1
```

#### Update issue template config (`.github/ISSUE_TEMPLATE/config.yml`):

```yaml
# Replace all instances of 'your-org' with your organization name:
contact_links:
  - name: Propose an idea (Discussions)
    url: https://github.com/acme-corp/org-issues/discussions/new?category=ideas
    about: Start with a discussion for early proposals.
  - name: Security vulnerability
    url: https://github.com/acme-corp/.github/blob/main/SECURITY.md
    about: Please follow our security policy.
  - name: Support/help
    url: https://github.com/acme-corp/org-issues/discussions/new?category=support
    about: Use Discussions for Q&A and help.
```

### 6. Create Labels

Create these labels in your repository (Settings → Labels):

| Label | Color | Description |
|-------|-------|-------------|
| `org-wide` | `#0E8A16` | Issues affecting multiple repos |
| `initiative` | `#1D76DB` | Cross-team initiatives |
| `epic` | `#5319E7` | Large multi-phase work |
| `rfc` | `#FBCA04` | Request for comments |
| `incident` | `#D93F0B` | Production incidents |
| `sev-1` | `#B60205` | Critical severity |
| `sev-2` | `#D93F0B` | High severity |
| `sev-3` | `#FBCA04` | Medium severity |
| `dependency` | `#0366D6` | Blocked by external dependency |
| `blocked` | `#D93F0B` | Cannot proceed |
| `needs-triage` | `#D876E3` | Needs initial review |
| `ready` | `#0E8A16` | Ready to work on |
| `in-progress` | `#1D76DB` | Currently being worked on |
| `done` | `#5319E7` | Completed |
| `wontfix` | `#FFFFFF` | Will not be addressed |

### 7. Enable GitHub Discussions (Optional)

1. Go to repository Settings
2. Scroll to "Features" section
3. Check "Discussions"
4. Configure discussion categories:
   - Ideas
   - Support
   - Q&A

### 8. Test the Setup

1. Create a test issue using one of the templates
2. Verify it appears in your organization Project
3. Test cross-linking between issues
4. Verify labels are applied correctly

## Advanced Configuration

### Customizing Templates

Edit template files in `.github/ISSUE_TEMPLATE/` to:
- Add or remove fields
- Change required validations
- Modify placeholder text
- Adjust labels

### Additional Workflows

Consider adding workflows for:
- Auto-assigning team members based on labels
- Sending notifications to Slack/Teams
- Creating follow-up tasks automatically
- Generating weekly status reports

### Multiple Organizations

If managing multiple organizations:
1. Use separate Projects for each organization
2. Adjust PAT permissions accordingly
3. Consider using separate org-issues repositories

## Troubleshooting

### Issues Not Auto-Adding to Project

- Verify `ORG_PROJECT_TOKEN` secret exists and has correct permissions
- Check workflow logs in Actions tab
- Ensure Project URL is correct
- Verify the PAT hasn't expired

### Templates Not Appearing

- Wait a few minutes after pushing changes
- Check YAML syntax is valid
- Ensure files are in `.github/ISSUE_TEMPLATE/` directory
- Verify repository has Issues enabled

### Workflow Permissions Error

- Check PAT has both Issues and Projects permissions
- Verify secret is accessible to the repository
- Ensure PAT is for the correct organization

## Maintenance

- Review and update templates quarterly
- Rotate PATs annually or as needed
- Audit label usage and consolidate if needed
- Update documentation as processes evolve
- Archive or close stale org-wide issues

## Organizational Principles

This repository operates under a **logic-first framework**:

- **[LOGIC_FRAMEWORK.md](LOGIC_FRAMEWORK.md)**: Philosophical and practical foundations
- **[PRINCIPLE_CONFLICTS.md](PRINCIPLE_CONFLICTS.md)**: Conflict resolution matrix and hierarchy
- **[COMMANDMENTS.md](COMMANDMENTS.md)**: Core principles with logical derivations

**Why this matters for setup**: When making configuration decisions, use logical analysis:
1. What is the goal? (Clear question)
2. What are the constraints? (Premises)
3. What options exist? (Possibilities)
4. Which option logically best achieves the goal given constraints? (Reasoning)
5. What are the potential contradictions or issues? (Verification)

Example:
```
Question: How many severity levels should incidents have?

Logical Analysis:
- Too few: Cannot distinguish critical from minor (communication loss)
- Too many: Confusion about which to use (decision paralysis)
- Industry standard: 3-4 levels (empirical data)
- Team size: Small teams need simpler systems (constraint)

Conclusion: 3 levels (Critical, High, Medium) balances clarity and simplicity
Logic: Optimizes communication (Level 3) within operational constraints (Level 2)
```

## Support

For questions or issues with this setup:
- Open a discussion in this repository
- Check the README for additional context
- Review GitHub's documentation on issue templates and Projects
- See [COMMANDMENTS.md](COMMANDMENTS.md) for guiding principles
- **When asking questions, frame them with logical reasoning for better answers**

## Next Steps

After completing setup:
1. Communicate the new process to your organization
2. Document triage SLAs and ownership
3. Train team leads on using the templates
4. Establish regular review cadences
5. Create a rollout plan for adoption across teams
