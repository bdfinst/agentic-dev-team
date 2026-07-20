# Record: mechanically enforcing "prefer Python over bash"

> **Status — Implemented in [#702](https://github.com/bdfinst/agentic-dev-team/issues/702).**
> `scripts/check-python-only.py` was extended to cover `.sh` **and** `.bats`
> repo-wide (outside an explicit allowlist), flipped to **blocking by default**
> (`--advisory` opts back out), and wired into **both** gates —
> `scripts/ci-local.sh` (`chk_python_only`, pre-push) and CI
> (`.github/workflows/plugin-tests.yml`, folded into the shell-hygiene job).
> ADR 0014's "Enforcement" line now records this. This page is retained as the
> design record behind that change; it is written in the past tense throughout.

**Exploration issue**: [#701](https://github.com/bdfinst/agentic-dev-team/issues/701) — exploration only, no mechanism was implemented in that issue.
**Implementation issue**: [#702](https://github.com/bdfinst/agentic-dev-team/issues/702) (see [Follow-up](#follow-up-implementation-issue) for the delivered scope).

## Problem

CLAUDE.md's Working Rules say "Prefer Python over bash, repo-wide, unless bash
is strictly required." Today that rule is prose, caught only if a human or
review agent happens to notice a new `.sh`/`.bats` file in a diff. It has
already regressed once: issue #700 documents
`tests/skills/mutation_kill_slice_loop_refinements_tests.bats` landing via
issues #667/#681 after epic #668 had ported every `tests/skills/*.bats` file
to pytest. Per this repo's own stance ("rules the agent should follow land as
hooks / ci-local.sh checks, not prose that can be ignored" —
`feedback_prefer_hooks_over_prose_enforcement`), this is a mechanical-gate gap.

## What already exists (and isn't wired in)

`scripts/check-python-only.py` already implements the diff-based mechanism
option 1 describes in the issue: it runs `git diff --diff-filter=A --name-only
<base>...HEAD`, filters for newly **added** `.sh` files, checks them against an
`AUDIT_EXCLUSIONS` set, and reports violations. It was added in PR #581
(commit `f2fb9e9d`) as the ADR 0014 enforcement script promised in that ADR's
"Enforcement" line. It has three material gaps:

1. **Not wired into anything.** It appears in no `ci-local.sh` check, no
   `.github/workflows/*.yml` job, and no pre-push path. `grep -rl
   check-python-only tests/ .github/` returns nothing. It has run zero times
   in CI since it was written — dead code, not a dead gate.
2. **Scoped only to `plugins/dev-team/`.** #700's regression was under
   `tests/skills/`, outside this script's path filter, so even wired in it
   would have missed the actual regression that motivated #701.
3. **Only checks `.sh`, not `.bats`.** #700's regression file was `.bats`.
4. **Advisory-only by design** (`--block` is opt-in), because ADR 0014 gated
   blocking mode on "the epic's Phase 3 gate." ADR 0015 (2026-07-02) now
   records that phase as complete for `plugins/dev-team/` — the gate this
   script was waiting on has landed.

The chosen move was to **extend and wire in this existing script**, not write a
new one. It already had the correct diff-based shape (`--diff-filter=A`, an
explicit exclusions set, `--base`/`--block`/`--list` flags) that issue #701's
option 1 asked for, and it already had ADR 0014 as its authority — no new ADR
needed, just an update noting the enforcement finally landed.

## Mechanism (as implemented): extended `check-python-only.py` + wired into both gates

**Chosen from the issue's three options: option 1 (CI/local diff gate),
generalized to cover `.bats` and a repo-wide (allowlisted) scope, run in both
`ci-local.sh` (pre-push, local) and a CI workflow job (PR, remote) — the
repo's existing dual-gate pattern.** Option 2 (PreToolUse hook at authoring
time) and option 3 (one-time baseline+drift) were addressed below as
considered-and-rejected-for-now, with a note on when option 2 becomes worth
revisiting.

### 1. Extend the script's scope and allowlist

Changes to `scripts/check-python-only.py`:

- **Add `.bats` to the tracked extensions**, not just `.sh`. `#700`'s
  regression was `.bats`; a rule that only watches `.sh` half-covers the
  problem this issue exists to close.
- **Broaden the path scope from `plugins/dev-team/` to the whole repo**, then
  carve out an explicit directory allowlist instead of a single path prefix.
  Rationale for each entry:

  | Allowlisted path | Why it's exempt |
  | --- | --- |
  | `plugins/dev-team/install.sh` (exact file) | Existing ADR 0014 exception — the two-line shell trampoline that must run before Python is guaranteed on `PATH`. |
  | `plugins/security-assessment/**` | A different plugin, shell-based by design (ADR 0014/0015 explicitly scope the Python rule to `plugins/dev-team/` only). |
  | `tests/security-assessment/**` | Test suite for the above; same rationale. |
  | `evals/**` | Eval fixtures deliberately exercise shell-script scenarios (e.g. `evals/codebase-recon/fixtures/polyglot/scripts/deploy.sh`) as **test data**, not shipped tooling. A fixture that's supposed to look like an arbitrary repo's shell script needs to stay a shell script. |
  | `.claude/*.sh` (exact files: `cloud-setup.sh`, `install-dev-team.sh`) | Same install-trampoline rationale as `install.sh` — these run in a `SessionStart` hook / cloud setup-script context before this repo's Python toolchain is guaranteed present. |
  | `tests/lib/hermetic_tests.bats` (exact file) | Named as out-of-scope-here in #700 itself; owned by #677 (retire bats-core), not this gate. Existing-file edits aren't flagged anyway (the script only checks **added** files), so this entry only matters if the file is ever deleted and re-added. |

  Everything else repo-wide — including `tests/skills/`, `tests/repo/`,
  `tests/agents/`, `tests/commands/`, `tests/docs/`, `tests/knowledge/`, and
  **repo-root `scripts/*.sh`** — is in scope for the gate.

- **Repo-root `scripts/*.sh`: block new additions, don't just discourage
  them.** CLAUDE.md already says existing ones are "convert opportunistically
  when touched" — that's a statement about the ~20 legacy files, not a license
  to keep adding more. A new repo-root `.sh` script has the exact same
  regression risk as a new plugin one (untested-until-CI, another shellcheck
  surface, another bats-vs-pytest fork). Blocking new ones (with the same
  allowlist escape hatch below) keeps the "convert opportunistically" carve-out
  honest — it shrinks the shell-script surface instead of quietly growing it
  around the edges.
- **False-positive / escape-hatch handling**: same mechanism as the existing
  `AUDIT_EXCLUSIONS` set, generalized to a directory-or-exact-path list, with
  a **required one-line comment justifying each entry inline in the source**
  (the table above is the pattern to follow). A genuinely-necessary new shell
  script is a one-line source diff to `check-python-only.py` in the same PR —
  reviewed like any other code change, not silently exempted by a separate
  untracked list. This makes "we needed bash here and here's why" an explicit,
  reviewable decision rather than a gate the author routes around.

### 2. Flip default mode to blocking

ADR 0014 gated `--block` on "the epic's Phase 3 gate" being reached. ADR 0015
records that gate as met for `plugins/dev-team/` (2026-07-02). The
implementation therefore flipped the script's **default** behavior to blocking
(blocking is now the default; an `--advisory` flag keeps the old warn-only
behavior for anyone who wants it locally), and updated ADR 0014's "Enforcement"
line to point at this doc + ADR 0015 instead of "Advisory in Phase 0-2."

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
to the `CHECKS` array (near `chk_rules_vs_prompts`, since both are
prose-to-mechanical boundary sensors over repo conventions). This makes it
part of the default full run and therefore part of what the `pre-push` hook
runs before every push — the same local gate `chk_rules_vs_prompts` gets
today. It follows the file's existing `BASE`/`HEAD` plumbing (used today only
by `chk_eval_semver`), so no new argument-parsing plumbing is needed.

