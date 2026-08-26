# Validating the context ceiling

The context ceiling enforced by `hooks/context_ceiling_guard.py` is a
judgement call, and [ADR 0038](adr/0038-raise-the-absolute-context-ceiling-to-350k.md)
named the weakest part of the reasoning behind its current 350K value:

> The turn-count estimate above is the weakest link in this reasoning — it is
> an inference from a token ratio, not a recorded count. If per-session peak
> occupancy is ever instrumented directly, re-derive the threshold from the
> actual distribution.

`scripts/context_ceiling_report.py` is the instrument that replaces that
inference. It replays real session transcripts, reconstructs the occupancy the
guard *would have measured* at every capability load, and reports what each
candidate ceiling would have done.

This is maintainer tooling. It lives at the repo root and is **not shipped**
with the plugin — see [ADR 0014](adr/0014-python-for-cross-os-scripts.md) on
the scope split. For the shipped guard's own user-facing guide (what it
measures, how to read its warning, which knobs exist), see
[`plugins/dev-team/docs/context-management.md`](../plugins/dev-team/docs/context-management.md).

## Running it

```bash
# default corpus: ~/.claude/projects/**/*.jsonl
python3 scripts/context_ceiling_report.py

# narrower corpus, custom sweep, machine-readable output
python3 scripts/context_ceiling_report.py \
  --transcripts ~/.claude/projects/-home-me-myproject \
  --ceilings 150000,250000,350000,450000 \
  --json /tmp/ceiling-report.json
```

| Flag | Default | Meaning |
| --- | --- | --- |
| `--transcripts` | `~/.claude/projects` | Files or directories to replay; directories are searched recursively for `*.jsonl`. |
| `--ceilings` | `150000,…,600000` | Comma-separated candidate absolute ceilings to sweep. |
| `--ceiling-pct` | `40` | The percentage-of-window bound, matching `DEV_TEAM_CONTEXT_CEILING_PCT`. |
| `--near-done-turns` | `5` | Assistant turns remaining at or below which a blocked session counts as "near done". |
| `--shipped` | `350000` | Which row to mark and summarize in the verdict. |
| `--json` | — | Also write the full per-session result for scripting. |

## Reading the sweep

A single "N% of sessions blocked" number cannot tell the two failure
directions apart, so the report prints a column for each:

| Column | Direction it detects | What a bad number looks like |
| --- | --- | --- |
| `near-done` | ceiling too **low** | a high share of blocked sessions were within a few turns of finishing — [ADR 0037](adr/0037-block-by-default-at-the-context-ceiling-2000.md)'s revisit trigger, verbatim |
| `tokens over` | ceiling too **high** | a large share of corpus prompt tokens was spent past the first block, i.e. the expensive tail ran anyway |

A better ceiling lowers `near-done` without letting `tokens over` climb. The
report deliberately does not collapse these into a score or pick a number for
you — the cost of a wrong ceiling is asymmetric in a way no single statistic
captures, and the 150K→350K move happened precisely because a number got
adopted without that trade-off being visible.

Sample output, against a synthetic corpus:

```text
  ceiling |  sessions |  blocked |  blocks |  median@1st |  near-done |  tokens over
------------------------------------------------------------------------------------
  150,000 |        12 |     100% |     100 |     181,249 |      16.7% |        89.7%
  250,000 |        10 |    83.3% |      85 |     291,246 |        50% |        78.8%
  350,000 |         7 |    58.3% |      75 |     420,000 |      42.9% |        69.8% *
  450,000 |         6 |      50% |      72 |     467,499 |      33.3% |        66.6%†
```

## Three properties worth knowing before acting on its output

**It conditions on gated calls, not on occupancy.** The ceiling only binds at
an `Agent`/`Skill` call, so a session can sit far above any candidate and
never trip it. This is not a detail — it is the flaw the tool was built to
correct. ADR 0038's own occupancy figures are per-turn averages, and the guard
does not fire per turn, so reasoning from occupancy alone systematically
*overstates* how often a given ceiling binds. The report's peak-occupancy
table carries an explicit warning against reading it as a block rate.

**A candidate above `ceiling_pct` of the window does nothing.** The effective
threshold is `min(pct% of window, cap)`, so on a 1M window at the default 40%,
no cap above 400K changes anything. Those rows are marked `†` rather than
being left to look like genuine data points — a sweep row that silently equals
its neighbour reads as "the ceiling made no difference" when the truth is
"this candidate was never applied". Raise `--ceiling-pct` too if you want to
test past that point.

**An empty result is reported as inconclusive, never as confirmation.** If no
session in the corpus reached the ceiling at a gated call, the verdict says so
and asks for a larger corpus. "0 blocked" on data containing no evidence is
not evidence the ceiling is right — that is this repo's *a gate that cannot
fail is worse than no gate* rule applied to the measurement itself.

## Why it cannot drift from the guard

Every policy decision — which tools are gated, which skills are exempt, how a
model maps to a window, how occupancy is summed, what counts as a sidechain
row — is **imported** from
[`plugins/dev-team/hooks/context_ceiling_guard.py`](../plugins/dev-team/hooks/context_ceiling_guard.py)
rather than restated. A validator that measured the ceiling even slightly
differently from the guard would be validating a threshold nobody ships.

[`tests/scripts/test_context_ceiling_report.py`](../tests/scripts/test_context_ceiling_report.py)
additionally pins the report's occupancy walk against the hook's own
`_measure_occupancy` on shared fixtures, in the same spirit as the hook
suite's utilization-formula equality test.

## Acting on the result

When the corpus is large enough to return a verdict other than "inconclusive",
amend [ADR 0038](adr/0038-raise-the-absolute-context-ceiling-to-350k.md) with
what it says. Both of that ADR's revisit triggers are now measurable rather
than hypothetical:

- `near-done` dominating the blocked population → the ceiling is too low; raise
  `DEV_TEAM_CONTEXT_ABS_CEILING`, per ADR 0037's explicit instruction not to
  return to warn-by-default instead.
- sessions again running far past the ceiling, with `tokens over` high at every
  candidate → the ceiling is too high, or the guard is not binding where the
  spend happens.
