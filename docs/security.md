# Secure API Gateway, Authentication & Authorization (Phase 28)

The `aireliability` package provides a secure, provider-neutral API Gateway and security boundary designed for multi-tenant AI systems. It introduces comprehensive identity propagation, granular role-based access control (RBAC), tenant boundary enforcement, replay protection, security rate limiting, secret sanitization, and structured audit trails without requiring external identity providers or heavyweight infrastructure.

---

## 1. Security Architecture

The API Gateway intercepts inbound client requests and enforces a multi-stage security pipeline before any compute or queue resources are allocated:

```text
Client Request
      │
      ▼
┌───────────────────────────────────────────┐
│               SecurityGateway             │
│                                           │
│  1. Request Structural Validation         │
│     (Payload bounds, identifier regex)    │
│                     │                     │
│                     ▼                     │
│  2. Authentication                        │
│     (API Key, Bearer Token, Service ID)   │
│                     │                     │
│                     ▼                     │
│  3. Authorization & Tenant Isolation      │
│     (RBAC, tenant, project, namespace)    │
│                     │                     │
│                     ▼                     │
│  4. Replay Protection                     │
│     (Request ID, Nonce, Time Skew)        │
│                     │                     │
│                     ▼                     │
│  5. Security Rate Limiting                │
│     (Scoped by Principal and Tenant)      │
│                     │                     │
│                     ▼                     │
│  6. Audit Logging & Telemetry             │
│     (Immutable records, Prometheus)       │
└─────────────────────┬─────────────────────┘
                      │
                      ▼
            Resource Governance
                      │
                      ▼
               Control Plane
```

---

## 2. Authentication Model

The gateway is provider-neutral and accepts multiple authentication schemes:

* **API Keys (`APIKeyAuthenticationProvider`)**: Validates salted cryptographic SHA-256 hashes against persisted key records. Raw secrets are prefix-tagged (`airel_...`) and only displayed at creation time.
* **Bearer Tokens (`BearerTokenAuthenticationProvider`)**: Decodes and verifies token claims including subject, issuer, audience, and expiration times.
* **Internal Service Identity (`ServiceAuthenticationProvider`)**: Authenticates node-to-node workers and daemon processes via service credentials.
* **Anonymous Identity**: Unauthenticated requests safely resolve to a restricted `VIEWER` role with read-only permissions on public jobs.

---

## 3. Authorization & RBAC

Permissions are explicit rather than inferred from role strings:

### Standard Roles

| Role | Target Persona | Granted Permissions |
|---|---|---|
| `ADMIN` | Global Administrator | Full access across all system and tenant actions (`*`) |
| `TENANT_ADMIN` | Tenant Admin | Full administration of jobs, quotas, keys, and audits within tenant |
| `PROJECT_ADMIN` | Project Owner | Job submission, cancellation, and execution inspection in project |
| `OPERATOR` | DevOps / SRE | Worker health management, scheduler controls, and resilience |
| `DEVELOPER` | Engineer / User | Job submission, retries, and execution outcome reads |
| `VIEWER` | Auditor / Read-Only | Read-only access to jobs, executions, and metrics |
| `WORKER` | Execution Node | Read tasks and report execution results |
| `SERVICE` | Microservice / CI | Automated job submission and tracking |

---

## 4. Multi-Tenant Security Boundaries

Cross-tenant access is prohibited by default. An authenticated principal can only manipulate resources matching their identity:

$$\text{principal.tenant\_id} == \text{resource.tenant\_id}$$

Hierarchical sub-boundaries (`project_id` and `namespace`) are strictly validated against the principal's scope unless the principal holds `TENANT_ADMIN` or global `ADMIN` status.

---

## 5. Replay Protection

The `ReplayProtection` subsystem protects endpoints against replay attacks and clock skew:
* Tracks `request_id` and optional cryptographic `nonce` within a sliding time window (default 300 seconds).
* Rejects duplicate request identifiers or nonces detected within the active window.
* Rejects timestamps drifting beyond allowable clock skew (default 60 seconds).
* In-memory, thread-safe, and zero external dependencies (no Redis requirement).

---

## 6. Audit Logging & Sanitization

Security-sensitive events (`security.api_key_created`, `security.authorization_denied`, `security.replay_detected`, etc.) are written to immutable audit trails via `AuditLogger`.

* **Secret Redaction**: Passwords, API keys, tokens, and authorization headers are recursively stripped before persisting.
* **Storage Options**: Preserved across both `InMemoryDistributedStorage` and `SQLiteDistributedStorage`.

---

## 7. CLI Operational Commands

```bash
# Gateway status & identities
airel security status
airel security identities
airel security roles
airel security permissions

# API Key Management
airel security keys list --tenant acme-corp
airel security keys create acme-corp --name "Production Key"
airel security keys rotate <key-id>
airel security keys revoke <key-id>

# Audit Logs & Replay
airel security audit --tenant acme-corp
airel security replay-status
```

---

## 8. Threat Model & Mitigations

| Threat | Attack Surface | Mitigation Strategy | Residual Risk |
|---|---|---|---|
| **Credential Theft** | Leaked client config | Salted SHA-256 hashing; raw keys never stored; immediate rotation API. | Compromised endpoints before revocation. |
| **Credential Replay** | Intercepted network traffic | `ReplayProtection` nonces, unique request IDs, and 300s windowing. | Replays within skew window if nonces omitted. |
| **Cross-Tenant Access**| Malicious tenant requests | Hard tenant isolation in `AuthorizationEngine` and persistence layer. | Admin misconfiguration granting wildcard `*`. |
| **Privilege Escalation**| Role manipulation | Explicit permissions required; RBAC managed through immutable structures. | Compromise of global `ADMIN` key. |
| **Request Flooding** | Gateway DoS | Per-principal and per-tenant rate limiters; pre-queue shedding. | Distributed DDoS saturating network socket. |
| **Audit Log Leakage** | Log inspection / breaches | Sanitization policy unconditionally redacts sensitive keys & tokens. | Accidental secret in arbitrary unkeyed string payload. |
