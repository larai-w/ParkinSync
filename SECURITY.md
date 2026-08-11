# Security Policy

ParkinSync is a public, health-adjacent open-source project. Security reports are welcome, but
testing must stay within the repository's synthetic-data boundary.

## Supported versions

Security fixes are applied to `main` and, when practical, the latest tagged release. Older tags
receive fixes only when the maintainer explicitly backports them.

## Report a vulnerability privately

Do not disclose a suspected vulnerability in a public issue, pull request, discussion, or log.

1. Use the repository's **Security** tab and select **Report a vulnerability** when that option is
   available.
2. If private reporting is unavailable, use the [VEAI LAB contact form](https://veai.jp/contact/)
   and ask for a private security-reporting channel. Do not include exploit details, credentials,
   personal data, or care records in the initial message.

Include the affected version or commit, the security impact, minimal reproduction steps using
synthetic data, and any mitigation you have tested. Reports are handled on a best-effort basis by a
solo maintainer; no response-time or remediation SLA is guaranteed.

## Safe testing boundary

Authorized testing is limited to code you run in an environment you own or control, using the
repository's synthetic fixtures. Do not:

- probe deployed VEAI or third-party systems;
- access, alter, retain, or disclose participant-derived or personal data;
- attempt credential theft, denial of service, social engineering, or persistence;
- test AWS accounts, APIs, devices, or repositories without explicit authorization;
- publish details before a fix or disclosure plan has been agreed.

This policy does not grant permission to test infrastructure or data outside this repository.

## Project security boundary

- Credentials belong in environment variables or AWS Secrets Manager, never in Git.
- Participant-derived data, raw care records, and identifying metadata are not permitted in the
  repository.
- Public examples and security reproductions must use clearly marked synthetic data.
- ParkinSync is not a medical device and does not provide diagnosis or treatment recommendations.
- Security findings and proposed fixes require maintainer review and regression evidence before
  release.

See [Data Governance](docs/DATA_GOVERNANCE.md) for the wider data-handling and publication boundary.
