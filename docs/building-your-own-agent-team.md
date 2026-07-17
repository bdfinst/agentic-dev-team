# Building Your Own Agent Team

*The mindset behind the dev-team plugin — for people building their own.*

This is not a manual for the dev-team plugin. It is an argument about how to
think when you build a system of AI agents that ships real software. The
plugin is the worked example; the ideas are meant to port to any harness — a
Claude Code plugin, a LangGraph app, a hand-rolled tool loop, a different
model entirely. Where a concrete mechanism helps, we name ours. Steal the
reasoning, not the file layout.

The premise: **an agent that can write code is not the same as a system you
can trust to ship it.** Closing that gap is not a matter of a better prompt.
It is a design problem, and the design has a point of view.

---

## The North Star: reduce friction, and prove it

Everything below descends from one line the plugin holds itself to:

> Every change must reduce friction — fewer missteps, less rework, lower
> token cost. Measure friction; don't assume it. A change that cannot name the
> friction it removes does not ship.[^northstar]

"Friction" is deliberately concrete: the moments where the system does the
wrong thing, redoes work it already did, or burns tokens to reach an answer it
could have reached cheaply. Those are measurable. Almost every principle here
is a bet about which friction matters most, and the discipline is to *check
the bet against evidence* rather than to admire it.

That discipline has teeth, and it produced the single most useful lesson in
the whole project — so we start there.

---

## 1. Measure friction; don't assume it

The obvious way to judge a coding workflow is by test coverage and mutation
score. It is also wrong, and we only know that because we measured.

Across a full matrix of workflows — test ordering × batch size × who writes
the code — coverage and mutation score **saturated**. Every arm landed near
100% coverage and near-perfect mutation score on small and medium tasks; even
on large tasks the arms sat on top of each other.[^saturate] Worse, the
*losing* workflows posted **higher** mutation scores (0.93–0.98) than the
winners (0.80–0.86) — thoroughness bought at two-to-four times the cost, with
worse changeability. If you had ranked workflows by mutation score you would
have chosen the expensive, rigid one and called it rigor.

The axis that actually separated good workflows from bad ones was none of the
headline metrics. It was the **structural review lens** — single
responsibility, complexity, coupling, duplication.[^reviewsignal] The winning
workflow produced meaningfully fewer weighted review findings than the
alternatives on the same tasks.

The transferable lesson is not "coverage is bad." It is: **the metric that is
easy to compute is rarely the metric that discriminates.** Before you let a
number steer your harness, run the arms and check whether that number can even
tell your options apart. Most can't. Instrument the thing you actually care
about — in code, that turned out to be structural quality a reviewer can name,
not a percentage a tool can print.

A corollary the plugin states plainly: *every claim must name its instrument.*
It is honest about what it has measured (token budgets, per-agent accuracy) and
what it has not yet (efficiency gains, hallucination rate). A harness that
can't tell you how it knows something is a harness that is guessing.

---

## 2. Find the load-bearing mechanism; don't cargo-cult the ritual

Once you measure, you can ask a sharper question: of all the things a workflow
*does*, which one actually carries the quality?

For code, the answer was surprising. Test-first versus test-after ordering —
the thing people argue about — bought essentially nothing on its own. The
load-bearing mechanism was **refactoring on every green**: after each small
batch reaches passing tests, clean up structure before moving on.[^refactor]
Deleting just that step erased the changeability advantage of the workflows
that won. Test ordering is a preference; the refactor is the mechanism.

This is a general trap in agent design. A workflow accretes rituals — a
planning step, a self-critique pass, a particular prompt structure — and it is
tempting to keep all of them because the whole thing works. But "it works" is
not "each part earns its place." Ablate. Find the one or two steps that, when
removed, make quality fall off a cliff, and make *those* non-negotiable and
enforced. Treat the rest as adjustable preference. The plugin makes the
refactor step mandatory on every batch and lets the ordering float, because
that is where the evidence pointed.

---

## 3. Small batches, one behavior at a time

The build cadence that won was the humble one: **for each behavior, write the
code, write the test that covers it, keep the suite green, refactor, move
on.** One agent, one behavior, tight loop.[^smallbatch] It beat both "write
all the code then all the tests" and "split the work across many agents" — on
quality *and* on cost, not a trade between them.

Why small batches keep winning is worth internalizing, because it is a
statement about how these systems fail. A large batch is a large bet: the
agent commits to a lot of structure before any feedback arrives, and when
something is wrong the blast radius is the whole batch. A small batch collapses
the distance between a decision and its verification. The agent is never more
than one behavior away from ground truth. That is the same reason the plan —
not the code — is the artifact humans review (Principle 5): both push
correction as early and as cheap as it will go.

