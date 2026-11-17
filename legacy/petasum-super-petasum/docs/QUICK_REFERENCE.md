# Quick Reference Guide

## Issue Templates

| Template | When to Use | Key Fields |
|----------|------------|------------|
| **Org-wide Initiative** | Cross-repo projects, migrations, policy rollouts | Summary, Problem, Scope, Repos, Owners, Success Criteria |
| **Org-wide Incident** | Multi-service outages, security incidents, critical bugs | Severity, Impact, Detection, Mitigation, Timeline |
| **RFC (org-wide)** | Architecture decisions, new patterns, process changes | Summary, Motivation, Design, Impact, Risks |

## Labels

| Label | Usage |
|-------|-------|
| `org-wide` | **Required** for all org-wide issues (triggers automation) |
| `initiative` | Long-term cross-team projects |
| `epic` | Large multi-phase initiatives |
| `rfc` | Proposals requiring review and consensus |
| `incident` | Production issues and outages |
| `sev-1` | Critical impact, immediate action required |
| `sev-2` | High impact, urgent but not critical |
| `sev-3` | Medium impact, important but not urgent |
| `dependency` | Blocked by external factors |
| `blocked` | Cannot proceed without resolution |
| `needs-triage` | Needs initial review and prioritization |
| `ready` | Approved and ready for work |
| `in-progress` | Currently being worked on |
| `done` | Completed |
| `wontfix` | Will not be addressed |

## Common Commands

### Creating Issues
```bash
# Via GitHub UI
1. Go to repository → Issues → New issue
2. Select template (Initiative/Incident/RFC)
3. Fill required fields
4. Add 'org-wide' label (auto-added by template)
5. Submit

# Via GitHub CLI
gh issue create --repo your-org/org-issues \
  --title "[Org-wide] Your title" \
  --label "org-wide,initiative" \
  --body "Issue content"
```

### Cross-linking Issues
```markdown
# Link to issue in same repo
#123

# Link to issue in another repo
owner/repo#123

# Create task list with links
- [ ] owner/repo#123 Implement feature A
- [ ] owner/repo#456 Implement feature B
```

### Searching Issues
```
# All org-wide issues
is:issue label:org-wide

# Open org-wide initiatives
is:issue is:open label:org-wide label:initiative

# Critical incidents
is:issue label:org-wide label:incident label:sev-1

# Issues needing triage
is:issue label:needs-triage

# Issues by owner
is:issue label:org-wide assignee:username
```

## Severity Guidelines

### SEV-1 (Critical)
- **Impact**: Significant business impact
- **Response**: Immediate
- **Examples**: Service outage, data loss, security breach
- **SLA**: Start mitigation within 15 minutes

### SEV-2 (High)
- **Impact**: Major functionality degraded
- **Response**: Urgent, same day
- **Examples**: Performance degradation, partial feature failure
- **SLA**: Begin investigation within 2 hours

### SEV-3 (Medium)
- **Impact**: Minor functionality affected
- **Response**: Important, within 1-2 days
- **Examples**: Non-critical bugs, workaround available
- **SLA**: Acknowledge within 24 hours

## Triage Process

### For Initiatives
1. **Review**: Assess scope and impact
2. **Stakeholders**: Identify affected teams
3. **Resources**: Determine capacity needed
4. **Timeline**: Establish deadlines
5. **Approval**: Get leadership sign-off
6. **Label**: Change from `needs-triage` to `ready`

### For Incidents
1. **Severity**: Assign SEV level
2. **Teams**: Notify affected teams
3. **War Room**: Set up communication channel
4. **Mitigation**: Begin immediate actions
5. **Updates**: Regular status updates
6. **Post-mortem**: Schedule after resolution

### For RFCs
1. **Reviewers**: Identify subject matter experts
2. **Timeline**: Set review period
3. **Discussion**: Gather feedback
4. **Consensus**: Build agreement
5. **Decision**: Accept, reject, or defer
6. **Action**: Convert to initiative or close

## Project Board Workflow

### Status Field Values
- **Backlog**: Accepted but not scheduled
- **Ready**: Prioritized and ready to start
- **In Progress**: Active work
- **Done**: Completed

### Priority Field Values
- **High**: Must be done this quarter
- **Medium**: Should be done this quarter
- **Low**: Nice to have

## Automation Features

### Auto-add to Project
Issues with `org-wide` label automatically added to organization Project

### Notification Rules
Configure GitHub notifications:
- Watch org-issues repository
- Subscribe to specific issues
- Filter by label or assignee

## Best Practices

### Do's ✅
- Add `org-wide` label to trigger automation
- Cross-link related issues
- Update status regularly
- Tag relevant teams/people
- Use checklists for tracking
- Document decisions in comments

### Don'ts ❌
- Don't create org-wide issues for single-repo concerns
- Don't skip required fields in templates
- Don't forget to update initiative issues when tasks complete
- Don't leave issues open indefinitely
- Don't use SEV-1 for non-critical issues

## Support

### Getting Help
- 💬 **Discussions**: For questions and proposals
- 📝 **Issues**: For tracking work
- 📖 **Docs**: Check SETUP.md and examples/
- 👥 **Team**: Tag @org-triage-team

### Resources
- [Setup Guide](../SETUP.md)
- [Examples](examples/README.md)
- [Security Policy](../SECURITY.md)
- [Contributing Guidelines](../CONTRIBUTING.md)

## Keyboard Shortcuts (GitHub)

| Shortcut | Action |
|----------|--------|
| `c` | Create new issue |
| `e` | Edit issue |
| `l` | Change labels |
| `m` | Change milestone |
| `a` | Assign yourself |
| `/` | Focus search |
| `?` | Show all shortcuts |

## Links Template

```markdown
## Related Issues
- Initiative: #42
- Dependencies: #43, owner/repo#123
- Blocked by: #44

## Documentation
- RFC Document: link
- Project Board: link
- Slack Channel: link
```

## Status Update Template

```markdown
## Weekly Status Update (YYYY-MM-DD)

**Progress This Week**
- [x] Completed task A
- [x] Completed task B
- [ ] In progress task C

**Blockers**
- Waiting on approval from @team

**Next Week**
- Complete task C
- Start task D

**Risks**
- Dependency on external API (mitigation: plan B)
```
