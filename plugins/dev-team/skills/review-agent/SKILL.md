---
name: review-agent
description: >-
  Run a single named review agent against target files. Use this when the
  user names a specific agent (e.g. "run security-review", "check for test
  issues", "run js-fp-review on this file") rather than wanting the full
  suite. Prefer this over /code-review when only one concern is relevant or
  speed matters. Also used by the orchestrator for inline review checkpoints
  during Phase 3 implementation.
argument-hint: "<agent-name> [--since <ref>] [--path <dir>] [--internal] [--json]"
user-invocable: true
allowed-tools: Read, Write, Grep, Glob, Bash(git diff *)
---

# Review Agent

Role: worker. This skill performs the actual review using the agent
definition as its specification.

You have been invoked with the `/review-agent` skill. Run a single named review agent.

This command is executed under orchestrator direction. Pass the named
agent's `model:`/`effort:` frontmatter as declared — the harness resolves
both fields natively before dispatch, per Model/Effort Resolution in
`.claude/agents/orchestrator.md` (ADR 0026).

## Worker constraints

1. **Follow the agent definition exactly.** The agent file is your
   specification — detect what it says to detect, skip what it says
   to skip.
2. **Respect context needs.** When reviewing uncommitted changes or `--since`,
   honor the agent's `Context needs` field (diff-only, full-file, or
   project-structure).
3. **Do not add findings beyond the agent's scope.** If the agent
   says "Ignore: naming, tests" — do not flag naming or test issues.
4. **The structured JSON result (step 3) is the canonical output.**
   In `--json` mode it is the *only* thing written to stdout — no
   formatted summary, no report, no prose (see step 3c). Otherwise it is
   also rendered as a formatted summary (step 4) and written to the durable
   report (step 4b).
5. **Be concise.** Issue messages should be one sentence. Suggested
   fixes should be actionable, not explanatory. No preambles or
   filler.

## Parse Arguments

Arguments: $ARGUMENTS

Required: agent name (`$0`, e.g., `test-review`, `js-fp-review`, `security-review`)

Optional:

- `--since <ref>`: Review files changed since a git ref
- `--path <dir>`: Target directory (default: current working directory)
- `--internal`: This is an orchestrator-internal dispatch (e.g. `/build`'s
  Phase 3 inline checkpoints) — skip the `.dev-team-reports/` report write in
  step 4b. `/build` is the only sanctioned caller of this flag today.
- `--json`: Machine-readable mode. Emit **only** the step-3 JSON result to
  stdout and nothing else — skip the formatted summary (step 4), skip the
  `.dev-team-reports/` report write (step 4b), and print no confirmation line,
  preamble, or trailing prose. Used by subprocess callers such as
  `/agent-eval --calibrate` that parse stdout and need a deterministic,
  model-independent result. See step 3c.

## Steps

### 1. Load agent definition

Read `.claude/agents/<name>.md`. If the file doesn't exist, list available
review agents from `.claude/agents/` (the Review Agents section of
`knowledge/agent-registry.md` is the roster) and ask the user to pick one.

### 2. Determine target files

Same auto-scope logic as `/code-review`:

- If uncommitted changes exist: review those files
- If working tree is clean: review all source files
- `--since <ref>`: `git diff --name-only <ref>...HEAD`
- `--path <dir>`: review files in that directory

### 3. Run review

Follow the agent definition to review each target file. Produce a JSON result:

```json
{
  "agentName": "<name>",
  "status": "pass|warn|fail",
  "issues": [
    {
      "severity": "error|warning|suggestion",
      "file": "<path>",
      "line": 0,
      "message": "<description>",
      "suggestedFix": "<fix>"
    }
  ],
  "summary": "<summary>"
}
```

### 3b. Apply ACCEPTED-RISKS.md suppression

Before reporting, consult `ACCEPTED-RISKS.md` at the repo root if present. For each issue, check rules in declaration order per `knowledge/accepted-risks-schema.md`. The first matching rule suppresses the issue from the displayed result and emits an audit entry of the form `SUPPRESSED: <file>:<line> [<rule_id>] by ACCEPTED-RISKS rule <rule.id>`. Expired rules become inert (stop suppressing). Schema-invalid rules fail the run with a specific parse error. Absent file: skip silently.

### 3c. `--json` mode (machine-readable output)

When `--json` is passed, your **entire stdout response MUST be exactly one
JSON object** matching the step-3 schema — nothing before it, nothing after
it. Do **not** render the formatted summary (step 4), do **not** write the
`.dev-team-reports/` report (step 4b), do **not** print a `Report written:`
line, do **not** wrap the object in a code fence, and do **not** add any
prose, preamble, or trailing commentary. ACCEPTED-RISKS suppression (step 3b)
still applies — emit the post-suppression result. This mode exists so that
subprocess callers (e.g. `/agent-eval --calibrate`) can parse the result
deterministically across every model; any extra text breaks that contract.

### 4. Report

**Skip this step entirely when `--json` was passed** (see step 3c) — stdout
must be exactly the JSON object. Otherwise, display the result as a formatted
summary with issues grouped by file. Include suggested fixes inline. If any
issues were suppressed by ACCEPTED-RISKS, list them in a dedicated trailing
section with rule ids for audit.

### 4b. Write the durable report (skip when `--internal` or `--json`)

See `knowledge/report-output-location.md` for the shared write-scope
convention this step follows.

When neither `--internal` nor `--json` was passed, write the same formatted
summary shown in step 4 to `.dev-team-reports/<agent-name>.md` in the target repository's
working directory (creating `.dev-team-reports/` if absent), overwriting any
existing file at that path — write it even when the review found zero
issues. Print one confirmation line after the chat summary: `Report
written: .dev-team-reports/<agent-name>.md`, or `Report written:
.dev-team-reports/<agent-name>.md (replaced previous run)` when a file
already existed at that path. If the write fails (permission/read-only):
report `Cannot write .dev-team-reports/<agent-name>.md: <error>` to chat, and
still return the JSON result and chat summary unchanged — the write failure
is non-fatal and never blocks or alters the primary output.

When `--internal` **was** passed (but not `--json`), skip this step entirely —
behavior stays exactly as today (JSON + chat summary only). When `--json` was
passed, this step is likewise skipped and stdout is the JSON object alone
(step 3c).
