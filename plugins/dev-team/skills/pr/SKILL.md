---
name: pr
description: >-
  Run a pre-PR quality gate (tests, typecheck, lint, code review) and then
  create a pull request with a structured summary. Use when the user says
  "create a PR", "open a PR", "submit for review", or "I'm done with this
  feature".
argument-hint: "[--skip-review] [--draft] [--base <branch>]"
user-invocable: true
allowed-tools: Read, Write, Edit, Glob, Grep, Bash(git *), Bash(gh *), Bash(npm *), Bash(npx *), Bash(pnpm *), Bash(yarn *), Bash(make *), Bash(pytest *), Bash(go *), Bash(cargo *), Bash(dotnet *), Skill(code-review *)
---

# Pull Request

Role: orchestrator. This command enforces quality gates before creating a PR.

You have been invoked with the `/pr` command.

## Orchestrator constraints

1. Run the quality gate and open the PR; do not bypass failing gates.
2. Delegate review to the review agents; do not review code yourself.
3. **Be concise.** Report gate results and the PR URL, no preamble.

## Parse Arguments

Arguments: $ARGUMENTS

- `--skip-review`: Skip the `/code-review` step (not recommended)
- `--draft`: Create a draft PR
- `--base <branch>`: Target branch (default: `main`)
- `--no-auto-merge`: Do not enable auto-merge (the default is to enable it; see Step 5)

## Steps

### 1. Pre-flight checks

Verify:

- Current branch is not `main` or `master`
- There are commits ahead of the base branch
- Working tree is clean (no uncommitted changes) — if dirty, ask whether to commit or stash

If a plan file is present (check `plans/` for the most recently modified approved or implemented plan), run the plan completion gate:

```bash
python3 scripts/progress_guardian.py --pre-pr --plan <plan-file>
```

A non-zero exit means incomplete steps remain; stop and surface the findings — do not open the PR until all steps are `[x]`.

### 2. Run quality gate

Run each check sequentially. Stop on first failure:

1. **Tests**: Detect and run the project's test suite
   - `package.json` scripts: `npm test` or `pnpm test` or `yarn test`
   - `pytest.ini` / `pyproject.toml`: `pytest`
   - `go.mod`: `go test ./...`
   - `Cargo.toml`: `cargo test`
   - `*.csproj`: `dotnet test`
   - `Makefile` with `test` target: `make test`

2. **Type check** (if applicable):
   - `tsconfig.json`: `npx tsc --noEmit`
   - `mypy.ini` / pyproject.toml with mypy: `mypy .`

3. **Lint** (if applicable):
   - `eslint` in deps: `npx eslint .`
   - `ruff` available: `ruff check .`
   - `golangci-lint` available: `golangci-lint run`

4. **Code review** (unless `--skip-review`):
   - Run `/code-review --json`. `/pr` owns the human gate, so code-review runs non-interactively: it skips its own "fix or report?" prompt and applies its fix loop automatically (up to 5 iterations), then returns an aggregated status.
   - Read the returned status field. A normal review returns `{"overall": "pass|warn|fail", ...}`; a documentation-only changeset short-circuits with `{"status": "skipped", ...}`:
     - `overall` of `pass` / `warn`, or `status` of `skipped` → continue to step 3.
     - `overall` of `fail` → show the remaining findings and ask the user whether to proceed anyway or stop and fix.

Report results as a checklist:

```
## Quality Gate
- [x] Tests pass (42 passed, 0 failed)
- [x] Type check clean
- [x] Lint clean
- [ ] Code review: 2 warnings (see below)
```

### 3. Generate PR summary

Analyze the diff against the base branch (`git diff <base>...HEAD`) and commit history to generate:

- **Title**: Short, imperative (<70 chars)
- **Summary**: 1-3 bullet points of what changed and why
- **Test plan**: How to verify the changes
- **Decisions & assumptions**: Collect everything decided without a human in the
  loop, from the run's artifacts: the plan's `## Approval` auto-approval record and
  any auto-passed gate lines from the build output; the plan's stated stances on
  `knowledge/decision-defaults.md` axes; the spec's `## Ambiguity Log` entries
  classified `inferable`; `assumptions` entries from implementer step outputs;
  auto-applied review fixes with `confidence: medium`; and deferred follow-ups.
  Omit the section only when every gate had an interactive human approval.
