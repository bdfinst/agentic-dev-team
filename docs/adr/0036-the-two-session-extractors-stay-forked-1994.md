# 36. The two session extractors stay forked, for now

Date: 2026-08-25

## Status

Accepted (narrow) — the shared-core question is deliberately left open; see
**Revisit trigger**.

Superseded by [42. Unify the session extractors](0042-unify-the-session-extractors.md)

## Context

Two scripts read Claude Code session transcripts and emit a metrics-only
digest, sharing a substantial body of near-identical code:

- `scripts/session_extract.py` — monorepo-only developer tooling. Feeds
  `/session-review` and the `session-digest.jsonl` trend stream this repo uses
  to judge its own harness. Carries per-model pricing, cost, rollup,
  gate-correlation and escalation commands that exist nowhere else.
- `plugins/dev-team/scripts/extract_session_report.py` — ships inside the
  plugin. A downstream user with no access to this repo runs it to produce one
  file they can hand to the maintainer.

The duplication has now cost the same defect twice. #1990 found that the
shipped extractor never opened subagent transcripts, missing 41% of spend;
#1991 fixed it there; the identical defect sat in `session_extract.py` until
#1994. Both `structure-review` and `arch-review` raised the duplication
independently while reviewing #1991.

**The evidence against a pure "port it deliberately" answer is stronger than
this ADR originally claimed, and is recorded here rather than argued away.**
An earlier draft asserted that a shared module was impossible in both
directions. Review of #1994 falsified two of its three load-bearing claims:

- `plugins/dev-team/scripts/lib/` **already exists** as a shipped, stdlib-only
  shared-helper package (11 modules), and this repo's own `CLAUDE.md` names it
  as the established convention. A module there is importable by the shipped
  extractor as a sibling, so the "a third home would just relocate the
  problem" claim was wrong.
- `scripts/session_extract.py` **already depends on the plugin tree** in three
  places — `_load_plugin_version`, `load_registry`, and the default pricing
  path all hardcode `plugins/dev-team/...`. The "a reverse import would invert
  the dependency direction" objection describes a boundary the code does not
  currently keep.

Decisively: the #1994 port — the very mitigation this ADR proposes — **itself
left four of #1991's fixes behind**, including the `_basename` Windows-path
privacy fix, and its review caught them. "Port deliberately" demonstrably does
not hold on its own.

## Decision

**The extractors' divergent layers stay forked: discovery/CLI surface,
pricing and cost, rollup, escalation, and the report shapes. Do not unify the
whole scripts.**

**The shared classification core is an open question, deliberately not decided
here.** That core is what actually duplicates and where both defects landed:
`_VERIFY_RE` / `_CORRECTION_RE` / `_PERMISSION_RE` / `_OLDSTRING_RE` /
`_COMMIT_RE` / `_BYPASS_RE`, `_strip_ns`, `_text_of`, `_safe_name`,
`_basename`, `_AGENT_TRANSCRIPT_RE`, `_HARNESS_ATTRIBUTIONS`,
`_is_transcript_path`, `_is_subagent_transcript`.

Until that is decided, a fix found in one extractor gets an issue for the
other **naming the decisions the port involves**, and the port is reviewed
against the source fix rather than assumed complete.

## Consequences

- Schema versions are bumped on both sides when semantics change
  (`session-digest/v2`, `downstream-session-report/v2`), so a consumer can tell
  eras apart. #1994's review showed this is easy to half-apply: `slim_record()`
  kept stamping v1 onto v2-basis numbers, and `eval_rawlog.py` exact-matched
  the old sync schema and silently returned an empty ranking. Both are fixed;
  the accepted schema list now lives in one exported constant.
- The two may legitimately **diverge** where their consumers differ, and do:
  cost/pricing/rollup/escalation exist only in the monorepo one. Divergence is
  not drift.

**Boundary of the evidence:** this ADR establishes only that unifying the
*whole* extractors is wrong, and that porting-by-hand has failed twice. It does
**not** establish that a shared classification core is unworkable — the review
showed the opposite is plausible. Nor has anyone measured the cost of building
one against the cost of the next missed port.

**Revisit trigger:** any of the following flips the open question and should
produce a follow-up ADR deciding the shared core —

1. a third instance of the same defect class crossing the fork;
2. any future port that itself ships an un-carried fix (this already happened
   once, in #1994);
3. the shared-core symbol list above growing beyond what one reviewer can
   diff by eye.

Reconcile any such decision with [ADR 0032](0032-shipped-script-path-resolution-taxonomy.md),
which governs how a shipped script may resolve paths, and with
[ADR 0014](0014-python-for-cross-os-scripts.md) /
[ADR 0015](0015-bash-removal-complete.md) on the shipped tree's stdlib-only
constraint.

## References

- Issues: #1990 (41% blind spot), #1991 (shipped fix), #1994 (this port)
- Files: `scripts/session_extract.py`,
  `plugins/dev-team/scripts/extract_session_report.py`,
  `plugins/dev-team/scripts/lib/` (the existing shipped shared-helper package)
- ADRs: [0014](0014-python-for-cross-os-scripts.md),
  [0015](0015-bash-removal-complete.md),
  [0032](0032-shipped-script-path-resolution-taxonomy.md)
- Same shape of recorded decision:
  [0034](0034-do-not-build-shared-context-pre-pass-for-duplicate-full-file-reads-1611.md),
  [0035](0035-defer-two-lane-generation-validation-concurrency-in-mutation-kill-all-1909.md)
