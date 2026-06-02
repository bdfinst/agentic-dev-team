---
name: accepted-risks-schema
description: Schema and matching semantics for project-local ACCEPTED-RISKS.md policy carveouts consumed by /code-review, /review-agent, and security-review.
version: 1.0.0
---

# ACCEPTED-RISKS.md schema

## Purpose

A project-local `ACCEPTED-RISKS.md` at the repo root declares findings the team has explicitly accepted as known risks. `/code-review`, `/review-agent`, and the `security-review` agent consult this file and **suppress matched findings from the report** while logging each suppression to the audit trail. The goal is to keep review output focused on new issues without silently dropping real problems.

Rules are **narrow by default**. A rule that suppresses too broadly (e.g. a whole subsystem) must carry an extra `broad: true` flag and is flagged in the suppression report for extra scrutiny.

## File location and format

- Location: repo root, filename `ACCEPTED-RISKS.md` (exact case, singular)
- Format: Markdown with YAML frontmatter (`---` delimited) containing a `rules:` list
- Optional prose after the frontmatter is allowed for human readers; tooling parses only the frontmatter

## Rule schema

```yaml
---
rules:
  - id: <stable-slug>                # required
    rule_id: <upstream-rule-id>      # required; finding's rule_id to match (e.g. "semgrep.python.hardcoded-password")
    files:                           # required; list of globs (at least one)
      - <glob>
    rationale: <string>              # required; minimum 50 chars, must be specific
    expires: <ISO-8601 date>         # required; when this suppression MUST be re-reviewed (typically 90-180 days out)
    owner: <name-or-team>            # required; accountable party
    scope: finding | file            # optional; default "finding"
    broad: true | false              # optional; default false — flags rules covering >1 file or >1 rule_id for extra scrutiny
---
```

### Field semantics

- **`id`**: kebab-case, unique within the file. Used to cite the rule in suppression log entries and the expiry-reminder report.
- **`rule_id`**: matches the finding's `rule_id` field from the unified finding envelope. Wildcards allowed as `semgrep.python.*` — BUT the `broad: true` flag is mandatory if the pattern is a wildcard.
- **`files`**: gitignore-style globs. At least one. If none match the finding's path, the rule does not apply.
- **`rationale`**: minimum 50 characters. Must be concrete — "known false positive" is not acceptable; "hardcoded test fixture used only in spec files; not loaded in production builds (verified by webpack.config.prod.js excluding test/)" is.
- **`expires`**: ISO-8601 date. After this date, the rule is inert (stops suppressing) and the next review run emits a WARN requesting re-review or rule deletion.
- **`scope`**:
  - `finding` (default): rule matches when both `rule_id` matches AND a file glob matches
  - `file`: rule matches any finding on a matched file path, regardless of `rule_id`. Always requires `broad: true`.

## Matching algorithm

For each finding F in the unified finding envelope:

1. Iterate rules in order of file declaration.
2. For each rule R:
   - If `R.expires` is in the past → skip R entirely for this run; enqueue a WARN.
   - Match `R.rule_id` against `F.rule_id`:
     - Exact match → OK
     - Wildcard pattern (ends in `.*`) → OK if wildcard base matches the prefix of `F.rule_id` AND `R.broad == true`
     - Otherwise → no match
   - Match `R.files` globs against `F.file`. Any matching glob → OK.
   - If both match: F is suppressed. Emit exactly one suppression log entry:
     ```
     SUPPRESSED: <F.file>:<F.line> [<F.rule_id>] by ACCEPTED-RISKS rule <R.id>
     ```
3. If no rule matches: F flows through to the report normally.

A finding matches **at most one rule** (first-match-wins). Order within `ACCEPTED-RISKS.md` matters for traceability.

## Report output

After a review run:

- **Suppression report**: one line per suppressed finding, grouped by rule id. Counted in the review summary.
- **Broad-rule callout**: any rule with `broad: true` gets a separate section naming the rule and its rationale — reviewers should audit these rules on every run.
- **Expiry report**: rules whose `expires` is in the past, or within 30 days of expiry, are listed with the owner name for action.

## Authoring policy

- Rules are **additive**, never removed silently. Deleting a rule must cite a git commit message explaining why the risk is no longer accepted (fixed, accepted permanently as a runbook entry, or scope changed).
- A rule's `rationale` is reviewed at each expiry renewal. The renewal extends `expires` and does not mutate other fields.
- A rule covering multiple files or a wildcard `rule_id` requires `broad: true` and is flagged for maintainer attention every run.
- The file itself may carry arbitrary markdown prose after the frontmatter — that prose is not parsed by tooling.

## Initialization

When `/code-review` runs in a repo without `ACCEPTED-RISKS.md`, the agent does NOT create one automatically. To scaffold:

```
/code-review --init-risks
```

This copies `plugins/agentic-dev-team/templates/ACCEPTED-RISKS.md.tmpl` to the repo root if the file is absent. If the file already exists, `--init-risks` exits non-zero without overwriting.

## Out of scope

- **This schema does NOT cover severity-threshold suppression.** Lowering severity is a review-agent configuration concern, not a project policy concern.
- **This schema does NOT cover global ignore patterns** (e.g. ignoring all findings in `vendor/`). Use each tool's native ignore mechanism for those.
- **This schema does NOT apply to security-review's findings only** — it applies to the full unified finding envelope from any review agent or static-analysis adapter.
