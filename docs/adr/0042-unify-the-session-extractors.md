# 42. Unify the session extractors

Date: 2026-08-27

## Status

Accepted

Supersedes [36. The two session extractors stay forked, for now](0036-the-two-session-extractors-stay-forked-1994.md)

## Context

[ADR 0036](0036-the-two-session-extractors-stay-forked-1994.md) was accepted
2026-08-25. This ADR reverses it within weeks — worth saying plainly, and
worth explaining why that is a **change of decision**, not a change of mind.

**0036's own revisit trigger had already fired when it was written.** 0036
named three conditions that would flip its "leave the shared-core question
open" stance and demand a follow-up ADR. Trigger 2 — "any future port that
itself ships an un-carried fix" — is not hypothetical: 0036's own Context
section names #1994, the port that motivated writing 0036 in the first
place, as *already* an instance of it. #1994 itself left four of #1991's
fixes behind, caught only by review. 0036 was accepted with its own revisit
condition standing, not merely at risk of it.

**#2029 crossed the fork again, independently, while 0036 was still
current.** Real per-agent `context_tokens` (#2010) landed only in the
shipped `extract_session_report.py`, leaving `session_extract.py` without
the field entirely — the identical duplication-cost shape 0036 was written
to characterize, recurring within the same short window 0036 was supposed
to hold the line for.

**0036 explicitly left the shared-core question open, and said the
evidence pointed the other way.** Its own "Boundary of the evidence"
section: *"this ADR establishes only that unifying the whole extractors is
wrong, and that porting-by-hand has failed twice. It does not establish
that a shared classification core is unworkable — the review showed the
opposite is plausible."* This ADR does not merely answer that open
question — it goes further than what 0036 contemplated: full unification
into one script with two profiles, not just a shared classification-core
module sitting beside two still-separate scripts. That wider scope is the
part that genuinely supersedes 0036 rather than settling the question 0036
deliberately left for later.

**What was measured, since 0036 noted nobody had.** 0036: *"Nor has anyone
measured the cost of building one against the cost of the next missed
port."* Epic #2040's own slices (#2042–#2045) measured it before unifying:
17 shared function names existed across the two scripts, 2 with
byte-identical bodies; among the diverged ones, `_is_subagent_transcript`
scored 0.22 similarity and `_accumulate_token_signals` scored 0.10 — two
names, two very different implementations, exactly the silent-drift shape
0036 worried about. Nine modules across the repo read `usage` blocks, using
four distinct null-handling idioms between them. That is the cost side of
the ledger 0036 said was missing; #2050 (folding the three remaining
transcript parsers onto `session_log.records`) is this epic's answer to the
other side — the cost of the *next* missed port, paid down rather than
deferred again.

## Decision

**Unify `scripts/session_extract.py` and
`plugins/dev-team/scripts/extract_session_report.py` into one script,
`plugins/dev-team/scripts/session_report.py`, selected by `--profile
maintainer|downstream`.** Both profiles ship together, under
`plugins/dev-team/scripts/`, closing #1779 at the root: the maintainer
profile — previously monorepo-only tooling, unreachable from an installed
plugin cache — is now shipped and runs from any install (#2046/#2047,
verified end-to-end against a simulated no-source-checkout install, not
merely assumed).

**What 0036 got right is preserved, not erased.** Divergence-by-consumer is
real and survives as **profiles**, not as forced erasure of the difference:
pricing, cost, rollup, `--sync-out`, `--correlate`, and `--escalate` remain
maintainer-profile-only, exactly as 0036 decided they should. The two
profiles' outputs are byte-equal to their predecessors' goldens modulo one
documented, deliberate difference: the schema-version bump (see below).
Two genuinely monorepo-only pieces of tooling that `/session-review` still
depends on — `scripts/telemetry-sync.sh` (`--cross-machine` sync) and
`scripts/eval_rawlog.py` (the raw-log semantic tier it gates) — are left
exactly where 0036's own ADR 0032 Category 2 reasoning puts them: not
shipped, both already opt-in and off by default.

**Schema eras stay tellable apart, per 0036's own hard-won lesson.** Both
profiles bump to `v3` (`session-digest/v3`, `downstream-session-report/v3`)
— a version label on the new unified entry point, not a retroactive
rewrite of history. `SYNC_SCHEMAS` is the **one** exported constant naming
every schema a reader accepts (`v1`/`v2`/`v3`); no call site literal-matches
a schema string. This directly targets 0036's own recorded failure mode:
`slim_record()` kept stamping `v1` onto `v2`-basis numbers, and
`eval_rawlog.py` exact-matched the old sync schema and silently returned an
empty ranking when the schema moved. `eval_rawlog.py` now imports
`SYNC_SCHEMAS` from `session_report.py` rather than carrying its own
literal, and a dedicated test
(`test_v3_digest_records_are_ranked_not_silently_dropped_2047`) asserts it
*finds* records in a `v3` digest, not merely that it doesn't raise.

