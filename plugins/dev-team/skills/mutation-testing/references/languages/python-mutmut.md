# Mutation Testing — Python (mutmut)

Tool: [mutmut](https://mutmut.readthedocs.io/). Detection: `mutmut` in requirements or pyproject.

## Install / detect

```bash
pip install mutmut
# or add to pyproject.toml [project.optional-dependencies] dev
```

## Run (scoped)

```bash
mutmut run --paths-to-mutate=src/calculator.py
```

## Per-mutant timeout flag

```bash
mutmut run --paths-to-mutate=src/calculator.py --timeout <seconds>
```

Default shipped: 60 s. Set `--timeout` to `timeout_seconds` (formula in [`SKILL.md`](../../SKILL.md) Step 1b). mutmut passes the value to the per-mutant subprocess.

## Native report → schema mapping

Source: `mutmut results --json`. Each surviving mutant carries `filename`, `line_number`, and a mutmut-specific mutation type.

```json
{
  "schema_version": 1,
  "tool": "mutmut",
  "scope": ["src/calculator.py"],
  "captured_at": "2026-06-19T14:28:42Z",
  "total": 28,
  "killed": 22,
  "survived": 5,
  "equivalent": 1,
  "survivors": [
    { "file": "src/calculator.py", "line": 12, "operator": "RelationalOperator", "status": "survived" }
  ]
}
```

## Language-specific notes

- mutmut stores per-mutant state in `.mutmut-cache` — keep it out of version control but cache it between CI runs for incremental speed.
- For pytest-based suites, ensure the runner inherits the project's `PYTHONPATH` / virtualenv; mutmut shells out to the same `python` it was invoked with.
