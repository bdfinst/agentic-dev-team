# Static self-heal pass (mechanism)

The deterministic pre-pass that `/build`'s inline review checkpoints run
**before** the semantic review sequence: scoped static-analysis tools fix or surface
mechanical findings so semantic reviewers spend their context on what static
analysis cannot see. This file is the **single source of truth** for the
mechanism — scoping, lanes, the shared fix loop, the attempt cap, detection
and provider binding, granularity, ordering, and metrics. Language lanes
(which tools, exact invocations, flags, adapters, install scripts) are
registered separately in the [**Build-time lanes** registry](../../static-analysis-integration/references/tool-configs.md)
(`${CLAUDE_PLUGIN_ROOT}/skills/static-analysis-integration/references/tool-configs.md`)
and must not restate anything specified here.

This pass is additive to, and does not modify, `/code-review`'s existing
`static-analysis-integration` pre-pass — that remains the backstop at step 6
of the build, covering all files modified during the build rather than a
single checkpoint's changed set.

## Placement — existing checkpoints only

The pass runs **wherever a review checkpoint already runs, and nowhere
else** — no second, finer-grained schedule:

- **Per-step checkpoint** (`complex` steps, step 4 sub-step 4): run the pass
  now, before the step's semantic review.
- **Slice-boundary checkpoint** (batched `standard`/unspecified steps, step 4
  sub-step 6): run the pass once over the slice's accumulated changes.
- **`trivial`-only slices get no build-time static pass** — their files are
  covered by `/code-review`'s static-analysis pre-pass at step 6, the
  backstop. Inventing a checkpoint for trivial steps would contradict the
  granularity rule this pass reuses.

The pass binds to **checkpoints, not to a cadence**: if the checkpoint
schedule changes, the pass rides the new schedule without modification.

## Opt-out toggle

`DEV_TEAM_STATIC_SELF_HEAL=off` skips the entire static self-heal pass. The
detection ladder short-circuits **before any probe** — no lane tool is
invoked, one info line notes the skip, and the checkpoint proceeds straight
to the semantic sequence. Any other value (or unset) leaves the pass enabled.
Mirrors the `DEV_TEAM_REVIEW_VALUE=off` convention.

## Lane registry

A **lane** is: a language, its file extensions, and up to two **capability
slots** — an optional **autofix** slot (mechanical pre-fix) and an optional
**diagnostic** slot (verify) — each carrying an **ordered provider list**,
plus a detection probe per candidate provider. Lanes are registered in the
"Build-time lanes" section of
`${CLAUDE_PLUGIN_ROOT}/skills/static-analysis-integration/references/tool-configs.md`.

**Zero registered lanes make this pass a structural no-op**: every partition
is empty, every lane skips, and the checkpoint proceeds unchanged. A language
whose lane is not yet registered is simply skipped (degradation rung 3).

## Scoping — what "changed files" means

Only findings in changed files enter the loop. Two cases, matching the two
checkpoint sites:

- **Per-step checkpoint:** the step's work is still uncommitted when the
  checkpoint runs, so the scope is the working tree vs `HEAD` — plus
  untracked files, because `git diff HEAD` alone misses brand-new files and
  TDD steps create new test/source files constantly:

  ```bash
  { git diff --name-only --diff-filter=ACM HEAD;
    git ls-files --others --exclude-standard; } | sort -u
  ```

- **Slice-boundary checkpoint:** record
  `slice_start_sha=$(git rev-parse HEAD)` immediately before the slice's
  first step begins (under concurrent dispatch each slice has its own
  worktree, so this is unambiguous per slice). Scope is
  `git diff --name-only --diff-filter=ACM $slice_start_sha` plus untracked as
  above. This naturally includes files touched by the slice's `trivial`
  steps — deterministic tools are cheap.

Resolve the set once per checkpoint, and **re-resolve at the start of each
retry attempt** — agent fixes may add files. `--diff-filter=ACM` excludes
deletions deliberately: you can't lint a deleted file.

**Partition by extension into lanes** and dispatch only lanes with matching
files. Do not hard-code an extension list — partition by the extensions of
whatever lanes are registered, so adding a lane never touches this mechanism.
**A lane whose partition is empty is never dispatched — no lane tool is ever
invoked with an empty file list.** (Load-bearing: some tools treat an empty
file list as "process everything", others error on empty input.)

Scoping is enforced either at invocation (pass the file list) or by
post-filtering results (the C# accommodation below). The semantics are
identical either way.

## Detection and provider binding

Probe each registered lane's slots **once per `/build` run** (not per
checkpoint) and cache the result, mirroring `static-analysis-integration`'s
tool-map. Per slot, probes walk the **ordered provider list** in order and
**bind the first provider that is present and configured in the project**;
later providers are not probed once one binds.

**Bind, don't replace:** an existing, configured tool is never displaced by
the plugin's default. The default heads each list and doubles as the
**last-resort provider** — the one the rung-3 install hint and
`/project-init` install, and only when no recognized provider is found.
`/build` itself never installs anything. (The default counts as configured by
presence alone — it honors project config when present and falls back to its
own defaults otherwise.)

Probe form is provider-defined, but **probes check repo-local install
locations first, then PATH** — a repo-level install must be found even when
nothing is user-installed (project-local `node_modules/.bin`, a repo-local
tool directory, an active project venv).

### Provider qualification contract

A tool is eligible as a provider only if it:

- **(a)** runs against a scoped file list;
- **(b)** emits machine-readable output that can reach the finding pipeline —
  native SARIF, or a ≤ 40 LOC adapter in `static-analysis-integration`;
