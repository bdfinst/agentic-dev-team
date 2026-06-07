# Implementation Plan — Remaining North Star Work

> Drives the open children of [#98](https://github.com/bdfinst/agentic-dev-team/issues/98) to done,
> ordered by the **North Star** (`plugins/dev-team/CLAUDE.md`: reduce friction — fewer missteps,
> less rework, lower token cost). Verdicts source:
> [`docs/north-star-task-reevaluation.md`](../docs/north-star-task-reevaluation.md).
> Loop deltas source: [`docs/specs/session-review-enhancements.md`](../docs/specs/session-review-enhancements.md).
>
> **Start with the open bugs** (Wave 0), then fan out. Each item is annotated **‖ parallel** (no
> dependency — can run concurrently) or **→ sequenced after X** (hard dependency).

## Scope

**In scope (open):** bugs #170, #171, #173; enhancements #103, #105, #106, #107, #109, #110, #111,
# 115; ADR follow-through #112; loop deltas A/B/C/D.

**Out of scope (resolved this cycle):** #108, #114 (closed *won't do*); #113 (closed *shipped*);
# 99/#100/#101/#102/#104/#139/#140 (landed — #139/#140 with the verified gaps that became #170/#171).
The security track (#38 family, #60/#62/#63) is a separate program, not North Star work.

## Dependency graph

```
WAVE 0 — BUGS (do first; all three parallel — different files)
  #173  /plan prompt path fix .................... ‖ independent (trivial)
  #170  stamp fixLoopIteration marker ........... ‖ independent → starts with a FEASIBILITY SPIKE
  #171  cost-regression real baseline ........... ‖ independent for the quick fix;
                                                    the *aggregated* baseline → sequenced after Delta D

WAVE 1 — HYGIENE / SCOPE (parallel with Wave 0; independent, low effort)
  #105  delete Gemini/Multi-LLM table ........... ‖ independent
  #115  reconcile agent-ast.md orphan spec ...... ‖ independent
  #106  narrow telemetry beacon (scope + doc) ... ‖ independent

WAVE 2 — LOOP SPINE + INDEPENDENT MEASUREMENT
  Delta D  cross-machine session-digest agg ..... ‖ foundational → unlocks #171(agg), #106-agg, Delta C counts
  #103  eval variance & saturation .............. ‖ independent (eval runner exists) → prereq for #110
  #107  knowledge ablation ...................... ‖ independent (eval harness exists)
  #111  process eval via trend stream ........... ‖ independent (trend stream exists) → produces evidence for #112

WAVE 3 — DEPENDENT MEASUREMENT + LOOP TAIL
  #110  persona-vs-context-boundary ............. → sequenced after #103 (needs variance to trust the delta)
  Delta C  frequency→lever escalation ........... → after Delta D (cross-machine counts); single-machine start OK
  Delta A/B  raw-log tier + methodology lens .... → after Delta D; LARGEST; gated behind the digest; do last
  #112  ADR-0006 Review → Accepted/Rejected ..... → after #111 evidence (decision, not implementation)
```

Critical path (longest chain): **Delta D → Delta A/B**, and **#103 → #110**. Everything else parallelizes around these two chains.

---

## Wave 0 — Bugs (start here)

All three touch different files and can be worked **in parallel**.

### #173 — `/plan` prompt path fix ‖ independent · trivial

- **Cause (verified):** `plugins/dev-team/skills/plan/SKILL.md` references `prompts/plan-review-*.md` skill-relative; the four templates actually live at `plugins/dev-team/prompts/`.
- **Fix:** correct the four references to `${CLAUDE_PLUGIN_ROOT}/prompts/plan-review-*.md` (Option 2 — these are shared plugin-root assets). Keep them at the plugin root.
- **Acceptance:** a `/plan` run seeds all four reviewer personas from their template files (no inline fallback). Add a doc/structural test asserting each referenced path resolves to an existing file.
- **Friction removed:** plan reviewers silently degrade to inline briefs today → rework/quality loss.

### #170 — stamp `fixLoopIteration` marker at runtime ‖ independent · **spike first**

- **Step 1 (spike, gates the rest):** determine whether a plugin can get `fixLoopIteration`/`orchestrationPhase` onto the transcript records `cost_meter.py` reads. The marker is read by the meter and lives only in fixtures today.
- **Step 2a (if feasible):** stamp the marker from the review→fix orchestration so live sessions attribute per-iteration spend.
- **Step 2b (if NOT feasible):** honor the issue's fallback — document the limitation in the cost-report SKILL and drop/relabel the per-iteration claim rather than ship an always-`unattributed` field.
- **Acceptance:** a real ≥2-iteration session produces non-`unattributed` `by_iteration` buckets, **or** the limitation is documented and the misleading field removed.

### #171 — cost-regression real baseline ‖ independent (quick) · agg → after Delta D

- **Fork to decide first:**
  - **Quick (now, independent):** commit a sanitized metrics-only baseline so `cost-regression-check.sh` runs the *real* check, and decide hard-fail vs warn given a non-deterministic meter.
  - **Durable (later):** derive the baseline from the **aggregated** session-digest → **sequenced after Delta D**.
- **Recommended:** ship the quick local baseline now to make the gate real; upgrade to the aggregated baseline when Delta D lands.
- **Acceptance:** a PR whose measured cost exceeds tolerance is flagged by CI using **real** data (not the synthetic self-test); baseline source + privacy boundary documented.

**Wave 0 exit:** no open bugs; the cost gate enforces something real; `/plan` reviewers are seeded correctly.

---

## Wave 1 — Hygiene / scope (parallel with Wave 0)

### #105 — delete Multi-LLM/Gemini table ‖ independent · trivial

Remove the unimplemented Gemini/Multi-LLM routing table and any vestigial references from
`plugins/dev-team/CLAUDE.md`. Extend the prose-honesty sensor to keep it from returning.
**Acceptance:** no shipped prose promises a routing capability no code provides.

### #115 — reconcile `agent-ast.md` orphan spec ‖ independent · trivial

Decide: promote to a tracked epic, relocate to `docs/spikes/` as an explicit not-scheduled spike, or
archive. **Acceptance:** no orphan spec at repo root; the idea is tracked or explicitly shelved.

### #106 — narrow the telemetry beacon ‖ independent

No new build — a scope decision plus doc. Confirm the beacon stays the cheap default-off counter; do
**not** grow it into the loop (that is `/session-review` + Delta D). **Acceptance:** the beacon's role
boundary is documented; the issue is closed as "narrowed, intentionally minimal."

---

## Wave 2 — Loop spine + independent measurement

### Delta D — cross-machine session-digest aggregation ‖ foundational

Per-host `metrics/session-digest-<host>.jsonl` pushed to a **separate private repo** (env-var remote);
union read by `/session-review` and `/harness-audit`. Raw `~/.claude/projects` logs never leave the
machine — only the metrics digest aggregates. **Unlocks** #171's durable baseline, #106's aggregation
question, and cross-machine counts for Delta C. **Needs a new issue filed.**

### #103 — eval variance & saturation ‖ independent → prereq for #110

Multi-trial (pass@k) eval runs persisted to an append-only log; flap detection + quarantine signal for
the #99 gate. **Acceptance:** report shows per-agent pass@k and per-fixture flap rate; flaky fixtures auto-flagged.

### #107 — knowledge ablation ‖ independent

Run the eval corpus with each knowledge file ablated; diff grades → per-file "retrieval value." Flag
zero-impact files for removal/consolidation. **Acceptance:** ranked impact report; zero-impact files listed.

### #111 — process eval via the trend stream ‖ independent → evidence for #112

**Narrowed:** no synthetic A/B. Use `/session-review`'s trend stream to find which phases/gates
correlate with high rework or bypass. **Acceptance:** a report ranks gates by rework/bypass correlation
from real sessions.

---

## Wave 3 — Dependent measurement + loop tail

### #110 — persona-vs-context-boundary → after #103

Run review agents with persona frontmatter ON vs OFF (same fixtures/knowledge), multi-trial; compare
pass@k using #103's variance to trust the delta. If personas don't improve detection, propose a
context-boundary migration and quantify maintenance/token savings. **Acceptance:** per-agent persona-on/off
delta with a data-grounded recommendation.

### Delta C — frequency→lever escalation → after Delta D

Make recurrence drive response strength (rare → hint; frequent + deterministically-matchable → promote to
a hook, validated via `/agent-eval`). Single-machine start OK; cross-machine counts need Delta D.
**Needs a new issue filed.**

### Delta A/B — raw-log tier + methodology lens → after Delta D · largest · last

Optional per-log agent pass over the top-N worst sessions the digest flags; adds semantic frictions
(hallucinated citations) and the operator `methodology` lens a metrics digest can't see. Cost bounded by
gating behind the digest; output held to metrics-only/no-quote discipline. **Needs a new issue filed.**

### #112 — ADR-0006 Review → Accepted/Rejected → after #111

Not an implementation task. When #111 produces evidence on whether current gates cause friction, move
ADR-0006 from **Review** to **Accepted** (with a migration slice) or **Rejected** (with rationale).

---

## New issues to file

The loop deltas aren't all tracked yet:

- **Delta D** — cross-machine session-digest aggregation (overlaps #171's durable baseline; reference both).
- **Delta C** — frequency→lever escalation rule.
- **Delta A/B** — raw-log tier + methodology lens.

(#171 and #106 already partially cover Delta D's territory — cross-link rather than duplicate.)

## Suggested execution order

1. **Wave 0 bugs in parallel** (#173, #170-spike, #171-quick) + **Wave 1 hygiene in parallel** (#105, #115, #106).
2. **Wave 2**: start **Delta D** and **#103** (both unblock Wave 3); run **#107** and **#111** alongside.
3. **Wave 3**: **#110** (after #103), **Delta C** then **Delta A/B** (after Delta D), **#112 decision** (after #111).

## Done definition

# 98 closes when: no open bugs; the cost gate enforces real data; the loop spine aggregates across
machines and escalates by frequency; knowledge/persona/process value are quantified; scope is honest
(#105) and hygiene clean (#115); and ADR-0006 is Accepted or Rejected. Per the North Star, any item
that cannot name the friction it removes is dropped, not carried.
