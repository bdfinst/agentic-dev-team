# Agentic Dev Team — Plugin Development

This is the marketplace repository for the dev-team Claude Code plugin.

## General
Unless asked to behave otherwise, always give concise responses and scrifice grammar for the sake of concision.  Ask clarifying questions when needed and offer your best guess at available interpretations/answers for those questions when possible.

### Be RUTHLESSLY concise — this is the rule I break most often
Default to a few sentences. If the answer is "yes", say "yes" and stop.

- **Answer the question asked. Nothing else.** No adjacent findings, no "while I was looking I noticed", no caveats I didn't ask for. Sit on it until I ask.
- **One thing at a time.** Never hand me a numbered list of 3+ considerations, options, or trade-offs unless I asked for options. Pick one, recommend it, move on.
- **No teaching.** Skip the mechanism, the background, the "why this matters". State the conclusion. I'll ask why if I care.
- **No tables, no headers, no bold-label paragraphs** for a simple answer. Prose or a couple of lines.
- **Cut every parenthetical, every "worth noting", every "the real finding is".**
- Corrections: one sentence, no post-mortem.

Length is the tell: if a reply is over ~10 lines and I didn't ask for depth, it's wrong. Detail I have to skim to find the answer is worse than no answer.

## Working Rules

- **Always work on a branch.** Never commit directly to `main`. Every change lands via a feature branch and PR. Release-please's own commits are the only exception. If a commit lands on `main` locally by accident, reset `main` to `origin/main` and move the commit to a branch before pushing.
- **Pull `origin main` before starting work.** `git fetch origin main` at session start and before branching; branch from `origin/main` directly (`git switch -c <branch> origin/main`). If your branch already exists and `origin/main` moved, merge/rebase it in before continuing.
- **Squash-merge all PRs**: `gh pr merge <num> --squash`. `main` forbids force-pushes.
- **Docs-only PRs auto-merge.** If the diff touches only `*.md`/`.gitignore`/`LICENSE` and no code/agent/skill/hook, arm auto-merge at open: `gh pr merge <num> --auto --squash`. Anything else needs explicit human merge.
- **Deterministic tools over inference.** Never dispatch a skill or agent for work a tool can decide — a compiler, test suite, linter, parser, schema validator, or `git` answers a mechanical question directly; a model's answer to one is a guess that fails silently. Prefer, in order: (1) run the real thing, (2) a deterministic script over its output, (3) a model, only for what's left.
  - Verify runtime properties by exercising them at runtime — byte-compile/import checks prove a module parses, not that it runs. `chk_python_floor` runs a real test slice (`FLOOR_TEST_SLICE` in [`tests/repo/test_python_floor.py`](tests/repo/test_python_floor.py)); don't duplicate that list elsewhere.
  - A gate that cannot fail is worse than no gate — make a new gate fail on purpose once before trusting it.
  - Name what a gate does *not* cover. `chk_python_floor` bounds the oldest supported interpreter; `chk_python_ceiling` (`PYTHON_CEILING` in `scripts/ci-local.sh`) bounds the newest and runs the full pytest directory list, not a curated slice. It's `exempt` in [`.github/required-status-checks.json`](.github/required-status-checks.json) (advisory) — treat a red run as blocking anyway.
  - Gates are platform-bound too. Every gate here runs on `ubuntu-*`; every maintainer develops on macOS — watch for GNU/BSD divergence (e.g. `mktemp -t` behaves differently). Portable form: `mktemp "${TMPDIR:-/tmp}/prefix-XXXXXX"` with the `X`s trailing.
  - Review your own fix before calling it done. Dispatch review agents (`correctness-review`, `test-review`) at your own diff from the top-level session and verify each finding by reproducing it.
- **A mechanical finding reported twice becomes a check.** On the second report of the same mechanically-checkable finding, add a `CHECKS` entry to [`repo_invariants.py`](plugins/dev-team/skills/code-review/scripts/repo_invariants.py) in the same PR that fixes it.
- **Prefer Python over bash, repo-wide.** Stdlib-only `.py` under `plugins/dev-team/`. Bash only for a genuine shell-script target or the unavoidable bootstrap shim. New `.bats` files are a review finding — port to `test_*.py` (see [ADR 0014](docs/adr/0014-python-for-cross-os-scripts.md), [ADR 0015](docs/adr/0015-bash-removal-complete.md)).
- **Specs and plans are GitHub issues, not files.** A spec becomes an epic issue, each plan slice a sub-issue — create them by default. Fall back to `docs/specs/<slug>/{spec.md,plans/}` only with no GitHub connection.
- **PRs close the issues they address.** `Closes #N` per sub-issue, `Part of #<epic>` for the epic. The `epic-auto-close` workflow closes the epic once its last sub-issue closes — GitHub itself won't.

