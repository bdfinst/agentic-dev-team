---
name: apply-test-doubles
description: >-
  Apply `/cd-test-architecture`'s Step 4b build-vs-document decision logic
  against an existing, saved assessment report — or, when no valid report
  path is given, against a target to assess first — without re-running the
  full Steps 0-6 assessment each time. Use when the user wants to revisit
  or change a component's Build/Document choice from a saved
  cd-test-architecture report, says "apply the test doubles", "re-run
  Step 4b", "change the build-vs-document decision", or cites the
  `/apply-test-doubles <path>` command from a test-double setup guide.
argument-hint: "[<report-path-or-target>] [--component <name>]"
role: worker
user-invocable: true
---

# Apply Test Doubles

Role: worker. Applies `../cd-test-architecture/SKILL.md`'s Step 4b
build-vs-document decision logic against a resolved report — one already
saved on disk, or a fresh one produced by assessing a target — without
re-running the full Steps 0-6 assessment when a valid report already
exists.

You have been invoked with the `/apply-test-doubles` command.

## Parse Arguments

Arguments: an optional positional `<report-path-or-target>` and an optional
`--component <name>`.

- `<report-path-or-target>` — a path to a previously saved
  `/cd-test-architecture` report, or a target application/repo path to
  assess when no such report exists yet. May be omitted entirely — see the
  absent-path row below.
- `--component <name>` — scope processing to one named component.
  Forwarded into the `/cd-test-architecture` self-invocation on the target
  path; applied as a post-hoc filter over the report's already-existing
  rows on the fast path.

## Steps

### 1. Resolve report or target

Every invocation resolves to exactly one **report** before anything else in
this skill runs — either an existing one read directly (the fast path), or
a fresh one produced by assessing a target (the target path). This is one
branch point, not two independently-described procedures: whichever state
below applies, resolution ends at the same "read the report" step.

**Resolution states:**

| `<report-path-or-target>` | Resolves to | Path |
|---|---|---|
| Absent | the current repo, passed to `/cd-test-architecture` as an explicit resolved cwd/repo path argument — never a bare invocation, which would trigger `cd-test-architecture`'s own interactive target prompt | target |
| Given, non-empty, resolves to no file or directory on disk | the given string, passed to `/cd-test-architecture` as its explicit target argument | target |
| Given, resolves to an existing directory | the given directory, passed to `/cd-test-architecture` as its explicit target argument — a directory is not a report; there is no file there to read | target |
| Given, resolves to an existing file | that file, checked against the structural validity check below | fast (if valid) / target (if not) |

**Target path.** Invoke `/cd-test-architecture` against the resolved target
(current repo / given string / given directory), always forwarding `--yes`
— so its own inline Step 4b prompt never fires; this skill's own
re-entrant Step 4b step (a later step of this skill) is the sole place the
operator is prompted, on both paths uniformly. Also forward `--component
<name>` when given, as `cd-test-architecture`'s own `--component`
argument — producing a single-component-scoped fresh assessment, not a
whole-app assessment filtered afterward. `cd-test-architecture`'s own
error handling governs an unresolvable target string; this skill does not
duplicate that validation. The freshly produced report then proceeds
through the fast path below, exactly as an existing report would.

**Structural validity check (existing-file case only).** A real
`cd-test-architecture` report carries three markers, checked together as
one cohesive procedure — not three independently-worded checks that could
drift out of sync with each other:

1. The `# CD Test Architecture` title line.
2. The `### Target architecture (per component)` heading — level 3, with
   the `(per component)` suffix.
3. A `Build/Document status` column in that section's table.

All three present → the fast path: read that report's Target architecture
table directly, and do not invoke `/cd-test-architecture`. Missing any one
of the three takes the target path too, treating the file's path string as
a target to assess — not a malformed-report error.

