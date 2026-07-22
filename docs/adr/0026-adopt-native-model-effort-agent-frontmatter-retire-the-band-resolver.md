# 26. Adopt native model:/effort: agent frontmatter, retire the band resolver

Date: 2026-07-22

## Status

Accepted

Supercedes [4. Pre-dispatch model tier resolution enforced by a PreToolUse hook](0004-pre-dispatch-model-resolution.md)

Supercedes [8. Use effort bands instead of model names in agent frontmatter](0008-use-effort-bands-instead-of-model-names-in-agent-frontmatter.md)

Supercedes [21. Claude-only model routing — no multimodal or cross-provider tier](0021-claude-only-model-routing-no-multimodal-tier.md)

Supercedes [23. Calibrate agent effort bands from the #1184 eval baseline](0023-calibrate-effort-bands-from-the-1184-eval-baseline.md)

Supercedes [24. Keep the single model-routing map keyed by canonical model IDs](0024-keep-single-model-routing-map-keyed-by-canonical-model-ids.md)

Supercedes [25. Allow versioned (dated-snapshot) model IDs in the routing map](0025-allow-versioned-model-ids-in-routing-map.md)

## Context

[ADR 0004](0004-pre-dispatch-model-resolution.md) built a PreToolUse hook to
resolve a tier alias to a concrete model before every `Agent` dispatch, because
at the time (2026-06-01) it was unverified whether the harness itself did
anything useful with `model:` beyond a bare alias lookup, and two real
populations (restricted corporate proxies, Anthropic snapshot deprecation)
needed that resolved reliably. [ADR 0008](0008-use-effort-bands-instead-of-model-names-in-agent-frontmatter.md)
renamed the frontmatter field from a vendor-named tier (`haiku|sonnet|opus`) to
a vendor-neutral `effort: low|medium|high` band, mapped to a model by the same
hook via `knowledge/model-routing.json` or a per-environment
`.claude/model-ladder.json`. [ADR 0021](0021-claude-only-model-routing-no-multimodal-tier.md)
scoped that routing to Claude-only. [ADR 0023](0023-calibrate-effort-bands-from-the-1184-eval-baseline.md)
validated several agents' bands against eval fixtures and downgraded eight of
them. [ADR 0024](0024-keep-single-model-routing-map-keyed-by-canonical-model-ids.md)
and [ADR 0025](0025-allow-versioned-model-ids-in-routing-map.md) settled the ID
shape the routing map's values should take. Six accepted ADRs, a PreToolUse
hook and its resolver library, a calibration subsystem
(`scripts/agent_calibrate.py`, `knowledge/calibration-floors.json`, `/agent-eval
--calibrate`), ~15 test files, and two dedicated docs
(`docs/model-routing.md`, `docs/band-calibration.md`) accumulated around this
one problem: the harness might not resolve `model:`/reasoning-effort
correctly on its own, so the plugin resolved it first.

ADR 0008's own amendment already recorded a live data point cutting against
that premise: the shipped hook layer did not load at all on Claude Code until
v10.12.1 (#1178), so every agent ran on the session model regardless of its
declared band for an unknown prior period — and nothing in production broke
in a way that surfaced the gap. The hook's enforcement guarantee was inert,
and the system still functioned.

Anthropic's own documentation (verified 2026-07-22, the source captured
verbatim in `plugins/marketplace-dev/knowledge/agent-contract.json`) confirms
Claude Code subagents natively support a `model:` field — an alias
(`sonnet|opus|haiku|fable`), a full model ID, or `inherit` — and an `effort:`
field (`low|medium|high|xhigh|max`), both resolved by the harness itself
before dispatch. This is exactly the mechanism ADR 0004 built a hook to
provide, now confirmed to already exist natively, with a wider effort range
(five levels, not three) and no dependency on a shipped routing map, ladder
file, or calibration subsystem to keep working. The custom machinery is not
wrong, it is redundant: the harness now does natively what the plugin spent
six ADRs building by hand.

A repo sweep found 70+ files referencing the system being retired: the six
ADRs above, ~15 test files, 2 dedicated docs, the hook and its lib, 51 agent
files across `plugins/dev-team/` and `plugins/security-assessment/`, and the
`marketplace-dev:agent-create`/`plugin-audit` tooling that scaffolds and
validates the old scheme today.

## Decision

**Adopt the native `model:`/`effort:` frontmatter contract on every agent, and
retire the band resolver, ladder, and calibration infrastructure it
replaces.** Concretely, sequenced across sub-issues of epic #1284:

1. **Contract validator (#1285, shipped).** A schema-driven validator
   (`plugins/marketplace-dev/scripts/validate_agent_contract.py`, wrapped at
   `scripts/validate_agent_contract.py` for this repo's own self-audit) checks
   any agent's frontmatter against `agent-contract.json` — required fields,
   name pattern, enum membership for `model`/`effort`/`permissionMode`/
   `memory`/`isolation`/`background`/`color`, unknown-key warnings, and a
   plugin-agent warning that `hooks`/`mcpServers`/`permissionMode` are inert
   for plugin-supplied agents.
2. **This ADR (#1286).** Records the decision and supersedes ADRs 0004, 0008,
   0021, 0023, 0024, and 0025.
3. **Mechanical migration (#1287).** Every agent in
   `plugins/dev-team/agents/` and `plugins/security-assessment/agents/` (51
   files) is rewritten from `effort: <band>` to `model: <alias>` +
   `effort: high`. The `model:` alias is derived once, mechanically, from each
   agent's *current* band through today's `knowledge/model-routing.json`
   (`low→haiku`, `medium→sonnet`, `high→opus`) — preserving which model each
   agent already dispatches to. `effort:` is set uniformly to `high` for
   every agent, not band-preserving: the old three-way band was doing double
   duty as both "which model" and "how much reasoning," and now that the
   native fields separate those concerns cleanly, `high` is the safe default
   until a follow-up calibration pass evaluates the native effort dial on its
   own terms (see Consequences).
4. **Retire the infrastructure (#1288).** Delete
   `hooks/agent_model_resolve.py`, `hooks/lib/model_resolve.py`, their
   `settings.json`/`hooks.json` registration, `knowledge/model-routing.json`,
   `knowledge/calibration-floors.json`, `skills/model-routing-check/`,
   `scripts/agent_calibrate.py`, `scripts/check_calibration_floors_sync.py`,
   `scripts/check_model_staleness.py`, `scripts/recalibrate_*.py`, the
   `--calibrate` mode's supporting scripts, and the ~15 associated test
   files. Update `plugins/dev-team/CLAUDE.md`'s Model Routing section,
   `docs/model-routing.md`, `docs/model-routing-overrides.md`,
   `docs/band-calibration.md`, and the band references in
   `knowledge/skills-registry.md`, `knowledge/agent-registry.md`,
   `agents/orchestrator.md`, and `agents/session-analysis.md`.
5. **Marketplace tooling (#1289).** `marketplace-dev:agent-create` and
   `plugin-audit` are updated to scaffold and validate `model:` + `effort:
   high` instead of the old band scheme, and gain optional `--memory`,
   `--isolation`, `--color`, `--max-turns`, `--background`, and a `skills:`
   preload list as creation-time inputs — matching the full native contract,
   not just the two fields this migration touches.
6. **Wire the validator in, drop the calibration mode (#1290).**
   `dev-team:agent-audit` invokes the contract validator from #1285 as part
   of its structural-compliance checks. `dev-team:agent-eval` drops its
   `--calibrate` mode (flag, docs, dispatch logic) — the calibration
   subsystem it drove no longer exists after #1288.

## Consequences

**Easier:**

- Zero plugin-owned code stands between an agent's frontmatter and the
  model/effort the harness actually runs it with. There is no PreToolUse
  hook to keep loading correctly (the exact failure mode ADR 0008's amendment
  already hit once, silently, for an unknown period), no routing map or
  ladder file to keep in sync with Anthropic's snapshot lineup, and no
  calibration subsystem to maintain.
- The native `effort:` field has five levels (`low|medium|high|xhigh|max`)
  instead of the retired scheme's three, and needs no shipped default map to
  function — `inherit`/session-effort is the harness's own fallback.
- ~70 files' worth of hand-built machinery (hook, lib, ladder convention,
  calibration scripts, ~15 tests, 2 docs, 6 ADRs) collapses to one validator
  script and one contract file.

**Harder / risks:**

- **The #1184/#1211/#1023 calibration evidence does not carry forward as an
  effort assignment.** Those baselines validated the retired band against
  eval fixtures; they said nothing about the *native* `effort:` dial, which
  didn't exist as an independent, harness-resolved field until now. Setting
  every agent to `effort: high` uniformly is a deliberate reset, not a
  regression of that evidence — but it does mean agents previously
  downgraded to a cheap model (e.g. `a11y-review` on Haiku, per ADR 0023) now
  run that cheap model at `effort: high`, a combination never calibrated.
  Re-running calibration against the native `model:`/`effort:` combination
  is out of scope for this epic and tracked as follow-up work, not a gap this
  ADR closes.
- **Breaking change for any downstream agent author who copied the retired
  scheme.** Anyone who forked an agent with `effort: medium` (the retired
  vocabulary) must migrate to `model:`/`effort: high` (the native one). The
  marketplace tooling update (#1289) ensures new agents are scaffolded
  correctly going forward; existing forks outside this repo are the fork
  owner's responsibility.
- **`agent-contract.json`'s enum values are a point-in-time capture of
  Anthropic's docs (retrieved 2026-07-22), not a live contract.** If the
  harness adds or renames `model`/`effort` values, `agent-contract.json` and
  the validator built on it need a manual refresh — the same staleness risk
  the retired `knowledge/model-routing.json` had, just with a much smaller
  surface (one JSON file describing an external contract, not a routing
  table this repo computed).
- **Sequencing risk across five sub-issues landing separately.** #1288
  depends on #1287 landing first (agents must already declare `model:`
  before the resolver that reads `effort: <band>` is deleted), and #1290
  depends on both #1285 and #1288. A partial landing (e.g. #1287 merged,
  #1288 not yet) leaves the retired hook resolving frontmatter that no
  longer uses its expected vocabulary — mitigated by shipping each sub-issue
  as its own reviewed PR in the dependency order recorded above, not by
  attempting one atomic change across 70+ files.