- **Evidence bundle**: Assemble per `${CLAUDE_PLUGIN_ROOT}/knowledge/evidence-bundle.md`
  from the Step 2 quality-gate results plus on-disk pipeline data — **no new
  checks, no re-execution**:
  - **Checks run**: the exact Step 2 commands (test/typecheck/lint/`/code-review
    --json`) and their results.
  - **Scope notes**: gates skipped as not-applicable in Step 2 (e.g. no
    `tsconfig.json` → type check skipped), plus `--skip-review` if passed.
  - **Untested regions**: read `baseline-coverage.json` / `coverage-history.json`
    if present; otherwise "not measured — no coverage tool detected."
  - **Residual risks**: derived-first from `metrics/review-value.jsonl` entries
    with `outcome: "escalated"`, gate-bypass audit lines, and negative coverage
    deltas; "None identified" only when all derived sources are empty.
  - This command assembles from its own runtime's live data — it never reads a
    handoff file from a prior `/build` run, so running `/pr` standalone still
    produces a complete (possibly more-degraded) bundle.

### 4. Create the PR

**Never phrase a non-closing issue reference with a closing keyword, even
negated.** GitHub's closing-keyword parser is a dumb regex over the PR body:
`(close|closes|closed|fix|fixes|fixed|resolve|resolves|resolved)\s+#\d+`. It
fires on that pattern regardless of grammar — "does not close #123", "won't
fix #123", and "this doesn't resolve #123" all still auto-close #123 on
merge (issue #977). If an issue is only partially addressed or deferred,
write around the keyword instead: "leaves #123 open", "the remaining scope
is deferred to #124", "see #123 for the rest of this work" — never
`<closing-keyword> #123` in any form, negated or not.

Before calling `gh pr create`, lint the drafted body for accidental matches:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/pr_close_keyword_lint.py --body-file <body-file>
```

This is advisory only (always exits 0). If it prints warnings, rephrase the
flagged sentence per the guidance above before creating the PR — do not
proceed with a body the linter flagged without fixing the phrasing.

```bash
gh pr create --title "<title>" --body "<body>" [--draft] --base <base>
```

Use the structured template:

```markdown
## Summary
- <bullet 1>
- <bullet 2>

## Quality Gate
- [x] Tests: <N> passed
- [x] Type check: clean
- [x] Lint: clean
- [x] Code review: <status>

## Decisions & Assumptions
<!-- Everything decided without a human in the loop. An empty section means a fully human-gated run. -->
- <axis or assumption> — <stance taken> — <one-line rationale / recommended-default basis>

## Test Plan
- [ ] <verification step 1>
- [ ] <verification step 2>

## Evidence Bundle
<!-- Per ${CLAUDE_PLUGIN_ROOT}/knowledge/evidence-bundle.md. All four headers always appear; a section with no data states why instead of being omitted. -->
**Checks run**
- `<command>` — <result>

**Scope notes**
- <what this gate does not cover for this diff>

**Untested regions**
- <coverage % + delta, or "not measured — <reason>">

**Residual risks**
- <deferred/escalated finding, waiver, or bypass line — or "None identified">
```

### 5. Enable auto-merge (default)

Unless `--no-auto-merge` or `--draft` was given, enable auto-merge so the PR lands automatically once checks pass and any required reviews are in — rather than merging directly to trunk. This is the default integration stance in `knowledge/decision-defaults.md` (auto-merge vs. direct-to-trunk).

```bash
gh pr merge --auto --squash
```

If the repository does not have auto-merge enabled (the command errors), report that and leave the PR open for manual merge — do **not** merge directly to trunk to work around it.

### 6. Report

Display the PR URL and a summary of the quality gate results.

If any gate failed and the user chose to proceed anyway, note this in the PR body as a caveat.
