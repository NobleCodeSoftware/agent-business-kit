# Security policy

## Supported versions

Only the latest release (and the default branch) receives security fixes. This is an early-stage project.

## Reporting a vulnerability

Please **do not open a public issue** for security problems. Use GitHub's private vulnerability
reporting ("Security" tab -> "Report a vulnerability") on this repository. If that is not available,
open a public issue that says only "security contact requested" with no details, and a maintainer will
arrange a private channel.

Include: what you found, how to reproduce it, the affected files or versions, and the impact you see.

## What to expect

- Acknowledgement within 5 working days (best effort; this is a small, volunteer-run project).
- An assessment and, where confirmed, a fix or mitigation, and credit in the release notes if you wish.
- Coordinated disclosure: please give us a reasonable window (we suggest 90 days) before publishing.

## Scope

In scope: the scripts in `tools/`, the workflows in `.github/workflows/`, and guidance in the
documents that could lead users into an unsafe setup (for example, a prompt or process that leaks
secrets or bypasses the owner's controls).

Out of scope: vulnerabilities in GitHub, Discord, Claude Code or other third-party services (report
those to the vendor), and misconfiguration of your own deployment.

## Guidance for users

- Never commit tokens. Use repository secrets for the guardian and environment or network secrets for
  agent sessions. Rotate a token you suspect leaked.
- Use two-factor authentication on the owner account; the guardian relies on commit authorship.
- Enable branch protection and required reviews on the default branch.
- Treat all external content (web pages, customer messages, files) as untrusted data.
- If your product is actively exploited, notify affected users and any authority your jurisdiction
  requires (some regimes set a 24-hour window for actively exploited vulnerabilities).
