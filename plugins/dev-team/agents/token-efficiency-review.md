---

name: token-efficiency-review
description: Token usage optimization, file length, CLAUDE.md size, LLM anti-patterns
tools: Read, Grep, Glob
model: haiku
effort: high
color: green
---

> **Implemented by:** ${CLAUDE_PLUGIN_ROOT}/scripts/token_efficiency_review.py

# Token Efficiency Review

Scope: always
Cites: [adversarial-review-protocol]
Enforcement: script

Output JSON: per `${CLAUDE_PLUGIN_ROOT}/knowledge/review-agent-output-contract.md` (Whole-file load: short, canonical schema).

Status: pass=efficient, warn=optimization opportunities, fail=major waste
Severity: error=critical waste, warning=significant, suggestion=minor
Confidence: high=mechanical (trim verbose rule, extract procedure to skill); medium=verbosity identified, rewrite depends on intent; none=requires human judgment (what detail level is appropriate)

Context needs: full-file

## Skip

Return `{"status": "skip", "issues": [], "summary": "No Claude Code config or source files in target"}` when:

- Target has no CLAUDE.md, rules, skills, or source code files
- Target contains only binary or generated files

## Thresholds

| Target | Limit |
| -------- | ------- |
| CLAUDE.md | <5000 chars |
| Code examples in CLAUDE.md | ≤10 |
| Rules | ≤200 chars each |
| Skill definitions | ≤2000 chars |
| File length | ≤500 lines |
| Function length | ≤50 lines |
| Nesting depth | ≤5 levels |
| JSDoc comments | ≤15 lines |
| Commented-out code | ≤5 lines total |

## Findings

Metric thresholds are enforced by `${CLAUDE_PLUGIN_ROOT}/scripts/token_efficiency_review.py` (exit 1 for errors, exit 2 for warnings). This agent provides qualitative analysis for issues the script cannot detect mechanically.

### CLAUDE.md

- Char limit exceeded (script-enforced at >5000)
- Excessive code examples
- Duplicate/repetitive sections
- Verbose command docs (prefer reference to package.json)
- Large ASCII diagrams
- Multi-step workflows that belong in skills

### Rules

- Verbose rules >200 chars
- Duplicate/similar rules
- Example-heavy rule files

### Skills

- Missing skills for common workflows
- Step-by-step procedures in CLAUDE.md that belong in skills
- Verbose skill definitions

### Code

- Long files (>500 lines, script-enforced)
- Long functions (>50 lines)
- Deep nesting (>5 levels)
- Duplicate code blocks

### Documentation

- Verbose JSDoc (>15 lines)
- Tutorial comments in source (belong in docs/)
- Commented-out code

## LLM-Native Validation

CLAUDE.md, rules, and skills must follow LLM-native patterns. Flag violations:

### Anti-patterns (flag these)

- Role preambles: "You are a...", "Act as...", "As an expert..."
- Conversational filler: "Please note that...", "It's important to...", "Remember to..."
- Redundant context: Repeating same information in different words
- Hedging language: "You might want to...", "Consider...", "Perhaps..."
- Verbose explanations before instructions
- Nested bullet hierarchies >2 levels deep
- Paragraph-form instructions (should be lists)
- Examples without clear pattern (>3 examples for same concept)

### Required patterns (flag if missing)

- Direct imperatives: "Use X", "Flag Y", "Return Z"
- Structured output schemas at top of prompts
- Lookup tables for mappings (status codes, severity levels)
- Flat list structures
- Terse detection patterns

### Severity mapping

- error: Role preambles, verbose explanations before action items
- warning: Conversational filler, redundant context, deep nesting
- suggestion: Minor verbosity, could be more terse

## Self-Challenge

After producing findings, run the shared challenger loop in `${CLAUDE_PLUGIN_ROOT}/knowledge/adversarial-review-protocol.md` (Whole-file load: the slim shared methodology — The Loop + Output format — read in full), then work these token-efficiency-review-specific challenges:

- Did you measure the actual char/line counts against the thresholds, or estimate "looks long"?
- For each LLM-anti-pattern finding (role preamble, filler, hedging), did you quote the offending text?
- Did you check whether a multi-step procedure in CLAUDE.md or rules should be a skill, not just flag its length?
- Are there duplicate or repetitive sections across files you missed by reviewing each file alone?
- For each "should be terser" suggestion, did you confirm trimming wouldn't drop a load-bearing instruction?

Append confidence level (High/Medium/Low) to the `summary` field.

## Ignore

Code correctness, security, logic (handled by other agents)
