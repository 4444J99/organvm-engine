# Using the Organization-Wide Issue Redirect Template

## Overview

The redirect template (`redirect-to-org-repo.yml`) helps guide users from individual repositories to this central issue tracking repository when they need to file organization-wide issues.

## Installation in Your Repository

### Option 1: Direct Copy

Copy the template file to your repository:

```bash
# From your repository root
mkdir -p .github/ISSUE_TEMPLATE
curl -o .github/ISSUE_TEMPLATE/redirect-to-org-repo.yml \
  https://raw.githubusercontent.com/ivi374forivi/petasum-super-petasum/main/.github/ISSUE_TEMPLATE/redirect-to-org-repo.yml
```

### Option 2: Manual Copy

1. Navigate to [redirect-to-org-repo.yml](./ISSUE_TEMPLATE/redirect-to-org-repo.yml)
2. Click **Raw** button
3. Copy the contents
4. Create the file in your repository at `.github/ISSUE_TEMPLATE/redirect-to-org-repo.yml`
5. Paste the contents
6. Commit and push

### Option 3: Use as Reference

Create your own version based on the template:

```yaml
name: Organization-Wide Issue
description: Redirect to central repository for org-wide issues
title: "[Org-Wide]"
body:
  - type: markdown
    attributes:
      value: |
        For organization-wide issues, please file them in:
        [petasum-super-petasum](https://github.com/ivi374forivi/petasum-super-petasum/issues/new/choose)
```

## Configuration

After adding the template, you can customize:

1. **Title prefix**: Change `"[Redirect to Central Repo]"` to match your style
2. **Labels**: Add repository-specific labels if needed
3. **Guidance text**: Adjust the markdown to fit your repository's context

## Testing

After adding the template:

1. Go to your repository's Issues tab
2. Click **New Issue**
3. Verify the redirect template appears
4. Test the links to ensure they work

## Best Practices

### Placement

- **Include in all repositories**: Consistency helps users
- **Update config.yml**: If you have a `config.yml`, consider adding a direct link there too

Example `config.yml`:
```yaml
blank_issues_enabled: true
contact_links:
  - name: 📋 Organization-Wide Issue
    url: https://github.com/ivi374forivi/petasum-super-petasum/issues/new/choose
    about: For issues affecting multiple repositories
```

### Naming

Use a clear name that indicates it's about organization-wide issues:
- ✅ "Organization-Wide Issue (Redirect)"
- ✅ "File Org-Wide Issue"
- ✅ "Multi-Repository Issue"
- ❌ "Other Issues"
- ❌ "Redirect"

### Ordering

In your repository's issue templates, consider ordering:
1. Repository-specific templates first
2. Organization-wide redirect template last
3. Or use `config.yml` contact links instead

## Maintenance

### Keeping Updated

The template may be updated over time. To stay current:

```bash
# Periodically update the template
cd /path/to/your/repo
curl -o .github/ISSUE_TEMPLATE/redirect-to-org-repo.yml \
  https://raw.githubusercontent.com/ivi374forivi/petasum-super-petasum/main/.github/ISSUE_TEMPLATE/redirect-to-org-repo.yml
git commit -m "Update org-wide issue redirect template"
```

### Watching for Changes

Watch the central repository for updates:
1. Go to https://github.com/ivi374forivi/petasum-super-petasum
2. Click **Watch** → **Custom** → **Issues**
3. You'll be notified of changes

## Examples

### Example 1: Minimal Integration

Just add the redirect template - users will see it as an option when creating issues.

### Example 2: Config.yml Integration

Use `config.yml` instead of a full template:

```yaml
# .github/ISSUE_TEMPLATE/config.yml
blank_issues_enabled: true
contact_links:
  - name: 🌐 Organization-Wide Issue
    url: https://github.com/ivi374forivi/petasum-super-petasum/issues/new/choose
    about: Issues affecting multiple repositories or the entire organization
  - name: 💬 Organization Discussion
    url: https://github.com/orgs/ivi374forivi/discussions
    about: General questions and discussions
```

This approach is lighter weight and doesn't add a full template.

### Example 3: Full Integration

Add both:
- The redirect template for detailed guidance
- A config.yml link for quick access

## Troubleshooting

### Template Not Appearing

**Check:**
- File is in `.github/ISSUE_TEMPLATE/` directory
- File has `.yml` extension (not `.yaml`)
- YAML syntax is valid
- Changes are committed and pushed

### Links Not Working

**Check:**
- Organization name is correct in URLs
- Repository name is correct
- Links are not broken (test in browser)

### Template Conflicts

If you have multiple templates, ensure:
- Each has a unique `name` field
- No duplicate file names
- `config.yml` doesn't conflict

## Support

For help with the redirect template:
- **Issues**: File in [petasum-super-petasum](https://github.com/ivi374forivi/petasum-super-petasum/issues)
- **Discussions**: Ask in [Organization Discussions](https://github.com/orgs/ivi374forivi/discussions)

## Further Reading

- [GitHub Issue Template Documentation](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/configuring-issue-templates-for-your-repository)
- [Issue Template Syntax](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/syntax-for-issue-forms)
