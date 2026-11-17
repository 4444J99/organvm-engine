# Examples

This directory contains examples of how to use the org-wide issue templates.

## Example 1: Org-wide Initiative

**Scenario**: Implementing organization-wide API versioning strategy

**Template Used**: Org-wide Initiative

**Key Fields**:
- **Summary**: Implement consistent API versioning across all services
- **Problem Statement**: Different services use different versioning strategies, causing confusion for API consumers
- **Impacted Repositories**: 
  - acme-corp/user-service
  - acme-corp/payment-service
  - acme-corp/notification-service
- **Primary Owners**: @platform-team
- **Success Criteria**: All services support v2 API with consistent versioning headers

## Example 2: Org-wide Incident

**Scenario**: Database connection pool exhaustion affecting multiple services

**Template Used**: Org-wide Incident

**Key Fields**:
- **Severity**: SEV-1
- **Impact**: 30% of user requests failing across authentication and payment services
- **Detection**: Automated monitoring alerts + customer reports
- **Impacted Repositories**:
  - acme-corp/user-service
  - acme-corp/payment-service
  - acme-corp/database-cluster

## Example 3: RFC (Request for Comments)

**Scenario**: Proposing migration from REST to GraphQL

**Template Used**: RFC (org-wide)

**Key Fields**:
- **Summary**: Evaluate and plan migration to GraphQL for all external APIs
- **Motivation**: Reduce over-fetching, improve mobile app performance
- **Design/Approach**: Phased migration starting with read-only endpoints
- **Affected Repos/Teams**: All services teams, mobile teams, frontend teams

## Best Practices for Using Templates

### When to Use Org-wide Initiative
- Cross-repo features requiring coordination
- Major technical migrations (e.g., language upgrades, framework changes)
- Organization-wide policy implementations
- Infrastructure changes affecting multiple teams

### When to Use Org-wide Incident
- Production outages affecting multiple services
- Security incidents requiring cross-team response
- Data integrity issues spanning multiple systems
- Critical dependency failures

### When to Use RFC
- Architectural decisions with broad impact
- Adopting new technologies or patterns
- Changing development workflows or processes
- Deprecating shared services or libraries

## Cross-linking Examples

### Linking Related Issues
```markdown
This initiative depends on:
- [ ] acme-corp/user-service#123 (API v2 implementation)
- [ ] acme-corp/payment-service#456 (API v2 implementation)
- [ ] acme-corp/docs#789 (API v2 documentation)
```

### Linking from Other Repos
```markdown
<!-- In acme-corp/user-service#123 -->
Part of org-wide initiative: acme-corp/org-issues#42
```

## Workflow Example

### Initiative Lifecycle

1. **Proposal Phase**
   - Create discussion in GitHub Discussions
   - Gather feedback from stakeholders
   - Refine scope and requirements

2. **Planning Phase**
   - Convert discussion to org-wide initiative issue
   - Create tracking tasks in affected repositories
   - Link all tasks back to initiative

3. **Execution Phase**
   - Teams work on individual tasks
   - Update initiative issue with progress
   - Hold regular sync meetings

4. **Completion Phase**
   - Verify all success criteria met
   - Document lessons learned
   - Close initiative and linked tasks

### Incident Lifecycle

1. **Detection**
   - Alert fires or user reports received
   - On-call engineer investigates

2. **Response**
   - Create org-wide incident issue
   - Notify affected teams
   - Begin mitigation

3. **Resolution**
   - Implement fix
   - Verify service recovery
   - Update incident issue

4. **Post-Mortem**
   - Document timeline
   - Identify root causes
   - Create follow-up tasks
   - Share learnings

## Label Usage Examples

### Combining Labels for Better Organization

```
Labels: [org-wide, initiative, sev-2, in-progress]
Meaning: An ongoing org-wide initiative with high severity
```

```
Labels: [org-wide, incident, sev-1, blocked]
Meaning: A critical incident that is currently blocked
```

```
Labels: [org-wide, rfc, needs-triage]
Meaning: A new RFC proposal that needs initial review
```

## Communication Templates

### Announcing an Org-wide Initiative

```markdown
**@all-engineers** 

We're launching a new org-wide initiative: [Initiative Name](link-to-issue)

**Why**: Brief explanation
**Timeline**: Target completion date
**Impact**: What this means for your team
**Action Required**: Any immediate actions needed
**Questions**: Post in the issue or #engineering-chat
```

### Incident Notification

```markdown
**@oncall @team-leads**

🚨 SEV-1 Incident: [Incident Title](link-to-issue)

**Status**: Investigating/Mitigating/Resolved
**Impact**: Brief description
**Affected Services**: List
**Next Update**: Time
**War Room**: Link to call/chat
```

## Tips for Issue Authors

1. **Be Specific**: Clearly define scope, success criteria, and timelines
2. **Tag Appropriately**: Use relevant labels for visibility
3. **Cross-link Early**: Link related issues from the start
4. **Update Regularly**: Keep stakeholders informed of progress
5. **Use Checklists**: Break down work into trackable tasks
6. **Document Decisions**: Record important choices in comments
7. **Close Properly**: Summarize outcomes before closing
