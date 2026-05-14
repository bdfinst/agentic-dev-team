# Fixture: aca-review-body-valid

**Skill**: agent-create  
**Scenario**: Review agent body generation produces valid, token-efficient output

## Input

- name: `unused-import-review`
- type: `review`
- description: `Detects unused import statements`
- tools: `Read, Grep, Glob`
- model: `haiku`

## Expected Body Properties

1. **Line count**: ≤ 40 lines (all content after closing `---` of frontmatter, inclusive)
2. **Required sections** (in order): `# Unused Import Review`, Output JSON block, Status/Severity/Confidence lines, `Model tier:`, `Context needs:`, `## Skip`, `## Detect`, `## Ignore`
3. **No "You are a/an" opener**: no line matches `^You are an? ` (case-insensitive)
4. **No description restatement**: body does not contain "Detects unused import statements" verbatim (whitespace-normalized)
5. **No placeholder text**: no `your-agent-name`, `One-sentence description`, `# Agent Name`
6. **Bullet length**: no bullet spans more than two lines

## Expected Output JSON Block

```json
{"status": "pass|warn|fail|skip", "issues": [{"severity": "error|warning|suggestion", "confidence": "high|medium|none", "file": "", "line": 0, "message": "", "suggestedFix": ""}], "summary": ""}
```

## Failure Conditions

- Body > 40 lines → FAIL
- Missing any required section → FAIL
- "You are a" opener → FAIL
- Description restated verbatim → FAIL
