# Context Management

A user-facing guide to `hooks/context_ceiling_guard.py` — what it measures,
why the ceiling is set where it is, how to read the warning it prints, and
how to tune or troubleshoot it. For the runtime procedure this backs
(what to load, when), see [Context Loading
Protocol](../skills/context-loading-protocol/SKILL.md); for the
compression procedure it nudges toward, see
[Handoff](../skills/handoff/SKILL.md).

## What the guard is, and the evidence behind it

A `PreToolUse` hook registered on `Agent` and `Skill` — every capability
load (dispatching a sub-agent, invoking a skill) is a choke point where the
hook can measure real context occupancy before the call proceeds. It reads
`utilization = (input + cache_read + cache_creation) / model_context_window`
from the session transcript's most recent assistant-message usage — ground
truth from the harness, not a model self-estimate (a model has no reliable
readout of its own context fill).

The 40% default ceiling is a conservative planning target, not a claimed
accuracy cliff:

- Chroma's [Context Rot study](https://www.trychroma.com/research/context-rot)
  found degradation across 18 models (including Claude 4) is gradual, not a
  sharp drop at any single percentage.
- Needle-in-a-haystack benchmarks like RULER and NoLiMa show a model's
  *effective* context is often only about half its advertised window, with
  sharp accuracy drops on non-lexical retrieval well before the window limit.
