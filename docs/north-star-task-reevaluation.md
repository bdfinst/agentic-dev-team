# North Star Re-evaluation of the External-Review Tasks

> Re-scores the 17 children of [#98](https://github.com/bdfinst/agentic-dev-team/issues/98)
> against the **North Star** (`plugins/dev-team/CLAUDE.md`): *reduce friction — fewer missteps,
> less rework, lower token cost.* Reputational novelty is explicitly **not** a goal.
>
> The original report (`proposed-improvements-from-external-reviews.md`) rated "Impact" on a blend
> of decision-quality, credibility, **and novelty/first-mover reputation**. Stripping reputation out
> changes the ranking materially. This doc is the filter applied to that backlog.
>
> Verdicts: **KEEP** (serves the North Star as-is) · **MODIFY** (valuable only after reframing toward
> friction) · **REJECT/DEFER** (reputation- or research-driven; no near-term friction payoff).

## The filter

A task earns priority by how much *observed* friction it removes. Anything justified mainly by "nobody
has done this / conference talk / first-mover" falls — that is the exact justification the North Star
rejects.

> **Correction (the feedback loop already exists).** An earlier pass treated the feedback loop as
> unbuilt and proposed a new `/telemetry-insights` skill. That was wrong: the plugin already ships
> **`/session-review`** (#127/#131), which mines transcripts via a deterministic, zero-token extractor
> (`scripts/session_extract.py`) for `token | rework | accuracy | utilization`, then suggests
> improvements and hands them to governed machinery (`/feedback-learning`, `/agent-eval`,
> `/harness-audit`, `token-efficiency-review`). The rework signals an earlier draft called "missing"
> are already extracted. So the loop is the **spine**, and the only genuine deltas are captured in
> [`docs/specs/session-review-enhancements.md`](specs/session-review-enhancements.md): cross-machine
> aggregation, a frequency→lever escalation rule, and an optional raw-log tier (adding a `methodology`
> lens). The verdicts below are updated accordingly.

## Verdicts

| # | Task | Original impact basis | Verdict | Rationale under the North Star |
|---|------|----------------------|---------|--------------------------------|
| 99 | Agent-eval regression gate in CI | self-testing | **KEEP** | Protects agent quality → fewer missed findings = less rework. Already landed; finish the live-gate so the non-deterministic part actually runs, not just the structural check. |
| 104 | `updatedInput` conformance test | self-testing | **KEEP** | A silent routing break is pure friction (wrong model, wrong cost). Cheap insurance. Landed. |
| 102 | Runtime cost/token metering | observability | **DONE (model+thread) + #171 open** | The spike (#170) verified that **only `model` and `total` were ever real**; `agent`/`command`/`phase`/`iteration` were all inert because the harness exposes none of those fields and a plugin can't stamp the transcript. #170 fixed this: the meter now attributes by **model** and by **thread** (main vs subagent, from native `isSidechain`) and the inert buckets are removed. Remaining: **#140's CI gate** is a mechanism self-test only — it needs a real baseline, deferred to Delta D (**#171**, **#178**). |
| 106 | Opt-in telemetry beacon | observability | **KEEP — narrow** | Local-only was the *right* call. But its events (command/skill/gate) are a thin subset of what `/session-review`'s digest already extracts from transcripts. Keep it as the cheap always-on counter; do **not** grow it into the loop. Cross-machine aggregation belongs to the session-digest (Delta D), not the beacon. |
| 139 | Fix-loop / per-phase cost granularity | refines #102 | **SUPERSEDED by #170** | Earlier note ("per-phase works") was wrong: phase derives from `attributionSkill`, which the harness never records, so per-phase *and* per-iteration were both inert. #170's spike confirmed stamping is impossible and removed both buckets in favor of the real `model`/`thread` attribution. Separately, rework *itself* is already extracted by `session_extract.py`. |
| 140 | Wire cost-regression into CI | refines #102 | **CLOSED — self-test only (→ #171)** | Wired, but the blocking part only self-tests the mechanism on synthetic data; the real check is warn-only and dormant (no committed baseline). It does not gate real cost regressions. Real gate needs a committed/aggregated baseline — overlaps the session-digest cross-machine aggregation (Delta D). Tracked in **#171**. |
| 113 | Automatic post-session learning loop | learning | **CLOSE — already shipped** | This is `/session-review` (#127/#131): it mines sessions and routes suggestions to `/feedback-learning`'s audited writes. The automatic-learning loop exists. Close #113 as delivered; track only the deltas in `session-review-enhancements.md`. |
| 107 | Knowledge ablation testing | self-testing | **KEEP** | Directly lowers token cost: identifies knowledge files that never change a verdict = dead weight on every dispatch. Concrete, recurring friction payoff. |
| 109 | Concurrency / multiplayer collisions | correctness | **KEEP — pull forward** | Literal friction (clobbered progress files, stale gate). Phase 1 (reproduce) is an afternoon. Mis-filed in Wave 3; do Phase 1 early. |
| 110 | Persona-vs-context-boundary test | architecture | **MODIFY** | Keep *only* as a maintenance/token-cost question: does the persona layer cost tokens without improving detection? If yes, dissolving it reduces friction. Drop the "deepest structural assumption / strong story" framing — that is reputation. |
| 101 | Eval-corpus-as-semver | self-testing | **MODIFY → minimal** | Strip the "first to formalize it" goal. Retain only the thin value: flag a commit whose type contradicts its eval-diff (catches a mis-typed release). Do not invest beyond that. Landed; do not expand. |
| 100 | Prose/Targets slop cleanup | credibility | **KEEP** | Honest docs reduce user missteps (no chasing promised-but-absent features). Landed, with a sensor. |
| 108 | Mutation testing for prose/prompts | self-testing (novel) | **DEFER** | Justification is explicitly "standout moonshot / conference talk." Output is an *ambiguous* coverage map (dead weight vs. missing fixture — undecidable without per-rule human judgment) at real per-ablation model cost. No direct friction payoff. Revisit only if a cheap, unambiguous variant appears. |
| 111 | Process eval (A/B the ceremony) | self-testing (novel) | **MODIFY → narrow** | The general "is the ceremony worth it" study is expensive and biased by weak ground truth. Replace with the *specific* question `/session-review`'s trend stream can already answer from real sessions: *which* phases/gates correlate with high rework or bypass? Let the digest answer it, not a synthetic A/B. |
| 112 | Per-increment trunk integration topology | CD alignment | **DEFER (ADR only)** | Intellectually the deepest reframe, but it is a *redesign*, not friction reduction for current users, and it assumes flag/rollback infra the plugin does not own. Keep as an ADR/spike; do not implement until the loop shows current gates actually cause friction. |
| 105 | Resolve Multi-LLM/Gemini vestigiality | scope honesty | **KEEP — just delete** | A doc promising an absent capability is a misstep generator. Delete the table (Low path). Trivial. |
| 114 | Component extraction / publication | distribution | **REJECT** | Explicitly reputational ("talk, blog, standalone repo"). The North Star rules this out as a goal. Park indefinitely; it removes no user friction. |
| 115 | Reconcile `agent-ast.md` orphan spec | hygiene | **KEEP — trivial** | An orphan spec is minor misdirection. Archive or issue-track it. Quick win. |
| 103 | Eval variance & saturation data | self-testing | **KEEP** | Tells you which agents/fixtures to trust in the #99 gate → fewer false blocks (friction). Supports the loop. |

## Net effect on the roadmap

**The loop already exists — extend, don't rebuild:** the spine is `/session-review` (#127/#131), so

# 113 **closes as shipped**. The only loop work left is the three deltas in

[`session-review-enhancements.md`](specs/session-review-enhancements.md): cross-machine aggregation of
the session-digest, a frequency→lever escalation rule, and an optional raw-log/`methodology` tier.

# 139 **demotes** (rework is already extracted) and #106 **narrows** to a cheap counter

**Teeth still worth finishing:** #102 + #140 (a cost meter that enforces nothing is documentation),

# 99 (finish the live eval gate)

**Stays (independent friction reducers):** #104, #107, #109 (pull Phase 1 forward), #103, #100,

# 105 (delete), #115

**Falls (reputation/research, no near-term friction payoff):** #114 **rejected**; #108 and #112
**deferred** to ADR/curiosity scope; #110 and #111 **narrowed** to their friction-relevant core;

# 101 frozen at minimal

## Decision rule going forward

For any *new* proposed task (including the deferred ones if revisited): it ships only if it can name
the friction it removes and the metric that would show the reduction. If the honest answer is "it
would be novel / a good talk / first-mover," that is a **REJECT** under the North Star — file it
elsewhere, not in this backlog.
