---
name: frontmatter-field-check
description: Verify each agent file declares the required frontmatter fields
tools: Read, Grep, Glob
effort: medium
---

# Frontmatter Field Check

Output JSON:

```json
{"status": "pass|fail", "issues": [{"file": "", "message": ""}], "summary": ""}
```

## Detect

For every file matching `agents/*.md`:

1. Read the YAML frontmatter between the first two `---` lines.
2. Assert the keys `name`, `description`, `tools`, and `effort` are all present.
3. Assert `effort` is exactly one of `low`, `medium`, `high`.
4. Assert the `description` value contains no `:` character.

Report one issue per file per missing or invalid key, with the exact key name.
The result is fully determined by the file contents — the same input always
produces the same list of missing keys, with no judgment involved.
