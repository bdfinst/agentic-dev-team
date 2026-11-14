# Rubric: codebase-recon

A good answer runs the seven-step recon procedure and emits a RECON envelope (schema_version 0.2) that names the true entry points with the signal that classifies each, the dependencies from the manifests, the package manager, the architecture layers, and the security surface by file path. It surfaces surfaces without evaluating findings, and it reports only files that exist.

## Criteria

- **envelope-present**: The answer includes the `RECON written:` summary and a JSON envelope with `schema_version` `"0.2"` and the repo, languages, entry points, dependencies, architecture, security surface, git history, and notes fields.
- **rationale-per-entry-point**: Every entry point carries a rationale naming the specific signal observed (shebang, `app.listen`, decorator, `exports.handler`, `main` field).
- **no-fabricated-paths**: Every path in the envelope is a file that exists in the fixture repository.
- **surface-not-findings**: The envelope lists surfaces without severity ratings or vulnerability verdicts.