### 4. Wire into CI (`.github/workflows/plugin-tests.yml`)

The workflow already dispatches `ci-local.sh --only=<comma-list>` per job.
Add `chk_python_only` to the same `--only=` group as
`chk_shellcheck_helpers,chk_shellcheck_tests,chk_sa_shell_suite` (line 42) —
it's conceptually the same "shell hygiene" job, and `check-python-only.py`
needs `git diff` against the PR's actual base ref, which that job step
already has checked out with fetch-depth sufficient for shellcheck's own
diffing needs (verify fetch-depth covers the merge-base; if not, add
`fetch-depth: 0` or the existing shallow-fetch pattern the shellcheck step
already uses). This keeps the required-status-check job count unchanged —
no new job, just one more check folded into an existing one.

### Dual-gate coverage answered directly

Yes — wire both, per this repo's existing dual-gate pattern (`chk_rules_vs_prompts`,
`chk_shellcheck_*`, etc. all run in both places today via the shared
`ci-local.sh --only=` dispatch). Local pre-push catches the regression before
it's pushed; CI catches it if someone pushes with `--no-verify` or the local
hook is skipped/misconfigured. Since both call the same `ci-local.sh`
function calling the same script, there's no duplicated logic to keep in
sync — just two invocation sites.

## Options considered and not recommended (for now)

