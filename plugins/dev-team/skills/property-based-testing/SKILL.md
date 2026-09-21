---
name: property-based-testing
description: Generate a runnable property-based test for a target function from its signature/docstring — a round-trip test when an encode/decode pair exists, or an invariant test when the docstring documents a postcondition (e.g. "returns sorted", "is idempotent"). Detects the project's language via project-init's stack detection, uses Hypothesis for Python and fast-check for JavaScript/TypeScript, and recommends running /mutation-testing against the generated suite afterward. Use when the user says "generate a property test", "property-based test this function", "add Hypothesis/fast-check tests", or wants round-trip/invariant coverage for a pure function rather than hand-written example-based tests.
role: worker
user-invocable: true
argument-hint: "<module_path> <function_name>"
allowed-tools: Read, Write, Bash(python3 "${CLAUDE_PLUGIN_ROOT}/skills/property-based-testing/scripts/detect_and_dispatch.py" *, python3 "${CLAUDE_PLUGIN_ROOT}/skills/property-based-testing/scripts/hypothesis_scaffold.py" *, npm install *, npx vitest *)
---

# Property-Based Testing

Role: worker. This command derives and generates property-based tests
directly — it does not replace example-based tests, and it does not
fabricate a weak "doesn't crash" property when no round-trip pair or
documented invariant can be found.

## Procedure

### Step 1: Detect the target language (reuse project-init — never re-derive)

Run project-init's own stack detection —
`${CLAUDE_PLUGIN_ROOT}/skills/project-init/SKILL.md` § "Step 1: Detect the
stack" — over the target project. That section is this repo's canonical,
single source of truth for stack detection (its own frontmatter says so);
this skill reuses its result and never re-implements the filesystem-signal
table (`package.json`/`tsconfig.json` for JS/TS, `pyproject.toml`/
`requirements*.txt`/`setup.py` for Python, `*.sln`/`*.csproj` for C#,
`pom.xml`/`build.gradle` for Java) itself.

Reduce that step's result to a single detected-language value:

- Exactly one stack detected → its display name (`Python`,
  `JavaScript/TypeScript`, `C#`, `Java`).
- Zero or ambiguous signals (project-init's own "ask the user" branch) →
  no detected language.

### Step 2: Gate on support

Pass the detected language (or nothing, when Step 1 found none) to
[`scripts/detect_and_dispatch.py`](scripts/detect_and_dispatch.py):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/property-based-testing/scripts/detect_and_dispatch.py" --language "<detected language>"
```

This script decides support — it does not detect anything itself (see its
own module docstring). When the language is neither `Python` nor
`JavaScript/TypeScript`, or no language was passed at all, it prints the
exact message below and exits non-zero. **Stop here — no partial run, no
file written**, exactly as the Gherkin "Unsupported or undetected language"
scenario requires:

```
Unsupported language: <detected|unknown> — supported: Python, JavaScript/TypeScript.
```

`<detected>` is the actual detected language name (e.g. `Go`, `C#`) when
Step 1 found one but it isn't supported; the literal word `unknown` when
Step 1 found nothing at all.

On a supported language, the script prints which generator to dispatch to
next and exits `0` — continue to Step 3.

### Step 3: Install the property-testing tool if missing

Follow project-init's own detection-gated-tool install pattern (`Step 4:
Install missing tools` of `project-init/SKILL.md`) rather than inventing a
new install mechanism — the tool is only installed when it's actually
missing from the target project:

- **Python — Hypothesis.** Add `hypothesis` to the project's own
  dev-dependency mechanism (`pyproject.toml` dev group or
  `requirements-dev.txt`, creating the latter if neither exists), exactly
  as project-init's Python lane already does for `ruff`/`mypy`/`pytest`.
- **JavaScript/TypeScript — fast-check.** `npm install --save-dev
  fast-check`, mirroring project-init's existing `npm` devDependency install
  shape for `oxlint`/`@playwright/test`.

Never a global/user-level install — same repo-level-only rule project-init
states for every lane and capability tool.

### Step 4: Generate the property test

- **Python** — invoke Step 4.1's scaffold directly:

  ```bash
  python3 "${CLAUDE_PLUGIN_ROOT}/skills/property-based-testing/scripts/hypothesis_scaffold.py" <module_path> <function_name> [--out-dir <dir>]
  ```

  It derives a round-trip property (a literal `encode`/`decode` pair) or an
  invariant property (a recognized docstring postcondition phrase near a
  type hint), writes `test_<function_name>_properties.py`, and prints its
  path. When neither heuristic matches, it prints the exact "No property
  derived" message and writes nothing — report that message verbatim rather
  than fabricating a property.

- **JavaScript/TypeScript** — follow
  [`references/languages/javascript.md`](references/languages/javascript.md)
  for the fast-check equivalent of the Python scaffold above: the same
  round-trip/invariant heuristic (an `encode`/`decode` export pair, or a
  recognized postcondition phrase in a JSDoc comment near a type
  signature), emitting a runnable `fc.assert(fc.property(...))` test file.

### Step 5: Recommend the mutation-testing follow-up (documentation only)

After Step 4 writes a test file, **recommend** — do not auto-run —
verifying it actually catches behavioral changes:

> Run `/mutation-testing` against the generated test file and report the
> resulting mutation score.

This skill never invokes `/mutation-testing` itself; that stays a separate,
user-initiated step so this skill doesn't re-implement mutation-testing's
own orchestration.

## When not to apply

- A function with no obvious round-trip pair or documented invariant — see
  Step 4's "No property derived" message rather than generating a weak
  "doesn't crash" test.
- A language other than Python or JavaScript/TypeScript, or a project whose
  stack detection is ambiguous — see Step 2's unsupported-language message.
