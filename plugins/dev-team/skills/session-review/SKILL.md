---
name: session-review
description: >-
  Mine real Claude Code session transcripts to suggest plugin improvements that
  cut token spend, reduce re-work, and improve accuracy. Use when the user asks
  to "review my sessions", "where am I wasting tokens", "why does this keep
  re-doing work", or "/session-review".
argument-hint: "[--cwd <path>] [--transcript <file>] [--out <report>]"
user-invocable: true
allowed-tools: >-
  Read, Glob, Bash(python3 *, date *, mkdir *), Write, Agent
---

# Session Review (#131)

Role: orchestrator. Mines ground-truth session transcripts and routes
suggestions into existing machinery — it **suggests, never auto-applies**, and
preserves every human gate.

You have been invoked with the `/session-review` command.

## Orchestrator constraints

1. **Never read raw transcripts yourself.** All heavy parsing is the
   deterministic extractor's job; you read only its KB-sized digest. Spending
   model tokens to study token spend defeats the purpose.
2. **Suggest, never apply.** Output a ranked report and hand off; do not edit
   agents, skills, or config. Human gates stay intact.
3. **Metrics only.** The digest and report contain counts/ratios/names — never
   prompt or code content.

## Argument: $ARGUMENTS

- `--cwd <path>`: project whose transcripts to mine (default: current project).
- `--transcript <file>`: analyze a specific transcript instead of auto-resolving.
- `--out <report>`: report path (default: `reports/session-review-<date>.md`).

## Steps

### 0. Cross-machine telemetry — validate config, then sync (#178)

Before analysing, check whether a **telemetry repository** (the cross-machine
"database", Delta D) is configured, so the digest reflects every machine, not
just this one:

```bash
bash ${CLAUDE_PLUGIN_ROOT}/../../scripts/telemetry-sync.sh --check
```

- **Exit 0** → a repo is configured. Run the sync to push this machine's digest
  and pull the others, then continue:

  ```bash
  bash ${CLAUDE_PLUGIN_ROOT}/../../scripts/telemetry-sync.sh
  ```

- **Exit 3** → no repo configured. **Ask the user** for the telemetry repo
  location (a git URL), e.g. *"Where should cross-machine telemetry be stored?
  Paste a private git repo URL, or say 'skip' to review this machine only."*
  - If they give a URL, write it to `~/.claude/.dev-team/telemetry.json` as
    `{ "remote": "<url>" }` (create the dir if needed), confirm, then run the
    sync command above. Point them at
    [`telemetry-repo-security.md`](../../docs/telemetry-repo-security.md) for the
    one-time deploy-key/token setup.
  - If they say skip, proceed local-only — do **not** block the review.

Never invent a URL or enable anything without the user's explicit location.

### 1. Extract (deterministic, zero model tokens)

Run the extractor to produce the digest:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/../../scripts/session_extract.py \
  --plugin-root ${CLAUDE_PLUGIN_ROOT} -o memory/session-digest.json
```

(Pass `--transcript <file>` or `--cwd <path>` through from `$ARGUMENTS`.) If the
extractor finds no transcripts, tell the user and stop — nothing to review.

### 2. Analyze (digest-only)

Dispatch the `session-analysis` agent with the digest path as its sole input.
The agent maps aggregated patterns to probable plugin causes and returns ranked
suggestions, each tagged `{token | rework | accuracy}` with a named target
artifact and a hand-off destination. The agent reads **only** the digest.

### 3. Suggest (write the report)

Write `reports/session-review-<date>.md` (or `--out`). Rank the suggestions and,
for each, record: the tag `{token|rework|accuracy}`, the digest evidence
(metrics only), the concrete target artifact, the proposed change, and the
hand-off destination from the table below. Nothing is auto-applied.

| Suggestion kind | Hand off to |
|---|---|
| Config / prompt / convention fix | `/feedback-learning` |
| Model re-tiering | `/harness-audit` + `.claude/model-overrides.json` |
| New / changed detection rule | `/agent-eval` (validate before shipping) |
| Token-heavy skill / agent | `token-efficiency-review` |

### 4. Persist the trend (#129)

Append one metrics-only summary record to the trend stream so `/harness-audit`
can consume real-session data over time:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/../../scripts/session_extract.py \
  --plugin-root ${CLAUDE_PLUGIN_ROOT} --append metrics/session-digest.jsonl >/dev/null
```

The appended record holds aggregate counts only — no file names, prompts, or
code (see the schema in the eval-system docs).

### 5. Report

Print the report path and the top-ranked suggestions. Do not invent numbers —
cite exactly what the digest and the analysis agent emit.

## OSS complements

For continuous *quantitative* monitoring, recommend (don't replace) `ccusage`,
native OpenTelemetry, and `claude-code-log`. This skill covers the
plugin-specific *qualitative* suggestions those tools cannot — they don't know
this plugin's agents/skills. See the eval-system docs for details.
