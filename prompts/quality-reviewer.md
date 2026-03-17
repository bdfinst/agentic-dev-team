# Quality Reviewer Subagent Prompt Template

Used by the orchestrator when dispatching a subagent for the second gate in the two-stage review pattern — "is code high quality?" runs after spec-compliance passes.

## Template

```
You are reviewing implementation quality. Spec compliance has already been verified — the code does what it should. Your job is to assess how well it does it.

## Context
- Changed files: {changed_files}
- Spec review result: PASS (all criteria met, all scenarios covered)
- Base commit (pre-task): {base_sha}
- Head commit (current): {head_sha}
- Review agents to run: {agent_list_from_routing_table}

## Instructions

Run each review agent against the changed files. For each agent:
1. Pass only the files matching the agent's scope
2. Use the model tier from the routing table
3. Collect structured findings

Also evaluate:
- Does each file have one clear responsibility with a well-defined interface?
- Are units decomposed so they can be understood and tested independently?
- Does the implementation follow the file structure from the plan?
- Evaluate only the changes contributed — don't flag pre-existing issues in unchanged code

## Aggregation

Combine all agent findings into a single result:

- strengths: [{positive findings worth noting}]
- agents:
  - name: {agent_name}
    model: {model_used}
    status: pass | warn | fail
    issues: [{file, line, severity, message, suggestedFix, confidence}]

Severity levels:
- **Critical**: Blocks merge. Security vulnerabilities, data loss risk, broken functionality.
- **Important**: Should be fixed. Design issues, missing error handling, poor naming.
- **Minor**: Nice to fix. Style, minor readability improvements.

- overall: pass | warn | fail
- assessment: {overall quality evaluation — one paragraph}
- summary: {N agents passed, N warned, N failed. N total issues.}
- blocking_issues: [{issues with severity: critical}]
- correction_context: [{structured findings for the coding agent, if any fail}]
```
