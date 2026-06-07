# Design — `/session-review` Enhancements

> **Status:** Design (not yet implemented). Tracks the North Star (`plugins/dev-team/CLAUDE.md`).
> **Supersedes:** the earlier `telemetry-feedback-loop.md` draft, which reinvented capability the
> plugin already ships and wrongly claimed rework signals were missing. They are **not** missing —
> `scripts/session_extract.py` already extracts `token | rework | accuracy | utilization` from
> transcripts, and `/session-review` (#127/#131) already mines them, suggests improvements, and
> hands off to governed machinery (`/feedback-learning`, `/agent-eval`, `/harness-audit`,
> `token-efficiency-review`). This spec covers only the **three deltas** that loop is genuinely missing.

## 0. Why this is a delta spec, not a new loop

The feedback loop already exists and is well-engineered:

- **Deterministic, zero-token extraction** — `session_extract.py` crushes MBs of JSONL into a
  KB-sized metrics digest with no model calls ("never spend tokens to study token spend").
- **Privacy by construction** — metrics only: counts, ratios, names, basenames; correction
  keywords counted, never quoted.
- **Governed apply path** — `/session-review` *suggests, never applies*; suggestions route to
  `/feedback-learning`'s audited writes, `/agent-eval` validation, etc.

Do not rebuild any of that. The gaps below were surfaced by comparing against a peer transcript-mining
skill (Alexandre Poitevin's "session-analysis") and against the original stated need (multi-machine).

## 1. Delta A — a raw-log (semantic) tier over digest-flagged sessions

**Gap.** The metrics digest is deliberately quantitative, so it discards frictions that have **no
count-signature**:

- *the AI cited a skill as its source when that content didn't exist* — a hallucinated-citation
  pattern invisible to ratios;
- *the operator keeps deferring decisions to "later" with no owner* — a methodology habit (see Delta B).

The digest approximates user-corrections with a keyword scan (`"no"`, `"actually"`, `"revert"`), which
is a crude proxy for what an agent reading the actual exchange would catch.

**Design.** Add an **optional second tier**, gated by the first:

1. Tier 1 (unchanged): the deterministic digest ranks/triages sessions cheaply.
2. Tier 2 (new): for the **top-N worst sessions the digest flags**, dispatch one agent **per raw log**
   (one ~1MB transcript = one agent = one context boundary; fan out in parallel). Each agent reads its
   single raw log and returns semantic frictions the digest can't see.

Cost is bounded *because* Tier 1 decides where Tier 2 is worth spending — you never read every raw log,
only the few already proven expensive/thrashy. Execution maps cleanly to a Workflow: `pipeline(flagged
logs, analyze-raw, ...) → consolidate`.

**Privacy note.** Tier 2 reads raw content, so its *output* must be held to the same metrics-only/
no-quote discipline as the digest: it may report *that* a hallucinated citation occurred and *which*
artifact to fix, not paste the prompt/code. The raw log itself never leaves the machine.

## 2. Delta B — a fifth lens: operator methodology ("just me")

**Gap.** The four extracted classes (`token | rework | accuracy | utilization`) are all about the AI
and harness. None mines the **operator's own habits**, yet the highest-value findings in the peer skill
were exactly that ("you keep deferring business decisions with no owner/deadline"). No gate fixes a
human habit — but surfacing it is valuable, and it is structurally invisible to a metrics digest.

**Design.** Add a `methodology` lens, produced **only** by the Tier-1-flagged Tier-2 raw pass (Delta A).
Its suggestions have no target artifact and no hook — the hand-off is "to the human, as an observation,"
a category the report must support alongside the existing artifact-targeted kinds.

## 3. Delta C — explicit frequency → lever-strength escalation

**Gap.** `/session-review` has the trend stream (`metrics/session-digest.jsonl`, #129) but no stated
rule turning *recurrence* into *response strength*. The peer skill states it crisply: a friction *"caught
13 times across sessions"* earned promotion from advice to an enforced **hook**.

**Design.** Make escalation an explicit ranking rule in the analysis step, driven by the trend stream:

| Recurrence (across sessions) | Determinism of the pattern | Recommended lever |
|---|---|---|
| Rare / one-off | any | hint / observation only |
| Recurring | judgment-shaped (no reliable matcher) | instruction-file rule → `/feedback-learning` |
| Frequent | deterministically matchable | **promote to a hook** (validate via `/agent-eval` first) |

This reuses the existing rules-vs-prompts ≤10% FP policy as the "deterministically matchable" test.

## 4. Delta D — cross-machine aggregation (the original stated need)

**Gap.** `/session-review` mines `~/.claude/projects/<current-project>/*.jsonl` — **single machine**. The
stated goal is to learn across *the multiple machines the author uses*.

**Design.** Aggregate the **trend stream** (`metrics/session-digest.jsonl`), not the telemetry beacon and
not raw logs:

- Each machine appends host-suffixed digest records / writes `metrics/session-digest-<host>.jsonl`.
- A sync step pushes/pulls those files to a **separate private repo** named by env var
  (e.g. `DEV_TEAM_TELEMETRY_REMOTE`). `metrics/*.jsonl` stays gitignored in *this* repo — the gitignore
  is untouched; aggregation targets the private repo only.
- Per-host filenames make the merge **conflict-free by construction** (add-files, never line-merge).
- `/session-review` (and `/harness-audit`, which already consumes the trend stream) reads the union of
  host files so recurrence in Delta C is counted **across machines**, not just one.
- Absent the env var, everything stays local and the loop still runs on one machine's data.

**Why git over a synced folder/hosted store:** versioned history (recurrence analysis needs time),
no new secret beyond an SSH key, conflict-free with per-host files, and it reuses the append-only-log
convention already in the repo.

## 5. Acceptance criteria

- [ ] Tier 2: for digest-flagged worst sessions only, a per-log agent pass runs and returns semantic
      frictions (e.g. hallucinated citations) the digest cannot; every raw log is one agent's sole input;
      Tier 2 output is metrics-only/no-quote.
- [ ] A `methodology` lens produces human-directed observations with no artifact/hook target.
- [ ] The analysis step applies the recurrence→lever table, using the cross-machine trend stream for counts.
- [ ] Each machine writes host-suffixed digest files; a sync command pushes/pulls them to a private repo
      named by env var; absent the env var, nothing leaves the machine and the loop still runs locally.
- [ ] No raw prompt/code/path content is ever written to any report or to the aggregation repo.

## 6. Build order

1. **Delta D (cross-machine aggregation)** — smallest, matches the literal stated need, and makes Delta C
   meaningful (recurrence across machines). Transport + host-suffixed files + union read.
2. **Delta C (escalation rule)** — pure analysis-step logic over the now-aggregated trend stream.
3. **Delta A + B (raw-log tier + methodology lens)** — the largest and most token-spending; gate it
   behind the digest so cost stays bounded. Do last.

## 7. What NOT to do

- Do not rebuild extraction, privacy handling, or the suggest-never-apply governance — they exist.
- Do not aggregate the telemetry beacon or raw logs across machines — aggregate the **digest** only.
- Do not let Tier 2 read every session — only the few Tier 1 already flagged as worst.
