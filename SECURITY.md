# Security Policy

## Supported Versions

The following versions of `aireliability` are currently supported with security updates:

| Version | Supported          |
| ------- | ------------------ |
| 1.4.x   | :white_check_mark: |
| < 1.4.0 | :x:                |

## Reporting a Vulnerability

We take the security of `aireliability` and its users seriously. If you believe you have discovered a security vulnerability in `aireliability`, please follow these guidelines:

### 1. Private Disclosure
- **Do not** open a public GitHub issue to report a potential security vulnerability.
- Please report vulnerabilities privately by emailing security@aireliability.dev or submitting a confidential report via GitHub Security Advisories at https://github.com/aireliability/aireliability/security/advisories/new.

### 2. Information to Include
To help us triage and resolve the issue quickly, please provide:
- A clear description of the vulnerability and its potential impact.
- Step-by-step reproduction instructions or a minimal proof of concept (PoC).
- The exact version of `aireliability`, Python interpreter version, and operating system.
- Any suggested mitigations or patches, if available.

### 3. Response Process
- **Acknowledgment**: You will receive an acknowledgment of your report within 48 business hours.
- **Triage & Assessment**: Our core team will evaluate the severity using CVSS v3.1 metrics and determine the remediation plan.
- **Fix & Patch**: We will work on a patch in a private security fork, write automated reproduction security tests, and prepare a release candidate.
- **Coordinated Advisory**: Once the fix is released, a public security advisory and CVE (if applicable) will be published with credit given to the reporter.

## Security Architecture & Best Practices

`aireliability` is designed with defense-in-depth security principles:

1. **Deterministic-First & Isolated Sandboxing**:
   - Model outputs, prompts, and adversarial test inputs are evaluated in memory without executing arbitrary code.
   - Evaluator logic strictly sanitizes file system paths and disables shell execution (`shell=False`).

2. **Hard Security Vetoes**:
   - Critical vulnerabilities (e.g., prompt injections escaping containment, unauthorized tool execution, cross-tenant leaks) immediately trigger hard vetoes, capping system reliability scores at $\le 0.30$.

3. **Multi-Tenant Context Isolation**:
   - Multi-tenant boundaries are strictly guarded via Python `contextvars` and the `TenantIsolationManager`.
   - Cross-tenant data retrieval and state sharing are blocked and logged with security audit events.

4. **Zero Production Secret Exposure**:
   - All tests, benchmarks, and demo workflows use synthetic, ephemeral credentials.
   - The CLI and SDK scrub sensitive headers (`Authorization`, `X-API-Key`) from error traces and logs.
