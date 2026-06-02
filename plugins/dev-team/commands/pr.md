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

## Parse Arguments

Arguments: $ARGUMENTS

- `--skip-review`: Skip the `/code-review` step (not recommended)
- `--draft`: Create a draft PR
- `--base <branch>`: Target branch (default: `main`)

## Steps

### 1. Pre-flight checks

Verify:
- Current branch is not `main` or `master`
- There are commits ahead of the base branch
- Working tree is clean (no uncommitted changes) — if dirty, ask whether to commit or stash

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
   - Run `/code-review`
   - If review returns `fail`, show the results and ask the user whether to proceed or fix

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

### 4. Create the PR

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

## Test Plan
- [ ] <verification step 1>
- [ ] <verification step 2>
```

### 5. Report

Display the PR URL and a summary of the quality gate results.

If any gate failed and the user chose to proceed anyway, note this in the PR body as a caveat.
