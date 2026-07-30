# Python hook contract

Phase 0 deliverable of the bash → Python hook migration ([#572]). Every
Python hook that ships with the `dev-team` plugin MUST honor this contract
byte-for-byte. During the migration (Phases 1–3), the parity harness at
`plugins/dev-team/tests/hooks/parity/` mechanically enforced it: for each
hook it ran the `.sh` and the `.py` against identical
`(stdin, env, argv, initial-tree)` fixtures and asserted equal stdout, exit
code, normalized stderr, and side-effect tree. Every hook is now Python-only
and the parity harness has been retired ([ADR 0015]); the contract below is
enforced by `plugins/dev-team/tests/hooks/test_*.py` (pytest) instead.

The contract mirrors the Claude Code hook payload conventions already in
use by the bash hooks; nothing here is Python-specific except the
authoring rules at the bottom.

---

## stdin

Hooks are launched by Claude Code with a JSON blob on stdin. The shape is
the same PreToolUse / PostToolUse / SessionStart / UserPromptSubmit /
Stop payload the bash hooks already parse. All fields are optional from
the hook's point of view — a well-behaved hook silently passes when a
field it needs is missing rather than crashing.

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

- Read stdin with `sys.stdin.read()` once. Do not `readline()` — payloads
  may span multiple lines and future events may embed newlines in string
  values.
- Parse with `json.loads`. Malformed input MUST NOT crash the hook — the
  bash hooks treat malformed input as advisory or silent-pass depending
  on the hook's contract. Follow the sibling `.sh`'s behavior byte-for-
  byte during parallel-ship.
- Empty stdin (`""`) is a valid input for every hook. A hook that has
  nothing to do returns 0 with empty stdout.

## stdout

- Stdout is the **user-visible channel**. Every non-empty line renders in
  the terminal — treat it as UI, not logging.
- Do not print trailing whitespace. Do not emit ANSI color escapes.
- Advisory messages are prefixed with `ADVISORY:` on the same line and
  end with a newline. Block messages are prefixed with `[BLOCK]` on the
  first line of a multi-line body. Silent-pass hooks emit nothing at all.
- Encoding is UTF-8. On Windows, do not rely on the code-page default —
  set `PYTHONIOENCODING=utf-8` in the hook when it cannot afford a mojibake.

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

Hooks MAY read the following environment variables. They are set by
Claude Code or by the plugin's own settings.json:

- `CLAUDE_PROJECT_DIR` — absolute path to the project root. Prefer
  `artifact_paths.project_root()` (git-root resolution via `git rev-parse
  --show-toplevel`, falling back to the start directory or `os.getcwd()` —
  it does not read `CLAUDE_PROJECT_DIR`) when writing to plugin-owned
  side-effect trees (`.claude/memory/`, `.claude/metrics/`, `.claude/plans/`,
  `.dev-team-reports/`, `.telemetry/`).
- `CLAUDE_TOOL_NAME` — name of the tool being invoked (`Bash`, `Edit`, …).
- `CLAUDE_SESSION_ID` — current session UUID (also on stdin, but this env
  var is set for hooks that don't parse stdin).
- `DEV_TEAM_PY_HOOK_<NAME>` — per-hook toggle described in
  `plugins/dev-team/hooks/settings-toggle.md`. Default `0` (bash);
  `1` routes to the `.py` port.
- `MUTATION_SMOKE_GATE_SKIP` — hook-specific escape hatch (see the
  smoke-gate hook).
- `DEV_TEAM_VERSION_CHECK_CACHE_DIR` — overrides `version_check.py`'s daily
  cache directory (default `/tmp`). Test-only escape hatch (#1574) so pytest
  can give each worker/run its own cache path instead of racing on the one
  real, shared `/tmp` file; production callers never set it.

A hook MUST NOT depend on any variable not listed here without adding it
to this doc. That is the mechanism that keeps parity fixtures reproducible
across macOS + Linux + Windows Git Bash.

## stderr

- Stderr is for **advisory diagnostics that should not appear in the
  terminal UI** — filesystem errors, JSON parse warnings on
  degenerate inputs, timing traces during `DEV_TEAM_DEBUG=1`.
- Never write user-actionable messages to stderr alone. Duplicate them to
  stdout with the `ADVISORY:` prefix if the operator needs to see them.
- **Exception — exit-2 (block) messages: mirror to stderr in addition to
  stdout** (`pre_commit_review.py`, #1367). Some Claude Code hook-error
  wrappers surface only stderr on a nonzero hook exit; a stdout-only block
  message can go completely unseen there, leaving only a generic "hook
  error, no stderr output" with no actionable reason. Stdout stays the
  canonical, primary UI channel — stderr is additive duplication for block
  paths specifically, not a general license to move messages to stderr.
  Treat dual-write as the standard for any new exit-2 hook, or any existing
  one you touch. Hooks not yet converged: stderr-only today
  (`contract_version_guard.py`, `context_ceiling_guard.py`,
  `pre_commit_knowledge_index.py`); stdout-only today
  (`destructive_guard.py`, `eval_compliance_check.py`). Converging them is a
  separate cleanup, not implied by this note.
- The parity harness normalizes stderr before comparison. It strips ISO-8601
  timestamps, PIDs, and tmpdir path prefixes. Nothing else. If two
  implementations diverge on anything past those three axes, that is a
  real divergence — fix the hook, don't widen the normalization.

## Python authoring rules

- **Stdlib-only.** Zero third-party imports. Every dependency the hook
  needs is in Python 3.8's stdlib: `argparse`, `dataclasses`, `hashlib`,
  `json`, `os`, `pathlib`, `re`, `shlex`, `shutil`, `signal`, `subprocess`,
  `sys`, `tempfile`. No `requirements.txt` for shipped hooks — the plugin
  ships to users who cannot `pip install` on their machines.
- **Target Python 3.8+.** No `match/case`, no `|`-unions in type hints,
  no `dict | None` — those need 3.10+. `from __future__ import annotations`
  is fine for type-hint delay.
- **CLI with argparse** when a hook takes arguments; otherwise read stdin
  and dispatch on JSON fields.
- **Tests: pytest.** Unit tests live under `plugins/dev-team/tests/hooks/`
  (per-hook file). The `.sh`↔`.py` parity harness that once lived under
  `plugins/dev-team/tests/hooks/parity/` was retired once every hook shipped
  as Python-only ([ADR 0015]) — `test_*.py` is the coverage source of truth.
- **Lint: ruff.** Type-check optional (`mypy` is not on the CI critical
  path).
- **`main() -> int`** returns the exit code. A trailing
  `if __name__ == "__main__": sys.exit(main())` shim runs the hook.
- **Signal handling.** Long-running hooks (like the mutation-testing
  wrapper's status loop) MUST register SIGINT/SIGTERM handlers that flush
  their state before exit. See `plugins/dev-team/skills/mutation-testing/scripts/csharp_stryker_net_wrapper.py`.
- **Cross-platform.** `pathlib.Path`, never string concatenation for paths.
  Never `subprocess.run(..., shell=True)` unless the command is a static
  literal — quote arguments through `shlex.quote` otherwise. `subprocess.run`
  behaves identically on all three platforms; `bash -c` does not.
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
