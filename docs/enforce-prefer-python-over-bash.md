# Record: mechanically enforcing "prefer Python over bash"

> **Status — Implemented in [#702](https://github.com/bdfinst/agentic-dev-team/issues/702).**
> The change extended `scripts/check-python-only.py` to cover `.sh` **and**
> `.bats` repo-wide (outside an explicit allowlist). It flipped the script to
> **blocking by default** (`--advisory` opts back out). It wired the script into
> **both** gates: `scripts/ci-local.sh` (`chk_python_only`, pre-push) and CI
> (`.github/workflows/plugin-tests.yml`, folded into the shell-hygiene job).
> ADR 0014's "Enforcement" line now records this. This page is the design
> record behind that change. It uses the past tense throughout.

**Exploration issue**: [#701](https://github.com/bdfinst/agentic-dev-team/issues/701) — exploration only. That issue implemented no mechanism.
**Implementation issue**: [#702](https://github.com/bdfinst/agentic-dev-team/issues/702) (see [Follow-up](#follow-up-implementation-issue) for the delivered scope).

## Problem

CLAUDE.md's Working Rules say "Prefer Python over bash, repo-wide, unless bash
is strictly required." Today that rule is prose. It is caught only if a human
or review agent happens to notice a new `.sh`/`.bats` file in a diff. The rule
has already regressed once. Issue #700 documents
`tests/skills/mutation_kill_slice_loop_refinements_tests.bats` landing via
issues #667/#681, after epic #668 had ported every `tests/skills/*.bats` file
to pytest. This repo's own stance is that "rules the agent should follow land
as hooks / ci-local.sh checks, not prose that can be ignored"
(`feedback_prefer_hooks_over_prose_enforcement`). By that stance, this
regression is a mechanical-gate gap.

## What already exists (and is not wired in)

`scripts/check-python-only.py` already implements the diff-based mechanism
that option 1 describes in the issue. It runs `git diff --diff-filter=A
--name-only <base>...HEAD` and filters for newly **added** `.sh` files. It
checks them against an `AUDIT_EXCLUSIONS` set and reports violations. PR #581
(commit `f2fb9e9d`) added it as the ADR 0014 enforcement script that the ADR's
"Enforcement" line promised. It has four material gaps:

1. **Not wired into anything.** It appears in no `ci-local.sh` check, no
   `.github/workflows/*.yml` job, and no pre-push path. `grep -rl
   check-python-only tests/ .github/` returns nothing. It has run zero times
   in CI since it was written. It is dead code, not a dead gate.
2. **Scoped only to `plugins/dev-team/`.** #700's regression was under
   `tests/skills/`, outside this script's path filter. Even wired in, the
   script would have missed the actual regression that motivated #701.
3. **Only checks `.sh`, not `.bats`.** #700's regression file was `.bats`.
4. **Advisory-only by design** (`--block` is opt-in). ADR 0014 gated blocking
   mode on "the epic's Phase 3 gate." ADR 0015 (2026-07-02) now records that
   phase as complete for `plugins/dev-team/`. The gate this script was
   waiting on has landed.

The chosen move was to **extend and wire in this existing script**, not write a
new one. The script already had the correct diff-based shape that issue #701's
option 1 asked for: `--diff-filter=A`, an explicit exclusions set, and
`--base`/`--block`/`--list` flags. It also already had ADR 0014 as its
authority. No new ADR was needed, only an update noting that the enforcement
finally landed.

## Mechanism (as implemented): extended `check-python-only.py` + wired into both gates

**The change implemented option 1 (CI/local diff gate), chosen from the
issue's three options. It generalized option 1 to cover `.bats` and a
repo-wide (allowlisted) scope. It runs in both `ci-local.sh` (pre-push, local)
and a CI workflow job (PR, remote), which is the repo's existing dual-gate
pattern.** The sections below address option 2 (PreToolUse hook at authoring
time) and option 3 (one-time baseline+drift) as considered-and-rejected-for-now.
They also note when option 2 becomes worth revisiting.

### 1. Extend the script's scope and allowlist

Changes to `scripts/check-python-only.py`:

- **Add `.bats` to the tracked extensions**, not just `.sh`. `#700`'s
  regression was `.bats`. A rule that only watches `.sh` half-covers the
  problem this issue exists to close.
- **Broaden the path scope from `plugins/dev-team/` to the whole repo.** Then
  carve out an explicit directory allowlist instead of a single path prefix.
  The table gives the rationale for each entry:

  | Allowlisted path | Why it's exempt |
  | --- | --- |
  | `plugins/dev-team/install.sh` (exact file) | Existing ADR 0014 exception — the two-line shell trampoline that must run before Python is guaranteed on `PATH`. |
  | `plugins/security-assessment/**` | A different plugin, shell-based by design (ADR 0014/0015 explicitly scope the Python rule to `plugins/dev-team/` only). |
  | `tests/security-assessment/**` | Test suite for the above; same rationale. |
  | `evals/**` | Eval fixtures deliberately exercise shell-script scenarios (e.g. `evals/codebase-recon/fixtures/polyglot/scripts/deploy.sh`) as **test data**, not shipped tooling. A fixture that's supposed to look like an arbitrary repo's shell script needs to stay a shell script. |
  | `.claude/*.sh` (exact files: `cloud-setup.sh`, `install-dev-team.sh`) | Same install-trampoline rationale as `install.sh` — these run in a `SessionStart` hook / cloud setup-script context before this repo's Python toolchain is guaranteed present. |

  Everything else repo-wide — including `tests/skills/`, `tests/repo/`,
  `tests/agents/`, `tests/commands/`, `tests/docs/`, `tests/knowledge/`, and
  **repo-root `scripts/*.sh`** — is in scope for the gate.

- **Repo-root `scripts/*.sh`: block new additions, do not just discourage
  them.** CLAUDE.md already says existing ones are "convert opportunistically
  when touched." That statement covers the ~20 legacy files. It is not a
  license to keep adding more. A new repo-root `.sh` script has the same
  regression risk as a new plugin one (untested-until-CI, another shellcheck
  surface, another bats-vs-pytest fork). Blocking new ones (with the same
  allowlist escape hatch below) keeps the "convert opportunistically" carve-out
  honest. It shrinks the shell-script surface instead of quietly growing it
  around the edges.
- **False-positive / escape-hatch handling**: use the same mechanism as the
  existing `AUDIT_EXCLUSIONS` set, generalized to a directory-or-exact-path
  list. Each entry has a **required one-line comment justifying it inline in
  the source** (follow the pattern of the table above). A genuinely necessary
  new shell script is a one-line source diff to `check-python-only.py` in the
  same PR. Reviewers treat it like any other code change. A separate untracked
  list never exempts it silently. This makes "we needed bash here and here's
  why" an explicit, reviewable decision rather than a gate the author routes
  around.

### 2. Flip default mode to blocking

ADR 0014 gated `--block` on "the epic's Phase 3 gate" being reached. ADR 0015
records that gate as met for `plugins/dev-team/` (2026-07-02). The
implementation therefore flipped the script's **default** behavior to blocking.
An `--advisory` flag keeps the old warn-only behavior for anyone who wants it
locally. The implementation also updated ADR 0014's "Enforcement" line to
point at this doc and ADR 0015 instead of "Advisory in Phase 0-2."

### 3. Wire into `scripts/ci-local.sh` (local, pre-push)

Add a check function alongside the existing ones:

```bash
chk_python_only() {
  if [ -n "$BASE" ]; then
    python3 scripts/check-python-only.py --base "$BASE" --block
  else
    python3 scripts/check-python-only.py --block   # defaults to origin/main
  fi
}
```

Add `"prefer-Python-over-bash audit (check-python-only.py)::chk_python_only"`
to the `CHECKS` array. Place it near `chk_rules_vs_prompts`, since both are
prose-to-mechanical boundary sensors over repo conventions. This makes the
check part of the default full run. It is therefore part of what the
`pre-push` hook runs before every push, the same local gate that
`chk_rules_vs_prompts` gets today. The check follows the file's existing
`BASE`/`HEAD` plumbing (used today only by `chk_eval_semver`). It needs no new
argument-parsing plumbing.

### 4. Wire into CI (`.github/workflows/plugin-tests.yml`)

The workflow already dispatches `ci-local.sh --only=<comma-list>` per job.
Add `chk_python_only` to the same `--only=` group as
`chk_shellcheck_helpers,chk_shellcheck_tests,chk_sa_shell_suite` (line 42).
It is conceptually the same "shell hygiene" job. `check-python-only.py` needs
`git diff` against the PR's actual base ref. That job step already has the
base ref checked out with fetch-depth sufficient for shellcheck's own diffing
needs. Verify that the fetch-depth covers the merge-base. If it does not, add
`fetch-depth: 0` or the existing shallow-fetch pattern that the shellcheck step
already uses. This keeps the required-status-check job count unchanged. The
change adds no new job, only one more check folded into an existing one.

### Dual-gate coverage answered directly

Yes, wire both, per this repo's existing dual-gate pattern. `chk_rules_vs_prompts`,
`chk_shellcheck_*`, and others all run in both places today via the shared
`ci-local.sh --only=` dispatch. Local pre-push catches the regression before
the push. CI catches it if someone pushes with `--no-verify` or the local
hook is skipped or misconfigured. Both gates call the same `ci-local.sh`
function, which calls the same script. No duplicated logic needs syncing,
only two invocation sites.

## Options considered and not recommended (for now)

**Option 2 — PreToolUse hook blocking `Write`/`Edit` of new `.sh`/`.bats`
paths at authoring time.** Rejected as the *primary* mechanism because:

- It only catches files created via Claude's own `Write`/`Edit` tools inside a
  Claude Code session. It misses files added via `git apply`, a human editor,
  `mv`, or a script. The diff-based gate is authoring-tool-agnostic and catches
  every path a new file can enter the tree.
- It would duplicate the allowlist logic in two places (a Python hook script
  reading the same exemption list as `check-python-only.py`). The benefit is
  only about *when* the author is told, not *whether* the rule is enforced.
- It is a legitimate **future enhancement**, not a replacement. Suppose the
  `check-python-only.py` allowlist logic moves into a small shared module
  (`scripts/lib/python_only_allowlist.py` or similar). A thin `PreToolUse`
  hook could then import that module and warn at write-time. This would
  shorten the feedback loop from "next push" to "next keystroke." Revisit it
  once the diff-gate is proven in CI and the allowlist has stabilized. The
  follow-up issue files it as a "nice to have, not blocking" note, out of
  scope for the first cut.

**Option 3 — one-time baseline snapshot + drift check.** Rejected as
redundant with the diff-based approach. The `--diff-filter=A` semantics of
`check-python-only.py` already give an equivalent "does the tracked set
grow" answer. They need no separately maintained baseline manifest file that
itself needs updating on every legitimate allowlist change. A baseline file is
one more artifact that can go stale between the manifest and the allowlist in
`check-python-only.py`. The diff-based check has a single source of truth: the
script's own exclusion table.

## Change surface (delivered)

- `scripts/check-python-only.py`:
  - Extended the extension filter to `.sh` + `.bats`.
  - Broadened scope repo-wide with the allowlist table above.
  - Flipped the default to blocking (kept the `--advisory` opt-out).
  - Updated the docstring and the `AUDIT_EXCLUSIONS` naming and shape to
    reflect the directory-allowlist generalization.
- `tests/scripts/test_check_python_only.py`: new pytest coverage for these
  cases:
  - New `.bats` under an allowlisted dir → pass.
  - New `.sh` under `plugins/security-assessment/` → pass.
  - New `.sh` under `scripts/` (not allowlisted) → fail.
  - New `.sh` under `plugins/dev-team/` → fail.
  - Edited (not added) existing `.bats` → pass (diff-filter=A semantics
    unchanged).
- `scripts/ci-local.sh`: added the `chk_python_only` function + `CHECKS` entry.
- `.github/workflows/plugin-tests.yml`: added `chk_python_only` to the
  shellcheck/shell-suite job's `--only=` list.
- `docs/adr/0014-python-for-cross-os-scripts.md`: updated the "Enforcement"
  line to reflect blocking-by-default and link this doc.

## Follow-up implementation issue

Shipped under **[#702](https://github.com/bdfinst/agentic-dev-team/issues/702)** —
"Extend and wire in check-python-only.py to block new .sh/.bats files
outside allowlist." Covered the concrete script extension, the `ci-local.sh`
and CI wiring, and the pytest coverage described above.
