# Rubric: tech-writer

A good tech-writer answer edits the documentation in place so that a stranger can follow it, and reports exactly what changed. It treats the code and glossary as the source of truth, uses one term per concept, and writes short, plain, active sentences. It keeps every fact intact and does not invent behavior.

## Criteria

- **reports-changes**: The final message states the concrete changes made (file plus old and new text, or the final file content) as the task asks.
- **facts-preserved**: Does not add, drop, or alter technical facts (commands, flags, defaults, ports, URLs, counts) except to correct them against the provided source of truth.
- **one-term-per-concept**: The edited text uses a single consistent term for each concept, matching the provided glossary or code.
- **scope-respected**: Changes only the documentation files the task names, never the code or files the task marks as the source of truth.
- **plain-language**: Edited prose uses plain words and sentences of 25 words or fewer, without unexplained jargon.