## Repository Structure

```
.claude-plugin/marketplace.json    # Marketplace catalog (points to plugins/)
plugins/dev-team/          # The plugin source
├── .claude-plugin/plugin.json     # Plugin manifest + version
├── agents/                        # Team agents + review agents
├── skills/                        # Agent-loaded + user-invocable (slash command) skills
├── hooks/                         # PreToolUse and PostToolUse scripts
├── knowledge/                     # Progressive disclosure reference files
├── templates/                     # Language-specific agent templates
├── docs/                          # Plugin-specific docs (architecture, agents, skills, eval system)
├── settings.json                  # Hook registrations (ships with plugin)
├── install.sh                     # Prerequisite checker
└── CLAUDE.md                      # Plugin instructions (ships with plugin)

docs/                              # Cross-plugin dev documentation (roadmaps, spikes)
plans/                             # Transient working plans — deleted after implementation
evals/                             # Agent eval fixtures (not shipped)
reports/                           # Legacy review reports (not shipped) — new reports land in .dev-team-reports/
```

- [`docs/marketplace-builder-plugin-playbook.md`](docs/marketplace-builder-plugin-playbook.md) — how to build a plugin for this marketplace pattern.
- [`docs/using-plugin-skills-in-the-web-environment.md`](docs/using-plugin-skills-in-the-web-environment.md) — using a plugin's skills from a Claude Code web session.

## Developing the Plugin

Edit files directly in `plugins/dev-team/`. All plugin components (agents, skills, hooks) live there.

### Prerequisites

`scripts/ci-local.sh` (run by the `pre-push` hook) needs on every dev machine:

- `jq`, `python3`, `uv` (`brew install jq python3 uv`, or `uv` via `curl -LsSf https://astral.sh/uv/install.sh | sh`).
- `shellcheck`, version-pinned as `SHELLCHECK_VERSION` in `scripts/ci-local.sh` (fetched to `~/.cache/agentic-dev-team/` on first use — not from a package manager).
- Python deps: `python3 -m pip install -r requirements-dev.txt`. On a PEP 668 "externally-managed" interpreter, use a project `.venv/`, or let `dev-setup.sh` retry `--user`/`--break-system-packages` for you.
- Graphify (optional): `uv tool install graphifyy`, then `dev-setup.sh` runs `graphify hook install` (never `graphify install --project`, which overwrites this file). Build the graph on demand with `graphify extract .`. Use **codegraph** for structural queries while editing; **graphify** for architecture/onboarding across code+docs+infra.

**One-shot setup:** `bash scripts/dev-setup.sh` (safe to re-run). `ci-local.sh` itself checks these and points at `dev-setup.sh` if anything's missing.

**Profiling the gate:** `CI_LOCAL_TIMING=1` appends per-check and total wall-clock timing.

**The pre-push pytest gate spans more than `plugins/dev-team/tests`.** It runs `plugins/dev-team/tests tests/repo tests/agents tests/commands tests/docs tests/knowledge tests/stack_aware tests/skills tests/scripts tests/hooks`. Editing agent/skill markdown can break repo-level content-guards outside `plugins/dev-team/tests` — always run the full dir list, plus `python3 scripts/check_md_references.py` and `python3 plugins/dev-team/hooks/lib/build_knowledge_index.py`, before pushing plugin-content changes.

### The inner loop

"What does this change affect" is a mechanical question a program should answer, not a guess:

1. **`--lf` / `--ff`** — pytest built-ins, free. `--lf` re-runs last run's failures; `--ff` runs them first.
2. **Impact selection** — `scripts/impact_tests.py` maps changed files to the tests that reach them via `pytest-cov`'s `--cov-context=test`:

   ```bash
   python3 scripts/impact_tests.py build --out .cache/impact-map.json -- \
     plugins/dev-team/tests tests/repo tests/agents tests/commands tests/docs \
     tests/knowledge tests/stack_aware tests/skills tests/scripts tests/hooks
   python3 scripts/impact_tests.py select --map .cache/impact-map.json \
     --changed-from-git | xargs python3 -m pytest -q
   ```

   `select` exits **2** (run the full suite) whenever it can't be sure — missing/malformed map, an unmapped changed file, or a changed test file. Rebuild the map after adding tests or source files.