**Fast path: locate the companion setup guide.** Locate the companion
setup-guide artifact
(`.dev-team-reports/cd-test-architecture-<app>-test-double-setup.md`,
#1436) via the resolved report's own `**Target**` header field — the
`<app>` value recorded in the report's content — never by the report
file's name on disk, so a renamed or relocated report still resolves its
companion file correctly. When no companion file is found at the derived
path, state plainly which of two non-error cases applies:

- The resolved report's Target architecture table has zero
  off-gate-eligible rows (no row with a non-blank `Build/Document status`
  cell) — nothing was ever expected to be written for this report; take no
  further action.
- The report has eligible rows but predates #1436 (no companion file was
  ever written for it) — state this plainly, then create the setup-guide
  artifact fresh at the derived path, exactly as `cd-test-architecture`
  itself would on a first run.

### 2. Apply Step 4b's decision logic

This step is the **only** place a decision is made this invocation,
regardless of which path produced the resolved report:

- **Fast path** — Steps 0, 1, 2, 2b, 3, 3b, 5, and 6 never ran at all this
  invocation; the resolved report was already sitting on disk and was read
  directly.
- **Target path** — those same steps did run, as part of producing the
  fresh report (the `/cd-test-architecture` self-invocation in Step 1
  above), but their own inline Step 4b was a no-op — every row defaulted to
  `Document-only` with no prompt — because Step 1 already forwards `--yes`.
  This step is still the first and only place the operator is actually
  prompted.

**Cite, don't restate.** Apply exactly the decision procedure in
`../cd-test-architecture/SKILL.md`'s `### 4b. Build-vs-document decision
(off-gate adapter test doubles)` heading — its Database-specific branch, its
Downstream-service branch, and that branch's library-vs-hand-rolled
sub-question — as the single source of the build-vs-document branching
rules. That procedure is not restated here.

**Off-gate-eligibility parsing rule.** A component is off-gate-eligible
**iff** it has at least one row in the Target architecture table whose
`Build/Document status` cell holds a non-blank value. This is a literal,
table-level parsing rule, not an inferred label.

**Every eligible component is re-offered, regardless of prior status.**
Every off-gate-eligible component is re-offered this decision on every run,
regardless of its currently-recorded `Build/Document status` — including a
component already resolved to `Build (testcontainers)` or `Build (Fake)` —
so the operator may change a prior decision.

**`--component <name>` scoping.** When `--component <name>` was given and it
matches an off-gate-eligible component (per the parsing rule above), only
that component's row resolves through this decision — no other component's
row is touched. When no `--component` was given, every off-gate-eligible
component in the resolved report is processed in one batched pass, mirroring
Step 4b's own batching rule (cited, not restated).

**Unmatched or non-eligible `--component <name>`.** Two distinct cases, both
stated by the exact name given, with no action taken — never a fuzzy or
nearest-match substitution:

1. `<name>` does not appear anywhere in the resolved report's Target
   architecture table — state that `<name>` was not found in the resolved
   report, and take no further action.
2. `<name>` appears in the report but has no Target architecture row with a
   non-blank `Build/Document status` cell — state that `<name>` has no
   build-vs-document decision to apply, and take no further action.

**Zero eligible components.** Same family of outcome as the two cases above,
just with no `--component` name to name: when the batched pass (no
`--component`) or the named lookup (`--component <name>`, once past the
unmatched/non-eligible check above) finds no off-gate-eligible component,
state that there is nothing to apply and take no further action.

**Version-skew advisory (non-blocking).** Resolve the currently installed
plugin version with the same resolver `/version` and `/upgrade` already use:

```bash
sh "$CLAUDE_PLUGIN_ROOT/hooks/py.sh" "$CLAUDE_PLUGIN_ROOT/hooks/lib/plugin_version.py"
```

This prints one line, e.g. `dev-team@bfinster v10.4.0 (scope: user)` — parse
the version out of the token between `v` and ` (scope:` (here, `10.4.0`).
Compare it against the resolved report's Provenance `dev-team plugin
version` field. If they differ, emit one non-blocking advisory line naming
both versions — e.g. "this report was generated by dev-team vX.Y.Z; you're
running vA.B.C — Step 4b's decision logic may have changed since this report
was written." — before applying Step 4b's current logic, then proceed
unchanged. This never blocks or alters the decision logic itself.
