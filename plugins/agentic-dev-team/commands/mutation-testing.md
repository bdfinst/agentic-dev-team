---
name: mutation-testing
description: >-
  Run a mutation testing tool (Stryker/pitest/mutmut) and triage surviving mutants. AI classifies survivors and writes fix tests.
argument-hint: "<source-file-or-module>"
user-invocable: true
---

Read skills/mutation-testing/SKILL.md and follow its 5-step procedure exactly:

1. **Detect tooling** — find the project's mutation testing tool (Stryker, pitest, mutmut). If none is installed, help set one up. Do NOT proceed without a real tool.
2. **Run the tool** — scoped to the target files. Capture full output.
3. **Parse results** — extract surviving mutants, mutation score, and report path.
4. **Triage survivors** — classify each as equivalent, missing-assertion, missing-test, undertested-boundary, or acceptable-risk. This is where AI adds value.
5. **Write fix tests** — for each non-equivalent survivor, write a test using RED-GREEN discipline.

**Critical constraints:**
- Do NOT estimate or academically reason about mutation outcomes. Run the tool, read real results, triage real survivors.
- **Always ask the user before running.** Present the time estimate and scope, get explicit approval. Never start a mutation run without confirmation — it can be slow.

Apply this to: $ARGUMENTS
