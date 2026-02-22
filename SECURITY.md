# Security Policy

## Supported Versions

Security fixes are applied on a best-effort basis to the latest code on `main`.

## Reporting a Vulnerability

Please do not disclose security vulnerabilities publicly before maintainers have a chance to investigate and patch.

When reporting, include:

- Affected component/file
- Reproduction steps or proof-of-concept
- Potential impact
- Suggested mitigation (if available)

Report through a private channel (security advisory or private maintainer contact) instead of public issues.

## Response Process

- Acknowledgement target: within 72 hours
- Triage and severity assessment
- Patch and verification
- Coordinated disclosure after fix availability

## Security Notes for Contributors

- Never commit API keys or secrets
- Use `.env` for local credentials
- Prefer pinned dependency ranges and keep dependencies up to date
- Validate all external input at API boundaries
