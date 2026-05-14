# Fixture: aca-registry-update

**Skill**: agent-create  
**Scenario**: After successful agent creation, registry and CLAUDE.md are updated

## Test Case A: Review Agent

Agent `unused-import-review` (type: review, model: haiku) created successfully.

Expected: `knowledge/agent-registry.md` contains a new row in the Review Agents table:
```
| unused-import-review | agents/unused-import-review.md | small | Detects unused import statements |
```

Expected: `plugins/agentic-dev-team/CLAUDE.md` contains a new row in the Review Agents table for `unused-import-review`.

Expected: NO row added to the Team Agents table in either file.

## Test Case B: Team Agent

Agent `schema-planner` (type: team, model: sonnet) created successfully.

Expected: `knowledge/agent-registry.md` contains a new row in the Team Agents table:
```
| schema-planner | agents/schema-planner.md | mid | Plans database schema migrations |
```

Expected: `plugins/agentic-dev-team/CLAUDE.md` contains a new row in the Team Agents table.

Expected: NO row added to the Review Agents table in either file.

## Failure Conditions

- Row added to wrong table → FAIL
- Existing rows modified → FAIL
- Row format deviates from `| <name> | <file-path> | <tier-label> | <description> |` → FAIL
- Both files not updated → FAIL

## Model → Tier Mapping

| Model | Tier Label |
|-------|-----------|
| haiku | small |
| sonnet | mid |
| opus | frontier |
| inherit | mid |
