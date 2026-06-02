---
name: threat-modeling
description: Structured STRIDE security analysis for identifying threats, attack surfaces, and mitigations. Use before implementing any new API, service, authentication change, or data flow crossing trust boundaries — security analysis belongs in the design phase, not after.
role: worker
user-invocable: true
---

# Threat Modeling

## Overview

Structured security analysis for identifying threats, attack surfaces, and mitigations during design or review phases. Ensures security considerations are addressed before implementation, not after.

## Constraints
- Focus on trust boundaries, not implementation details
- Every mitigation must map to a verifiable test or verification method
- Document accepted risks explicitly with rationale; do not silently ignore threats
- Revisit the threat model when architecture, authentication, or data flows change

## Core Concepts

### STRIDE Classification

| Category | Definition | Example Threats |
| --- | --- | --- |
| **S**poofing | Pretending to be something or someone else | Forged authentication tokens, impersonated services |
| **T**ampering | Modifying data or code without authorization | Altered request payloads, modified configuration files |
| **R**epudiation | Denying an action was performed | Unlogged administrative actions, unsigned transactions |
| **I**nformation Disclosure | Exposing data to unauthorized parties | Leaked credentials in logs, verbose error messages |
| **D**enial of Service | Making a system unavailable | Resource exhaustion, unbounded queries |
| **E**levation of Privilege | Gaining access beyond authorization | Broken access control, privilege escalation via injection |

### Trust Boundaries

Points where data crosses privilege levels. Every trust boundary is a potential attack surface. Common boundaries:

- Client to server
- Service to service (internal)
- Application to database
- System to external dependency
- User role transitions

### Attack Surface

Entry points exposed to untrusted input: API endpoints, file uploads, message queues, configuration inputs, user-supplied queries. Smaller attack surface means fewer threats to mitigate.

## Patterns

### Threat Identification Procedure

1. **Enumerate assets** — identify what needs protection (data, services, credentials, infrastructure)
2. **Draw trust boundaries** — map where data crosses privilege levels
3. **Identify entry points** — list all inputs exposed to untrusted sources
4. **Classify threats per STRIDE** — for each entry point, apply each STRIDE category and document applicable threats
5. **Rate severity** — assess impact (critical/high/medium/low) and likelihood for each threat

### Mitigation Mapping

| Threat Category | Standard Mitigations | Verification Method |
| --- | --- | --- |
| Spoofing | Authentication, mutual TLS, token validation | Auth integration tests, certificate verification |
| Tampering | Input validation, integrity checks, signed payloads | Tampering test cases, checksum validation |
| Repudiation | Audit logging, event sourcing, digital signatures | Log completeness review, signature verification |
| Information Disclosure | Encryption at rest/in transit, access controls, log scrubbing | Security scan, log audit, access control tests |
| Denial of Service | Rate limiting, resource quotas, circuit breakers | Load tests, resource monitoring |
| Elevation of Privilege | Least privilege, role-based access, input sanitization | Authorization test matrix, penetration tests |

### Threat Model Review Triggers

Revisit the threat model when any of the following occur:

- New external dependency added
- New API endpoint or entry point exposed
- Authentication or authorization changes
- Data flow changes crossing trust boundaries
- Infrastructure topology changes

## When to Apply

| Scenario | Apply? |
| --- | --- |
| New service or API endpoint | Yes |
| New external integration | Yes |
| Authentication or authorization changes | Yes |
| Data flow crossing trust boundaries | Yes |
| Internal refactoring with no boundary changes | No |
| UI-only cosmetic changes | No |

## Guidelines

1. **Focus on trust boundaries, not implementation details.** Threats exist at boundaries where privilege levels change.
2. **Mitigations must be verifiable.** Every mitigation maps to a test or verification method; unverifiable mitigations are theater.
3. **Document accepted risks explicitly.** When a threat is acknowledged but not mitigated, record the rationale, severity, and conditions for revisiting.
4. **Review when architecture changes.** The threat model is a living document that stays current with the system it describes.
5. **Severity drives priority.** Critical and high-severity threats block implementation; medium and low are tracked and scheduled.
6. **Threat models are collaborative.** Security analysis improves with input from architects, developers, and operations engineers.

## Output
STRIDE threat table with severity ratings, mitigation mapping, and verification methods. Explicitly list accepted risks with rationale. Be concise — table format; group by STRIDE category.

## Integration

- **Agent-Assisted Specification** — invoke during the Architecture Specification stage to identify security constraints before implementation
- **Governance & Compliance** — threat documentation feeds compliance audit trails and security review records
- **Accuracy Validation** — verify threat assessments against actual system state, not assumed state
