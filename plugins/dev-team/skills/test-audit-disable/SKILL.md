---
name: test-audit-disable
description: >-
  Phase-3 worker for `/test-modernize`. Audits the existing test suite for
  tests that cannot fail — no assertions, assertions on constants, expect-true,
  swallowed exceptions, self-equality — and disables each one by skip-and-tag
  (never deletes). Records each disabled test plus its reason in a JSON log
  under `memory/test-modernize/` so Phase 4 can later repair them. Pairs with
  `/coverage-baseline` to produce a true baseline coverage number.
argument-hint: "<repo-path> [--repo-slug <slug>] [--dry-run]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash, Edit, Write
---

# Test Audit + Disable

Role: worker. Identifies tests that cannot fail and disables them so the next coverage run measures a true baseline, not a false positive inflated by tautologies. Tests are skipped + tagged, never deleted — Phase 4 repairs them.

You have been invoked with the `/test-audit-disable` command.

## Parse Arguments

Arguments: $ARGUMENTS

- Positional: `<repo-path>` — the repo under modernization.
- `--repo-slug <slug>` — namespace under `memory/test-modernize/`. Defaults to the last path segment.
- `--dry-run` — print the cannot-fail list and exit without disabling.

## Steps

### 1. Detect language + test framework

Probe the repo root for the test stack. Take the first match:

- `package.json` → JS/TS — `jest`, `vitest`, `mocha`, `playwright`. Skip helpers per framework: `it.skip` / `test.skip` / `xit` / `xdescribe`.
- `pyproject.toml` / `setup.py` / `setup.cfg` → Python — `pytest`, `unittest`. Skip helpers: `@pytest.mark.skip(reason=...)`, `@unittest.skip(...)`.
- `pom.xml` / `build.gradle*` → JVM — `JUnit5`, `JUnit4`, `TestNG`, `Kotest`. Skip helpers: `@Disabled("...")`, `@Ignore("...")`, `@Test(enabled=false)`.
- `*.csproj` → .NET — `xunit`, `nunit`, `mstest`. Skip: `[Fact(Skip="…")]`, `[Test, Ignore("…")]`.
- `Cargo.toml` → Rust — `#[ignore = "…"]`.
- `go.mod` → Go — `t.Skip("…")`.

If multiple stacks are present, process each. If none, ask the operator which to use.

### 2. Detect cannot-fail tests

For each test file, search for the cannot-fail patterns. The set is language-agnostic conceptually but the regex differs per framework — use these signal patterns:

| Pattern | Example | Reason |
|---|---|---|
| No assertion at all | `it('does X', () => { service.doX(); })` | nothing to fail on |
| Assertion on a literal | `expect(1).toBe(1)`, `assertEquals(true, true)` | self-evaluating |
| Expect-truthy on a constant | `expect(true).toBeTruthy()` | tautology |
| Self-equality | `expect(x).toBe(x)`, `assertEquals(obj, obj)` | always true |
| Swallowed exception with no assertion in the catch | `try { … } catch { }` | masks failures |
| Assertion only inside a never-entered branch | `if (false) { assert … }` | dead test |
| `expect.anything()` / `expect.any(*)` as the only assertion | | matches anything |
| Negative assertion on a never-thrown error | `expect(() => fn()).not.toThrow()` with no throw path | tautology unless fn can throw |

For Python add: `assert True`, `self.assertTrue(True)`, `self.assertIsNotNone(self)`. For JVM add: `assertTrue(true)`, `assertEquals(x, x)`. For Go add: `if err != nil { t.Errorf(…) }` blocks with no error-path coverage and `t.Log` as the only call.

A finding requires **file path + line + snippet + reason**. Use `Grep` (ripgrep) with file globs scoped to the framework's test conventions.

### 3. Build the cannot-fail list

Collect all findings into a JSON array:

```json
[
  {
    "file": "src/widget/widget.test.ts",
    "line": 42,
    "test": "renders without crashing",
    "snippet": "it('renders without crashing', () => { render(<Widget/>) });",
    "reason": "no-assertion"
  },
  …
]
```

### 4. Preview + confirm

Print the count by reason and the first ~20 entries. Ask:

> Disable these N cannot-fail tests? (yes / no / show all)

If `--dry-run`, print and exit zero without modifying anything.

### 5. Disable in place

For each finding, use `Edit` to insert the framework's skip helper at the matching test boundary, with the reason as the skip message:

- JS/TS: `it(...)` → `it.skip(...)` and add a leading comment `// disabled by /test-audit-disable: <reason> — repair in Phase 4`.
- Python: prepend `@pytest.mark.skip(reason="cannot-fail: <reason> — repair in Phase 4")`.
- JVM: prepend `@Disabled("cannot-fail: <reason> — repair in Phase 4")`.
- .NET: change `[Fact]` → `[Fact(Skip="cannot-fail: <reason> — repair in Phase 4")]`.
- Rust: prepend `#[ignore = "cannot-fail: <reason> — repair in Phase 4"]`.
- Go: insert `t.Skip("cannot-fail: <reason> — repair in Phase 4")` at the top of the test body.

**Never** delete the test body. Phase 4 needs the original implementation to repair against the public-interface Gherkin.

### 6. Persist phase-3 progress + the disabled-tests log

Write:

- `memory/test-modernize/<slug>/disabled-tests.json` — the array from Step 3, augmented with the disabling tag inserted at each site.
- `memory/test-modernize/<slug>/phase-3-audit.md` — counts by reason, framework, file. Lists any test files the worker could not parse (call out as "needs hand-audit").

The orchestrator's Phase-3 progress file is owned by `/coverage-baseline`, which runs immediately after this worker.

### 7. Report

Print:

- Total tests disabled, broken down by reason.
- The first ~10 disabled tests (file + line) for sanity-check.
- Any files flagged for hand-audit.
- The log path.

## Notes

- The disabled tag carries the reason and the "repair in Phase 4" hint so the operator can see the audit history in source control, not only in `memory/`.
- Test-file detection follows framework conventions; configurable extensions / patterns can be added later, but the defaults cover the matrix above.
- Tests that pass for the wrong reason but DO assert (e.g. brittle snapshot tests, over-mocked tests with no real-behavior assertion) are out of scope here — those land in Phase 5 `[Re-scope]` Stories, not the cannot-fail audit.
