# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Sibelium, please report it privately instead of opening a public issue.

**Contact:** Open an issue labeled `security` or contact the maintainer directly.

## Supported Versions

| Version | Supported |
|---------|-----------|
| Latest commit on `main` | ✅ |
| All previous versions | ❌ |

## Scope of Concern

Security issues include but are not limited to:
- Prompt injection that bypasses entity identity constraints
- Unauthorized access to entity memory or state files
- Exploitation of the web search module to exfiltrate data
- Denial of service via resource exhaustion (infinite thought loops, memory saturation)

## API Keys

Sibelium uses API keys for cloud model access. Never commit your `config.py` with real API keys. The `.gitignore` should exclude `config.py` from version control. Use environment variables or a separate untracked file for production deployments.

## Responsible Disclosure

Report vulnerabilities at least 30 days before any public disclosure. We will acknowledge receipt within 48 hours and provide a timeline for resolution.