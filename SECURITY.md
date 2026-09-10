# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.3.x   | :white_check_mark: |
| 1.2.x   | :white_check_mark: |
| 1.1.x   | :white_check_mark: |
| < 1.1.0 | :x:                |

## Reporting a Vulnerability

We take the security of AVA School Assistant 2 seriously. If you discover a vulnerability or security risk, please do not open a public issue.

### Reporting Process
1. Contact the maintainer directly via GitHub or email.
2. Provide detailed steps to reproduce the issue, including environment details and any relevant payload or logs.
3. Allow reasonable time for the maintainer to review and release a patch before disclosing publicly.

## Security Best Practices for Users
- **Credentials & API Keys**: Never commit your `config.json` file or any file containing API keys (`GEMINI_API_KEY`, OpenAI or Anthropic keys) to public repositories.
- **Git Ignore**: The repository includes `.gitignore` rules that protect `config.json`, `*.secret.json`, and local log files. Always use `config.default.json` as a sanitized template.
