---
name: init-plugin-eval
description: >-
  Scaffold the eval directory structure for a plugin's review agents and advisory
  skills. Use after creating a plugin or adding its first review agent, or when
  the user says "set up evals for this plugin", "init plugin evals", "scaffold
  eval fixtures", or "create the eval harness for <plugin>". Creates the
  fixtures/ and expected/ dirs plus a README describing the grading contract.
argument-hint: "<plugin-name> [--dir evals/<plugin-name>]"
role: implementation
allowed-tools: Read, Write, Bash, Glob
---

# Init Plugin Eval

Role: implementation. Create the eval scaffold so a plugin's review agents and
advisory skills can be graded — without shipping any of it inside the plugin.

## Constraints

1. **Evals never ship.** The eval tree lives at the **repo root** under
   `evals/<plugin>/`, never under `plugins/<plugin>/`. Build/test tooling inside
   a plugin dir is a shipping bug.
2. **Stub, don't fake.** Scaffold empty `fixtures/` and `expected/` dirs and a
   README. Do **not** invent fixtures — an empty scaffold must grade as
   "no fixtures", a clean no-op, not an error.
3. **Never overwrite.** If `evals/<plugin>/` exists, report and stop.

## Step 1 — Parse

- `NAME` = `$0` (the plugin name, matching its `plugin.json` `name`).
- `DIR` = `--dir` value, else `evals/<NAME>`.
- If `DIR` exists → report and stop.

## Step 2 — Create the structure

```bash
mkdir -p "$DIR/fixtures" "$DIR/expected"
for d in fixtures expected; do : > "$DIR/$d/.gitkeep"; done
```

- `fixtures/` — input artifacts an agent/skill runs against (sample agent files,
  plugin dirs, prose use-cases).
- `expected/` — one `<fixture-stem>.json` per fixture declaring the expected
  grading (which agent/skill it targets and the pass condition).

## Step 3 — Write the grading-contract README

**`$DIR/README.md`** documents the contract a grader enforces:

```markdown
# Eval corpus — <NAME>

Fixtures (`fixtures/`) and their expected gradings (`expected/*.json`) for the
<NAME> plugin's review agents and advisory skills.

## Grading contract

Each `expected/<stem>.json` pairs with a `fixtures/<stem>.*` input and declares:

- `fixture` — the fixture file/dir this grades.
- `description` — what the fixture exercises.
- `applicableAgents` / `applicableSkills` — the unit(s) under test.
- For a **review agent**: `expectedStatus` (`pass|warn|fail|skip`),
  `issueCount` ({min,max}), and `severities` bounds.
- For an **advisory skill**: the expected `recommendation`/fields and the
  rule citations or gates the output must contain.

A grader pairs every `expected/*.json` with a fixture and checks the actual
output falls within the declared bounds. An **empty corpus grades as
"no fixtures"** — a clean no-op, never an error.
```

## Step 4 — Verify the empty scaffold is a clean no-op

Confirm the scaffold grades as "no fixtures", not an error:

- `expected/` contains only `.gitkeep` (no `*.json`) → a corpus check finds
  nothing to grade and reports "no fixtures".
- If a project-level eval runner exists (e.g. `scripts/eval_grade.py
  --check-corpus`), run it scoped to `evals/<NAME>/` and confirm exit 0 with a
  "no fixtures" / "nothing to grade" message.

## Completion report

```text
Eval scaffold created: <DIR>
Dirs:  fixtures/ expected/
Docs:  README.md (grading contract)
State: no fixtures yet → grades as a clean no-op
Next:  add a fixtures/<stem>.* input and an expected/<stem>.json grading
```