If you take one operational habit from this document: shrink the unit of work
until the feedback loop is tight, then refactor at every green.

---

## 4. Rules land as code, not prose

Here is the failure mode that quietly kills agent harnesses: you write the
rule into the system prompt — "always run the smoke test before the full run,"
"never edit tests during a refactor" — and the agent follows it most of the
time. Most of the time is not a guarantee. Prose is advisory; the model can
reason its way past it, forget it under context pressure, or never load the
document that contains it.

So the discipline is: **a rule the system must follow becomes a
deterministic check, not a paragraph.** In the plugin these are hooks that fire
around every tool call, and they are the real enforcement layer:

- A **context-ceiling guard** reads the harness's own recorded token usage and
  refuses to load more capability when the window is too full — because *the
  model has no reliable readout of its own context fill; the transcript's usage
  is the ground truth.*[^ceilingguard]
- A **sensitive-path guard** blocks writes to credentials and secrets and
  enforces the scope lock set by a "freeze" command.
- A **refactor freeze guard** mechanically denies edits to test files while a
  refactor is in progress — the invariant that makes Principle 2 safe — and it
  held across tens of thousands of experiment cells with zero violations
  precisely because it was enforced, not requested.[^freezeguard]
- A **mutation smoke gate** blocks an expensive whole-scope run until a cheap
  one-file probe has proven the tooling actually registers kills.

The meta-rule: if you find yourself writing "the agent should always X" into a
prompt, ask whether X can instead be a gate. If it can, move it. Prose is for
judgment; code is for invariants.

Two design choices make this humane rather than tyrannical. The guards
**fail open** — a broken guard must never block real work; it degrades to a
warning and an audit line. And they are **warn-by-default**: the ceiling guard
nudges rather than blocks unless you opt into strict mode, and it never gates
the recovery skill you'd use to dig out. An enforcement layer that punishes the
operator for its own bugs gets disabled; one that fails safe gets trusted.

---

## 5. Keep the human at the high-consequence seams

Autonomy is not all-or-nothing, and the interesting design work is deciding
*where* a human must be in the loop. The plugin's answer: autonomous
everywhere, with hard approval gates at exactly the seams where a mistake
cascades.

The gates are few and deliberate: the human signs off on **the research
findings** before planning starts, on **the plan** before building starts, and
on **the final output / PR**.[^gates] A handful of always-approve actions sit
alongside them — production deploys, schema migrations, deleting data, adding a
new external dependency. Everything between the gates runs without asking.

The load-bearing insight is *which* artifact you gate on: **the plan, not the
code.** Two hundred lines of plan is far more reviewable than two thousand
lines of code, and a misunderstanding caught at the plan stage costs a
sentence to fix instead of a rewrite. The stance is almost a slogan — *if the
plan is correct and the tests pass, the code is trustworthy* — so the plan is
where human attention is spent.

Intervention is symmetrical: the human can `override`, `pause`, or `stop` at
any time, and those take effect immediately, without debate.[^commands] The
point of cheap, no-argument interruption is that it makes autonomy *safe to
grant* — you extend more rope precisely because you can pull it back instantly.

Design your gates by consequence, not by nervousness. Gate the decisions whose
errors are expensive and hard to reverse; let the reversible middle run free.

---

## 6. Treat context as the scarce resource it is

A model's context window is a budget, and a naive multi-agent system blows it
instantly by loading every agent, every instruction, and every artifact at
once. The plugin treats context occupancy as a first-class constraint with a
conservative ceiling (a target near 40% of the window, not because accuracy
falls off a cliff there but because headroom is cheap insurance).[^ceiling]

The architecture that keeps it under budget is **progressive
disclosure**, layered by how often something is truly needed:[^layers]

- a small always-loaded core (philosophy + quick reference),
- detailed procedures loaded **on demand** when a task needs them,
- reference registries and rubrics pulled in only by the agents that use them,
- and behavioral agent specs loaded **per phase, never all at once.**

Two habits keep the budget honest across a long task: **load on demand** rather
than preemptively, and **summarize each phase to durable memory before the next
begins**, so a later phase — or a fresh session — reads a compact summary
instead of replaying the whole history. Only the coordinator spans phases;
specialist agents are loaded when their phase starts and unloaded by
summarization before the next.

