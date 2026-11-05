# Security Policy

## Reporting Security Issues

If you discover a security vulnerability in this template repository, please report it responsibly:

1. **Do not** open a public issue
2. Email the repository maintainers directly
3. Include details about the vulnerability and steps to reproduce

## Scope

This repository contains templates and configurations for GitHub issue tracking. Security concerns might include:

- Workflow vulnerabilities that could expose secrets
- Template configurations that could leak sensitive information
- YAML injection vulnerabilities in templates

## Using These Templates Securely

When implementing these templates in your organization:

1. **Secrets Management**
   - Never commit secrets or tokens to the repository
   - Use GitHub Secrets for sensitive values like `ORG_PROJECT_TOKEN`
   - Use fine-grained Personal Access Tokens with minimal required permissions

2. **Visibility Considerations**
   - Be aware of the visibility (public/private) of repositories using these templates
   - Don't use public repositories for sensitive incident tracking
   - Consider using a private `org-issues` repository for internal matters

3. **Access Control**
   - Configure appropriate team and user permissions
   - Limit who can create org-wide incidents and initiatives
   - Review and audit org-wide issues regularly

4. **Workflow Security**
   - Review all GitHub Actions workflows before enabling them
   - Ensure the `ORG_PROJECT_TOKEN` has minimal necessary permissions
   - Pin action versions to specific commits or tags

## Updates

We will update these templates when security issues are discovered. Subscribe to repository notifications to stay informed.
