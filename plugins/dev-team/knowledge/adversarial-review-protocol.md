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

## Output

After the challenger pass, append to the `summary` field in your JSON output:

```
Challenge: N round(s). Revisions: <count>. Blind spots examined: <list>. Confidence: High|Medium|Low.
```

Agents that emit a non-JSON report instead of a `summary` field — `data-flow-tracer` (trace report) and `session-analysis` (ranked suggestion list) — append the same `Challenge:` line to the report's closing summary sentence.

- **High**: all files examined, every finding has a code citation, no suspicious absences
- **Medium**: 1-2 files not examined or 1 finding revised downward
- **Low**: >2 files not examined, multiple revisions, or a finding was retracted
