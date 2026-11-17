# GitHub Projects Integration Guide

This guide explains how to use GitHub Projects to track organization-wide issues across multiple repositories.

## Overview

GitHub Projects provides powerful project management capabilities:

- **Track issues across repositories**: See all related work in one place
- **Multiple views**: Table, board, roadmap, and custom views
- **Automation**: Auto-add issues, update status, and more
- **Custom fields**: Add metadata specific to your organization
- **Insights**: Visualize progress and burndown

## Creating an Organization-Wide Project

### Step 1: Create a New Project

1. Go to your organization: `https://github.com/orgs/ivi374forivi`
2. Click **Projects** tab
3. Click **New project**
4. Choose a template or start from scratch:
   - **Team backlog**: For tracking work items
   - **Feature release**: For coordinating releases
   - **Bug triage**: For managing bugs
   - **Blank**: Start from scratch

### Step 2: Configure Project Settings

1. **Name**: "Organization-Wide Issues Tracking"
2. **Description**: "Central tracking for issues affecting multiple repositories"
3. **Visibility**: 
   - **Public**: Visible to everyone
   - **Private**: Visible to organization members only
4. **README**: Add context about the project's purpose

### Step 3: Set Up Views

#### View 1: By Priority (Board)

**Purpose**: Visualize issues by priority

**Configuration:**
- **Layout**: Board
- **Group by**: Priority (custom field)
- **Columns**: Urgent, High, Medium, Low
- **Filter**: `is:open label:org-wide`

#### View 2: By Repository (Table)

**Purpose**: See which repositories are affected

**Configuration:**
- **Layout**: Table
- **Group by**: Repository
- **Columns**: Title, Status, Priority, Assignees, Labels
- **Sort by**: Priority (descending), then Created date

#### View 3: By Status (Board)

**Purpose**: Track progress through workflow stages

**Configuration:**
- **Layout**: Board
- **Group by**: Status
- **Columns**: Triage, Backlog, In Progress, Blocked, Done
- **Filter**: `is:open`

#### View 4: Roadmap (Timeline)

**Purpose**: Visualize work over time

**Configuration:**
- **Layout**: Roadmap
- **Date field**: Target date (custom field)
- **Zoom level**: Quarter
- **Show**: Milestones and issues

## Custom Fields

Add custom fields to track organization-specific metadata:

### Recommended Custom Fields

1. **Priority** (Single select)
   - Options: Urgent, High, Medium, Low
   - Use for sorting and filtering

2. **Status** (Single select)
   - Options: Triage, Backlog, In Progress, Blocked, Done
   - Drives the status board view

3. **Affected Repositories** (Text)
   - List of repositories affected
   - Helps with filtering and grouping

4. **Impact Score** (Number)
   - Rate impact from 1-10
   - Helps prioritize work

5. **Target Resolution Date** (Date)
   - When the issue should be resolved
   - Used in roadmap view

6. **Team Owner** (Single select)
   - Options: DevOps, Frontend, Backend, Security, Platform
   - Assign ownership

7. **Cross-Repo Tracking** (URL)
   - Links to related issues in other repos
   - Maintains traceability

## Automation

### Built-in Automations

#### Auto-add Items

Automatically add issues to the project:

```yaml
When: Issue is opened or labeled
Filter: label:org-wide repo:ivi374forivi/petasum-super-petasum
Action: Add to project
Set fields:
  - Status: Triage
  - Priority: Based on labels
```

#### Auto-archive

Archive completed items:

```yaml
When: Issue is closed
Action: Archive item
```

#### Status Sync

Keep status in sync with issue state:

```yaml
When: Issue is closed
Action: Set Status to "Done"

When: Issue is reopened
Action: Set Status to "Backlog"
```

### Custom Automations with GitHub Actions

#### Sync Labels to Project Fields

```yaml
# .github/workflows/sync-project-fields.yml
name: Sync Project Fields

on:
  issues:
    types: [opened, labeled, unlabeled]

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - name: Update project priority
        uses: actions/github-script@v7
        with:
          script: |
            const labels = context.payload.issue.labels.map(l => l.name);
            
            let priority = 'Medium';
            if (labels.includes('urgent')) priority = 'Urgent';
            else if (labels.includes('high-priority')) priority = 'High';
            else if (labels.includes('low-priority')) priority = 'Low';
            
            // Update project field via GraphQL API
            console.log(`Setting priority to: ${priority}`);
```

## Linking Issues to Projects

### Automatic Linking

Configure automation to automatically add issues:

