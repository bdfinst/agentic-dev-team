# Fixture: aca-review-preamble-rejected

**Skill**: agent-create  
**Scenario**: Role-playing opener ("You are an expert...") must not appear in generated body

## Expected Behavior

When generating ANY review or team agent body, the skill must never produce a
line matching `^You are an? ` (case-insensitive).

This fixture validates the anti-pattern rule is enforced at generation time,
not as a post-hoc check.

## Examples of Forbidden Lines

```
You are an expert code reviewer.
You are a security specialist.
You are an experienced TypeScript developer.
```

## Examples of Acceptable Openers

```
# Import Cycle Review
Review agent for detecting circular imports.
Detects unused import statements in JavaScript and TypeScript files.
```

## Failure Conditions

- Any generated body line matches `^You are an? ` (case-insensitive) → FAIL
- Must FAIL even if this appears mid-body, not just as the first line
