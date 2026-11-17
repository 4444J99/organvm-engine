# Quick Start Guide - Organization-Wide Issue Tracking

Get started with the organization-wide issue tracking system in 5 minutes.

## For Issue Reporters

### 1. Determine if Your Issue is Organization-Wide

**File here if:**
- Affects 2+ repositories
- Organization-wide security concern  
- Process/workflow improvement needed
- Requires cross-team coordination

**File in specific repo if:**
- Only affects one repository
- Repository-specific bug or feature

### 2. Create an Issue

1. Go to [Issues](../../issues)
2. Click **New Issue**
3. Select a template:
   - **Organization-Wide Issue** - General multi-repo issues
   - **Security Concern** - Security issues
   - **Process Improvement** - Workflow suggestions

### 3. Fill Out the Template

- Provide clear description
- List affected repositories
- Set severity level
- Identify affected teams
- Describe expected vs current behavior

### 4. Submit and Monitor

- Your issue will be automatically labeled
- Workflows will add helpful comments
- Teams will be notified
- You'll get updates as it progresses

## For Repository Maintainers

### 1. Watch This Repository

1. Click **Watch** at the top of this page
2. Select **All Activity** or **Custom**
3. Enable notifications for issues

### 2. Add Redirect Template to Your Repo

```bash
cd /path/to/your/repo
mkdir -p .github/ISSUE_TEMPLATE
curl -o .github/ISSUE_TEMPLATE/redirect-to-org-repo.yml \
  https://raw.githubusercontent.com/ivi374forivi/petasum-super-petasum/main/.github/ISSUE_TEMPLATE/redirect-to-org-repo.yml
git add .github/ISSUE_TEMPLATE/redirect-to-org-repo.yml
git commit -m "Add org-wide issue redirect template"
git push
```

### 3. Link Issues to Your Repo

When an org-wide issue affects your repo:

1. Create an issue in your repository
2. Reference the org-wide issue:
   ```
   Related to ivi374forivi/petasum-super-petasum#123
   ```
3. Comment on the org-wide issue with your repo's issue link

### 4. Keep Status Updated

Update the org-wide issue as you make progress:
- Comment with status updates
- Close when resolved in your repo
- Mention blockers or dependencies

## For Organization Administrators

### 1. Configure Team Notifications

Edit `.github/CODEOWNERS`:
```
# Add your teams
* @ivi374forivi/your-team
/.github/workflows/ @ivi374forivi/devops-team
```

### 2. Set Up GitHub Projects

1. Create organization-level project
2. Add automation to include org-wide issues
3. Configure views for different teams
4. See [PROJECTS.md](PROJECTS.md) for details

### 3. Enable Discussions (Optional)

1. Go to repository Settings
2. Enable Discussions
3. Set up categories
4. See [DISCUSSIONS.md](DISCUSSIONS.md) for details

### 4. Configure Labels

Apply labels to this repository:

```bash
# Using github-label-sync (if installed)
github-label-sync --labels .github/labels.yml ivi374forivi/petasum-super-petasum
```

Or apply manually through GitHub UI using [labels.yml](labels.yml) as reference.

## Common Workflows

### Workflow 1: Reporting a Cross-Repository Bug

1. Create issue using "Organization-Wide Issue" template
2. List all affected repositories
3. Set severity to "High" 
4. Add `cross-repo` label
5. Workflow automatically notifies teams
6. Repository maintainers create linked issues
7. Track progress in all repos

### Workflow 2: Proposing a Process Change

1. Start discussion to gather feedback (optional)
2. Create issue using "Process Improvement" template
3. Describe current process and proposed changes
4. List affected teams
5. Teams discuss and refine
6. Reach consensus
7. Implement across repositories
8. Close issue when complete

### Workflow 3: Security Concern

1. Create issue using "Security Concern" template
2. Set severity appropriately
3. Add `security` and `urgent` labels if critical
4. Workflow prioritizes notification
5. Security team triages
6. Create private issues if needed
7. Coordinate fixes across repos
8. Verify and close

## Tips and Tricks

### For Everyone

- **Search first**: Check if issue already exists
- **Use labels**: They help categorize and find issues
- **Be specific**: Clear details help faster resolution
- **Follow up**: Respond to questions and comments
- **Link issues**: Cross-reference related issues

### For Maintainers

- **React quickly**: Acknowledge org-wide issues promptly
- **Provide estimates**: Let others know your timeline
- **Share learnings**: Document solutions for others
- **Update regularly**: Keep stakeholders informed

### For Admins

- **Triage regularly**: Review new issues within 24-48 hours
- **Assign ownership**: Ensure someone owns each issue
- **Track metrics**: Monitor resolution time and patterns
- **Iterate process**: Improve templates and workflows based on feedback

## Getting Help

- **Documentation**: Check the [README](../README.md)
- **Discussions**: Ask in [Organization Discussions](https://github.com/orgs/ivi374forivi/discussions)
- **Issues**: File an issue in this repository
- **Direct Contact**: Reach out to organization admins

## Next Steps

### New Users
1. Read the [README](../README.md) for complete documentation
2. Browse existing issues to see examples
3. File your first issue

### Maintainers
1. Install redirect template in your repos
2. Set up project tracking
3. Configure team notifications

### Administrators
1. Review [PROJECTS.md](PROJECTS.md) for project setup
2. Review [DISCUSSIONS.md](DISCUSSIONS.md) for discussion setup
3. Customize templates for your organization's needs
4. Train teams on the process

## Resources

- [Complete Documentation](../README.md)
- [Issue Templates](./ISSUE_TEMPLATE/)
- [GitHub Projects Guide](PROJECTS.md)
- [Discussions Guide](DISCUSSIONS.md)
- [Contributing Guide](CONTRIBUTING.md)
- [Redirect Template Usage](REDIRECT_TEMPLATE_USAGE.md)

---

**Questions?** Open a [discussion](https://github.com/orgs/ivi374forivi/discussions) or file an [issue](../../issues).
