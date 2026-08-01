---
name: harness-e2e-check
description: >-
  On-demand end-to-end integration check of the dev-team plugin's own
  harness mechanisms — failure-class routing, dead-end detection, evidence
  bundles, invariants/rollback, the REFACTOR-phase test-freeze guard family,
  lesson-validation weighting, and the handoff rename — running each live
  rather than trusting a per-PR test
  result. Originated as issue #907's post-merge integration test plan;
  this is that plan made repeatable. Use when the user says "run the
  harness e2e check", "re-run 907", "smoke-test the harness", or after any
  batch of harness-mechanism changes lands on main.
argument-hint: "[--item N] [--output <path>]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash(python3 *, git *, pytest *), Write
---

# Harness E2E Check

Role: worker. This command drives real, live exercises of the harness's own
mechanisms in throwaway scratch fixtures and reports pass/fail with evidence
— it does not modify the plugin, and it is not a substitute for `/agent-eval`
(per-agent detection accuracy) or `/harness-audit` (usage-metrics-driven
staleness analysis). It exists because those mechanisms only prove
themselves working *together*, in a live run, not from each one's own
isolated unit tests.

## Worker constraints

1. **Read-only against the plugin itself.** All exercises run inside scratch
   directories (a fresh `mktemp -d` per item, or the caller's `--output`
   sibling) — never inside the plugin's own working tree.
2. **Live, not simulated.** Where a mechanism can be exercised without an
   LLM call (guard hooks, `lesson_validate.py`, structural gates,
   stale-reference scans), run the real script/hook against a real fixture —
   never hand-wave "this should work." Where a mechanism genuinely requires
   a live `/build` run (Steps 3-4 below), drive it for real via `/headless-run`
   or an equivalent live session — do not substitute a description of what a
   run would show.
3. **Be concise.** Report each item as one line (pass/fail + one-line
   evidence pointer), then a short summary. Full transcripts/output go to
   the scratch dir, not chat.
4. **Every run maintains `references/watchlist.md`.** See "Hardening over
   time" below — this is not optional bookkeeping, it's the point of running
   this repeatedly instead of once.

## Parse Arguments

Arguments: $ARGUMENTS

- No argument: run all 8 items below.
- `--item N`: run only item N (1-6).
- `--output <path>`: write the full report to a specific path. Default:
  `.dev-team-reports/harness-e2e-check-<date>.md`.

## The 8 items

Each item mirrors one from issue #907's original test plan. Item numbers are
stable — do not renumber even if an item is skipped or split.

### Item 1 — Full automated suite

Run the repo's actual CI-equivalent gate (`scripts/ci-local.sh`, or the
component pytest suites directly: `plugins/dev-team/tests`, `tests/repo`,
`tests/agents`, `tests/commands`, `tests/scripts`, `tests/hooks`). Zero
regressions is the bar — a red suite is a fail for this item, full stop.

### Item 2 — Structural gates

Run `scripts/check_md_references.py`, the `knowledge/index.json` freshness
check, and the citation-lint suite. All clean.

### Item 3 — `/build` end-to-end smoke test

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/harness-e2e-check/scripts/make_toy_repo.py" \
  --target <scratch>/toy-repo --date "$(date +%F)"
```

Then drive a real `/build` run against `<scratch>/toy-repo/plans/calc-ops.md`
(via `/headless-run` or an equivalent live session with
`${CLAUDE_PLUGIN_ROOT}` resolved to this plugin's own checkout). Confirm, from
real output, not description:

- Failure-class routing fires on the deliberate Slice 1 bug (`behavioral-test`
  class, inline-fix route).
- Dead-end detection does **not** fire (the iteration-1 → iteration-2 failure
  signature changes).
- The 4-section evidence bundle renders with real data.
- Slice 2's `Invariants`/`Rollback point`/`Files` are honored.
- Gate-decision audit entries carry `proposed`/`evidence_shown`/`risks_surfaced`.

This fixture is also the regression bait for the three open SKILL.md-drift
gaps in `references/watchlist.md` (#915, #916, #917) — check those too while
you're in here, per the watchlist's "how to re-check" column.

### Item 4 — Refactor-freeze smoke test

In the same toy repo, during a REFACTOR-phase step: attempt a `Write`/`Edit`
test-file change (must block via `refactor_test_freeze_guard.py`), a
recognized Bash shape like `sed -i` against a test file (must block via
`refactor_test_bash_guard.py`, #906), and a genuinely unrecognized Bash shape
(must fall through to the revert-guard safety net and emit
`decision: "revert"` to `.claude/metrics/boundary-events.jsonl`). This is also where
#913 (no Python detection in `is_test_file()`) and #914 (compound-command
first-match-wins gap) live — #914 already has a standing regression test
(`tests/hooks/test_refactor_test_bash_guard.py`, `xfail(strict=True)`); no
need to hand-re-verify it here, just note whether it's still `xfail` or has
flipped (which would mean someone fixed it without updating the watchlist).

### Item 5 — `feedback-learning` + `harness-audit` combined run

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/harness-e2e-check/scripts/make_lesson_fixtures.py" \
  --target <scratch>/lesson-fixture --mode validated
python3 "${CLAUDE_PLUGIN_ROOT}/skills/harness-audit/scripts/lesson_validate.py" \
  --changelog <scratch>/lesson-fixture/metrics/config-changelog.jsonl \
  --digest <scratch>/lesson-fixture/metrics/session-digest.jsonl \
  --apply -o <scratch>/lesson-fixture/memory/lesson-validation.json
```

Confirm verdict `"validated"`, and that the changelog append stayed
byte-identical-prefix (append-only). Repeat with `--mode harmful` and confirm
a rollback **proposal** (`requires_human_approval: true`, never an automatic
rollback). Repeat with `--mode insufficient` and confirm `"insufficient
data"` — never `"neutral"` on a thin sample.

### Item 6 — `/handoff` rename verification

Covered permanently by
`tests/repo/test_no_stale_context_summarization_references.py` — this item
is "confirm that test is still green," not a fresh manual grep.

## Output format

One line per item (`✅ item N — <one-line evidence>` or `❌ item N —
<what failed>`), then update `references/watchlist.md` per its own
instructions, then a short summary. Full command transcripts go to the
scratch dir or `--output` path, not chat.

## Hardening over time

This skill is meant to get stricter every time it finds something, not stay
a fixed 8-item checklist forever:

1. **Every newly-found gap gets a watchlist row and a follow-up issue** — see
   `references/watchlist.md`'s own instructions. Do not fix a finding inline
   here; this command reports, `/apply-fixes` or a normal implementation
   pass changes the plugin.
2. **Prefer promoting a live-run check to a hard pytest regression the moment
   it's mechanically possible** — item 5's `lesson_validate.py` fixtures and
   item 4's `#914` `xfail(strict=True)` test are the pattern: encode the
   *desired* behavior as a real assertion now, marked expected-to-fail (or
   scripted-but-manually-triggered) while the gap is open, so a fix is caught
   automatically instead of relying on someone remembering to re-check by
   hand.
3. **When a fixture accidentally reproduces a gap** (like `make_toy_repo.py`
   baiting #915/#916/#917 just from its natural shape), keep the fixture as
   it is and document the coincidence in the watchlist rather than
   "fixing" the fixture to stop tripping it — a fixture that stops
   reproducing a real gap is worse than one that never did.
