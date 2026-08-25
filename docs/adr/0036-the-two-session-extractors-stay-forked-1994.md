# 36. The two session extractors stay forked

Date: 2026-08-25

## Status

Accepted

## Context

Two scripts read Claude Code session transcripts and emit a metrics-only
digest, sharing a great deal of near-identical logic — the classification
regexes, `_strip_ns`, `_text_of`, tool-call and tool-error classification,
correction-turn detection, and now the whole subagent-discovery and
attribution mechanism:

- `scripts/session_extract.py` — monorepo-only developer tooling. Feeds
  `/session-review` and the `session-digest.jsonl` trend stream this repo uses
  to judge its own harness. Carries per-model pricing, cost, rollup,
  gate-correlation and escalation commands that only make sense here.
- `plugins/dev-team/scripts/extract_session_report.py` — ships inside the
  plugin. A downstream user with no access to this repo runs it to produce one
  file they can hand to the maintainer.

The duplication has cost real correctness. Issue #1990 found that the shipped
extractor never opened subagent transcripts, missing 41% of spend; #1991 fixed
it there, and the identical defect sat in `session_extract.py` for another
release because nothing carried the fix across (#1994). Both `structure-review`
and `arch-review` raised the duplication independently while reviewing #1991.

The obvious remedy — extract a shared module — is not available.

## Decision

**The two extractors stay forked. Do not extract a shared module between
them.**

Fixes that apply to both are ported deliberately, with the porting issue
naming what must be decided rather than copied.

## Consequences

Why a shared module cannot work here:

- `plugins/dev-team/` is **shipped**, stdlib-only, and self-contained
  ([ADR 0014](0014-python-for-cross-os-scripts.md),
  [ADR 0015](0015-bash-removal-complete.md)). It runs from a bare `python3` on
  a machine that has only the installed plugin. It cannot import repo-root
  developer tooling, because that tooling is not shipped.
- The reverse import — `scripts/session_extract.py` importing from
  `plugins/dev-team/` — inverts the dependency direction: monorepo tooling
  would take a hard dependency on the shipped artifact's internals, and a
  refactor inside the plugin would break the repo's own metrics pipeline.
- A third home (a package both import) would have to be shipped inside the
  plugin to satisfy the first constraint, which just relocates the problem.

What this costs, stated plainly: a fix in one is not a fix in the other, and
the gap is silent. #1990's 41% blind spot survived in `session_extract.py`
after being fixed in its twin, which is exactly this failure mode.

What we do instead:

- A defect found in one extractor gets an issue for the other, immediately,
  naming the decisions the port involves rather than implying a copy-paste.
  #1994 is the worked example: it called out the metric-basis change, the
  field-name collision, and the harness-role and non-transcript traps.
- The two may legitimately **diverge** where their consumers differ. They do
  today: `session_extract.py` carries cost/pricing, rollup and escalation;
  the shipped one carries none of that. Divergence is not drift.
- Schema versions are bumped on both sides when semantics change, so a
  consumer can tell eras apart (`session-digest/v2`,
  `downstream-session-report/v2`).

Do not "fix" this by unifying them. If a future maintainer reaches for that,
the constraint above is why it was not done — the same shape of decision
recorded in [ADR 0034](0034-do-not-build-shared-context-pre-pass-for-duplicate-full-file-reads-1611.md)
and [ADR 0035](0035-defer-two-lane-generation-validation-concurrency-in-mutation-kill-all-1909.md).
