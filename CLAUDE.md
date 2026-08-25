# Agentic Dev Team — Plugin Development

This is the marketplace repository for the dev-team Claude Code plugin.

## Working Rules

- **Always work on a branch.** Never commit directly to `main`. Every change — including documentation-only changes, gitignore tweaks, and one-line fixes — lands via a feature branch and a pull request. If a commit accidentally lands on `main` locally, reset `main` to `origin/main` and move the commit to a branch before pushing. Release commits authored by release-please are the only exception; they arrive as their own PR.
- **Always pull `origin main` before starting work.** Run `git fetch origin main` at the start of every session and before branching, then cut new branches from `origin/main` directly (e.g. `git switch -c <branch> origin/main`) — never from a local `main` you haven't fast-forwarded. If your feature branch already exists and `origin/main` has moved, merge or rebase the fresh `origin/main` into it before continuing — don't let a branch drift behind `main` across a long-running session.
- **Squash-merge strategy.** `main` is protected by a ruleset that forbids force-pushes. Use squash-merge for all PRs to keep `main` history clean: `gh pr merge <num> --squash`. Signed commits are not required.
- **Documentation-only PRs auto-merge.** When the diff touches only `*.md` files (plus `.gitignore`, `LICENSE`, or other non-shipping metadata) and changes no code, agent, skill, or hook, arm auto-merge at PR-open time: `gh pr merge <num> --auto --squash`. Required checks still run; the PR lands the moment they pass. Any PR that touches code, agents, skills, hooks, eval fixtures, or marketplace manifests requires explicit human merge.
- **Deterministic tools over inference — never dispatch a skill or agent for work a tool can decide.** If a question has a mechanical answer, the mechanism must produce it: a compiler, a test suite, a type checker, a linter, a parser, a schema validator, `git` itself. Agents and skills are for judgement — design trade-offs, review of intent, prose — not for facts a program can compute. This is a correctness rule, not a cost rule: a model's answer to a mechanical question is a *guess that looks like a result*, and it fails silently, in the confident direction. Prefer, in order: (1) run the real thing and read its output; (2) a deterministic script over its artifacts; (3) a model, only for what is left. Two rules follow from it, both learned the expensive way:
  - **Verify a runtime property by exercising it at runtime.** Static approximations of a runtime question rot into false assurance. The Python floor gate began as a hand-maintained denylist of post-3.8 APIs (the floor was 3.8 at the time); it reported the shipped tree clean while `hooks/lib/cost_meter.py` used PEP 584's `dict | dict`, which 3.8 rejects. A one-time manual run of the full suite on a real 3.8 interpreter — not something the gate itself did — found it in nine failing tests. The gate that replaced the denylist was, at first, still only a byte-compile + import pass (`.github/workflows/plugin-tests.yml` → "Python 3.10 floor", `scripts/import_probe_shipped.py`; see [`tests/repo/test_python_floor.py`](tests/repo/test_python_floor.py)) — real progress over a hand-maintained list, but still one layer short of "exercising it at runtime": compiling and importing a module proves it *parses* and *loads*, not that every function *body* runs clean, so a runtime-only API used only inside a function (`asyncio.to_thread` in `orchestrator.py`, issue #1650) stayed invisible to it regardless of which version the floor was pinned to. `chk_python_floor` now closes that gap too, actually running a curated test slice over the shipped tree under the resolved 3.10 interpreter via `uv run --python`, not just compiling and importing it. That slice is declared once, as `FLOOR_TEST_SLICE` in [`tests/repo/test_python_floor.py`](tests/repo/test_python_floor.py), and held equal to `chk_python_floor`'s actual pytest arguments in both directions — deliberately not re-enumerated here, because a copy of the list in prose is exactly what went stale when the coverage-discovery modules joined the slice (#1826) and nothing held this file to it. The floor itself later moved to 3.10 once the original OS-availability rationale expired ([ADR 0031](docs/adr/0031-raise-shipped-python-floor-to-3-10.md)) — the gate's mechanism (the interpreter, not a list) is what survived that move unchanged.
  - **A gate that cannot fail is worse than no gate.** It reads as a guarantee and delivers none. `engines.node` sat at `>=24` while this project's own containers ran Node 22, so `npm ci` failed, `node_modules` never installed, husky's hooks went inert, and `scripts/ci-local.sh` skipped eslint *while still printing "All local CI checks passed."* When you add a gate, make it fail on purpose once before you trust it.
  - **A gate bounds only the case it can observe — say what the other end is.** The floor gate above asks "does this still run on the OLDEST supported interpreter", which is a real question and answers only itself. For a long time nothing asked about the newest: `content-guard-tests` runs on the runner image's *implicit* system `python3` (~3.12 on ubuntu-24.04, with no `python-version` pin anywhere in `plugin-tests.yml`), so the suite's green read as "works on Python" when it meant "works on 3.10 and whatever the runner happens to ship." `main` was consequently red on 3.13+ with every check green: `coverage_discovery_js.py` detected a malformed `**` glob by catching `ValueError` from `Path.glob`, and CPython 3.13's pathlib rewrite stopped raising it, so the guard silently returned an empty result instead of a `discovery_error` (#1832, fixed in #1833). `chk_python_ceiling` / the `Python ceiling` job now names the other end (`PYTHON_CEILING` in `scripts/ci-local.sh` — one place, so a runner-image bump cannot move it silently), and runs the **full** pytest directory list rather than a curated slice like the floor job's. That choice is the point, not an optimization: when the regression landed, the offending test file was *not* in the floor slice, and it took a follow-up commit (#1836) to add the coverage-discovery modules to it — a curated list only covers what someone remembered to enumerate, and it lagged the very bug that motivated it. A ceiling gate on a slice would inherit that lag. Read its status honestly, though: it is currently listed in `exempt` in [`.github/required-status-checks.json`](.github/required-status-checks.json), so it reports on every PR but does **not** block a merge — advisory by choice, not because it is path-filtered or opt-in like the other exemptions. Treat a red ceiling run as blocking by convention, and see #1837 for the ruleset edit that would make that automatic. Two transferable pieces: when a library's *error* behavior is your guard, validate the property explicitly in your own code instead — an exception is a contract that can be withdrawn; and do not add a pinned interpreter to `content-guard-tests` via `actions/setup-python`, which is the known-wrong fix (a prior attempt put it ahead of the system `python3` for every other step in that job, breaking `chk_md_references` and silently degrading `chk_hook_units`'s pytest guard to "skipped" — use `uv`, which never touches `PATH`).
  - **Review your own fix before calling it done — a green suite on code you just wrote is weak evidence.** Tests written alongside a fix encode the same mental model as the fix, so they inherit its blind spots. The #1833 brace-glob fix passed all 71 tests, 15 of them written specifically for it; `correctness-review` and `test-review`, dispatched independently at the diff, both caught that brace balance was tracked only from the first `{` onward — so `apps/}x{a,b}` expanded to globs matching nothing, reintroducing the exact silent-zero failure the fix existed to remove. The parametrized case that *looked* like it covered this passed only because of an unrelated unclosed trailing brace. The same pass found two more real defects (an empty alternative failing the whole workspace, and per-alternative `**` checking letting `{**/x,**/y,**/z}` slip past the cost guard). This is judgement, not mechanism, so no gate enforces it: dispatch the review agents at your own diff from the top-level session, and verify each finding by reproducing it before fixing.
- **Prefer Python over bash, repo-wide, unless bash is strictly required.** This applies everywhere in the repo, not just shipped plugin code — new tests under `tests/`, new `scripts/*`, new CI helpers. Write `.py` (stdlib-only for anything under `plugins/dev-team/`) by default. Bash is acceptable only when the thing under test genuinely is a shell script, or for the unavoidable pre-Python bootstrap shim (`install.sh`'s two-line trampoline). New `.bats` files are a review finding, not a style choice — see [ADR 0014](docs/adr/0014-python-for-cross-os-scripts.md) and [ADR 0015](docs/adr/0015-bash-removal-complete.md). If you find yourself adding a `.bats` file, port the assertions to `test_*.py` instead — see `### Script authoring — Python only` below for the mechanical pattern.
- **Specs and plans are GitHub issues here, not files.** When developing this repo (GitHub-connected — the normal case), a spec becomes an **epic issue** and each plan slice a **sub-issue** of that epic — create them by default, don't leave local drafts. Fall back to untracked files only when there is no GitHub connection: the spec at `docs/specs/<slug>/spec.md` and its plans under a `docs/specs/<slug>/plans/` subdirectory (never a root-level `plans/`). This governs development of *this* plugin only — it is not shipped skill behavior imposed on people who use the plugin on their own projects.
- **PRs close the issues they address.** Every PR body carries a closing keyword — `Closes #N` for each sub-issue the PR resolves, and `Part of #<epic>` (non-closing) for the epic — so merging the PR closes its slices. GitHub does **not** auto-close a parent/epic issue as a side effect of every sub-issue closing (it only tracks completion percentage); the `epic-auto-close` workflow (`.github/workflows/epic-auto-close.yml`, #987) is what closes the epic once its last sub-issue closes.

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
reports/                           # Legacy review reports (not shipped, pre-.dev-team-reports/) — new reports land in .dev-team-reports/
```

Two guides explain how the marketplace works:

- [`docs/marketplace-builder-plugin-playbook.md`](docs/marketplace-builder-plugin-playbook.md) — how to build a plugin that scaffolds/audits/maintains marketplace monorepos (shipping hygiene, portability, testing, release/catalog sync).
- [`docs/using-plugin-skills-in-the-web-environment.md`](docs/using-plugin-skills-in-the-web-environment.md) — how to use a plugin's skills from a Claude Code web session.

## Developing the Plugin

Edit files directly in `plugins/dev-team/`. All plugin components (agents, skills, hooks) live there.

### Prerequisites

The local gates (`scripts/ci-local.sh`, run by the `pre-push` hook) need these tools on every dev machine:

- CLI: `jq`, `python3`, `uv` (macOS: `brew install jq python3 uv`; `uv` otherwise via `curl -LsSf https://astral.sh/uv/install.sh | sh`). `shellcheck` still lints repo-root shell (`scripts/audit-rules-vs-prompts.sh`, etc.) and the `plugins/security-assessment/` plugin; the `plugins/dev-team/` plugin itself is now Python. It is deliberately NOT in that install line: it is version-PINNED as `SHELLCHECK_VERSION` in `scripts/ci-local.sh`, which fetches that exact release into `~/.cache/agentic-dev-team/` on first use, because a package manager gives whatever it happens to ship — Homebrew's 0.11.0 and Ubuntu's 0.9.0 disagree on real findings, and CI used to install the latter while developers ran the former. `uv` provisions the Python 3.10 floor interpreter and runs the floor-interpreter test slice (`chk_python_floor` in `scripts/ci-local.sh`) — the default pre-push gate fails outright without it, not just the `Python 3.10 floor` CI job.
- Python modules: install the declared dev dependencies once with `python3 -m pip install -r requirements-dev.txt` (PyYAML for a few content-guard tests that shell out to Python; pytest for every content-guard suite and the plugin's own unit tests; semgrep for the security-assessment suites; httpx for the red-team harness smoke test). On a PEP 668 "externally-managed-environment" interpreter (e.g. Homebrew Python on macOS), a bare `pip install` is rejected outright — `dev-setup.sh` handles this itself, retrying `--user` then `--break-system-packages` and only printing success if one of the three actually succeeds; the failure is never silently swallowed. Prefer a project `.venv/` if you'd rather not use `--break-system-packages` system-wide.
- Graphify (optional, code knowledge graph): `uv tool install graphifyy` (or `pipx install graphifyy`). Its native Claude wiring is committed once — the `## graphify` section at the end of this file, `.claude/skills/graphify/`, and the PreToolUse nudge hooks in `.claude/settings.json`. `dev-setup.sh` installs graphify and runs `graphify hook install` (never `graphify install --project`, which rewrites this curated file); graphify targets `.husky/post-commit` + `.husky/post-checkout` here because git hooks route through husky, and those embed a machine-specific Python path so they're gitignored and regenerated per-clone. Build the graph on demand with `graphify extract .` (writes `graphify-out/graph.json`, gitignored). Codegraph stays a personal, user-level MCP — not committed. When to use which: **codegraph** for fast structural queries while editing (callers/impact); **graphify** for architecture/onboarding across code + docs + infra.

**One-shot setup:** `bash scripts/dev-setup.sh` validates this toolchain and installs anything missing (Homebrew on macOS, apt-get on Debian/Ubuntu, then the `requirements-dev.txt` deps). Safe to re-run.

`ci-local.sh` checks these up front and exits with an actionable message (pointing at `dev-setup.sh`) if any are missing.

**Profiling the gate:** set `CI_LOCAL_TIMING=1` to append a timing section — each check's individual wall-clock (in declared order, regardless of completion order under the parallel pool) plus the total run wall-clock, followed by an uncolored machine-parseable block (`label<TAB>seconds`) for scripting. It is off by default and changes nothing when unset; a `--changed-only`-skipped check reads `skipped`, never `0.00s`. Use it to find the slowest gates before optimizing (issue #1118).

**The pre-push pytest gate spans more than `plugins/dev-team/tests`.** `ci-local.sh`'s unit-test step runs pytest over `plugins/dev-team/tests tests/repo tests/agents tests/commands tests/docs tests/knowledge tests/stack_aware tests/skills tests/scripts tests/hooks` (with `-n auto --dist loadgroup`; two csharp-stryker files `--ignore`d). Editing agent/skill markdown can break repo-level content-guards that live **outside** `plugins/dev-team/tests` — e.g. `tests/skills/test_code_review_frontend_dispatch.py` asserts specific agent names appear verbatim in `code-review/SKILL.md`, and `tests/repo` runs `check_md_references.py` (a backticked cross-skill path must be file-relative, e.g. `../code-review/SKILL.md`). `tests/hooks/` (repo-root, distinct from `plugins/dev-team/tests/hooks/`) joined this list in #1475 after two of its tests — pinning `hooks.json`'s dispatch-matcher registration — went silently red for a full ADR migration (ADR 0026) because this directory wasn't in the gate; the stryker/pitest/mutmut *adapter* tests that actually shell out to those tools live in `plugins/dev-team/tests/hooks/` (already covered by `plugins/dev-team/tests` above) — this directory only hosts the static fixture files those adapter tests read (`tests/hooks/fixtures/`, `tests/hooks/fake-bin/`), so `tests/hooks/` itself is fast and portable. Before pushing plugin-content changes, run that **full dir list** — not just the plugin subdir — plus `python3 scripts/check_md_references.py` and `python3 plugins/dev-team/hooks/lib/build_knowledge_index.py`, or the `pre-push` hook / CI will catch what a plugin-only run missed.

### Worktrees — run `npm ci` first

Run `npm ci` as the first step in any new worktree, before committing. An unprovisioned worktree has no `.husky/_`/`node_modules`, so git hooks silently don't run; `scripts/ci-local.sh` and CI backstop what the hooks would have caught.

**Self-healing SessionStart hooks (issue #1469).** `.claude/settings.json` registers two additional, time-boxed, fail-open `SessionStart` hooks alongside `install-dev-team.sh`: `.claude/ensure_npm_ci.py` runs `npm ci` automatically when `node_modules/.bin/husky` is missing (the exact gap above), and `.claude/ensure_code_graph_tools.py` builds the CodeGraph/Repowise/Graphify index for any of those tools that's already installed but not yet indexed in this checkout — it never installs a missing CLI (that stays an explicit `/project-init`/`/setup` opt-in). Both are best-effort: a fresh worktree still benefits from the manual `npm ci` above if a hook's time-box or environment prevents it from completing. The two hooks share their subprocess/path-resolution plumbing via `.claude/lib/session_start_common.py`, mirroring the `plugins/dev-team/hooks/lib/` and `scripts/lib/` shared-helper convention.

### Script authoring — Python only

**Every shipped script under `plugins/dev-team/` is Python 3.10+ using stdlib only.** See [ADR 0014](docs/adr/0014-python-for-cross-os-scripts.md) (the decision), [ADR 0015](docs/adr/0015-bash-removal-complete.md) (the completion), and [ADR 0031](docs/adr/0031-raise-shipped-python-floor-to-3-10.md) (the floor's move off EOL 3.8). Concretely:

- **All shipped hooks + scripts are `.py` files.** The only `.sh` in `plugins/dev-team/` are the two pre-Python bootstrap shims, which cannot themselves be Python because they run before an interpreter is guaranteed on PATH: `install.sh` (the `install.py` trampoline) and `hooks/py.sh` (resolves a real Python 3 across `python3`/`py -3`/`python`/`$DEV_TEAM_PYTHON` so hooks and `/version` work on Windows, where `python3` is often absent — see #1078). Every other shipped invocation routes through `py.sh`, not a bare `python3`.
- **Stdlib only.** No `pip install`, no `requirements.txt` for shipped code. `subprocess`, `signal`, `pathlib`, `argparse`, `json`, `hashlib`, `re` cover the vast majority of shell-script territory portably.
- **Cross-OS by default.** Python runs natively on macOS, Linux, and Windows — no more Git Bash requirement for plugin hooks. When probing OS-specific paths (DOTNET_ROOT, tool install locations), use runtime probes (`subprocess`, `pathlib`) rather than hard-coding macOS or Linux paths.
- **Tests are pytest.** New tests land as `test_*.py` under the plugin's `tests/` tree.

Repo-root `scripts/*.sh` (`ci-local.sh`, `dev-setup.sh`, `cost-regression-check.sh`, the various `assemble-docs.sh`/`eval-changed.sh`/`run-full-eval.sh` helpers) are OUT of this rule's scope — they orchestrate developer tooling around the plugin, not the plugin itself, and are not shipped downstream. Convert them opportunistically when you touch them.

### Testing locally

Register the local checkout as a marketplace, then install from it into a test project:

```bash
claude plugin marketplace add /path/to/agentic-dev-team
claude plugin install --scope project dev-team@bfinster
# Or from the published marketplace (GitHub):
# claude plugin marketplace add bdfinst/agentic-dev-team
# claude plugin install dev-team@bfinster
```

### Adding agents, skills, or hooks

- **Agent**: Add a `.md` file to `plugins/dev-team/agents/`
- **Agent-loaded skill**: Add a `SKILL.md` under `plugins/dev-team/skills/<name>/`
- **User-invocable skill** (slash command): Add a `SKILL.md` under `plugins/dev-team/skills/<name>/` with `user-invocable: true` in frontmatter
- **Hook**: Add a `.py` file to `plugins/dev-team/hooks/` and register it in `plugins/dev-team/settings.json`

After changes, run `/agent-audit` to verify structural compliance.

[`plugins/dev-team/docs/developer-notes.md`](plugins/dev-team/docs/developer-notes.md) is the maintainer-facing entry point: an index of the plugin-development docs plus the playbook for adding a new static-analysis language.

### Testing hook changes before release

**A hook edit in this checkout does not affect a live session until it ships.** Real hook invocations — PreToolUse/PostToolUse hooks like `agent_dispatch_ledger.py`, `pre_commit_review.py`, the guards — run from the **installed plugin cache** (`~/.claude/plugins/cache/bfinster/dev-team/<version>/hooks/`), not from `plugins/dev-team/hooks/` in your working tree. `settings.json` registers each hook by a plugin-root-relative path (`sh hooks/py.sh hooks/<name>.py`), and that root resolves to the cache copy for the running session. So a hook fix cannot be validated by the very session you fix it in — it only takes effect after the change ships in a release and the cache updates (`/dev-team:upgrade`). This bit issue #1500: a fix to the dispatch-ledger's `subject_type` matching (PR #1498) could not record a single `agent_dispatch_ledger` "record" event during the session that authored it, because that session was still running the pre-fix cached hook. Validate hook changes one of two ways instead:

1. **Unit-test the hook directly (fast, deterministic, no live session — the primary path).** Every shipped hook is invoked as a subprocess with a crafted stdin payload by a `test_*.py` under `plugins/dev-team/tests/hooks/` (plus the repo-level gate/contract tests under `tests/hooks/` and `tests/repo/`). This runs the code **in your working tree**, so it reflects your edit immediately. Any hook whose behavior is only observable through a live Agent/tool dispatch (e.g. the ledger → `.review-passed` corroboration chain) must carry module-level coverage of that end-to-end path, so a fix is verifiable here rather than only after release. Run e.g. `python3 -m pytest plugins/dev-team/tests/hooks tests/hooks tests/repo -q`.

2. **End-to-end against a live session (when you must exercise the real dispatch path).** Install the plugin from the local checkout marketplace into a throwaway project (see [Testing locally](#testing-locally) for the two `claude plugin` commands). **`claude plugin install` copies the checkout into the versioned cache**, so it is a snapshot, not a live link — **re-run the install after every hook edit** to refresh the cache, then start a fresh session in the test project. Confirm the hook fired by inspecting its side effect — for the dispatch ledger, a `"decision":"record"` line in `.claude/metrics/boundary-events.jsonl` after a real review dispatch.

Prefer path 1; reach for path 2 only when the behavior genuinely cannot be reproduced by invoking the hook module directly.

### Releasing

Releases are managed by release-please. Push conventional commits to main:

- `feat:` → minor version bump
- `fix:` → patch version bump
- `feat!:` or `BREAKING CHANGE` → major version bump

A release PR is opened automatically. Merging it creates a GitHub Release with a version tag.

**PR titles must be conventional.** This repo squash-merges PRs (see [Working Rules](#working-rules)). Squash-merge creates a single commit on `main` using the PR title, so **the PR title must follow the conventional format** for release-please to read it correctly.

- Format PR titles as `<type>(<scope>): <description>` — e.g., `feat(agents): add concurrent-request-review agent`, `fix(skills): resolve circular path references`.
- Scope is optional; type is required (`feat`, `fix`, `chore`, `docs`, `refactor`, etc.).
- If a release is silently missed, recover with a follow-up commit carrying a `Release-As: X.Y.Z` footer.

## Cloud sessions (claude.ai/code)

For running this repo in a Claude Code web/cloud session — installing the plugin via the Setup script, the SessionStart fallback, and the file-based fallback — see the `cloud-setup` skill (`.claude/skills/cloud-setup/SKILL.md`) or [`docs/cloud-setup.md`](docs/cloud-setup.md).

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:

- For codebase questions — architecture, symbol relationships, cross-file structure, "how does X work" — first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
- graphify is for understanding source, not for metadata lookups. Skip it — plain `grep`/`find`/`ls`/`Read` is fine — for: package manifests and lockfiles (`package.json`, `package-lock.json`, `yarn.lock`, `requirements.txt`, etc.), `node_modules`/`dist`/`build`/`coverage` contents, VCS metadata (`.git/`), bare directory listings, and single-file line/count lookups. The `PreToolUse` nudge hooks in `.claude/settings.json` enforce this same exclusion list so the reminder only fires on genuine source exploration.
