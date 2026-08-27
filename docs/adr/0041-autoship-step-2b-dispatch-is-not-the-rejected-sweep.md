# 41. Autoship's per-round agent dispatch is not ADR 0022's rejected sweep

Date: 2026-08-27

## Status

Accepted

## Context

[ADR 0022](0022-reject-delegation-only-sweep-dispatch.md) rejected #1092/#1093's
delegation-only sweep — an orchestrator posture that replaced bulk reading with
low-band model judgment as *default* dispatch behavior — after a controlled
experiment showed its cost rising with task size despite moving tokens to a
cheaper band. It fixed a general principle from that result: **"delegation
must earn its overhead with a measured win at matched rigor before it ships as
default dispatch behavior."**

`skills/autoship/SKILL.md`'s Step 2b dispatches a `general-purpose` agent, via
the `Task` tool, on every `/autoship` round that has two or more issues left
in `autoship_group.py`'s `ungrouped` output after its four deterministic
signals (native dependency, shared parent, shared label, confirmed-batch
override) have already grouped everything they can. The agent's job: propose
additional groupings among titles/bodies a script cannot compare — issues that
describe the same feature in different words, with no shared label, parent, or
dependency link to key off. On its face this looks like exactly the shape ADR
0022 evaluated: an agent dispatch, on by default, adding cost with no
dedicated #1095-style experiment behind it.

That reasoning — why Step 2b does not need to clear ADR 0022's bar via a
dedicated controlled experiment before shipping — was worked out during
Slice 4 of the autoship build but lived only in a plan file since deleted per
this repo's `plans/` convention (transient working plans, not permanent
records). Nothing in `docs/adr/` stated it. Issue #2071 asks for that
reasoning to be recorded properly, so a future reviewer re-reading Step 2b
against ADR 0022's bar has an answer instead of a gap.

**What actually gates Step 2b, read directly from `skills/autoship/SKILL.md`:**

1. **Cost-cap check (before dispatch).** Step 2b reads the round's accumulated
   cost the same way Step 3a does (`/cost-report`) and skips the agent
   dispatch entirely once accumulated cost meets or exceeds `--max-cost-usd`
   — every ungrouped issue then proceeds to `autoship_queue.py` as a solo
   dispatch unit, exactly as if zero proposals had been returned. The
   dispatch's own cost counts against `--max-cost-usd` like every other spend
   in the round; a round that has already spent its budget never pays for a
   proposal it has no budget left to act on.
2. **Bounded, non-scaling dispatch shape.** Fewer than two ungrouped issues:
   no dispatch at all — a single leftover issue has nothing to be grouped
   with. Two or more: **exactly one** agent dispatch for the whole round,
   never one dispatch per ungrouped issue. The cost of this mechanism does not
   grow with the number of ungrouped issues, only with whether the leftover
   set is non-trivial at all.
3. **The agent's output can only narrow the deterministic set, never act on
   its own.** Response validation (Step 2b) discards any issue number the
   agent didn't actually see, resolves an issue claimed by more than one
   proposal to its first occurrence only, trims an oversized proposal to
   `--max-batch-size` by the same oldest-first rule the deterministic pass
   uses, drops any proposal left with fewer than two members, and treats an
   unparseable response as zero proposals. The agent is explicitly instructed
   that issue titles/bodies are untrusted data to analyze, not instructions to
   follow, and it is given no Bash/Write/Edit capability — its entire
   contribution is a JSON list of issue-number groupings that this
   deterministic validation layer then filters.
4. **Step 2c: every proposal is blocked pending human confirmation, not
   auto-applied.** A surviving proposal never becomes a batch on its own
   authority. Step 2c labels every member issue `autoship:blocked` and posts a
   comment naming the rationale, the members, and a literal copy-pasteable
   `gh issue edit ... --add-label autoship:batch-confirmed` command. Only a
   human running that command (in full or for a subset — partial confirmation
   is explicitly supported) lets `autoship_group.py`'s
   `has_batch_confirmed_override` signal union those issues on a **later**
   round. A rejected proposal costs one dispatch's tokens and one GitHub
   comment thread; it never itself ships code, opens a PR, or mutates issue
   state beyond the block-and-comment.

## Decision

Step 2b's one-dispatch-per-round agent proposal ships as default `/autoship`
behavior without a dedicated #1095-style pre-registered cost/quality
experiment against a non-delegating baseline. This is not an exception to ADR
0022's bar — it is a different class of delegation than the one ADR 0022
measured, and the difference is what substitutes for a measured win here:

1. **ADR 0022 rejected *replacing* a deterministic default with model
   judgment; Step 2b only *augments* a deterministic default that already
   ran.** `autoship_group.py`'s four signals execute first and unconditionally
   — dependency, parent, and label matching are comparisons a script can and
   does make. Step 2b activates only on the residue those signals could not
   resolve, for a task with no deterministic proxy in this codebase (natural-
   language similarity between issue titles/bodies). #1093 proposed skipping
   deterministic reads *in favor of* low-band judgment as the default path;
   Step 2b never displaces a mechanism it could have used instead.

2. **The cost-cap check is a substitute for a controlled cost ceiling, not a
   substitute for measuring cost.** ADR 0022's experiment existed because
   #1092/#1093's cost was unbounded and unmeasured until the pre-registered
   run produced numbers. Step 2b's cost is bounded on every single invocation
   by the operator's own `--max-cost-usd` — the same cap every other spend in
   the round already answers to — and is visible per round in the Step 4
   summary and `.claude/metrics/autoship-log.jsonl`, not only in a one-time
   benchmark. A mechanism whose worst-case cost is capped and observed on
   every run needs a different justification than one whose cost was unknown
   until an experiment measured it.

3. **The human-confirmation gate (Step 2c) is what ADR 0022 had no equivalent
   for.** #1092/#1093 shipped its judgment calls as *executed* default
   behavior — a wrong low-band read became the orchestrator's basis for
   further action with no human checkpoint in between, which is exactly why a
   controlled experiment against ground truth was the only way to know if it
   was safe. Step 2b's output is never executed directly: it is blocked
   pending a human decision, every time, with no auto-confirm path anywhere
   in the pipeline. A wrong proposal is rejected by a human before it can cost
   anything beyond the one dispatch and one comment thread that produced it.
   Measuring "does this delegation produce a good outcome" is what the human
   gate does continuously, in production, on real issues — a cheaper and more
   directly relevant signal than a one-time synthetic-fixture experiment would
   have been for a mechanism this narrowly scoped.

Points 2 and 3 together are the substitution this ADR records: where ADR
0022's rejected mechanism needed a pre-registered experiment to establish that
its cost was worth its judgment quality, Step 2b's cost is capped and
observed on every run (point 2) and its judgment quality can never reach
production before a human reviews it (point 3) — so the risk a controlled
experiment exists to catch (an expensive default that silently makes bad
calls) cannot manifest the same way here. This ADR does not reopen or weaken
ADR 0022's decision on #1092/#1093, and it does not lower the bar for
delegation generally — a dispatch that lacked either the cost cap or the
human gate would need to clear ADR 0022's bar the same way #1092/#1093 did.

## Consequences

**Easier:**

- Issue groupings a deterministic signal cannot express (two issues that
  describe the same feature in different words) get a real chance at being
  batched, without requiring a synthetic experiment before the feature could
  ship at all.
- The cost/quality tradeoff is visible on every round via `/cost-report` and
  the round summary, rather than needing a periodic audit to notice drift —
  the revisit trigger below can be evaluated from data this pipeline already
  produces.
- A future reviewer re-reading Step 2b against ADR 0022 has a recorded answer
  instead of a plan file that no longer exists.

**Harder / risks:**

- No pre-shipment quantitative bound exists on how *good* the agent's
  proposals are, only on how much they can cost and how little damage a bad
  one can do before a human catches it. This ADR accepts that tradeoff
  explicitly rather than silently.
- The human-confirmation gate only substitutes for a measured win as long as
  humans are actually reviewing proposals critically, not rubber-stamping
  them — see the revisit trigger below.

**Revisit triggers.** Re-evaluate this decision (via a #1095-style controlled
experiment, per ADR 0022's method) if any of:

1. Confirmation-comment data (or `.claude/metrics/autoship-log.jsonl`) shows
   operators confirming Step 2b's proposals as-is with a near-zero rejection
   rate over a meaningful number of rounds — the human gate would then be
   functioning as a rubber stamp, not the review this ADR relies on.
2. Step 2b's accumulated cost becomes a material line item across rounds
   (visible in `/cost-report` rollups), rather than an occasional single
   dispatch bounded by whatever budget was left.
3. A deterministic or substantially cheaper signal (e.g. a title/body
   similarity heuristic) is found to cover the cases Step 2b currently
   handles, making the agent dispatch redundant rather than necessary.

## Notes

Issue #2071. Companion mechanism: [ADR 0022](0022-reject-delegation-only-sweep-dispatch.md).
See `skills/autoship/SKILL.md`'s Step 2b ("Ungrouped-issue grouping") and Step
2c ("Block-and-comment on proposed batches") for the full mechanism this ADR
describes.