**Option 2 — PreToolUse hook blocking `Write`/`Edit` of new `.sh`/`.bats`
paths at authoring time.** Rejected as the *primary* mechanism because:

- It only catches files created via Claude's own `Write`/`Edit` tools inside a
  Claude Code session — not files added via `git apply`, a human editor, `mv`,
  or a script. The diff-based gate is authoring-tool-agnostic and catches
  every path a new file can enter the tree.
- It would duplicate the allowlist logic in two places (a Python hook script
  reading the same exemption list as `check-python-only.py`) for a benefit
  that's purely about *when* the author is told, not *whether* the rule is
  enforced.
- It's a legitimate **future enhancement**, not a replacement: once
  `check-python-only.py`'s allowlist logic is extracted into a small shared
  module (`scripts/lib/python_only_allowlist.py` or similar), a thin
  `PreToolUse` hook could import that module and warn at write-time,
  shortening the feedback loop from "next push" to "next keystroke" — worth
  revisiting once the diff-gate is proven in CI and the allowlist has
  stabilized. Filed as a "nice to have, not blocking" note in the follow-up
  issue rather than in scope for the first cut.

**Option 3 — one-time baseline snapshot + drift check.** Rejected as
redundant with the diff-based approach: `check-python-only.py`'s
`--diff-filter=A` semantics already give an equivalent "does the tracked set
grow" answer without needing a separately-maintained baseline manifest file
that itself needs updating on every legitimate allowlist change. A baseline
file is one more artifact that can go stale between the manifest and the
allowlist in `check-python-only.py`; the diff-based check has a single
source of truth (the script's own exclusion table).

## Change surface (delivered)

- `scripts/check-python-only.py`: extended the extension filter to `.sh` +
  `.bats`, broadened scope repo-wide with the allowlist table above, flipped the
  default to blocking (kept `--advisory` opt-out), and updated its docstring +
  `AUDIT_EXCLUSIONS` naming/shape to reflect the directory-allowlist
  generalization. New pytest coverage landed in `tests/scripts/test_check_python_only.py`
  for: new `.bats` under an allowlisted dir → pass; new `.sh` under
  `plugins/security-assessment/` → pass; new `.sh` under `scripts/` (not
  allowlisted) → fail; new `.sh` under `plugins/dev-team/` → fail; edited
  (not added) existing `.bats` → pass (diff-filter=A semantics unchanged).
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