The generalization for any harness: decide, per piece of knowledge, *when* it
becomes relevant, and pay for it only then. Context spent on things you might
need is context you don't have for the thing in front of you.

---

## 7. Prefer honest signals to flattering ones

When a system reports on its own work, it is under quiet pressure to look good.
Resisting that is a design commitment, not a personality trait.

The sharpest example is the mutation score. The off-the-shelf tool counts
timed-out mutants as "killed," which inflates the number — on one real run,
999 of 1,305 headline "kills" were timeouts: about 23% genuine versus the ~61%
the tool advertised.[^honest] The plugin computes an **honest score** — hard
kills only, timeouts excluded — and shows it *above* the tool's flattering
figure, with a warning when the gap is large. It would have been easier to
print the big number. The whole value of the signal is that it is true.

The same instinct shows up as a family of rules: **never fabricate a result**
(if no tool is available to run, help set one up — do not substitute reasoning
for execution); **degrade gracefully** rather than grind or fake (when a real
run isn't feasible, say so and fall back to an honest, cheaper pass); and **no
silent skips** (a skipped check is surfaced and explained, never quietly
dropped). A system that is allowed to round its own grades upward will, and you
will trust it right up until it matters.

---

## 8. Design for the substrate you actually run on

Principles are portable; implementations meet reality. The plugin shipped its
automation first in shell scripts, then deleted all of it and rewrote every
shipped hook and tool in Python (standard library only), because bash on
Windows was a permanent tax — missing tools, stale linters, a fork-hang bug
that only appeared under one shell — and a Python interpreter was already a
hard dependency of every hook.[^adr] Consolidating on the substrate that ran
everywhere added no new dependency and removed a whole class of
platform-specific failures.

The lesson is not "use Python." It is: **the environment your agents actually
run in is part of the design, and portability is a feature you either buy early
or pay for forever.** Probe for tools at runtime instead of hard-coding paths;
pick the one substrate present on every target; treat "works on my machine" as
a bug in the harness, not the user's setup.

---

## 9. Let the system learn from being corrected

The last principle is what keeps the other eight from going stale. When a human
corrects the system, that correction is data. The plugin captures lightweight
feedback keywords in the flow of work — a way to *amend* a rule, *remember* a
fact, or note a preference — and logs configuration changes to an audit trail.
A standing heuristic: **the same correction three times is a missing rule.**
Three overrides on one topic should become an amended configuration, so the
human stops having to make the same call.

For your own harness: build the cheapest possible path from "the human just
corrected me" to "the system's default changed," and watch which corrections
recur. Recurring corrections are your backlog of missing gates and stale
prompts, handed to you for free.

---

## A worked example: knowing when *not* to run

Principles are easiest to trust when you watch them collide with a hard case.
Here is one, recent and real.

Mutation testing is one of the plugin's quality tools. On a particular .NET
stack it turned out that the underlying tool couldn't capture per-test coverage
— every run silently degraded to re-running the entire suite against every
mutant, which for one repo extrapolated to hours. Worse, the survivor-reduction
*loop* re-runs mutation after every fix, so the cost multiplied. The naive
behaviors were both bad: grind for hours, or fake a score.

The fix was the mindset applied end to end. **Detect the failure honestly** — a
guard learned to recognize the tool's own capture-failure message instead of
treating a silent degrade as success (Principle 7, Principle 4). **Put the
human at the consequential seam** — when the workaround would require disabling
tests, the operator is shown a classified list and always decides; nothing is
dropped silently (Principle 5). **Measure feasibility instead of guessing it**
— before entering the expensive loop, a one-file timed probe estimates a full
round; if it blows a budget, the system does not enter the loop at all
(Principle 1). **Degrade gracefully** — it falls back to a single honest
advisory pass and records a plain-language waiver rather than a fabricated
result (Principle 7). And each slice of the change was **built in small batches
and adversarially reviewed** before it merged, which is how the review caught
that one planned safeguard was, on closer inspection, wired to a place it could
never fire — and it was cut rather than shipped inert (Principles 2, 3).

The feature's headline capability is unremarkable: it runs mutation testing.
Its actual value is that it *knows when it cannot* and says so. That is the
whole mindset in one feature.

---

## Where to start

If you are building your own agent team, you do not need this plugin. You need
these decisions, made deliberately for your domain:

1. **Name the friction.** Write down the missteps, rework, and cost you are
   trying to remove. If you can't name it, you can't tell whether you removed
   it.
2. **Run the arms before you trust a metric.** Check that your quality signal
   can actually distinguish your options. Most convenient metrics can't.
3. **Ablate to the load-bearing mechanism.** Keep what carries the quality;
   demote the rest to preference.
4. **Shrink the batch** until the feedback loop is tight, and verify at every
   green.
5. **Move invariants out of the prompt and into gates** that fail open and
   warn by default.
6. **Gate the human by consequence** — on the plan, not the code — and make
   interruption instant.
7. **Budget context**; load on demand; summarize before you continue.
8. **Report the true number**, even when the flattering one is right there.
9. **Design for every machine you run on**, and probe instead of assuming.
10. **Turn recurring corrections into rules.**

None of these is exotic. The discipline is holding all of them at once, and
refusing to ship the change that can't say which friction it removed.

---

### Notes

[^northstar]: dev-team plugin philosophy — the "North Star," in
    [`../plugins/dev-team/CLAUDE.md`](../plugins/dev-team/CLAUDE.md).

[^saturate]: Workflow experiments, Recommendation 5 ("Use review agents — not
    coverage — as the design signal"), in
    [`experiments/RECOMMENDATIONS.md`](experiments/RECOMMENDATIONS.md). Coverage
    and mutation "saturate near 100% / 1.0" across arms; losing arms posted
    higher mutation (0.93–0.98) than winners (0.80–0.86). Results on a fixed
    model across a multi-hundred-cell matrix.

[^reviewsignal]: Same source; the structural review lens "was the one axis that
    separated arms on quality." Winning arm produced fewer weighted review
    findings than test-after / test-first alternatives on the same tasks.

[^refactor]: Recommendation 4 ("Refactor on every small batch — never only at
    the end"), [`experiments/RECOMMENDATIONS.md`](experiments/RECOMMENDATIONS.md):
    "Refactoring is the load-bearing mechanism of every workflow that won." The
    tests-frozen-during-refactor invariant held with zero violations across both
    experiment campaigns.

[^smallbatch]: Recommendation 3 ("Build with code-first small batches, one
    agent"), [`experiments/RECOMMENDATIONS.md`](experiments/RECOMMENDATIONS.md).
    Winner on quality-per-dollar; adopted as the plugin's sole build cadence.

[^ceilingguard]: [`../plugins/dev-team/hooks/context_ceiling_guard.py`](../plugins/dev-team/hooks/context_ceiling_guard.py)
    — PreToolUse guard; warn-by-default, fail-open, never gates recovery skills.

[^freezeguard]: [`../plugins/dev-team/hooks/refactor_test_freeze_guard.py`](../plugins/dev-team/hooks/refactor_test_freeze_guard.py)
    and its Bash-aware siblings; enforces Recommendation 4's invariant.

[^gates]: Human approval gates and the "plan is the primary review artifact"
    stance:
    [`../plugins/dev-team/skills/human-oversight-protocol/SKILL.md`](../plugins/dev-team/skills/human-oversight-protocol/SKILL.md)
    and the orchestrator agent spec.

[^commands]: `override` / `pause` / `stop` (immediate, no-debate) and the
    `amend` / `learn` / `remember` / `forget` feedback keywords —
    [`../plugins/dev-team/skills/human-oversight-protocol/SKILL.md`](../plugins/dev-team/skills/human-oversight-protocol/SKILL.md).

[^ceiling]: The 40% context ceiling and its rationale ("conservative target,
    not an accuracy cliff") —
    [`../plugins/dev-team/CLAUDE.md`](../plugins/dev-team/CLAUDE.md) and
    [`../plugins/dev-team/docs/context-management.md`](../plugins/dev-team/docs/context-management.md).

[^layers]: Architecture layering and context rules ("load on demand; summarize
    phases to memory before the next") —
    [`../plugins/dev-team/CLAUDE.md`](../plugins/dev-team/CLAUDE.md); phase
    load/unload in
    [`../plugins/dev-team/docs/team-structure.md`](../plugins/dev-team/docs/team-structure.md).

[^honest]: The "honest score" (hard kills only, timeouts excluded) —
    [`../plugins/dev-team/skills/mutation-testing/SKILL.md`](../plugins/dev-team/skills/mutation-testing/SKILL.md).
    On one real run, 999 of 1,305 headline kills were timeouts (~23% honest vs.
    ~61% claimed).

[^adr]: [`adr/0014-python-for-cross-os-scripts.md`](adr/0014-python-for-cross-os-scripts.md)
    and [`adr/0015-bash-removal-complete.md`](adr/0015-bash-removal-complete.md)
    — the decision to author all shipped scripts in stdlib-only Python and
    retire bash.
