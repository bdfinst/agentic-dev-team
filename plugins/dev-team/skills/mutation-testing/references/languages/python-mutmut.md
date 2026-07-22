# Mutation Testing — Python (mutmut)

Tool: [mutmut](https://mutmut.readthedocs.io/). Detection: `mutmut` in requirements or pyproject.

**Pin `mutmut<3`.** mutmut 3.x ships an incompatible config/CLI contract
(`source_paths` in a `[mutmut]` setup.cfg section, no `--paths-to-mutate`
flag, no `run`/`results`/`junitxml` subcommands in the same shape) that the
adapter and this reference below do not speak. `pip install mutmut`
unpinned resolves to 3.x today.

## Install / detect

Both install paths are **local** — scoped to the active virtual environment (`.venv/bin/mutmut`), not the system-wide `pip`. Pick one:

```bash
# (a) install directly into the active venv
pip install "mutmut<3"

# (b) declare it in pyproject.toml and let pip resolve it as a dev dep
# [project.optional-dependencies]
# dev = ["mutmut<3"]
pip install -e .[dev]
```

Never `pip install --user mutmut` or run `pip install` outside a venv for this — that puts mutmut in a location whose `PATH` presence depends on the user's shell config, which is the silent-failure trap the skill's "prefer local install" note is trying to avoid.

Confirm the tool resolves in the active venv before configuring a run
(`version` is a subcommand — there is no `--version` flag):

```bash
mutmut version
```

## Run (scoped)

> When capturing run output to a log file, do **not** use a bare `mutmut run ... 2>&1 | tee run.log` — the pipeline exit code is `tee`'s (always 0), so a tool failure is silently masked. Use `>run.log 2>&1` for one-shot runs or `set -o pipefail` for live tail. See [`SKILL.md` → Capturing run output safely](../../SKILL.md#capturing-run-output-safely).

```bash
mutmut run --paths-to-mutate=src/calculator.py
```

## Per-mutant timeout

mutmut has no `--timeout <seconds>` flag. Its own per-mutant timeout is
`baseline_time * test_time_multiplier + test_time_base` (`-m`/`-b`,
defaults `2.0`/`0.0`) — a mutant whose test run exceeds that computed
budget is reported `TIMEOUT`. The shipped adapter
(`hooks/mutation_adapters/mutmut.py`) does not rely on this; it wraps the
whole `mutmut run` invocation in an external, OS-level timeout
(`ADAPTER_TIMEOUT`, from `MUTATION_GATE_TIMEOUT`, default 120s) so a
runaway run is killed regardless of mutmut's own per-mutant accounting.

## Native report → schema mapping

mutmut has no `--json` results output. Source: `mutmut junitxml` — a
`<testcase>` with a `<failure>` child is a survived mutant under the
default suspicious/untested policies (both `ignore`); one without is
killed. `name`, `file`, and `line` come from the `<testcase>` attributes:

```xml
<testcase name="Mutant #8" file="src/calculator.py" line="12">
  <failure type="failure" message="bad_survived">--- diff ---</failure>
</testcase>
```

Map each `<failure>`-bearing `<testcase>` to a `survived` entry in the
normalized envelope below (`operator` has no mutmut equivalent — omit it
or leave `null`, unlike Stryker/pitest which name a mutator/operator per
survivor):

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
    { "file": "src/calculator.py", "line": 12, "operator": null, "status": "survived" }
  ]
}
```

This normalized envelope is produced by the triaging agent reading the
native report (per this doc's mapping) — `mutation_report.py` and
`mutation_kill_loop.py` have no mutmut-specific parsing yet (see
[SKILL.md → Machine-readable output](../../SKILL.md#machine-readable-output)).

## Language-specific notes

- mutmut stores per-mutant state in `.mutmut-cache` — keep it out of version control but cache it between CI runs for incremental speed.
- For pytest-based suites, ensure the runner inherits the project's `PYTHONPATH` / virtualenv; mutmut shells out to the same `python` it was invoked with.
