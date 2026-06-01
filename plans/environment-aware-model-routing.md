# Plan: Environment-Aware Model Routing with Fallback

**Created**: 2026-06-01
**Branch**: cut `feat/env-aware-model-routing` from `main` before Step 1
**Status**: approved
**Spec**: [docs/specs/environment-aware-model-routing.md](../docs/specs/environment-aware-model-routing.md)
**Issue**: [#37](https://github.com/bdfinst/agentic-dev-team/issues/37)
**Revision note**: addresses blockers from the first plan-review pass (R1 enforcement, missing scenarios, undefined error/prompt/output text, scope boundaries).

## Goal

Make tier-to-snapshot resolution deterministic and environment-aware so the
plugin runs unchanged on personal Anthropic keys, corporate proxies with
restricted model allowlists, and Bedrock/Vertex deployments. Resolution lives
in a shipped JSON file (`knowledge/model-routing.json`) plus an optional
per-user gitignored override cache (`.claude/model-overrides.json`), and is
**enforced by a PreToolUse hook on the `Agent` matcher** — not by orchestrator
instructions. An opt-in probe in `/init-dev-team` populates the override cache
for restricted endpoints; a read-only `/model-routing-check` command surfaces
the resolved state and recent tier bumps for triage.

## Acceptance Criteria

Mirrors the spec's AC table. Each TDD step traces back to specific AC IDs.

- [ ] **AC1** Zero-config baseline (no overrides → silent dispatch, no metrics writes)
- [ ] **AC2** Single source of truth (grep returns only three approved files)
- [ ] **AC3** Pre-dispatch resolution (override haiku→sonnet)
- [ ] **AC4** Cascade (haiku→sonnet→opus chain)
- [ ] **AC5** Top-tier exhaustion error template (exit 3 + sentence + path + entry + command)
- [ ] **AC5a** Cycle detection (exit 3 + cycle sentence + visited tiers)
- [ ] **AC5b** Missing routing.json (exit 4 + remediation)
- [ ] **AC5c** Malformed overrides file (exit 5 + remediation)
- [ ] **AC6** Gitignored override file + bump log
- [ ] **AC7** Probe is opt-in (decline → no file, exit status golden)
- [ ] **AC7a** Probe happy path — all tiers available
- [ ] **AC7b** Probe happy path — tier missing → write overrides
- [ ] **AC8** Probe shape gating (Bedrock + Vertex hosts skipped)
- [ ] **AC9** Probe failure tolerance (timeout / 500 / malformed JSON, three distinct messages)
- [ ] **AC10** Diagnostic side-effect-free (sha256sum identical)
- [ ] **AC11** Diagnostic surfaces bumps (format `<ts>  <req> → <served>  [<reason>]  caller=<caller>`)
- [ ] **AC11a** Diagnostic tail cap at 10 (with `Showing last 10 of N …` line)
- [ ] **AC11b** Diagnostic probe-applicability line
- [ ] **AC12** Documentation completeness (eight required H2 sections)
- [ ] **AC13** ADR records both decisions (pre-dispatch + hook enforcement)
- [ ] **AC14** Backward compat (`/agent-audit` clean; tier-alias frontmatter retained)
- [ ] **AC15** Performance (1000 invocations < 5s wall-clock)
- [ ] **AC16** Hook rewrites `tool_input.model` via `hookSpecificOutput.updatedInput`
- [ ] **AC17** Hook refusal emits PreToolUse `permissionDecision="deny"` with the AC5 template
- [ ] **AC18** Hook registered in `settings.json` under `PreToolUse.matcher="Agent"`
- [ ] **AC19** Bump discoverability banner when overrides file present

## User-Facing Behavior

Gherkin scenarios are the single source of truth — copied verbatim from the spec. See `docs/specs/environment-aware-model-routing.md` §User-Facing Behavior. Each scenario maps to one or more steps below; the cross-reference is in the step's `Maps to` line.

## Implementation Strategy

Three layers, each independently testable:

1. **Resolver helper** (`hooks/lib/model-resolve.sh`) — pure shell + jq. Reads routing.json + overrides, walks the alias chain, prints snapshot on stdout, appends bump JSONL, exits with a specific status code per failure mode. Bats-testable in isolation via env-var-overridable paths.
2. **PreToolUse hook** (`hooks/agent-model-resolve.sh`) — thin Claude Code hook adapter. Reads JSON from stdin (PreToolUse contract: `tool_name`, `tool_input`, `transcript_path`, `cwd`), extracts `tool_input.model` and `tool_input.subagent_type`, shells out to the resolver, and emits the appropriate `hookSpecificOutput` JSON (`updatedInput` on success, `permissionDecision="deny"` on resolver exit 3/4/5). Registered in `settings.json` under `PreToolUse` with `matcher: "Agent"`. **This is the enforcement surface** — LLMs cannot bypass it.
3. **Diagnostic command** (`/model-routing-check`) — markdown command that shells out to the resolver helper with a `--dump-map` flag plus a `tail`+`jq` of the bump log. Read-only.

The probe is a fourth, optional layer: `hooks/lib/model-probe.sh` invoked only by `/init-dev-team` when the user opts in. It's a convenience for populating the override cache; the resolver works fine with hand-written overrides.

Bats infrastructure: extend the existing `tests/hooks/`, `tests/commands/`, `tests/docs/`, `tests/repo/` directories. Use the established `tests/hooks/fake-bin` PATH-override pattern for `curl` and `claude` shims; do not introduce a new env-var-holds-a-shell-command shim.

## Steps

### Step 0: Verify the PreToolUse matcher name for sub-agent dispatch

**Complexity**: trivial (research gate; no code, no commit)
**Maps to**: AC16, AC17, AC18 (precondition); R1 enforcement
**Why**: The plan assumes `matcher: "Agent"` for the PreToolUse hook. Claude Code's sub-agent dispatch is routed through either `Agent` or `Task` depending on harness version. If we ship the wrong matcher, the hook never fires and R1 collapses to a no-op silently. Verify before writing any of Steps 8/9/15/AC16-18.

**Action**:

1. Inspect `~/.claude/plugins/cache/anthropics/claude-code/**/hooks/*` documentation, or run a transient PreToolUse probe hook that registers under both matchers and prints `$CLAUDE_HOOK_TOOL_NAME` to a temp file when fired; spawn a sub-agent; observe which matcher fires.
2. Record the verified matcher name and the source of truth (doc URL or live transcript) inline in this step.
3. If the matcher is `Task` rather than `Agent`, search-and-replace `matcher: "Agent"` → `matcher: "Task"` and rename `hooks/agent-model-resolve.sh` → `hooks/task-model-resolve.sh` and test files accordingly **before** starting Step 1.

**Exit criterion**: A one-paragraph note appended to this step recording the verified matcher name and the verification method. Without that note, Step 8 cannot begin.

**Files**: None (research step). Output captured inline in this plan file.

**Verification result (2026-06-01)**: Verified `matcher: "Agent"`. Evidence:

1. **Production plugin precedent (primary)**: `~/.claude/plugins/cache/bfinster/agentic-security-assessment/2.1.0/settings.json` and `~/.claude/plugins/cache/bfinster/agentic-security-review/0.1.0/settings.json` both register `PreToolUse` entries with `{"matcher": "Agent", "hooks": [...]}` pointing at `hooks/agent-dispatch-log.sh`. Both plugins ship and run in this user's environment.
2. **Doc coverage (secondary)**: `https://code.claude.com/docs/en/hooks.md` confirms the `PreToolUse` decision-control contract: `hookSpecificOutput.permissionDecision="deny"` with `permissionDecisionReason` (matches AC17). `updatedInput` for input mutation is referenced but the detailed field-level contract was truncated in the fetched page; AC16's `updatedInput` shape follows the PermissionRequest example.
3. **Negative evidence**: No occurrence of `matcher: "Task"` in any installed plugin's settings.json across 5 plugin versions surveyed.

No rename needed. Steps 1–20 proceed as written with `matcher: "Agent"`.

### Step 1: Ship `knowledge/model-routing.json` with defaults

**Complexity**: trivial
**Maps to**: AC1 (precondition), AC2
**RED**: `tests/knowledge/model_routing_defaults.bats` asserts the file exists, parses as JSON, contains exactly the three keys `haiku|sonnet|opus`, and that values match the spec literals (`claude-haiku-4-5-20251001`, `claude-sonnet-4-6`, `claude-opus-4-8`).
**GREEN**: Create `plugins/agentic-dev-team/knowledge/model-routing.json`.
**REFACTOR**: None.
**Files**: `plugins/agentic-dev-team/knowledge/model-routing.json`, `tests/knowledge/model_routing_defaults.bats`
**Commit**: `feat(model-routing): ship knowledge/model-routing.json defaults`

### Step 2: Gitignore the override cache and bump log

**Complexity**: trivial
**Maps to**: AC6
**RED**: `tests/repo/gitignore_overrides.bats` runs `git check-ignore` for both `.claude/model-overrides.json` and `.claude/metrics/model-routing.log` from repo root; both must exit 0.
**GREEN**: Append explicit entries to root `.gitignore` (the existing `.claude/metrics/*.log` glob already covers the log; add an explicit line + comment for grep-ability and rename safety).
**REFACTOR**: None.
**Files**: `.gitignore`, `tests/repo/gitignore_overrides.bats`
**Commit**: `chore: gitignore .claude/model-overrides.json and routing bump log`

### Step 3: Resolver helper — happy path (no override)

**Complexity**: standard
**Maps to**: Background, AC1
**RED**: `tests/hooks/model_resolve_tests.bats`:

- `model-resolve.sh haiku` (no overrides, `MODEL_ROUTING_JSON` pointing at a temp fixture) prints `claude-haiku-4-5-20251001` and exits 0.
- Same for sonnet → `claude-sonnet-4-6`, opus → `claude-opus-4-8`.
- Unknown tier (`gpt`) exits 2 with stderr `Unknown tier 'gpt'. Valid tiers: haiku, sonnet, opus.`.
- No file is created under `.claude/metrics/` on the happy path.

**GREEN**: Create `plugins/agentic-dev-team/hooks/lib/model-resolve.sh`. Env vars (test-only, documented in header comment as such): `MODEL_ROUTING_JSON`, `MODEL_OVERRIDES_JSON`, `MODEL_BUMP_LOG`. Happy-path read via `jq -r ".$TIER"`.
**REFACTOR**: Extract `_resolve_paths` and the test-only env-var header comment.
**Files**: `plugins/agentic-dev-team/hooks/lib/model-resolve.sh`, `tests/hooks/model_resolve_tests.bats`
**Commit**: `feat(model-resolve): happy-path tier→snapshot resolution`

### Step 4: Resolver — single-hop override + bump logging

**Complexity**: standard
**Maps to**: Scenario "Override cache marks haiku as unavailable", AC3
**RED**: Extend bats: overrides `{"tier_aliases":{"haiku":"sonnet"}}`, `model-resolve.sh haiku --caller naming-review` prints `claude-sonnet-4-6` and appends exactly one JSONL line containing `requested="haiku"`, `served="sonnet"`, `reason="override"`, `caller="naming-review"`, and an ISO-8601 `ts` (validated via `date -d` or regex). Bump-log directory is created on demand.
**GREEN**: Merge overrides over defaults via `jq`; emit JSONL via `jq -nc`; `mkdir -p` the log dir; accept `--caller <name>` arg (default empty string).
**REFACTOR**: Extract `_log_bump` function.
**Files**: same as Step 3.
**Commit**: `feat(model-resolve): apply override aliases and log tier bumps`

### Step 5: Resolver — alias chain cascade + cycle detection

**Complexity**: standard
**Maps to**: Scenarios "Cascade resolution", "Cycle detection", AC4, AC5a
**RED**: Two bats cases:

- Overrides `{"tier_aliases":{"haiku":"sonnet","sonnet":"opus"}}`; `model-resolve.sh haiku` prints `claude-opus-4-8`; exactly one bump line with `served="opus"`.
- Overrides `{"tier_aliases":{"haiku":"sonnet","sonnet":"haiku"}}`; `model-resolve.sh haiku` exits 3; stderr starts with `Cycle detected in tier aliases:` and lists `haiku → sonnet → haiku`; no bump logged.

**GREEN**: Walk alias chain up to 3 hops, tracking visited tiers; reject on revisit with the cycle template from the spec.
**REFACTOR**: `_cascade` function; constant `_MAX_HOPS=3` with comment.
**Files**: same as Step 3.
**Commit**: `feat(model-resolve): cascade alias chain with cycle detection`

### Step 6: Resolver — exhaustion, missing routing.json, malformed overrides

**Complexity**: standard
**Maps to**: AC5, AC5b, AC5c, "Opus is the top tier", "knowledge/model-routing.json is missing", "Override file is malformed JSON"
**RED**: Three bats cases:

- Overrides `{"tier_aliases":{"opus":"unavailable"}}`; `model-resolve.sh opus` exits 3; stderr matches the AC5 template (first sentence literal, then absolute paths and the override entry on subsequent lines, then `/model-routing-check`); no bump.
- `MODEL_ROUTING_JSON` points at a non-existent file; `model-resolve.sh haiku` exits 4; stderr starts with `Model routing file missing:` and names `git checkout knowledge/model-routing.json`.
- `MODEL_OVERRIDES_JSON` points at a file containing `{not json`; `model-resolve.sh haiku` exits 5; stderr starts with `Override file is not valid JSON:` and tells the user to delete or fix.

**GREEN**: Implement the three error paths with the exact templates from the spec's §Error templates. Centralise templates as shell heredocs at the top of the helper.
**REFACTOR**: Single `_die <status> <template-name>` function so templates live in one place.
**Files**: same as Step 3.
**Commit**: `feat(model-resolve): exhaustion, missing-file, and malformed-overrides errors`

### Step 7: Resolver — `--dump-map` flag for diagnostic command

**Complexity**: standard
**Maps to**: enables Step 9; AC11b
**RED**: Bats: `model-resolve.sh --dump-map` (no tier arg) prints a three-line tier→snapshot map matching the spec's `/model-routing-check` output template, exits 0, writes no files. With overrides applied, the map reflects them.
**GREEN**: Add the flag; reuse the merged resolver state.
**REFACTOR**: None.
**Files**: same as Step 3.
**Commit**: `feat(model-resolve): --dump-map flag for diagnostic output`

### Step 8: PreToolUse hook — rewrite `tool_input.model`

**Complexity**: complex
**Maps to**: AC16, AC18, R1 resolution
**RED**: `tests/hooks/agent_model_resolve_hook_tests.bats`:

- Hook receives PreToolUse-shaped stdin JSON with `tool_name="Agent"`, `tool_input.model="haiku"`, `tool_input.subagent_type="naming-review"`, in a cwd with overrides mapping haiku→sonnet.
- Hook stdout is JSON matching `{"hookSpecificOutput":{"hookEventName":"PreToolUse","updatedInput":{"model":"claude-sonnet-4-6", ...}}}` (full `tool_input` echoed back with only `model` rewritten).
- Hook exit 0.
- One bump line appended to `.claude/metrics/model-routing.log` with `caller="naming-review"`.
- Second case: same hook with no overrides; stdout is exactly `{}` (empty JSON object, signalling "no change" per the PreToolUse contract); exit 0. No `updatedInput` block; no `permissionDecision` field.
- Third case: non-`Agent` `tool_name` (e.g., `Bash`); hook is a no-op (empty stdout, exit 0).
- Fourth case: `settings.json` PreToolUse block contains an entry with `matcher: "Agent"` invoking `bash hooks/agent-model-resolve.sh`.

**GREEN**: Create `plugins/agentic-dev-team/hooks/agent-model-resolve.sh` following the established hook style (`set -uo pipefail`, fail-open posture, descriptive `[agent-model-resolve]` tag). Parse stdin via `jq`; shell out to `hooks/lib/model-resolve.sh` with the requested tier and `--caller "$subagent_type"`; emit `updatedInput` only when the resolved snapshot differs from a literal pass-through of the original tier alias. Register in `settings.json` PreToolUse.
**REFACTOR**: Comment block in the hook that links to the ADR and the resolver helper.
**Files**: `plugins/agentic-dev-team/hooks/agent-model-resolve.sh`, `plugins/agentic-dev-team/settings.json`, `tests/hooks/agent_model_resolve_hook_tests.bats`
**Commit**: `feat(hooks): PreToolUse Agent hook enforces pre-dispatch resolution`

### Step 9: PreToolUse hook — refusal on resolver exhaustion

**Complexity**: complex
**Maps to**: AC17
**RED**: Extend `agent_model_resolve_hook_tests.bats`: with overrides marking opus unavailable, requested model opus, hook emits `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"<AC5 template body>"}}`; exit 0 (block-by-output per Claude Code hook contract); no Agent dispatch occurs (test verified via shim that records calls). Same for resolver exit 4 (missing routing.json) and exit 5 (malformed overrides) — all three map to `permissionDecision="deny"` with the resolver's stderr as the reason.
**GREEN**: Inspect resolver exit code; on 3/4/5 emit the deny payload with the stderr embedded as `permissionDecisionReason`.
**REFACTOR**: None.
**Files**: `plugins/agentic-dev-team/hooks/agent-model-resolve.sh`, `tests/hooks/agent_model_resolve_hook_tests.bats`
**Commit**: `feat(hooks): refuse Agent dispatch when resolver cannot satisfy tier`

### Step 10: `/model-routing-check` command — clean install + bumps + tail cap

**Complexity**: standard
**Maps to**: Scenarios "Diagnostic on a clean install", "after bumps", "tail cap"; AC10, AC11, AC11a, AC11b
**RED**: `tests/commands/model_routing_check_tests.bats` covering:

- Doc-inspection: `commands/model-routing-check.md` exists with valid frontmatter (`name`, `description`, `user-invocable: true`, `allowed-tools: Read, Bash`); body states "read-only, no side effects"; body contains the four required sections.
- Behavioral clean: no overrides, no log → output matches the template's four sections; `find . -type f | sort | sha256sum` identical before/after.
- Behavioral with bumps: 3 pre-seeded events → all 3 printed in the format `<ts>  <req> → <served>  [<reason>]  caller=<caller>`; exit 0.
- Behavioral tail cap: 25 pre-seeded events; default → last 10 + `Showing last 10 of 25 bump events; raise MODEL_BUMP_TAIL to see more.`; `MODEL_BUMP_TAIL=30` → all 25 + line absent.
- Probe-applicability line: with `ANTHROPIC_BASE_URL` unset → `standard Anthropic endpoint (probe supported)`; with Bedrock URL → `non-Anthropic endpoint (probe skipped)`.

**GREEN**: Create `plugins/agentic-dev-team/commands/model-routing-check.md`. Body uses `bash hooks/lib/model-resolve.sh --dump-map` + a small `tail -n "$N"` + `jq -r` line that formats events into the spec's template. Tail count from `${MODEL_BUMP_TAIL:-10}`.
**REFACTOR**: None.
**Files**: `plugins/agentic-dev-team/commands/model-routing-check.md`, `tests/commands/model_routing_check_tests.bats`
**Commit**: `feat(commands): add /model-routing-check diagnostic`

### Step 11: Probe helper — decline path and fake-bin shim setup

**Complexity**: standard
**Maps to**: Scenario "User declines the probe", AC7; establishes test infrastructure for Steps 12–14
**RED**: `tests/commands/init_dev_team_probe_tests.bats`:

- Doc-inspection: `commands/init-dev-team.md` contains a `## Step N — Probe model availability (opt-in)` section with the **verbatim prompt text** from the spec's §Probe.
- Behavioral: simulate user answering "n"; no `.claude/model-overrides.json` created; `/init-dev-team` exit status matches a golden file captured in `tests/golden/init-dev-team-baseline.exit` (committed by the test setup).
- `tests/hooks/fake-bin/` is populated with a `curl` shim that defaults to "should not be called" (touches a sentinel file the test checks).

**GREEN**: Add the probe step to `init-dev-team.md` with the spec's verbatim prompt. Create `plugins/agentic-dev-team/hooks/lib/model-probe.sh` as a stub that returns 0 immediately when input is "n". Capture and commit the baseline exit-status golden.
**REFACTOR**: None.
**Files**: `plugins/agentic-dev-team/commands/init-dev-team.md`, `plugins/agentic-dev-team/hooks/lib/model-probe.sh`, `tests/commands/init_dev_team_probe_tests.bats`, `tests/golden/init-dev-team-baseline.exit`, `tests/hooks/fake-bin/curl`
**Commit**: `feat(init-dev-team): opt-in probe prompt (decline path) + test infrastructure`

### Step 12: Probe — Anthropic happy path (both branches as separate scenarios)

**Complexity**: standard
**Maps to**: Scenarios "Probe succeeds and all tier snapshots are available", "Probe succeeds but a tier snapshot is missing", AC7a, AC7b
**RED**: Extend bats with fake-bin `curl` returning two distinct fixtures:

- Fixture A: `data[].id` lists all three default snapshots → no overrides written; stderr message is exactly `All model tiers available; no overrides needed.`
- Fixture B: `data[].id` omits the haiku snapshot → `.claude/model-overrides.json` written with `tier_aliases.haiku="sonnet"`, `reason="haiku snapshot not in /v1/models response"`, `available_models` matching fixture B, `generated_at` is parseable ISO-8601; stderr names the bumped tier.

**GREEN**: Implement probe HTTP call (5s timeout, `MODEL_PROBE_TIMEOUT` override), parse with `jq -e`, diff against routing.json, write overrides only when diff non-empty.
**REFACTOR**: Extract `_diff_against_routing` and `_write_overrides` functions.
**Files**: `plugins/agentic-dev-team/hooks/lib/model-probe.sh`, `tests/commands/init_dev_team_probe_tests.bats`, `tests/hooks/fake-bin/curl` fixtures
**Commit**: `feat(model-probe): /v1/models probe and conditional overrides write`

### Step 13: Probe — non-Anthropic base URL gating

**Complexity**: standard
**Maps to**: Scenario "Probe skipped on non-Anthropic base URL", AC8
**RED**: Bats: `ANTHROPIC_BASE_URL=https://bedrock-runtime.us-east-1.amazonaws.com`, accept probe; fake-bin `curl` sentinel is **not** touched; stderr contains `Probe skipped:` naming the host and referencing `docs/model-routing.md`; no overrides written. Repeat for `https://aiplatform.googleapis.com`.
**GREEN**: Host allowlist check: proceed only when base URL host is unset, `api.anthropic.com`, or matches `*.anthropic.com`. Use `_host_from_url` helper.
**REFACTOR**: None.
**Files**: `plugins/agentic-dev-team/hooks/lib/model-probe.sh`, `tests/commands/init_dev_team_probe_tests.bats`
**Commit**: `feat(model-probe): skip /v1/models on Bedrock/Vertex/non-Anthropic hosts`

### Step 14: Probe — three differentiated failure modes

**Complexity**: standard
**Maps to**: Scenario Outline "Probe HTTP call fails", AC9
**RED**: Bats parameterised over three fake-bin `curl` setups:

- `curl` exits 28 → stderr starts with `Probe timed out after 5s:` and ends with `Dispatch fallback still applies; see docs/model-routing.md.`
- `curl` returns HTTP 500 → stderr starts with `Probe endpoint returned HTTP 500:` and same ending.
- `curl` returns HTTP 200 with invalid JSON → stderr starts with `Probe response was not valid JSON:` and same ending.

For all three: no overrides written; `/init-dev-team` exit status matches the golden file from Step 11.

**GREEN**: Wrap probe in three guarded blocks: `curl --fail --max-time` exit-code check, HTTP status parse, `jq -e` JSON parse. Each path emits a distinct prefixed message.
**REFACTOR**: Single `_probe_failed <prefix> <details>` function.
**Files**: `plugins/agentic-dev-team/hooks/lib/model-probe.sh`, `tests/commands/init_dev_team_probe_tests.bats`
**Commit**: `feat(model-probe): differentiated messages for timeout, 5xx, malformed JSON`

### Step 15: Orchestrator + CLAUDE.md — replace static routing tables with resolver pointer

**Complexity**: complex
**Maps to**: AC2, AC14, AC18 (cross-reference); covers the full surface in `agents/orchestrator.md`
**RED**: `tests/agents/orchestrator_routing_doc_tests.bats`:

- `agents/orchestrator.md` no longer contains a heading `## Model Routing Table`.
- It DOES contain `## Resolution Procedure` which names `hooks/agent-model-resolve.sh`, `hooks/lib/model-resolve.sh`, `knowledge/model-routing.json`, and `.claude/model-overrides.json`.
- Downstream tier-bearing tables in the same file (currently at lines ~105-108 plan-review personas, ~147 complexity, ~159-169 file-type → reviewer per the design reviewer's audit) either: (a) remove tier columns, or (b) reference the resolver. Test asserts no table row in this file contains a bare `haiku|sonnet|opus` cell in a "model" column.
- `CLAUDE.md` `## Model Routing` section reduced to a one-paragraph pointer to the resolver hook + helper + docs.
- `CLAUDE.md` Slash Commands Registry table contains a row for `/model-routing-check`.
- `/agent-audit` exits 0 against `agents/orchestrator.md`.

**GREEN**: Rewrite the orchestrator's routing surface as a `## Resolution Procedure` section citing the hook, helper, and docs. Refactor the plan-review-personas, complexity, and file-type-reviewer tables to reference the resolver or drop the tier column. Update CLAUDE.md.
**REFACTOR**: Cross-link to `docs/model-routing.md` and the ADR.
**Files**: `plugins/agentic-dev-team/agents/orchestrator.md`, `plugins/agentic-dev-team/CLAUDE.md`, `tests/agents/orchestrator_routing_doc_tests.bats`
**Commit**: `refactor(orchestrator): replace static routing tables with resolver pointer`

### Step 16: Snapshot-ID audit — purge stragglers

**Complexity**: standard
**Maps to**: AC2
**RED**: `tests/repo/no_pinned_snapshots_test.bats`:

- Primary check: `git grep -nE 'claude-(haiku|sonnet|opus)-[0-9]'` from repo root returns matches only in the three approved files.
- Secondary check: in the orchestrator file specifically, no table cell contains a bare `(haiku)`, `(sonnet)`, or `(opus)` tier mention in a column whose header is "Model" or "Tier".

**GREEN**: Rewrite `templates/agents/agent-template.md:32` to point at routing.json. Rewrite `skills/performance-metrics/SKILL.md:79` (`claude-opus-4-6` → tier-alias example). Sweep any other matches the test surfaces.
**REFACTOR**: None.
**Files**: `plugins/agentic-dev-team/templates/agents/agent-template.md`, `plugins/agentic-dev-team/skills/performance-metrics/SKILL.md`, `tests/repo/no_pinned_snapshots_test.bats`
**Commit**: `chore: remove pinned snapshot IDs outside routing.json`

### Step 17: Bump discoverability banner — SessionStart hook

**Complexity**: standard
**Maps to**: AC19, Scenario "Active overrides surface a one-line session note"
**Why a hook**: Markdown slash commands are prompts to Claude, not shell scripts — they cannot deterministically emit a literal terminal line. The same enforcement-by-instruction failure that R1 rejected for dispatch resolution applies here. A `SessionStart` hook (Claude Code's session-lifecycle hook) writes to stderr and is guaranteed to fire once per session, regardless of which slash command the user runs.
**RED**: `tests/hooks/overrides_banner_tests.bats`:

- With `.claude/model-overrides.json` present in cwd, `bash hooks/overrides-banner.sh` (driven by a SessionStart-shaped stdin JSON per the Claude Code contract) prints the literal line `Note: model routing overrides active — run /model-routing-check to review.` to stderr; exit 0.
- With no overrides file, same hook invocation prints nothing; exit 0.
- `plugins/agentic-dev-team/settings.json` `SessionStart` block contains an entry invoking `bash hooks/overrides-banner.sh`.

**GREEN**: Create `plugins/agentic-dev-team/hooks/overrides-banner.sh` following the established hook style (`set -uo pipefail`, fail-open, `[overrides-banner]` tag); register in `settings.json` under `SessionStart`.
**REFACTOR**: None.
**Files**: `plugins/agentic-dev-team/hooks/overrides-banner.sh`, `plugins/agentic-dev-team/settings.json`, `tests/hooks/overrides_banner_tests.bats`
**Commit**: `feat(ux): SessionStart hook surfaces routing overrides banner`

### Step 18: Performance gate

**Complexity**: standard
**Maps to**: AC15
**RED**: `tests/hooks/model_resolve_perf_tests.bats`: 1000 sequential `model-resolve.sh haiku` invocations on a clean install complete in < 5s wall-clock (measured via `time`). Test is gated by `MODEL_RESOLVE_PERF=1` so CI can run it on demand only — local runs skip by default to keep the suite fast.
**GREEN**: Profile and trim. Each invocation is a separate bash process, so cross-invocation caching is not viable; the optimisation lever is **per-invocation jq minimisation** — collapse multiple `jq` calls (defaults read, override merge, alias-chain walk) into a single `jq` pipeline that returns the resolved snapshot in one process. If even that's not enough, accept the limit and document the achievable p99 in `docs/model-routing.md`.
**REFACTOR**: None.
**Files**: `plugins/agentic-dev-team/hooks/lib/model-resolve.sh`, `tests/hooks/model_resolve_perf_tests.bats`
**Commit**: `feat(model-resolve): performance gate (1000 invocations < 5s)`

### Step 19: ADR — pre-dispatch resolution + hook enforcement decisions

**Complexity**: standard
**Maps to**: AC13
**RED**: `tests/docs/adr_pre_dispatch_resolution_test.bats`: file matching `docs/adr/00*-pre-dispatch-resolution.md` exists; contains Context, Decision, Consequences sections; Decision section explicitly rejects runtime `model_not_available` retry citing "harness owns the dispatch surface"; Decision section also records the choice of PreToolUse hook over orchestrator instruction citing enforceability; file is referenced from `docs/model-routing.md`.
**GREEN**: Invoke the project's `adr-tools` skill to scaffold the ADR; populate with the two decisions and rationale.
**REFACTOR**: None.
**Files**: `docs/adr/00NN-pre-dispatch-resolution.md`, `tests/docs/adr_pre_dispatch_resolution_test.bats`
**Commit**: `docs(adr): pre-dispatch resolution and hook enforcement decisions`

### Step 20: Documentation — `docs/model-routing.md`

**Complexity**: standard
**Maps to**: AC12
**RED**: `tests/docs/model_routing_doc_test.bats` asserts H2 sections matching the eight names in AC12 each contain at least one paragraph; file links to the ADR; file documents the test-only env vars as test-only and the user-facing env vars (`ANTHROPIC_BASE_URL`, `MODEL_PROBE_TIMEOUT`, `MODEL_BUMP_TAIL`) as supported.
**GREEN**: Write the doc covering: contract (tier → snapshot via routing.json + overrides + hook), when fallback fires, interpreting the override file, adding a new tier, troubleshooting (Bedrock, Vertex, corporate proxy), hand-writing the override file.
**REFACTOR**: None.
**Files**: `plugins/agentic-dev-team/docs/model-routing.md`, `tests/docs/model_routing_doc_test.bats`
**Commit**: `docs: model routing contract and troubleshooting guide`

## Complexity Classification

| Step | Rating | Why |
|---|---|---|
| 1, 2 | trivial | Config files + gitignore |
| 3–7 | standard | Resolver helper + bats; bounded surface |
| 8, 9 | complex | New PreToolUse enforcement hook; cross-cutting; touches `settings.json` |
| 10 | standard | Diagnostic command + bats |
| 11–14 | standard | Probe + bats; fake-bin shim pattern |
| 15 | complex | Rewrites authoritative routing documentation across multiple tables in `orchestrator.md` + `CLAUDE.md` |
| 16 | standard | Mechanical sweep guarded by grep tests |
| 17 | standard | Small UX surface across two commands |
| 18 | standard | Perf gate, opt-in |
| 19, 20 | standard | Documentation + ADR + audit |

## Pre-PR Quality Gate

- [ ] All bats suites pass: `tests/hooks/`, `tests/commands/`, `tests/agents/`, `tests/docs/`, `tests/repo/`, `tests/knowledge/`
- [ ] Opt-in: `MODEL_RESOLVE_PERF=1 bats tests/hooks/model_resolve_perf_tests.bats` passes
- [ ] `git grep -nE 'claude-(haiku|sonnet|opus)-[0-9]'` returns only the three approved files
- [ ] `/agent-audit` clean
- [ ] `/code-review` clean (no error/warning severity findings) — this is a gate, not a TDD step
- [ ] Manual smoke: `bash plugins/agentic-dev-team/hooks/lib/model-resolve.sh haiku` returns the haiku snapshot on a fresh checkout
- [ ] Manual smoke: with a hand-written `.claude/model-overrides.json` mapping haiku→sonnet, the resolver returns `claude-sonnet-4-6` AND `.claude/metrics/model-routing.log` shows the bump
- [ ] Manual smoke: `/model-routing-check` output renders all four sections cleanly in the terminal
- [ ] Manual smoke: drop in an overrides file and verify the banner appears on `/version`
- [ ] `docs/model-routing.md` rendered preview reviewed for broken links and section completeness
- [ ] PR description references issue #37 and links the ADR

## Out of Scope (v1)

Inherited from spec §Out of Scope. Implementers must not expand this slice to include any of these:

- Multi-region Anthropic endpoint auto-detection
- Override file UI / interactive editor
- Per-agent model overrides beyond `model:` frontmatter
- Telemetry beyond the bump log
- Runtime `model_not_available` retry (harness owns dispatch)
- Wiring PostToolUse review hooks (`js-fp-review.sh`, `token-efficiency-review.sh`) through the resolver — these scripts do not spawn agents
- Documenting test-only env vars as user-facing config

## Risks & Open Questions

- **R1 (RESOLVED)** — Enforcement moved to a PreToolUse hook on the `Agent` matcher (Steps 8–9). The LLM cannot bypass it. The orchestrator markdown becomes documentation only.
- **R2 — Probe latency.** 5s timeout per probe attempt could feel slow on flaky networks. Documented via `MODEL_PROBE_TIMEOUT` env var.
- **R3 — Anthropic-shape proxies behind custom hostnames.** The host allowlist will under-probe corporate proxies that *do* speak the Anthropic API but are not on `*.anthropic.com`. Mitigation: `docs/model-routing.md` documents `MODEL_PROBE_FORCE=1` for those users (env var in scope; documentation in scope; default-skip behavior unchanged).
- **R4 — Banner rollout across all slash commands.** Step 17 covers `/model-routing-check` and `/version` only. Extending to every command is a low-risk follow-on; tracked in the PR description and not blocking this slice.
- **R5 (REMOVED)** — Mis-stated in the prior draft. PostToolUse review hooks are static grep scripts, not agent spawners.

---

## Plan Review Summary

Two passes of plan-review personas (Acceptance, Design, UX, Strategic).

**Pass 1**: 4/4 needs-revision. Major blockers: enforcement-by-orchestrator-instruction (R1), missing scenarios for cycle/missing/malformed routing.json, undefined error/prompt/output templates, probe scope question. All resolved in the revised plan and spec.

**Pass 2**: 3/4 approve (Acceptance, UX, Strategic). Design returned needs-revision; the two design blockers were addressed in this revision:

- **PreToolUse matcher name verification** — Added Step 0 as a non-negotiable research gate: verify whether the sub-agent dispatch tool is `Agent` or `Task` before Steps 8/9 begin. Search-and-replace path documented if `Task` turns out to be correct.
- **Banner mechanism unsound** — Step 17 rewritten to use a `SessionStart` hook (`hooks/overrides-banner.sh`) instead of markdown command bodies. Spec §Bump discoverability and AC19 updated to match.

Mechanical pass-2 fixes folded in:

- AC4 cascade-bump-count clarified: one event per resolver invocation, recording originally-requested and final-served tier; intermediate hops do not log separately.
- AC7b given a literal success message: `Model tier 'haiku' bumped to 'sonnet'; .claude/model-overrides.json written.`
- Step 8 pass-through case pinned to exactly `{}` on stdout — removed the "or no `updatedInput` block" ambiguity.
- `MODEL_PROBE_CURL` removed from spec §Out of Scope; the shim no longer exists.
- `MODEL_PROBE_FORCE=1` explicitly scoped: recognised by the probe helper, documented in AC12, no dedicated bats case (documented-but-untested for corporate-proxy users opting in).
- Step 18 GREEN rewritten: cross-invocation caching impossible (separate processes); optimisation lever is per-invocation jq minimisation.

Outstanding non-blocking warnings (acknowledged, not addressed):

- AC18 test placement (config-file assertion sitting inside a behavioural bats suite) — cosmetic.
- R4 about per-command banner rollout is now moot — the SessionStart hook supersedes per-command instrumentation.
- `--dump-map` as a flag on `model-resolve.sh` is mild responsibility creep; sibling helper deferred to a future refactor.
- Bump-log JSONL schema worth promoting to a one-paragraph subsection in `docs/model-routing.md` — captured as part of Step 20's H2 coverage.

**Status**: ready for human approval.