3. **The full directory list** — what `pre-push` and CI run, and the fallback whenever selection refuses.

`scripts/ci_tree_cache.py` skips `chk_hook_units` outright when the working tree is byte-identical to one that already passed; `CI_LOCAL_NO_TREE_CACHE=1` forces a run.

### Worktrees — run `npm ci` first

Run `npm ci` as the first step in any new worktree. An unprovisioned worktree has no `node_modules`, so git hooks silently don't run — `ci-local.sh`/CI backstop it. `SessionStart` hooks (`.claude/ensure_npm_ci.py`, `.claude/ensure_code_graph_tools.py`) do this automatically on a best-effort basis.

### Script authoring — Python only

Every shipped script under `plugins/dev-team/` is Python 3.10+, stdlib only (see [ADR 0014](docs/adr/0014-python-for-cross-os-scripts.md), [ADR 0015](docs/adr/0015-bash-removal-complete.md), [ADR 0031](docs/adr/0031-raise-shipped-python-floor-to-3-10.md)):

- All shipped hooks/scripts are `.py`. The only `.sh` are the two pre-Python bootstrap shims (`install.sh`, `hooks/py.sh`) that must run before an interpreter is guaranteed on PATH.
- Stdlib only — no `pip install`, no `requirements.txt` for shipped code.
- Probe OS-specific paths at runtime rather than hard-coding them.
- Tests are pytest, `test_*.py` under the plugin's `tests/` tree.

Repo-root `scripts/*.sh` are out of scope — they orchestrate dev tooling, not shipped code.

### Testing locally

```bash
claude plugin marketplace add /path/to/agentic-dev-team
claude plugin install --scope project dev-team@bfinster
```

### Adding agents, skills, or hooks

- **Agent**: `.md` file in `plugins/dev-team/agents/`
- **Agent-loaded skill**: `SKILL.md` under `plugins/dev-team/skills/<name>/`
- **User-invocable skill**: same, with `user-invocable: true` in frontmatter
- **Hook**: `.py` file in `plugins/dev-team/hooks/`, registered in `plugins/dev-team/settings.json`

Run `/agent-audit` after changes. See [`plugins/dev-team/docs/developer-notes.md`](plugins/dev-team/docs/developer-notes.md) for the full maintainer index.

### Testing hook changes before release

A hook edit in this checkout doesn't affect a live session until it ships — real hook invocations run from the **installed plugin cache**, not your working tree. Validate one of two ways:

1. **Unit-test the hook directly (primary path).** `python3 -m pytest plugins/dev-team/tests/hooks tests/hooks tests/repo -q` runs the code in your working tree immediately.
2. **End-to-end against a live session.** Re-run `claude plugin install` to refresh the cache, then confirm the hook's side effect in a fresh session (e.g. a line in `.claude/metrics/boundary-events.jsonl`).

Prefer path 1; use path 2 only when the behavior can't be reproduced by invoking the hook module directly.

### Releasing

Release-please manages releases from conventional commits (`feat:` minor, `fix:` patch, `feat!:`/`BREAKING CHANGE` major) — merging its release PR cuts a GitHub Release.

**PR titles must be conventional** (`<type>(<scope>): <description>`) since squash-merge uses the PR title as the commit message. If a release is silently missed, recover with a follow-up commit carrying `Release-As: X.Y.Z`.

## Cloud sessions (claude.ai/code)

See the `cloud-setup` skill or [`docs/cloud-setup.md`](docs/cloud-setup.md) for running this repo in a Claude Code web/cloud session.

## graphify

Knowledge graph at `graphify-out/`.

- For architecture/symbol/cross-file questions, run `graphify query "<question>"`, `graphify path "<A>" "<B>"`, or `graphify explain "<concept>"` first.
- Use `graphify-out/wiki/index.md` for broad navigation; `graphify-out/GRAPH_REPORT.md` only when those don't surface enough.
- After modifying code, run `graphify update .`.
- Skip graphify for manifests/lockfiles, `node_modules`/`dist`/`build`/`coverage`, `.git/`, directory listings, and single-file lookups — plain `grep`/`find`/`ls`/`Read` is fine there.