1. Go to project settings
2. Click **Workflows**
3. Enable **Auto-add**
4. Set filters (e.g., `label:org-wide`)

### Manual Linking

Add an issue to a project:

1. Open the issue
2. Click **Projects** in the sidebar
3. Select the project
4. The issue appears in the project

### From Project View

1. Open the project
2. Click **Add item**
3. Search for issues
4. Select issues to add

## Best Practices

### Naming Conventions

- **Projects**: Use clear, descriptive names
  - Good: "Q4 2025 Organization-Wide Initiatives"
  - Bad: "Project 1"

### View Organization

- **Limit views**: 4-6 views maximum
- **Purpose-driven**: Each view should serve a specific need
- **Consistent naming**: Use clear prefixes (e.g., "View: By Priority")

### Regular Maintenance

1. **Weekly triage**: Review new issues
2. **Update status**: Keep project fields current
3. **Archive completed**: Remove clutter
4. **Adjust priorities**: Re-prioritize as needed

### Team Collaboration

1. **Share views**: Create views for different teams
2. **Assign owners**: Every item should have an owner
3. **Comment on items**: Use comments for coordination
4. **Link related items**: Connect related issues and PRs

## Multi-Repository Tracking

### Strategy 1: Central Project

Create one project in the central repository:

**Pros:**
- Single source of truth
- Easy to see all work
- Consistent process

**Cons:**
- Can become large
- May need careful filtering

### Strategy 2: Federated Projects

Create projects in each repository, with a central overview:

**Pros:**
- Team autonomy
- Focused views
- Clear ownership

**Cons:**
- Harder to see big picture
- More setup required

### Recommended Approach

Use a **hybrid approach**:

1. **Central project**: Track organization-wide issues
2. **Repository projects**: Track repository-specific work
3. **Link items**: Connect related issues across projects

## Reporting and Insights

### Built-in Insights

Projects provide several insight charts:

1. **Burn up**: Track cumulative completion
2. **Burn down**: Track remaining work
3. **Velocity**: Track completion rate
4. **Cycle time**: Measure time to complete

### Custom Reports

Export project data for custom reporting:

1. Use GitHub API to fetch project data
2. Export to CSV for analysis
3. Create dashboards in BI tools

### Metrics to Track

- **Issues created per week**: Trend of new issues
- **Issues resolved per week**: Completion rate
- **Average time to resolution**: Efficiency metric
- **Issues by repository**: Distribution of work
- **Issues by priority**: Workload assessment

## Project Templates

Save project configurations as templates:

1. Create a well-configured project
2. Click **...** menu
3. Select **Save as template**
4. Share with the organization

### Example: Organization-Wide Issue Tracker Template

**Views:**
- Priority board
- Status board
- Repository table
- Quarterly roadmap

**Custom fields:**
- Priority
- Status
- Affected repos
- Team owner
- Target date

**Automations:**
- Auto-add org-wide issues
- Sync status with issue state
- Archive when closed

## Integration with Existing Workflows

### Issue Templates

Include project instructions in issue templates:

```yaml
body:
  - type: markdown
    attributes:
      value: |
        This issue will be automatically added to the 
        [Organization-Wide Issues project](link-to-project).
```

### README Links

Add project links to README:

```markdown
## 📊 Project Tracking

View organization-wide issues in our [GitHub Project](link-to-project).
```

### Workflow Comments

GitHub Actions can comment with project links:

```javascript
const projectUrl = 'https://github.com/orgs/ivi374forivi/projects/1';
const comment = `Added to [organization project](${projectUrl})`;
await github.rest.issues.createComment({...});
```

## Troubleshooting

### Issue Not Appearing in Project

**Check:**
1. Issue matches the filter criteria
2. Automation is enabled
3. Issue is in a repository the project can access
4. Project has correct permissions

### Status Not Syncing

**Check:**
1. Automation rules are enabled
2. Field mappings are correct
3. GitHub Actions have correct permissions

### Performance Issues

**Solutions:**
1. Archive old items regularly
2. Split into multiple projects
3. Use filters to reduce visible items
4. Limit number of views

## Additional Resources

- [GitHub Projects Documentation](https://docs.github.com/en/issues/planning-and-tracking-with-projects)
- [Project Automation Documentation](https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project)
- [GraphQL API for Projects](https://docs.github.com/en/graphql/reference/objects#projectv2)

---

**Next Steps:**

1. Create your first organization project
2. Configure automations to add org-wide issues
3. Set up views for your teams
4. Train team members on using the project
5. Establish a regular maintenance schedule
