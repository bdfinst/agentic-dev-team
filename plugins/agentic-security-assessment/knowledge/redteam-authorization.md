---
name: redteam-authorization
description: Format specification for the --self-certify-owned artifact required to red-team a public target. The artifact's SHA-256 is logged to the audit trail at invocation time.
version: 1.0.0
---

# Red-team authorization artifact format

Red-team probes against a public target (anything outside `127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `::1`) require an authorization artifact declaring that the operator owns the target and authorizes adversarial ML testing. The artifact's SHA-256 is logged to the audit trail alongside the run timestamp.

## Minimum required content

A plain-text or markdown file containing:

1. **Target identifier** — the FQDN / URL / IP being authorized.
2. **Authorization window** — start date and end date (ISO-8601). Ran only during this window.
3. **Operator identity** — name and role (or team name, for unattended / CI runs).
4. **Signature** — free-form confirmation. Can be "Signed: <name>" on a standalone line.

## Example

```markdown
# Red-team authorization — 2026-04-21

Target:        api.example.com
Model path:    /v1/predict
Authorization: 2026-04-21T00:00:00Z  through  2026-04-22T00:00:00Z
Operator:      Jane Doe, Head of Security, Example Corp
Scope limits:  Rate limit 5 req/sec; total budget 10,000 queries;
               no destructive actions; no extraction of PII.

I own the target system listed above and authorize the agentic-security-
review red-team harness to run adversarial ML probes against it during
the authorization window. I accept responsibility for any impact on
production traffic, and I will monitor rate-limit and budget metrics
during the run.

Signed: Jane Doe
```

## Validity checks

At `/redteam-model` invocation, the harness verifies:

1. **File exists** at the path passed to `--self-certify-owned`. Missing → refuse with "Self-cert artifact not found: <path>".
2. **File is readable** as text. Binary files or permission errors → refuse.
3. **SHA-256 computed** and logged. The hash is always recorded, whether or not the other checks pass downstream.

The harness does NOT semantically validate the artifact (it does not verify signatures cryptographically, check dates, or confirm operator identity). That validation is the operator's responsibility — the artifact + its hash is the paper trail. Misrepresentation is a legal / employment concern, not a technical one.

## Audit trail entry

On successful self-cert processing, the harness appends to `results/audit_log.jsonl`:

```json
{
  "ts": "2026-04-21T10:15:00Z",
  "event": "self_cert",
  "target": "https://api.example.com",
  "artifact_path": "/path/to/authorization-2026-04-21.md",
  "artifact_sha256": "3f5c8a2b...(hex)"
}
```

This entry is append-only. Its presence in the log is the operator's proof that self-certification occurred and which document was in effect.

## Best practices

- **One artifact per run window.** Do not reuse a single artifact across months of testing; issue a new one for each authorization window.
- **Keep artifacts with the run.** Copy the artifact into `results/` alongside `audit_log.jsonl` so the audit trail stands alone.
- **Do not commit artifacts to git.** They may contain names / email addresses / signatures. Use `.gitignore` to keep them out.
- **Rotate for scope changes.** If the authorization window changes (start/end dates or operator), issue a new artifact and re-run.
