Build a Universal AST Harvester system under an `ast-harvester/` directory.

The system crawls a list of repositories, parses source code into Abstract Syntax Trees using tree-sitter, and exports a Domain-Enriched Structural Index in JSON and Markdown formats optimised for LLM consumption.

## Requirements

**Multi-repo support**
Accept a YAML or JSON config file listing repositories as Git URLs or local paths. Support per-repo branch selection and token-based authentication via environment variables.

**Parser engine**
Use tree-sitter with language grammars for TypeScript, JavaScript, Python, and Go. Extract:
- Definitions: classes, interfaces, structs, enums
- Behaviors: function and method signatures with decorators/annotations
- Relationships: import/export graphs

**Contextual enrichment**
- Domain Triggers: flag methods whose names contain keywords like `publish`, `emit`, `send`, `handle`, `dispatch`, `notify`
- State Managers: flag classes whose names match patterns like `Repository`, `Cache`, `Store`, `Registry`, `Singleton`

**Output**
- Context Map (per repo): full structural index with definitions, functions, imports, exports, domain triggers, and state managers — no raw implementation bodies
- LLM Manifest (cross-repo): flattened API surface, DDD classification (aggregates, repositories, services, domain events, value objects), and external dependencies

**Incremental indexing**
Track each repo's HEAD commit SHA. Skip re-parsing repos whose SHA has not changed since the last run.

**CLI**
- `harvest` — clone/pull repos and write context maps and manifest
- `manifest` — rebuild the manifest from existing context maps without re-parsing

## Tech stack
- TypeScript (CommonJS, ts-node)
- tree-sitter + tree-sitter-typescript, tree-sitter-javascript, tree-sitter-python, tree-sitter-go
- simple-git for repository operations
- js-yaml for config parsing
- commander for CLI
