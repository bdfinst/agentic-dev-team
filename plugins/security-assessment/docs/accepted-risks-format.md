# ACCEPTED-RISKS.md format

`ACCEPTED-RISKS.md` is a per-target markdown file that declares security findings the repo owners have reviewed and accepted. The security-assessment pipeline parses it in Phase 1c (`scripts/apply-accepted-risks.sh`) and suppresses matching findings before they reach the disposition register.

## File location

`<target-dir>/ACCEPTED-RISKS.md` — at the root of the repository being assessed. If absent, the Phase 1c step is a no-op and every finding proceeds to triage.

## Machine-parseable block

The first fenced ```` ```json ```` code block in the file is authoritative. Prose before, between, or after the block is ignored by the parser — use it for context, justification history, or approval notes.

The JSON block must be a top-level object with an `accepted_risks` array:

````markdown
# ACCEPTED-RISKS

Additional prose can live here and is ignored by the parser.

```json
{
  "accepted_risks": [
    {
      "rule_id": "semgrep.csharp.sqli.raw-sql-concat",
      "source_ref_glob": "src/Legacy/**/*.cs",
      "reason": "Legacy reporting module scheduled for deletion Q3 2026 (ACI-RPT-1234).",
      "expires": "2026-09-30"
    },
    {
      "rule_id": "hadolint.DL3003",
      "source_ref_glob": "docker/base/Dockerfile",
      "reason": "Base image built in a controlled CI step; cd is intentional.",
      "expires": "2027-01-01"
    }
  ]
}
```
````

## Field reference

| Field | Type | Required | Semantics |
|---|---|---|---|
| `rule_id` | string | yes | Exact string equality against a finding's `rule_id`. |
| `source_ref_glob` | string | yes | Glob pattern matched against a finding's `source_ref`. See *Glob semantics* below. |
| `reason` | string | yes | Human-readable justification; copied into the suppression log for audit. |
| `expires` | string | yes | `YYYY-MM-DD` UTC calendar date. Entry is active through that date; expired starting the following day. |

Any entry missing a required field, or with `expires` not matching `YYYY-MM-DD`, is a parse error — the script exits non-zero (code 3) and makes no changes.

## Glob semantics

Globs use a restricted subset documented here, deterministic across platforms:

- `*` matches any character *except* `/`. Example: `src/*.cs` matches `src/Foo.cs` but NOT `src/nested/Bar.cs`.
- `**` matches any characters *including* `/`. Example: `src/**/*.cs` matches both `src/Foo.cs` and `src/nested/deep/Bar.cs`.
- `?` matches a single non-`/` character.
- All other characters match literally. JSON escaping still applies (e.g., `"\\"` in JSON source for a literal backslash).

No Python `fnmatch` variance — the parser implements the glob-to-regex translation itself so behavior is identical regardless of the host Python version.

## Expiry

- `expires` is always a UTC calendar date. The script compares against today's UTC date at invocation time.
- Active entries (today ≤ expires) suppress matching findings and emit a `status: "suppressed"` log record.
- Expired entries (today > expires) do NOT suppress. Instead they emit a `status: "expired"` log record so operators notice a lapsed exception during report review. This is a surveillance-not-silence approach: operators who let an exception lapse see a visible signal in the suppression log instead of a silent regression to unsuppressed behavior.

## Parse error envelope

On malformed input the script writes `apply-accepted-risks.sh: ACCEPTED-RISKS.md parse error at <path> — <detail>; no risks applied` to stderr and exits 3. `findings-<slug>.jsonl` is left unchanged. No partial suppression is possible — parse-or-nothing.

## Log artifact

Each invocation writes `<memory-dir>/accepted-risks-<slug>.jsonl`. Two record shapes:

```json
{"status":"suppressed","rule_id":"...","source_ref":"src/matched/path.cs","source_ref_glob":"src/**/*.cs","reason":"...","expires":"2026-09-30","iso":"2026-04-24T17:30:39Z"}
```

```json
{"status":"expired","rule_id":"...","source_ref_glob":"...","reason":"...","expires":"2020-01-01","iso":"2026-04-24T17:30:39Z"}
```

The record schemas are registered in `plugins/agentic-dev-team/knowledge/security-primitives-contract.md` alongside the other security-assessment artifacts.

## Idempotency

The log file is rewritten (not appended) on each invocation, so repeated runs against unchanged inputs produce byte-identical outputs. If you need a historical audit trail across runs, rotate or archive the log file between invocations — the pipeline itself does not accumulate history in this artifact.
