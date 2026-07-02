# Mutation Testing — Python (mutmut)

Tool: [mutmut](https://mutmut.readthedocs.io/). Detection: `mutmut` in requirements or pyproject.

## Install / detect

Both install paths are **local** — scoped to the active virtual environment (`.venv/bin/mutmut`), not the system-wide `pip`. Pick one:

```bash
# (a) install directly into the active venv
pip install mutmut

# (b) declare it in pyproject.toml and let pip resolve it as a dev dep
# [project.optional-dependencies]
# dev = ["mutmut"]
pip install -e .[dev]
```

Never `pip install --user mutmut` or run `pip install` outside a venv for this — that puts mutmut in a location whose `PATH` presence depends on the user's shell config, which is the silent-failure trap the skill's "prefer local install" note is trying to avoid.

Confirm the tool resolves in the active venv before configuring a run:

```bash
mutmut --version
```

## Run (scoped)

> When capturing run output to a log file, do **not** use a bare `mutmut run ... 2>&1 | tee run.log` — the pipeline exit code is `tee`'s (always 0), so a tool failure is silently masked. Use `>run.log 2>&1` for one-shot runs or `set -o pipefail` for live tail. See [`SKILL.md` → Capturing run output safely](../../SKILL.md#capturing-run-output-safely).

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
