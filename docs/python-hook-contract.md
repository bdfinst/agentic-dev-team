# Python hook contract

Phase 0 deliverable of the bash → Python hook migration ([#572]). Every
Python hook that ships with the `dev-team` plugin MUST honor this contract
byte-for-byte. During the migration (Phases 1–3), the parity harness at
`plugins/dev-team/tests/hooks/parity/` mechanically enforced the contract. For
each hook, the harness ran the `.sh` and the `.py` against identical
`(stdin, env, argv, initial-tree)` fixtures. It asserted equal stdout, exit
code, normalized stderr, and side-effect tree. Every hook is now Python-only,
and the team retired the parity harness ([ADR 0015]). The pytest files
`plugins/dev-team/tests/hooks/test_*.py` now enforce the contract.

The contract mirrors the Claude Code hook payload conventions that the bash
hooks already use. Nothing here is Python-specific except the authoring rules
at the bottom.

---

## stdin

Claude Code launches hooks with a JSON blob on stdin. The shape is the same
PreToolUse / PostToolUse / SessionStart / UserPromptSubmit / Stop payload that
the bash hooks already parse. All fields are optional from the hook's point of
view. A well-behaved hook silently passes when a field it needs is missing,
rather than crashing.

Canonical (partial) shape:

```json
{
  "session_id": "<uuid>",
  "hook_event_name": "PreToolUse",
  "cwd": "/abs/path/to/project",
  "tool_name": "Bash",
  "tool_input": {
    "command": "dotnet stryker ..."
  },
  "tool_response": {
    "exitCode": 0,
    "stdout": "...",
    "stderr": "..."
  },
  "transcript_path": "/abs/path/to/transcript.jsonl",
  "prompt": "the user prompt (UserPromptSubmit only)"
}
```

- Read stdin with `sys.stdin.read()` once. Do not use `readline()`. Payloads
  may span multiple lines, and future events may embed newlines in string
  values.
- Parse with `json.loads`. Malformed input MUST NOT crash the hook.
  Treat it as advisory or silent-pass, depending on the hook's contract.
- Empty stdin (`""`) is a valid input for every hook. A hook that has
  nothing to do returns 0 with empty stdout.

## stdout

- Stdout is the **user-visible channel**. Every non-empty line renders in
  the terminal. Treat stdout as UI, not logging.
- Do not print trailing whitespace. Do not emit ANSI color escapes.
- Prefix advisory messages with `ADVISORY:` on the same line, and end them
  with a newline.
- Prefix block messages with `[BLOCK]` on the first line of a multi-line body.
- Silent-pass hooks emit nothing at all.
- Encoding is UTF-8. On Windows, do not rely on the code-page default. Set
  `PYTHONIOENCODING=utf-8` in the hook when it cannot afford mojibake.

## Exit codes

The bash hooks use a four-tier convention that Claude Code understands:

| Code | Meaning | UX |
| ------ | --------- | ----- |
| `0` | pass (silent or advisory) | Claude Code proceeds |
| `1` | soft-fail / advisory error | Claude Code proceeds but surfaces the message |
| `2` | **block** — Claude Code halts the tool call | required for gate hooks |
| `≥ 3` | tool-specific | reserved for the hook's own consumers |

`0` combined with non-empty stdout prefixed `ADVISORY:` is the standard
"warn but do not block" pattern (see `mutation-testing-smoke-gate.sh`).

## Environment variables

Hooks MAY read the following environment variables. Claude Code or the
plugin's own settings.json sets them:

- `CLAUDE_PROJECT_DIR` — absolute path to the project root. When writing to
  plugin-owned side-effect trees, prefer `artifact_paths.project_root()`. The
  trees are `.claude/memory/`, `.claude/metrics/`, `.claude/plans/`,
  `.dev-team-reports/`, `.telemetry/`, and `.claude/hooks/`. The function
  resolves the git root via `git rev-parse --show-toplevel`. It falls back to
  the start directory or `os.getcwd()`. It does not read `CLAUDE_PROJECT_DIR`.
  The `.claude/hooks/` tree (issue #1904 item 10) holds plugin **runtime
  state** files. `/freeze`, `/unfreeze`, `/careful`, and `/guard` write them.
  `pre_tool_guard.py` and `destructive_guard.py` read them back
  (`freeze-state.json`, `careful-state.json`). It is NOT operator-authored
  hook code, despite the name collision with the top-level `hooks/` directory
  that plugin authors do own.
- `CLAUDE_TOOL_NAME` — name of the tool being invoked (`Bash`, `Edit`, …).
- `CLAUDE_SESSION_ID` — current session UUID. The UUID is also on stdin, but
  Claude Code sets this env var for hooks that do not parse stdin.
- `MUTATION_SMOKE_GATE_SKIP` — hook-specific escape hatch (see the
  smoke-gate hook).
- `DEV_TEAM_VERSION_CHECK_CACHE_DIR` — overrides `version_check.py`'s daily
  cache directory (default `/tmp`). This is a test-only escape hatch (#1574).
  It lets pytest give each worker or run its own cache path instead of racing
  on the one real, shared `/tmp` file. Production callers never set it.

A hook MUST NOT depend on any variable not listed here without adding the
variable to this doc. That rule keeps parity fixtures reproducible across
macOS + Linux + Windows Git Bash.

## stderr

- Stderr is for **advisory diagnostics that should not appear in the
  terminal UI**. Examples are filesystem errors, JSON parse warnings on
  degenerate inputs, and timing traces during `DEV_TEAM_DEBUG=1`.
- Never write user-actionable messages to stderr alone. Duplicate them to
  stdout with the `ADVISORY:` prefix if the operator needs to see them.
- **Exception — exit-2 (block) messages: mirror to stderr in addition to
  stdout** (`pre_commit_review.py`, #1367). Some Claude Code hook-error
  wrappers surface only stderr on a nonzero hook exit. A stdout-only block
  message can go completely unseen there. The operator sees only a generic
  "hook error, no stderr output" with no actionable reason.
- Stdout stays the canonical, primary UI channel. Stderr is additive
  duplication for block paths specifically. It is not a general license to
  move messages to stderr.
- Treat dual-write as the standard for any new exit-2 hook, or any existing
  one you touch.
- Hooks not yet converged write to stderr only today
  (`contract_version_guard.py`, `pre_commit_knowledge_index.py`) or to stdout
  only today (`destructive_guard.py`, `eval_compliance_check.py`). Converging
  them is a separate cleanup. This note does not imply it.
- The parity harness normalizes stderr before comparison. It strips ISO-8601
  timestamps, PIDs, and tmpdir path prefixes. It strips nothing else. If two
  implementations diverge on anything past those three axes, that is a
  real divergence. Fix the hook. Do not widen the normalization.

## Python authoring rules

- **Stdlib-only.** Zero third-party imports. Every dependency the hook
  needs is in Python 3.10's stdlib: `argparse`, `dataclasses`, `hashlib`,
  `json`, `os`, `pathlib`, `re`, `shlex`, `shutil`, `signal`, `subprocess`,
  `sys`, `tempfile`. No `requirements.txt` for shipped hooks. The plugin
  ships to users who cannot `pip install` on their machines.
- **Target Python 3.10+** (ADR 0031). `match/case` and `X | None` unions
  are allowed. `from __future__ import annotations` is fine for type-hint
  delay.
- **CLI with argparse** when a hook takes arguments. Otherwise, read stdin
  and dispatch on JSON fields.
- **Tests: pytest.** Unit tests live under `plugins/dev-team/tests/hooks/`
  (per-hook file). The `.sh`↔`.py` parity harness once lived under
  `plugins/dev-team/tests/hooks/parity/`. The team retired it once every hook
  shipped as Python-only ([ADR 0015]). `test_*.py` is the coverage source of
  truth.
- **Lint: ruff.** Type-check optional (`mypy` is not on the CI critical
  path).
- **`main() -> int`** returns the exit code. A trailing
  `if __name__ == "__main__": sys.exit(main())` shim runs the hook.
- **Signal handling.** Long-running hooks (like the mutation-testing
  wrapper's status loop) MUST register SIGINT/SIGTERM handlers that flush
  their state before exit. See `plugins/dev-team/skills/mutation-testing/scripts/csharp_stryker_net_wrapper.py`.
- **Cross-platform.** Use `pathlib.Path`, never string concatenation for paths.
  Never use `subprocess.run(..., shell=True)` unless the command is a static
  literal. Otherwise, quote arguments through `shlex.quote`. `subprocess.run`
  behaves identically on all three platforms. `bash -c` does not.
- **Privacy boundary.** Persist tokens, dollars, model IDs, or hashes —
  never prompt text, code, file paths, or tool payloads. Mirror
  `hooks/lib/cost_meter.py`'s posture.

## References

- [`#572`](https://github.com/bdfinst/agentic-dev-team/issues/572) — the
  migration epic.
- [ADR 0015](adr/0015-bash-removal-complete.md) — the migration's
  completion; retires the parity harness referenced above.
- `plans/cached-inventing-wave.md` — Phase 0 architectural context.
- `plugins/dev-team/hooks/lib/cost_meter.py`,
  `plugins/dev-team/hooks/lib/build_knowledge_index.py`,
  `plugins/dev-team/hooks/lib/telemetry_report.py` — reference Python
  hook implementations (already in production).
