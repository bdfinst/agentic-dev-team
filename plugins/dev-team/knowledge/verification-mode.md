# Verification-mode re-dispatch (#1628)

The single definition of what a **fix-verification** re-dispatch sends and
what it may cost. Referenced by [`skills/code-review/SKILL.md`](../skills/code-review/SKILL.md)
step 6a and [`skills/build/SKILL.md`](../skills/build/SKILL.md)'s inline
checkpoint loops — stated once here, never restated in either caller.

## The problem

When a fix loop re-dispatches an agent to confirm a fix, that dispatch is
indistinguishable from discovery: same tier, same full context payload. But
the task is far narrower — *here is the finding, here is the fix diff:
resolved or not?* `correctness-review` (opus/`effort: high`, the most
dispatched review agent in the project's logged history at 24) pays full
discovery cost for every confirmation.

`/code-review` step 6a's deterministic-first triage (#1610) already removes
the mechanically-checkable confirmations. This contract cheapens the ones
that genuinely need semantic judgment.

## Stage 1 — context narrowing (no routing change)

A verification re-dispatch passes **only**:

1. The finding: its signature (#1625), original message, severity, and
   confidence.
2. The fix diff hunks, ± ~20 lines of surrounding context.
3. The agent's own lens definition.

It does **not** pass the full target file set. Token cost of a confirmation
drops roughly with context size regardless of tier, and #1611/#1618 measured
full-file payloads as the dominant input cost.

**The `insufficient-context` escape is mandatory.** The dispatch prompt must
state the narrowed contract explicitly and grant the agent this exit:

> If the fix's correctness cannot be judged from this context, reply
> `insufficient-context` — do not guess.

An `insufficient-context` reply escalates to a **full-context re-dispatch of
that same agent**, at its discovery tier. Narrowing must never become a quiet
downgrade in review quality: an agent that says it cannot judge is answered
with more context, not with a shrug. A verification-mode prompt that omits
this escape is malformed.

## Stage 2 — tier-down, declared per agent, never inferred

An agent may opt in to a cheaper tier **for verification dispatches only** by
declaring these in its **body** (not frontmatter — see below):

```
Verify-model: haiku
Verify-effort: medium
```

**Default when absent: unchanged** — verification runs at the same tier as
discovery. This default is deliberate, not conservatism for its own sake:
#1619 showed some confirmations genuinely need top-tier judgment. The
`Intl.NumberFormat.prototype.format` call — determining that a spec-bound
getter does not lose its receiver when unbound, per ECMA-402 — was a
verification-shaped question that a cheap tier would plausibly have gotten
wrong, and getting it wrong would have shipped a fixture that didn't test
what it claimed.

Resolve the pair with the shared helper, never by reading frontmatter
directly:

```bash
python3 "$CLAUDE_PLUGIN_ROOT/scripts/verify_tier.py" --agent <name>
```

It prints `{"agent", "model", "effort", "opted_in"}` — the tier to dispatch
this agent at in verification mode, already falling back to the discovery
tier when no opt-in is declared.

### Why a body declaration, not frontmatter

Issue #1333 established that this plugin's own tooling metadata lives in the
agent **body**, because frontmatter is reserved for the official Claude Code
sub-agent contract recorded in
`plugins/marketplace-dev/knowledge/agent-contract.json` — a dated snapshot of
upstream documentation, not a schema this plugin may extend. `Scope:`,
`Cites:`, and `Enforcement:` all follow that rule; these two join them.
(Claude Code silently ignores unknown frontmatter keys, so putting them in
frontmatter would also have made a typo invisible.) See
[`docs/agent_info.md`](../docs/agent_info.md) § Non-standard body
declarations.

### Initial opt-ins

| Agent | Verify tier | Why |
| --- | --- | --- |
| `structure-review` | haiku | Confirming an extracted function or a flattened nesting level is a structural read, not a judgment call |
| `naming-review` | haiku | Confirming a rename landed consistently is near-mechanical once the rename itself is applied |
| `doc-review` | haiku | Confirming a doc line now matches the code it describes is a comparison, not an inference |

`correctness-review` and `security-review` deliberately do **not** opt in.
They are the two most expensive lenses and the two most obvious candidates —
and that is exactly why the decision waits for #1624's per-agent
discovery-vs-verification data to show their verification dispatches are
low-yield. Tiering them down on intuition is the mistake this table exists to
avoid.

## Recording

Every verification dispatch is recorded with `dispatch_purpose: "verification"`
(#1624), so per-agent cost splits by purpose. The dispatch ledger still records
it as a genuine dispatch of that agent (`subagent_type` unchanged), so gate
corroboration semantics are untouched — a tiered-down verification dispatch
corroborates the commit gate exactly as a discovery dispatch does.

## Out of scope

- Auto-inferring the tier from a finding's severity or confidence. Needs
  #1624's data first.
- Changing discovery-dispatch tiers. This contract governs verification only.