- **(c)** fits the latency budget of the checkpoint granularity it runs at —
  a qualifying-but-slow provider may still be bound with its lane **demoted**
  to slice-boundary granularity only, with one info line telling the user the
  fast default exists;
- **(d)** has deterministic exit codes.

Recognized-provider lists are deliberately short — each provider needs an
adapter and a registry row someone maintains; this is not an open-ended
plugin system. **A present tool that fails the contract binds nothing.** It
is reported honestly (which item it fails and why), and the default is
offered *alongside* it — never as a silent replacement.

### Degradation ladder

Evaluated per lane on each slot's *bound* provider (a slot whose entire
provider list binds nothing is "missing"):

1. **Diagnostic present, autofix missing** → run diagnose-only (skip the
   pre-fix).
2. **Autofix present, diagnostic missing** → run fix, verify with the autofix
   tool's own check mode.
3. **Both missing, or no lane row registered for the language** → skip the
   lane with one info line using `static-analysis-integration`'s install-hint
   format. Never a failure.
4. **Tool present but crashes / config error** (as opposed to reporting
   findings) → treat as missing for this run: warn once, skip the lane,
   continue. A broken linter must not block a green build.

Rung-3 install hints name the slot's **default (last-resort) provider** and
carry its **repo-level** install command — the project-local,
versioned-with-the-repo form — never a user-level/global form, so following a
hint keeps the repo's toolchain reproducible for every contributor and CI.
Hints may append "or run `/project-init`" as the one-command path to the same
repo-level install. Per-lane setup, config, and verification commands for
users live in the [per-language setup guide](../../static-analysis-integration/references/language-setup.md).

## The shared fix loop (one loop, both tool kinds)

```text
attempt = 0
loop:
  re-resolve changed-file set (per Scoping)
  if lane has an autofix tool:
      run <autofix-tool> on scoped files          # mechanical pre-fix
  run <verify> on scoped files                     # diagnostic tool, autofix tool in
                                                   # check mode, or post-filtered SARIF
  if no findings in scoped files: lane passes — done
  attempt += 1
  if attempt > 2:
      escalate (below)
  hand remaining findings to the coding agent using static-analysis-integration's
  context-injection framing, repurposed as a fix directive: fix these specific
  findings, nothing else
  coding agent edits; loop
```

One loop, not two branches: a "retry" that re-runs a deterministic tool on
unchanged input produces identical output by definition — a retry only means
something if the coding agent edits between attempts, so the agent hand-off
is *inside* the loop for both tool kinds.

- **Partial autofix is covered by construction:** any finding that survives
  the pre-fix is, by definition, not auto-fixable this round — it goes to the
  coding agent on the *same* attempt. Never burn retries hoping a
  deterministic fixer changes its mind.
- **Diagnose-only tools** run the identical loop minus the pre-fix line.
- **Counters:** `attempt` is **per lane, per checkpoint**. It resets at every
  checkpoint. Lanes count independently: one lane's escalation doesn't
  consume another's attempts. In a mixed-language checkpoint, run every
  active lane to pass-or-cap before escalating, so the escalation report is
  complete in one shot.
- **Cross-lane invalidation — none:** a lane that passed its verify **stays
  passed for the checkpoint**, even when a later agent-fix attempt for
  another lane edits files matching the passed lane. Per-attempt
  re-resolution affects only lanes still in their loop; the final
  `/code-review` pre-pass backstops the drift.
- **Tests stay green:** after any agent-fix edit, re-run the tests that
  confirmed GREEN before the lane's next verify. A static fix that breaks a
  test is a failed attempt handled inside this loop — not a reason to
  re-enter RED.

### Escalation

Cap exhaustion (a lane still failing after 2 agent-fix attempts) reuses the
build skill's existing Escalation convention — no new one. Stop the
checkpoint, run the [Systematic Debugging](../../systematic-debugging/SKILL.md)
one-liner (reproduce, root cause, one sentence), and surface the remaining
findings plus that diagnosis to the user — never just an attempt count.

## C# accommodation — ErrorLog rides the build

The C# lane's diagnostic source is the Roslyn ErrorLog SARIF emitted by the
same `dotnet build` that confirms GREEN — not a separate scoped invocation.
Two consequences the mechanism owns:

- **Scoping is post-hoc:** filter the SARIF `results[*]` to the checkpoint's
  changed-file set instead of scoping the invocation.
- **Freshness:** verify against the SARIF from the most recent build. If any
  `.cs` file changed after that build (a mechanical pre-fix rewrote files, or
  an agent-fix landed), re-run `dotnet build` to regenerate before filtering
  — for the C# lane, "verify" *is* build-then-filter, and the build is
  already a cost the TDD loop pays.

## Ordering — deterministic first, semantic second

At every checkpoint where both run: the static self-heal loop completes first
(pass, or cap-and-escalate), then the semantic sequence exactly as the
checkpoint already orders it — spec-compliance-review, then the quality
agents, with their existing review-fix loop. Inject the static outcome into
the semantic reviewers' context using the same format
`static-analysis-integration` mandates for `/code-review`: resolved findings
need no mention; findings escalated past the cap are listed under the
"Do not re-report these issues" framing. Net effect: semantic reviewers
always see a mechanically clean (or explicitly annotated) diff.

## Metrics — fold into the existing sensor

Each checkpoint already appends one line to `metrics/review-value.jsonl`
(step 4 sub-step 7). The static pass folds into that same record — no new
file, one sensor: lane tools are appended to `agents_run`, deterministic
findings/fixes are included in `issues_found`/`issues_fixed`, static attempts
count in `fix_iterations`, and an escalated lane makes the checkpoint's
`outcome` `"escalated"`. Disabled together with `DEV_TEAM_REVIEW_VALUE=off`.
