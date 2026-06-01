# Spec: Environment-Aware Model Routing with Fallback

Source: [issue #37](https://github.com/bdfinst/agentic-dev-team/issues/37)

## Intent Description

The plugin currently pins tier aliases (`haiku`, `sonnet`, `opus`) in agent
frontmatter, in the orchestrator's routing table, and in CLAUDE.md prose. The
Claude Code harness resolves each alias to a fixed snapshot ID such as
`claude-haiku-4-5-20251001`. This works on a personal Anthropic API key but
fails for two real populations: users whose corporate proxy exposes only a
subset of models, and users whose pinned snapshot has been retired by
Anthropic. In both cases dispatch fails opaquely and the user loses work.

This change moves all tier-to-snapshot resolution into a single shipped file
(`knowledge/model-routing.json`) and gives the orchestrator a **pre-dispatch
resolution step** that consults an optional per-user override cache
(`.claude/model-overrides.json`) and walks haiku→sonnet→opus *before* invoking
the harness Agent tool — never relying on catching a runtime
`model_not_available`. A new opt-in probe inside `/init-dev-team` populates
the override cache when the user is behind a restricted endpoint; a new
read-only `/model-routing-check` command surfaces the resolved state and
recent tier bumps for triage.

The unifying principle: same plugin code works on personal Anthropic keys,
restricted corporate proxies, and Bedrock/Vertex deployments, with zero
environment-specific config checked into the repo.

## User-Facing Behavior

```gherkin
Feature: Environment-aware model routing

  Background:
    Given the plugin ships knowledge/model-routing.json with defaults
      | tier   | snapshot                       |
      | haiku  | claude-haiku-4-5-20251001      |
      | sonnet | claude-sonnet-4-6              |
      | opus   | claude-opus-4-8                |

  # --- Zero-config personal API key ---

  Scenario: Personal API key with all tiers available
    Given no .claude/model-overrides.json exists
    And ANTHROPIC_BASE_URL is unset or api.anthropic.com
    When the orchestrator dispatches an agent that requests tier "haiku"
    Then the harness Agent tool is called with model "claude-haiku-4-5-20251001"
    And no tier-bump event is logged
    And no error or warning is surfaced to the user

  # --- Pre-dispatch resolution with override cache ---

  Scenario: Override cache marks haiku as unavailable
    Given .claude/model-overrides.json contains
      """
      { "tier_aliases": { "haiku": "sonnet" } }
      """
    When the orchestrator dispatches an agent that requests tier "haiku"
    Then the orchestrator resolves the requested tier to "sonnet" before dispatch
    And the harness Agent tool is called with model "claude-sonnet-4-6"
    And a tier-bump event is appended to .claude/metrics/model-routing.log
    And the event records requested="haiku", served="sonnet", reason="override"

  Scenario: Cascade resolution when both haiku and sonnet are unavailable
    Given .claude/model-overrides.json contains
      """
      { "tier_aliases": { "haiku": "opus", "sonnet": "opus" } }
      """
    When the orchestrator dispatches an agent that requests tier "haiku"
    Then the harness Agent tool is called with model "claude-opus-4-8"
    And a tier-bump event is logged with served="opus"

  Scenario: Opus is the top tier and cannot be bumped further
    Given .claude/model-overrides.json contains
      """
      { "tier_aliases": { "opus": "unavailable" } }
      """
    When the orchestrator dispatches an agent that requests tier "opus"
    Then the resolver exits with status 3
    And no Agent tool call is made
    And stderr contains the literal path to knowledge/model-routing.json
    And stderr contains the override entry `"opus": "unavailable"`
    And stderr names the command `/model-routing-check`
    And stderr opens with the sentence "All model tiers exhausted for requested tier 'opus'."

  Scenario: Cycle detection in override aliases
    Given .claude/model-overrides.json contains
      """
      { "tier_aliases": { "haiku": "sonnet", "sonnet": "haiku" } }
      """
    When the orchestrator dispatches an agent that requests tier "haiku"
    Then the resolver exits with status 3
    And stderr opens with "Cycle detected in tier aliases:"
    And stderr lists the visited tiers in order
    And no Agent tool call is made
    And no bump event is logged

  Scenario: knowledge/model-routing.json is missing
    Given knowledge/model-routing.json has been deleted
    When the resolver is invoked with any tier
    Then the resolver exits with status 4
    And stderr opens with "Model routing file missing:"
    And stderr names the expected path and the remediation `git checkout knowledge/model-routing.json`
    And no Agent tool call is made

  Scenario: Override file is malformed JSON
    Given .claude/model-overrides.json contains invalid JSON
    When the resolver is invoked with any tier
    Then the resolver exits with status 5
    And stderr opens with "Override file is not valid JSON:"
    And stderr names the override file path and instructs the user to delete or regenerate it
    And no Agent tool call is made

  # --- Probe step in /init-dev-team ---

  Scenario: User declines the probe
    When the user runs /init-dev-team
    And the probe prompt is shown
    And the user answers "n"
    Then no .claude/model-overrides.json is written
    And dispatch behavior is unchanged

  Scenario: Probe succeeds and all tier snapshots are available
    Given ANTHROPIC_BASE_URL is unset
    And the user runs /init-dev-team and accepts the probe with "y"
    When the probe receives an HTTP 200 listing all three default snapshot IDs
    Then no .claude/model-overrides.json is written
    And the user sees the message "All model tiers available; no overrides needed."

  Scenario: Probe succeeds but a tier snapshot is missing
    Given ANTHROPIC_BASE_URL is unset
    And the user runs /init-dev-team and accepts the probe with "y"
    When the probe receives an HTTP 200 omitting the haiku snapshot
    Then .claude/model-overrides.json is written with `tier_aliases.haiku = "sonnet"`
    And the file's `reason` field is "haiku snapshot not in /v1/models response"
    And the file's `available_models` field matches the IDs returned by the endpoint
    And the user sees the message "Model tier 'haiku' bumped to 'sonnet'; .claude/model-overrides.json written."

  Scenario: Probe skipped on non-Anthropic base URL
    Given ANTHROPIC_BASE_URL is "https://bedrock-runtime.us-east-1.amazonaws.com"
    And the user accepts the probe with "y"
    When the probe runs
    Then no HTTP request is issued
    And the user sees "Probe skipped: <host> is not a supported Anthropic endpoint."
    And the message references docs/model-routing.md for Bedrock/Vertex setup
    And no .claude/model-overrides.json is written

  Scenario Outline: Probe HTTP call fails
    Given the user has accepted the probe on a supported Anthropic endpoint
    When the probe call fails with "<failure>"
    Then no .claude/model-overrides.json is written
    And the user-visible message starts with "<message_prefix>"
    And the message ends with "Dispatch fallback still applies; see docs/model-routing.md."
    And /init-dev-team exit status is unchanged

    Examples:
      | failure                          | message_prefix                                |
      | curl timeout (exit 28)           | Probe timed out after 5s:                     |
      | HTTP 500                         | Probe endpoint returned HTTP 500:             |
      | HTTP 200 with malformed JSON     | Probe response was not valid JSON:            |

  # --- /model-routing-check diagnostic ---

  Scenario: Diagnostic on a clean install
    Given no override file exists and no bump log exists
    When the user runs /model-routing-check
    Then the output lists the three default tier→snapshot pairs from routing.json
    And the output includes the line "Overrides: none"
    And the output includes the line "Recent tier bumps: none recorded"
    And the output includes the line "Probe applicability: standard Anthropic endpoint (probe supported)"
    And no files are written or modified

  Scenario: Diagnostic after bumps have occurred
    Given .claude/metrics/model-routing.log contains 3 bump events
    When the user runs /model-routing-check
    Then the output lists all 3 bump events
    And each line follows the format "<ts>  <requested> → <served>  [<reason>]  caller=<caller>"
    And the command exits 0

  Scenario: Diagnostic caps the bump tail at 10
    Given .claude/metrics/model-routing.log contains 25 bump events
    When the user runs /model-routing-check with MODEL_BUMP_TAIL unset
    Then exactly the last 10 events are printed
    And the output includes the line "Showing last 10 of 25 bump events; raise MODEL_BUMP_TAIL to see more."

  Scenario: Active overrides surface a one-line session note
    Given .claude/model-overrides.json exists with at least one tier alias
    When a Claude Code session starts and the SessionStart hook fires
    Then hooks/overrides-banner.sh prints to stderr the single line "Note: model routing overrides active — run /model-routing-check to review."
    And exits 0
    And when no override file exists the same hook prints nothing and exits 0

  # --- Migration / no leaks ---

  Scenario: No pinned snapshot IDs remain outside routing.json
    When a static check greps the plugin source for "claude-(haiku|sonnet|opus)-[0-9]"
    Then the only matches are inside knowledge/model-routing.json,
      docs/model-routing.md (illustrative),
      and templates/agents/agent-template.md (commented documentation)

  Scenario: Override file does not leak into git
    Given .claude/model-overrides.json has been generated locally
    When the user runs `git status --ignored`
    Then .claude/model-overrides.json is listed as ignored
```

## Architecture Specification

### Components changed or added

| File | Status | Purpose |
|---|---|---|
| `plugins/agentic-dev-team/knowledge/model-routing.json` | NEW | Single source of truth: tier → snapshot map |
| `plugins/agentic-dev-team/hooks/lib/model-resolve.sh` | NEW | Reusable resolver helper invoked by the PreToolUse hook and the diagnostic command |
| `plugins/agentic-dev-team/hooks/lib/model-probe.sh` | NEW | Probe helper (curl + jq) invoked by `/init-dev-team` |
| `plugins/agentic-dev-team/hooks/agent-model-resolve.sh` | NEW | PreToolUse hook on the `Agent` matcher; rewrites `tool_input.model` via the resolver |
| `plugins/agentic-dev-team/settings.json` | MODIFIED | Registers the PreToolUse `Agent` hook |
| `plugins/agentic-dev-team/agents/orchestrator.md` | MODIFIED | Replaces the static Model Routing Table with a "Resolution Procedure" section that documents the hook + helper; downstream tier-bearing tables (plan-review personas, complexity, file-type → reviewer) are refactored to reference the resolver |
| `plugins/agentic-dev-team/CLAUDE.md` | MODIFIED | Replaces inline Model Routing table with a pointer to routing.json and the resolution procedure; adds `/model-routing-check` to the Slash Commands Registry |
| `plugins/agentic-dev-team/commands/init-dev-team.md` | MODIFIED | Adds an opt-in probe sub-step (see §Probe) |
| `plugins/agentic-dev-team/commands/model-routing-check.md` | NEW | Diagnostic-only slash command |
| `plugins/agentic-dev-team/docs/model-routing.md` | NEW | Contract + Bedrock/Vertex/proxy troubleshooting |
| `.gitignore` (repo root) | MODIFIED | Adds `.claude/model-overrides.json` |
| `plugins/agentic-dev-team/agents/*.md` | MODIFIED | `model:` frontmatter stays as a tier alias; no snapshot IDs |
| `plugins/agentic-dev-team/templates/agents/agent-template.md` | MODIFIED | Comment block updated to point at routing.json instead of listing snapshot IDs inline |
| `plugins/agentic-dev-team/skills/performance-metrics/SKILL.md` | MODIFIED | Replaces pinned `claude-opus-4-6` example with a tier-alias example |
| `docs/adr/00NN-pre-dispatch-resolution.md` | NEW | ADR recording (a) pre-dispatch vs. runtime retry and (b) PreToolUse hook vs. orchestrator-instruction enforcement |
| `tests/hooks/model_resolve_tests.bats` | NEW | Bats coverage for resolver helper (happy path, override, cascade, cycle, exhausted, missing routing.json, malformed overrides) |
| `tests/hooks/agent_model_resolve_hook_tests.bats` | NEW | Bats coverage for the PreToolUse hook (model rewrite, pass-through, refusal-on-exhaustion) |
| `tests/commands/model_routing_check_tests.bats` | NEW | Bats coverage for the diagnostic command (clean, with bumps, >10 cap, probe-applicability line) |
| `tests/commands/init_dev_team_probe_tests.bats` | NEW | Bats coverage for probe (decline, accept-happy, accept-missing-tier, non-Anthropic skip, three failure modes) |
| `tests/repo/no_pinned_snapshots_test.bats` | NEW | Enforces AC2 across the tree |
| `tests/repo/gitignore_overrides.bats` | NEW | Enforces AC6 |
| `tests/knowledge/model_routing_defaults.bats` | NEW | Enforces routing.json shape and default values |
| `tests/docs/adr_pre_dispatch_resolution_test.bats` | NEW | Enforces ADR existence and section coverage |
| `tests/docs/model_routing_doc_test.bats` | NEW | Enforces docs section coverage |

### Interfaces

**`knowledge/model-routing.json` (shipped)**:

```json
{
  "haiku":  "claude-haiku-4-5-20251001",
  "sonnet": "claude-sonnet-4-6",
  "opus":   "claude-opus-4-8"
}
```

**`.claude/model-overrides.json` (per-user, gitignored, never edited by hand)**:

```json
{
  "tier_aliases":      { "haiku": "sonnet" },
  "generated_at":      "<iso8601>",
  "available_models":  ["claude-sonnet-4-6", "claude-opus-4-8"],
  "reason":            "haiku snapshot not in /v1/models response"
}
```

**`.claude/metrics/model-routing.log` (per-user, gitignored, append-only JSONL)**:

```json
{"ts":"<iso8601>","requested":"haiku","served":"sonnet","reason":"override","caller":"naming-review"}
```

### Pre-dispatch resolution procedure (enforced by PreToolUse hook)

Resolution is enforced by `hooks/agent-model-resolve.sh`, registered in `settings.json` under `PreToolUse` with `matcher: "Agent"`. The hook reads `tool_input.model`, invokes `hooks/lib/model-resolve.sh`, and writes the resolved snapshot back via `hookSpecificOutput.updatedInput` (Claude Code PreToolUse contract). The LLM cannot bypass it.

Resolution algorithm (implemented in `hooks/lib/model-resolve.sh`):

1. Read `knowledge/model-routing.json` (required; missing → exit 4 with remediation).
2. Read `.claude/model-overrides.json` if present; on malformed JSON exit 5 with remediation; otherwise merge `tier_aliases` over defaults.
3. For the requested tier T, follow the alias chain up to 3 hops:
   - Track visited tiers; on revisit exit 3 with "Cycle detected in tier aliases:" naming the chain.
   - If the chain terminates at a known tier with a snapshot, print the snapshot on stdout.
   - If the chain terminates at the sentinel `"unavailable"` or at a tier with no snapshot, exit 3 with the actionable error template (see §Error templates).
4. On any bump (originally-requested tier ≠ final served tier), append **exactly one** JSONL event per resolver invocation to `.claude/metrics/model-routing.log`. Intermediate hops in a multi-hop alias chain do not log separately — the event records the originally-requested tier and the final served tier only.

**Sentinel values for `tier_aliases` targets**: another tier name (`"haiku"|"sonnet"|"opus"`) or the literal string `"unavailable"`. Any other value is rejected by the probe and is invalid hand-written input.

**Caller attribution**: the PreToolUse hook reads `tool_input.subagent_type` (when present) and passes it to the resolver as `--caller`. The bump-log `caller` field is derived deterministically.

**Performance**: resolver caches the routing.json read in process; total resolver cost per dispatch is two `jq` invocations on small files. AC15 is verified with a `time` harness around 1000 sequential invocations (see Test Strategy).

This is **pre-dispatch resolution only**. The plugin does not attempt to catch `model_not_available` at runtime — the harness owns dispatch and that error surface is not reachable from plugin code. The ADR records both decisions: (a) pre-dispatch vs. runtime retry, (b) PreToolUse hook vs. orchestrator instruction.

### Error templates

All resolver/hook errors emit a single stderr block with a leading sentence (machine-checkable in bats), context lines, and a remediation line.

```
All model tiers exhausted for requested tier 'opus'.
  Routing defaults: <abs path to knowledge/model-routing.json>
  Override entry:   "opus": "unavailable"   (from <abs path to .claude/model-overrides.json>)
  Run /model-routing-check to inspect resolved state and recent bumps.
```

```
Cycle detected in tier aliases: haiku → sonnet → haiku
  Override file:    <abs path>
  Edit the file to remove the cycle, or delete it to restore defaults.
  Run /model-routing-check after editing.
```

```
Model routing file missing: <expected abs path>
  This file ships with the plugin and must be present.
  Restore with: git checkout knowledge/model-routing.json
```

```
Override file is not valid JSON: <abs path>
  Delete the file to restore default routing, or fix the JSON and re-run.
  Run /model-routing-check after editing.
```

### Bump discoverability

When `.claude/model-overrides.json` exists at session start, a Claude Code `SessionStart` hook (`hooks/overrides-banner.sh`) emits the one-line note `Note: model routing overrides active — run /model-routing-check to review.` to stderr. The hook fires once per session, regardless of which slash command the user runs — markdown command bodies cannot deterministically emit terminal output, so enforcement lives in the hook layer. When no overrides file is present, the hook emits nothing. Bumps themselves remain silent (per AC1's zero-warning rule on clean installs).

### Probe (opt-in, `/init-dev-team` sub-step)

- Runs only when the user explicitly answers "y" to the probe prompt.

**Prompt text (verbatim)**:

```
Probe Anthropic's model list to detect which tiers are available?

  What this does:    one GET request to $ANTHROPIC_BASE_URL/v1/models (5s timeout)
  What it writes:    .claude/model-overrides.json (only if a default tier is missing)
  What it skips:     Bedrock, Vertex, or non-Anthropic proxies (auto-detected)
  Default is "n":    the resolver works without probing; this just makes the
                     first dispatch faster for restricted endpoints.

Probe model availability? [y/N]
```

- Skipped automatically when `ANTHROPIC_BASE_URL` is set to a host that is not `api.anthropic.com` or `*.anthropic.com` (Bedrock, Vertex, custom proxy that doesn't speak the `/v1/models` shape).
- Issues `GET $ANTHROPIC_BASE_URL/v1/models` with a 5s timeout (`MODEL_PROBE_TIMEOUT` override for slow networks).
- On 200: diffs returned IDs against routing.json's snapshots; writes overrides only if at least one tier needs bumping.
- On any non-success (timeout, 5xx, malformed JSON): writes nothing; emits a failure-mode-specific message (see User-Facing Behavior); `/init-dev-team` exit status unchanged.

### Test shim contract

Probe tests use the established `tests/hooks/fake-bin` PATH-override pattern. A `fake-bin/curl` script is placed on `PATH` to deterministically return the fixture for each scenario. This matches existing bats infrastructure rather than introducing a new env-var-holds-a-shell-command shim.

### `/model-routing-check`

- Read-only. Touches no files. Exits 0 regardless of whether bumps are present.
- Four sections, in order: (a) effective tier→snapshot map (defaults + overrides), (b) override file presence + contents, (c) last N=10 bump events (oldest first), (d) probe applicability (base URL + whether probe shape applies).
- Default N=10; `MODEL_BUMP_TAIL` env var raises the cap.

**Output template (verbatim)**:

```
Model Routing Check
===================

Effective tier → snapshot map:
  haiku   → <snapshot>
  sonnet  → <snapshot>
  opus    → <snapshot>

Overrides: <none | from .claude/model-overrides.json>
  <key: value lines when present>

Recent tier bumps: <none recorded | N events>
  <ts>  <requested> → <served>  [<reason>]  caller=<caller>
  ...
  [Showing last 10 of N bump events; raise MODEL_BUMP_TAIL to see more.]

Probe applicability: <message>
  ANTHROPIC_BASE_URL=<value or "unset">
```

### Constraints

- **No pinned snapshot IDs outside `knowledge/model-routing.json`.** Enforced by a grep audit step in the plan; documentation references inside `docs/model-routing.md` and a single illustrative comment in `templates/agents/agent-template.md` are the only exceptions.
- **No corporate config in the repo.** `.claude/model-overrides.json` is gitignored; no proxy URLs or allowlists ever ship.
- **Plugin code never edits user state without consent.** Overrides written only by the probe or by the user.
- **Backward compatible with current agents.** Existing `model: haiku|sonnet|opus` frontmatter continues to work unchanged.

### Dependencies

- Existing `.claude/metrics/` directory convention (already gitignored).
- `jq` (already a hard dep via `/init-dev-team`) for JSON read/write in any shell helpers.
- `curl` for the probe (assumed present on macOS/Linux/Git Bash).

## Acceptance Criteria

| # | Criterion | Pass condition |
|---|---|---|
| AC1 | Zero-config baseline | Fresh install with no `.claude/model-overrides.json`: full bats suite passes; resolver hook emits nothing on stderr; no files created under `.claude/metrics/` during dispatch |
| AC2 | Single source of truth | `git grep -nE 'claude-(haiku\|sonnet\|opus)-[0-9]'` from repo root returns matches only in `plugins/agentic-dev-team/knowledge/model-routing.json`, `plugins/agentic-dev-team/docs/model-routing.md`, and `plugins/agentic-dev-team/templates/agents/agent-template.md` |
| AC3 | Pre-dispatch resolution | Bats: overrides map haiku→sonnet; `model-resolve.sh haiku` prints `claude-sonnet-4-6` (exit 0) and appends a JSONL line with `requested="haiku"`, `served="sonnet"`, `reason="override"` |
| AC4 | Cascade | Bats: overrides map haiku→sonnet and sonnet→opus; `model-resolve.sh haiku` follows the chain and prints `claude-opus-4-8`; exactly one bump event written with `served="opus"` |
| AC5 | Top-tier-fails actionable | Bats: overrides map opus→"unavailable"; `model-resolve.sh opus` exits with status 3; stderr starts with `All model tiers exhausted for requested tier 'opus'.`; stderr contains the absolute path to routing.json, the literal override entry, and `/model-routing-check`; no bump event written |
| AC5a | Cycle detection | Bats: overrides map haiku→sonnet and sonnet→haiku; `model-resolve.sh haiku` exits 3; stderr starts with `Cycle detected in tier aliases:` and lists the visited tiers; no bump event written |
| AC5b | Missing routing.json | Bats: `model-resolve.sh` with `MODEL_ROUTING_JSON` pointing at a non-existent file exits 4; stderr starts with `Model routing file missing:` and names `git checkout knowledge/model-routing.json` |
| AC5c | Malformed overrides file | Bats: `.claude/model-overrides.json` contains `{not json`; `model-resolve.sh haiku` exits 5; stderr starts with `Override file is not valid JSON:` and tells the user to delete or fix |
| AC6 | Gitignored override file | `git check-ignore .claude/model-overrides.json` and `git check-ignore .claude/metrics/model-routing.log` both exit 0 from repo root |
| AC7 | Probe is opt-in | Bats: declining the prompt with "n" writes no `.claude/model-overrides.json`; `/init-dev-team` exit status matches the pre-change baseline captured in a golden file |
| AC7a | Probe happy path — all available | Bats: probe shim returns all three default snapshot IDs; no overrides file written; user message is exactly `All model tiers available; no overrides needed.` |
| AC7b | Probe happy path — tier missing | Bats: probe shim omits the haiku snapshot; `.claude/model-overrides.json` is written with `tier_aliases.haiku="sonnet"`, `reason="haiku snapshot not in /v1/models response"`, `available_models` matching the shim, and ISO-8601 `generated_at`; user message is exactly `Model tier 'haiku' bumped to 'sonnet'; .claude/model-overrides.json written.` |
| AC8 | Probe shape gating | Bats: with `ANTHROPIC_BASE_URL=https://bedrock-runtime.us-east-1.amazonaws.com`, accepting the probe touches no sentinel file via the curl shim (no HTTP issued); stderr contains `Probe skipped:` and references `docs/model-routing.md`; no overrides written. Repeat with `https://aiplatform.googleapis.com` |
| AC9 | Probe failure tolerance | Bats parameterised over three failure modes (curl exit 28, HTTP 500, HTTP 200 + malformed JSON). For each: no overrides written; `/init-dev-team` exit status matches baseline; user message starts with the failure-mode-specific prefix from the spec table and ends with `Dispatch fallback still applies; see docs/model-routing.md.` |
| AC10 | Diagnostic side-effect-free | Bats: `find . -type f \| sort \| sha256sum` snapshot before and after `/model-routing-check` is identical |
| AC11 | Diagnostic surfaces bumps | Bats: pre-seed log with 3 bump events; output prints all 3 in format `<ts>  <requested> → <served>  [<reason>]  caller=<caller>`; exit 0 |
| AC11a | Diagnostic tail cap | Bats: pre-seed log with 25 events; default output shows last 10 and includes the line `Showing last 10 of 25 bump events; raise MODEL_BUMP_TAIL to see more.`; with `MODEL_BUMP_TAIL=30` all 25 are shown and the line is absent |
| AC11b | Diagnostic probe-applicability line | Bats: output includes a `Probe applicability:` line. With `ANTHROPIC_BASE_URL` unset: `standard Anthropic endpoint (probe supported)`. With Bedrock URL: `non-Anthropic endpoint (probe skipped)` |
| AC12 | Documentation completeness | `docs/model-routing.md` contains H2 sections matching: `Contract`, `When the fallback fires`, `Interpreting the override file`, `Adding a new tier`, `Troubleshooting: Bedrock`, `Troubleshooting: Vertex`, `Troubleshooting: corporate proxy`, `Hand-writing the override file` |
| AC13 | ADR exists | `docs/adr/00NN-pre-dispatch-resolution.md` exists with Context/Decision/Consequences sections; Decision section explicitly rejects runtime `model_not_available` retry AND records the PreToolUse-hook-vs-orchestrator-instruction choice; file is linked from `docs/model-routing.md` |
| AC14 | Backward compat | `/agent-audit` exits 0 after the change; every agent file under `plugins/agentic-dev-team/agents/` retains its `model: haiku\|sonnet\|opus` frontmatter |
| AC15 | Performance | Bats: 1000 sequential `model-resolve.sh haiku` invocations (happy path, no override) complete in < 5s wall-clock on a baseline laptop, giving a 5ms p99 ceiling per invocation (50ms target with 10× headroom) |
| AC16 | Hook enforcement | Bats: `hooks/agent-model-resolve.sh` invoked with a PreToolUse-shaped stdin containing `tool_input.model="haiku"` and an overrides file mapping haiku→sonnet emits a `hookSpecificOutput.updatedInput` JSON payload with `model="claude-sonnet-4-6"`; exit 0 |
| AC17 | Hook refusal | Bats: same hook with overrides marking opus unavailable, requested model opus, emits a PreToolUse `permissionDecision="deny"` with `permissionDecisionReason` containing the AC5 error template; exit 0 (block-by-output, not by exit code) |
| AC18 | Hook registration | Bats: `plugins/agentic-dev-team/settings.json` PreToolUse block contains an entry with `matcher: "Agent"` invoking `hooks/agent-model-resolve.sh` |
| AC19 | Bump discoverability | Bats: with overrides file present, `hooks/overrides-banner.sh` (driven by a SessionStart-shaped stdin) prints to stderr the literal banner line `Note: model routing overrides active — run /model-routing-check to review.` and exits 0; without overrides file, the hook prints nothing and exits 0; `settings.json` registers the hook under `SessionStart` |

## Out of Scope (v1)

These are explicitly **not** part of this slice. Each is captured for the follow-on backlog.

- **Multi-region Anthropic endpoints**. The probe allowlist is `api.anthropic.com` and `*.anthropic.com`. Region-specific subdomains that exist in the future are not auto-detected; users override with `MODEL_PROBE_FORCE=1` documented in `docs/model-routing.md`.
- **Override file UI**. No interactive editor for `.claude/model-overrides.json`. Generated by probe; hand-editable; that is the entire authoring surface.
- **Per-agent model overrides**. The override file maps tiers globally; per-agent customisation stays via `model:` frontmatter and is not extended.
- **Telemetry beyond the bump log**. No phone-home, no anonymous metrics, no per-session aggregate report.
- **Runtime `model_not_available` retry**. The harness owns dispatch; the plugin does not attempt to intercept dispatch errors. (Recorded in ADR.)
- **Wiring existing PostToolUse review hooks through the resolver**. `js-fp-review.sh` and `token-efficiency-review.sh` are static grep scripts that do not spawn agents; no wiring needed.
- **Env vars as user-facing configuration surface**. `MODEL_ROUTING_JSON`, `MODEL_OVERRIDES_JSON`, `MODEL_BUMP_LOG` are **test-only injection seams** documented as such in the helper header (the prior draft also listed `MODEL_PROBE_CURL`; that shim has been replaced by the `tests/hooks/fake-bin` PATH-override pattern and no such env var exists in the implementation). The only user-facing env vars are `ANTHROPIC_BASE_URL` (existing), `MODEL_PROBE_TIMEOUT`, `MODEL_BUMP_TAIL`, and `MODEL_PROBE_FORCE` (documented in `docs/model-routing.md` for users behind Anthropic-shape proxies on non-`*.anthropic.com` hosts).
- **`MODEL_PROBE_FORCE=1` behaviour beyond documentation**. The env var is recognised by the probe helper (when set, it bypasses the host allowlist and attempts `/v1/models`), but the only AC coverage is its mention in AC12 (docs). No dedicated bats case ships in this slice — corporate-proxy users opting in accept that they are exercising a documented-but-untested path.

## Consistency Gate

- [x] Intent is unambiguous — two developers would interpret "pre-dispatch resolution" the same way given the architecture section's procedure.
- [x] Every behavior in the intent has at least one BDD scenario (zero-config, override resolution, cascade, top-tier-fails, probe accept/decline, probe non-Anthropic, probe failure, diagnostic clean/dirty, gitignore, no-pinned-IDs).
- [x] Architecture constrains without over-engineering — pre-dispatch resolution is one read + one merge + one walk; no daemon, no cache invalidation, no schema versioning beyond the single optional file.
- [x] Terminology consistent across artifacts — "tier", "snapshot", "override", "bump", "probe", and "pre-dispatch resolution" used identically throughout.
- [x] No contradictions — issue's "dispatch-side fallback" is explicitly reframed as pre-dispatch resolution in intent + architecture + ADR; runtime retry is excluded everywhere.

**Verdict: PASS.** Proceeding to `/plan`.