**The classification core moved to a shared package**, `plugins/dev-team/
scripts/lib/session_log/` (`classify.py`, `discovery.py`, `records.py`,
`signals.py`, `redact.py`, epic #2040's #2042–#2045), exactly the shape 0036
said the evidence made plausible. `session_report.py` is the one sanctioned
entry point composing those primitives — not a third independent
reimplementation, which is the failure mode
`skills/code-review/scripts/repo_invariants.py`'s
`check_transcript_parsing_confined_to_session_log` (#2048) now guards
against mechanically: no module outside `session_log/` may parse a
transcript record or a `usage` block, `session_report.py` itself excepted
as the sanctioned composer, everything else allowlisted with a stated
reason or migrated.

**Both old scripts are retired** (#2048) once every real consumer was cut
over (#2047) and their own test coverage was migrated onto the new script
rather than deleted.

## Consequences

- `/session-review`'s core extraction (Extract, Analyze, Suggest, Persist
  trend) no longer requires this monorepo's own dev checkout — the actual
  #1779 fix, not merely a guard around the absence of one.
- A fix found in the shared classification core now has exactly one home
  to land in, closing the two-scripts-drift class 0036 was written to
  manage by discipline rather than mechanism. `check_transcript_parsing_
  confined_to_session_log` is the standing mechanism that replaces that
  discipline going forward.
- Three transcript parsers still exist outside `session_log/`
  (`hooks/lib/cost_meter.py`, `hooks/context_ceiling_guard.py`,
  `scripts/measure_full_file_duplication.py`), each carrying its own reason
  in `repo_invariants._TRANSCRIPT_PARSING_ALLOWLIST` and each named for
  migration in #2050 — the epic is not yet fully discharged by this ADR
  alone.
- A downstream user's `--profile downstream` output and a maintainer's
  `--profile maintainer` output now come from the same binary, so a bug
  fixed in one profile's shared logic (`session_log/`) is fixed in both
  simultaneously — the class of risk 0036 accepted as a known cost (a fix
  landing in one script and not the other) is structurally closed for
  everything routed through `session_log/`, and visibly tracked via the
  allowlist for what is not yet routed through it.

## Reconciliation with standing ADRs

- **[ADR 0032](0032-shipped-script-path-resolution-taxonomy.md)** (shipped-script
  path resolution): `session_report.py` is Category 1 (shipped and
  portable) in both profiles — every path it touches resolves relative to
  its own location inside `plugins/dev-team/`. The reclassification ADR
  0032 anticipated ("`INTENTIONAL_BARE_INVOCATION` must be reclassified as
  `KNOWN_BARE_INVOCATION` … once the script ships") is discharged, not
  triggered as a defect: #2047 moved every `/session-review` reference to a
  resolved `${CLAUDE_PLUGIN_ROOT}/scripts/session_report.py` form in the
  same slice that shipped the script, so the defect state was never
  observed live. `tests/repo/test_shipped_script_refs.py`'s
  `ESCAPE_ALLOWLIST` entry for `skills/session-review/` is *kept*, not
  removed — the two remaining monorepo-only helpers still need it.
- **[ADR 0014](0014-python-for-cross-os-scripts.md) / [ADR
  0015](0015-bash-removal-complete.md)** (stdlib-only, cross-OS Python):
  `session_report.py` and `session_log/` are stdlib-only Python, consistent
  throughout.
- **[ADR 0031](0031-raise-shipped-python-floor-to-3-10.md)** (3.10 floor):
  `session_report.py` deliberately uses `timezone.utc`, never
  `datetime.UTC` (3.11+) — the one genuine floor-sensitive difference from
  its monorepo-only predecessor, verified by actually running the
  floor-slice tests under a real 3.10 interpreter (`uv run --python 3.10`),
  not inferred from a grep.

## References

- Issues: #1779 (root cause closed), #1990/#1991/#1994 (the defect class
  0036 was written to manage), #2010/#2029 (the class recurring while 0036
  was current), #2040 (epic), #2042–#2050 (slices)
- Files: `plugins/dev-team/scripts/session_report.py`,
  `plugins/dev-team/scripts/lib/session_log/`,
  `plugins/dev-team/skills/code-review/scripts/repo_invariants.py`
- Superseded: [ADR 0036](0036-the-two-session-extractors-stay-forked-1994.md)
- Reconciled: [ADR 0032](0032-shipped-script-path-resolution-taxonomy.md),
  [ADR 0014](0014-python-for-cross-os-scripts.md),
  [ADR 0015](0015-bash-removal-complete.md),
  [ADR 0031](0031-raise-shipped-python-floor-to-3-10.md)
