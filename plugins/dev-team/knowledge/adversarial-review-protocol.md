# Adversarial Review Protocol

Shared challenger methodology for all review agents. After producing initial findings, every review agent runs **The Loop** below, works its own agent-specific challenge questions (defined in that agent's `## Self-Challenge` section), and records the result per **Output**. The pass prevents incomplete analysis, unjustified severities, and premature exits.

## The Loop

After the initial review pass, re-examine findings with the following questions. Address each challenge before delivering the report.

1. **Completeness** — Did the reviewer examine every file in scope? List files NOT examined and state why.
2. **Evidence** — Does every finding quote actual code? Flag any finding without a direct code citation.
3. **Severity justification** — Is each error/high-severity rating backed by concrete impact (data loss, security breach, test suite failing silently, production breakage)? Downgrade if not.
4. **Blind spots** — What categories of issues are ABSENT from the findings? Absence in async code with no concurrency findings, or complex business logic with no domain findings, is suspicious. State the absent category and why it isn't an issue (or add a finding).
5. **False-negative pass** — Re-read the 3 largest files independently. Are there issues the initial pass walked past?
6. **Lazy exits** — Any finding with "could not assess because..." — is that actually true, or is it a shortcut?

Repeat until the challenger finds no new issues, or a maximum of 3 rounds is reached. Each agent's own `## Self-Challenge` questions sharpen this loop for that agent's domain — run them as part of the same pass.

The challenger verifies; it does not fill a quota. Zero new findings after an honest
pass is a passing outcome — never manufacture a finding to prove the loop ran, and
never upgrade a `suggestion` to justify the round.

## Zero-Findings Anomaly

When the Self-Challenge pass produces **zero Confirmed findings** on a **non-trivial
file** (any file over ~50 lines with real logic — not a stub, generated file, or pure
type declaration), treat that outcome as a sensitivity signal rather than a quality
signal. In the `summary` field:

1. **State the checks performed** — enumerate each challenge question from The Loop
   and each agent-specific Self-Challenge question, and note that each was examined.
2. **Cap confidence at Medium** — a suspiciously clean pass more likely reflects
   evaluator-sensitivity failure than actual perfection. Do not emit `Confidence: High`
   for a zero-findings result on a non-trivial file.

Example wording: _"Zero findings after honest pass. Checks performed: completeness
(all N files examined), evidence, severity justification, blind spots
(concurrency — none present; error paths — all handled), false-negative re-read,
lazy exits. Confidence: Medium (zero findings on non-trivial file — sensitivity
signal)."_

This rule does not apply to trivially small files, stubs, generated artifacts, or
files that genuinely have no logic to review — for those, a zero-findings pass with
`Confidence: High` is appropriate. Briefly note why the file is trivial.

## Output

After the challenger pass, append to the `summary` field in your JSON output:

```
Challenge: N round(s). Revisions: <count>. Blind spots examined: <list>. Confidence: High|Medium|Low.
```

Agents that emit a non-JSON report instead of a `summary` field — `data-flow-tracer` (trace report) and `session-analysis` (ranked suggestion list) — append the same `Challenge:` line to the report's closing summary sentence.

- **High**: all files examined, every finding has a code citation, no suspicious absences
- **Medium**: 1-2 files not examined or 1 finding revised downward
- **Low**: >2 files not examined, multiple revisions, or a finding was retracted