- Anthropic's [effective context engineering
  guidance](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
  recommends proactive compaction well ahead of the limit — the Claude API's
  own compaction default is 150K absolute tokens even on 1M-window models.

Given that evidence, budgeting to 40% of the window (capped at 150K
absolute) leaves headroom before quality degrades, rather than chasing a
precise threshold that doesn't exist.

## Reading the warning line

The warning follows one pinned template, field by field:

```text
🪟 Context at {occ} of {window} tokens — over the effective ceiling of {eff} tokens ({bound} bound; window {provenance}) before {label}.
```

| Field | Meaning |
| --- | --- |
| `{occ}` | Measured occupancy in tokens (input + cache_read + cache_creation of the latest transcript usage line). |
| `{window}` | The resolved context window in tokens. |
| `{eff}` | The effective ceiling: `min(ceiling_pct% of window, abs_ceiling)`. |
| `{bound}` | Which threshold is binding — `percentage` or `absolute`. The two framings never co-occur; exactly one is reported. |
| `{provenance}` | Where `{window}` came from — `override` (`DEV_TEAM_CONTEXT_WINDOW` set), `detected` (matched a pinned model family/version), or `default` (unrecognized model, or no model info — falls back to 200K). |
| `{label}` | What triggered the check — `loading agent '<name>'` or `invoking skill '<name>'`. |

A second line follows, naming the Handoff action band for
the current occupancy (see below), and — for the two lower bands — a
knob-tuning footer.

## Graduated bands: concrete fire-points

Bands are keyed to multiples of the *effective ceiling* (`{eff}`), not raw
window percentage, so the table below applies whether the threshold landed
on the percentage bound or the absolute bound:

| Band | Multiple of `{eff}` | Action |
| --- | --- | --- |
| nudge | 1x – 1.25x | Consider running `/handoff`. |
| run-now | 1.25x – 1.5x | Run `/handoff` now. |
| full-summary (top band) | 1.5x+ | Write a full summary to `.claude/memory/` and start a new conversation. Leads with the directive; no knob footer. |

Concrete fire-points at default settings (`DEV_TEAM_CONTEXT_CEILING_PCT=40`,
`DEV_TEAM_CONTEXT_ABS_CEILING=150000`):

| Window | Effective ceiling (`{eff}`) | Bound | nudge fires at | run-now fires at | full-summary fires at |
| --- | --- | --- | --- | --- | --- |
| 200K (e.g. Haiku) | 80,000 tokens | percentage (40% of 200K) | 80,000 | 100,000 | 120,000 |
| 1M (e.g. current Opus/Sonnet/Fable) | 150,000 tokens | absolute (150K cap < 400K) | 150,000 | 187,500 | 225,000 |

## Expectations

- **stderr-only by default.** Warn mode (the default) writes the message to
  stderr and exits 0 — the tool call proceeds. Nothing is written to
  stdout.
- **Strict mode blocks.** `DEV_TEAM_CONTEXT_STRICT=on` escalates an
  at-or-above-ceiling warning to `exit 2` (the tool call is blocked), with
  `[blocked: DEV_TEAM_CONTEXT_STRICT=on]` appended to the message.
- **Fail-open guarantees.** The hook never blocks a session because of its
  own failure: missing or unreadable transcript, malformed or empty stdin,
  unmeasurable usage, a malformed env var, or any internal parse error all
  resolve to a silent `exit 0`. A measurement failure is never treated as
  "over the ceiling."
- **Recovery skills are never gated**, strict mode included —
  `/handoff`, `/context-loading-protocol`, `/continue`,
  `/review-summary`, `/session-review` always proceed, so the path back
  under budget can never deadlock.
- **Per-session dedupe.** Repeated warnings at the same band and the same
  coarse 5%-of-window bucket are suppressed; a band escalation always
  breaks through even when the bucket hasn't moved.

## Knobs

| Env var | Default | Effect |
| --- | --- | --- |
| `DEV_TEAM_CONTEXT_CEILING` | (unset = on) | `off` disables the guard entirely. |
| `DEV_TEAM_CONTEXT_STRICT` | (unset = warn) | `on` blocks (`exit 2`) at or above the ceiling instead of warning. |
| `DEV_TEAM_CONTEXT_CEILING_PCT` | `40` | Percentage-of-window threshold before the absolute cap is applied. |
| `DEV_TEAM_CONTEXT_WINDOW` | (unset = auto-detect) | Overrides window auto-detection explicitly; always wins over detection. |
| `DEV_TEAM_CONTEXT_ABS_CEILING` | `150000` | Absolute token cap on the effective threshold — `min(ceiling_pct% of window, this)`. |

## Troubleshooting

**"Why does the warning say `window default` instead of `window
detected`?"** The transcript's `message.model` was missing, or didn't match
a known pinned family/version. This is a conservative fallback to 200K —
never a large window — so an unrecognized model never triggers an
under-nudge. See the family/version list in
[context-loading-protocol/SKILL.md](../skills/context-loading-protocol/SKILL.md#enforcement).
If the model is a known large-window model that isn't in the pinned list
yet, set `DEV_TEAM_CONTEXT_WINDOW` explicitly.

**"The window looks wrong for a model I know is 1M."** Only version-pinned
models auto-detect as 1M (Fable, Mythos, Opus 4.6/4.7/4.8, Sonnet 5, Sonnet
4.6) — window is a fixed per-model property, not a family-wide one, so a
same-family model outside that pinned list (e.g. an older Opus or Sonnet
snapshot) intentionally falls back to 200K rather than being assumed large.
Override with `DEV_TEAM_CONTEXT_WINDOW=1000000` if you know better.

**"I ran `/handoff` but the guard still warned."** Recovery
skills are exempt from gating, but only the skills listed above — check the
skill name doesn't have a plugin prefix mismatch (`plugin:continue` is
recognized as the recovery `continue`, stripped of its plugin prefix).

**"Nothing fires even though I'm clearly over budget."** Check
`DEV_TEAM_CONTEXT_CEILING` isn't set to `off`, and that the transcript path
passed to the hook is readable — a missing or unreadable transcript
fails open silently by design.

## Source

- `plugins/dev-team/hooks/context_ceiling_guard.py`
- Registered in `plugins/dev-team/settings.json` under `PreToolUse`
  (`Agent`, `Skill`).
- Tests: `plugins/dev-team/tests/hooks/test_context_ceiling_guard.py`.
- Design record: [ADR 0011](../../../docs/adr/0011-enforce-context-ceiling-with-transcript-measured-pretooluse-hook.md)
  (see its 2026-07-03 amendment for the window-detection design reversal).
