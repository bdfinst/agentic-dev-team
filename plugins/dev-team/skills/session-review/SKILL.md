---
name: session-review
description: >-
  Mine real Claude Code session transcripts to suggest plugin improvements that
  cut token spend, reduce re-work, and improve accuracy. Use when the user asks
  to "review my sessions", "where am I wasting tokens", "why does this keep
  re-doing work", or "/session-review".
argument-hint: "[--cwd <path>] [--transcript <file>] [--out <report>] [--cross-machine]"
user-invocable: true
allowed-tools: >-
  Read, Glob, Bash(python3 *, date *, mkdir *, test *, echo *, bash *), Write, Agent
---

# Session Review (#131)

Role: orchestrator. Mines ground-truth session transcripts and routes
suggestions into existing machinery — it **suggests, never auto-applies**, and
preserves every human gate.

Every `.claude/metrics/*.jsonl`/`.json` schema referenced below (including
`pending-review.jsonl` and the boundary-level `boundary-events.jsonl` block/
warn/bypass/intervention causes, #859) is documented in full at
`${CLAUDE_PLUGIN_ROOT}/knowledge/telemetry-schema.md` — read it before
reasoning about a stream's fields ad hoc.

You have been invoked with the `/session-review` command.

## Orchestrator constraints

1. **Never read raw transcripts yourself.** All heavy parsing is the
   deterministic extractor's job; you read only its KB-sized digest. Spending
   model tokens to study token spend defeats the purpose. The one exception is
   the gated raw-log tier (Step 3b — the raw-log semantic tier): even there *you* never read a raw log — you
   dispatch one isolated sub-agent per flagged log and keep only its metrics-only
   findings.
2. **Suggest, never apply.** Output a ranked report and hand off; do not edit
   agents, skills, or config. Human gates stay intact.
3. **Metrics only.** The digest and report contain counts/ratios/names — never
   prompt or code content.

## Argument: $ARGUMENTS

- `--cwd <path>`: project whose transcripts to mine (default: current project).
- `--transcript <file>`: analyze a specific transcript instead of auto-resolving.
- `--out <report>`: report path (default: `.dev-team-reports/session-review-<date>.md`).
- `--cross-machine`: opt into cross-machine telemetry sync + rollup (#1480). **Absent by default** — a plain `/session-review` analyzes only this machine's local digest. See Step 1.

## Steps

### Pre-flight — dev-checkout guard (#1779)

`/session-review` is maintainer-only tooling that operates on this repo's own
infrastructure — its extractor (`session_extract.py`, `eval_rawlog.py`) is
deliberately monorepo-only, never shipped inside the plugin (see
`tests/repo/test_shipped_script_refs.py`'s `ESCAPE_ALLOWLIST` for the
rationale). Before Step 0 — this Pre-flight section runs first — check that
the extractor actually exists at the path every later command references:

```bash
test -f "${CLAUDE_PLUGIN_ROOT}/../../scripts/session_extract.py" \
  && test -f "${CLAUDE_PLUGIN_ROOT}/../../scripts/eval_rawlog.py" \
  && echo present || echo absent
```

If `absent` (the normal case for every downstream install, and any dev
checkout missing the repo-root `scripts/` tree — e.g. a shallow or
sparse clone), stop here and tell the user plainly: "`/session-review`
requires the `agentic-dev-team` monorepo dev checkout (it mines this repo's
own session telemetry) — not available from an installed plugin cache." Do
not proceed to Step 0 or run any command that references
`session_extract.py`; a raw `FileNotFoundError` traceback is not an
acceptable substitute for this message.

### 0. Queued Findings — surface pending-review queue before fresh analysis

Before running fresh analysis, check whether background analysis has produced
findings that are waiting for review.

1. Check `.claude/metrics/pending-review.jsonl` for entries where `reviewed_at` is absent.
   Count them and note their `queued_at` timestamps.
2. If one or more unreviewed entries exist, display a **Queued Findings** section:

   ```
   ## Queued Findings (N unreviewed)

   | # | queued_at | source | findings |
   |---|-----------|--------|----------|
   | 1 | <ts>      | <src>  | <count>  |
   ```

   Then offer: *"Run `/feedback-learning` to approve or reject each queued finding
   before proceeding with fresh analysis."*

3. If `.claude/metrics/pending-review.jsonl` does not exist, or all entries have
   `reviewed_at`, skip this section silently and proceed.
4. If any JSONL lines are malformed, skip those lines, emit a one-line warning
   (`WARN: skipped N malformed line(s) in pending-review.jsonl`), and continue
   with the valid entries.

### `pending-review.jsonl` Schema

Full field reference: `${CLAUDE_PLUGIN_ROOT}/knowledge/telemetry-schema.md`
(`pending-review.jsonl` section). Summary — each line is a JSON object:

```json
{
  "queued_at":  "2026-06-01T12:00:00Z",
  "source":     "session-learning-trigger",
  "session_id": "abc-123",
  "findings": [
    {
      "lever":           "instruction-rule",
      "evidence":        "3 occurrences in last 5 sessions",
      "target_artifact": "agents/orchestrator.md",
      "proposed_change": "Add constraint: always load context-loading-protocol first",
      "route":           "feedback-learning"
    }
  ]
}
```

Optional fields added by `/feedback-learning` after disposition:
- `reviewed_at` (ISO-8601 UTC) + `approved_by` — written on approval
- `rejected_at` (ISO-8601 UTC) + `rejected_by` — written on rejection

---

### 1. Cross-machine Telemetry — opt-in only (#178, #1480)

**Local-only is the default.** A plain `/session-review` never touches the
cross-machine telemetry repo — skip this step entirely (go straight to Step 2)
unless `--cross-machine` is present in `$ARGUMENTS`. This keeps a normal
invocation about *this developer's own working patterns on this machine*, not
conflated with every other machine's sessions.

**Only when `--cross-machine` is given:** check whether a **telemetry
repository** (the cross-machine "database", Delta D) is configured:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/../../scripts/telemetry-sync.sh" --check
```

- **Exit 0** → a repo is configured. Run the sync to push this machine's digest
  and pull the others, then continue:

  ```bash
  bash "${CLAUDE_PLUGIN_ROOT}/../../scripts/telemetry-sync.sh"
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

### 2. Extract (deterministic, zero model tokens)

Run the extractor to produce the local digest:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/../../scripts/session_extract.py" \
  --plugin-root "${CLAUDE_PLUGIN_ROOT}" -o memory/session-digest.json
```

(Pass `--transcript <file>` or `--cwd <path>` through from `$ARGUMENTS`.) If the
extractor finds no transcripts, tell the user and stop — nothing to review. The
local digest is always current-version-scoped by construction — it's a live
extraction tagged with the plugin version installed right now (`plugin_version`,
#1471) — so no extra filtering is needed here.

**Only when `--cross-machine` synced in Step 1 (cross-machine telemetry sync)**,
also build the cross-machine rollup (the union of every host's digest, #178)
and prefer it for analysis — it sees all machines and projects, not just this
one. Scope it to the **current and immediately previous plugin version**
(`--version-scope current-and-previous`, #1480) so a friction already fixed in
a newer version, or telemetry from a host still several versions behind,
doesn't weigh into current-version suggestions:

```bash
CLONE="${DEV_TEAM_TELEMETRY_CLONE:-$HOME/.claude/.dev-team/agent-telemetry}"
python3 "${CLAUDE_PLUGIN_ROOT}/../../scripts/session_extract.py" \
  --plugin-root "${CLAUDE_PLUGIN_ROOT}" --rollup "$CLONE/digests" \
  --version-scope current-and-previous \
  -o memory/telemetry-rollup.json
```

The rollup is metrics-only (`telemetry-rollup/v1`): per-host and per-project
token/cost, summed rework/accuracy, and skills/agents **never invoked on any
machine**, plus the `version_window` actually applied. Hand the analysis agent
the rollup when present, the local digest otherwise.

Then compute the **frequency → lever escalation** (Delta C, #179) — recurrence
decides how strong a response each friction earns — with the same version scope:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/../../scripts/session_extract.py" \
  --plugin-root "${CLAUDE_PLUGIN_ROOT}" --escalate "$CLONE/digests" \
  --version-scope current-and-previous \
  -o memory/telemetry-escalation.json
```

Each recommendation carries a `lever`: **hint** (rare — surface only),
**instruction-rule** (recurring; hand to `/feedback-learning`), or **hook**
(frequent *and* deterministically matchable; validate via `/agent-eval` before
shipping). "Matchable" is the deterministic side of the rules-vs-prompts ≤10% FP
policy. Use the escalation `lever` to set the hand-off in Step 3 (Analyze, digest-only).

Optionally compute the **gate correlation** (process eval, #111) — does bypassing
the pre-commit review gate correlate with more rework across sessions? — again
version-scoped:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/../../scripts/session_extract.py" \
  --plugin-root "${CLAUDE_PLUGIN_ROOT}" --correlate "$CLONE/digests" \
  --version-scope current-and-previous \
  -o memory/gate-correlation.json
```

This compares mean rework between bypass and non-bypass committing sessions. It is
correlational, not causal — surface it as evidence for whether the review gate
earns its place (feeds the ADR-0006 decision, #112), never as proof.

### 3. Analyze (digest-only)

Dispatch the `session-analysis` agent with the digest path as its sole input.
The agent maps aggregated patterns to probable plugin causes and returns ranked
suggestions, each tagged `{token | rework | accuracy}` with a named target
artifact and a hand-off destination. The agent reads **only** the digest.

### 3b. Raw-log semantic tier — only the worst sessions (#214, Delta A/B)

The digest is quantitative, so it is **blind to frictions with no count-signature**
— a hallucinated citation (the AI cited a skill/source that does not exist), or an
operator habit (deferring decisions with no owner). Surface those with a **bounded**
second tier: the deterministic digest decides *where* it is worth spending tokens,
then you read only those few raw logs. This tier needs the cross-machine digests
(the `$CLONE/digests` from Step 1 (cross-machine telemetry sync)); if no telemetry repo synced, **skip it**.
Step 1 is opt-in (#1480) — that includes the default plain-invocation case,
where it never runs.

1. Flag the worst sessions (deterministic, zero model tokens):

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/../../scripts/eval_rawlog.py" \
     --flag "$CLONE/digests" --top 5 -o memory/worst-sessions.json
   ```

   If it flags nothing, skip this tier — there is nothing expensive to read.

2. For each flagged `session_id` **only**, locate its raw transcript
   (`~/.claude/projects/**/<session_id>.jsonl`) and dispatch **one sub-agent per
   transcript** (one ~1MB log = one agent = one context boundary; fan out in
   parallel). Each sub-agent reads its single raw log and returns semantic
   frictions the digest cannot see. **You never read the raw log yourself**
   (constraint 1); the raw log never leaves the machine. Require each finding in
   the metrics-only shape the validator enforces — only these keys:
   `{lens, friction_type, target_artifact, confidence, count}` (plus optional
   `session_id`/`project`/`host`), with `lens` ∈ `{methodology, harness, devex,
   accuracy}`. A finding may say *that* a friction occurred and *which* artifact to
   fix, never a prompt, code, path, or quote.

3. Mechanically verify the privacy boundary before keeping anything — drop (do
   not report) any finding with violations:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/../../scripts/eval_rawlog.py" \
     --validate memory/tier2-findings.json
   ```

### 4. Suggest (write the report)

Write `.dev-team-reports/session-review-<date>.md` (or `--out`). Rank the suggestions and,
for each, record: the tag (`{token|rework|accuracy}` from the digest, or a Tier-2
lens `{methodology|harness|devex}`), the evidence (metrics only), the concrete
target artifact, the proposed change, and the hand-off destination from the table
below. Nothing is auto-applied.

The **`methodology`** lens (from Step 3b — the raw-log semantic tier — only) observes the *operator's own habits*
(e.g. deferring decisions with no owner). These have **no target artifact and no
hook** — their hand-off is "to the human, as an observation." Put them under their
own report heading; never route them to a gate.

| Suggestion kind | Hand off to |
|---|---|
| Config / prompt / convention fix | `/feedback-learning` |
| Model/effort re-tuning | `/harness-audit` + the agent's `model:`/`effort:` frontmatter (ADR 0026) |
| New / changed detection rule | `/agent-eval` (validate before shipping) |
| Token-heavy skill / agent | `token-efficiency-review` |
| Operator methodology observation (`methodology`) | the human, as an observation — no artifact, no hook |

### 5. Persist the trend (#129)

Append one metrics-only summary record to the trend stream so `/harness-audit`
can consume real-session data over time:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/../../scripts/session_extract.py" \
  --plugin-root "${CLAUDE_PLUGIN_ROOT}" --append metrics/session-digest.jsonl >/dev/null
```

The appended record holds aggregate counts only — no file names, prompts, or
code (see the schema in the eval-system docs).

### 6. Report

Print the report path and the top-ranked suggestions. Do not invent numbers —
cite exactly what the digest and the analysis agent emit.

## OSS complements

For continuous *quantitative* monitoring, recommend (don't replace) `ccusage`,
native OpenTelemetry, and `claude-code-log`. This skill covers the
plugin-specific *qualitative* suggestions those tools cannot — they don't know
this plugin's agents/skills. See the eval-system docs for details.
