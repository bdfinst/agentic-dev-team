# Recorded `claude -p` transcripts

Real `claude` 2.1.294 stream-json output, recorded 2026-10-08 with `haiku` at `--effort low`. See [Scrub rules](#scrub-rules) for what is removed. Each run used a fresh temp directory as the cwd, containing `note.txt` (`status: ok`), and stdin from `/dev/null`.

Common argv, called `BASE` below:

```text
claude -p "<prompt>" --model haiku --effort low --output-format stream-json --verbose \
  --no-session-persistence --disable-slash-commands --strict-mcp-config \
  --tools Read,Grep,Glob --system-prompt "You are a terse assistant."
```

`--tools` takes a comma-separated list. `--tools ""` disables all tools.

| File | Extra argv | Demonstrates |
| --- | --- | --- |
| `pass-readonly.jsonl` | `--add-dir <repo>/plugins/dev-team/knowledge --restricted` | Happy path. `Read` works in the cwd and in the `--add-dir` directory. Init lists only builtin plugins, no hooks. |
| `unrestricted-baseline.jsonl` | none | Same task without `--restricted`. Init lists the user's plugins and agents, and six `SessionStart` hooks run. |
| `tool-denied-bash.jsonl` | none | Prompt asks for `Bash echo hi`. Init `tools` is `[Glob, Grep, Read]`. The model emits no `tool_use` and says Bash is unavailable. |
| `read-outside-allowed-default.jsonl` | `--add-dir <repo>/plugins/dev-team/knowledge` | `Read` of `<repo>/evals/expected/a11y-clean-form.json` is not denied. Init `permissionMode` is `auto`, and `permission_denials` is `[]`. |
| `read-outside-denied.jsonl` | `--add-dir <repo>/plugins/dev-team/knowledge --restricted` | The same read is denied. The stream has a `system`/`permission_denied` event and a `tool_result` with `is_error: true`. `result.permission_denials` lists the call. |
| `init-setting-sources-none.jsonl` | `--setting-sources ""` | Prompt `Reply with the single word ok.` Drops user plugins and hooks. Init still reports `memory_paths`. |
| `init-safe-mode.jsonl` | `--safe-mode` | Same prompt. No hooks and no `memory_paths`, but init still lists the user's plugins. |
| `claudemd-control.jsonl` | none | Control for the CLAUDE.md probe. The model quotes the user-scope `~/.claude/CLAUDE.md` rule about `Co-Authored-By` lines. |
| `claudemd-restricted.jsonl` | `--restricted` | Same prompt. The model answers `NO`, so user-scope CLAUDE.md is not loaded. `--safe-mode` and `--setting-sources ""` also answered `NO` (not saved). |
| `no-tools.jsonl` | `--tools "" --restricted` | Init `tools` is `[]`. |
| `bad-model.jsonl`, `bad-model.stderr.txt` | `--model not-a-model --restricted` | Exit code 1. Stdout holds a normal stream whose `result` event has `is_error: true`, `subtype: "success"`, `total_cost_usd: 0`, `modelUsage: {}`, `api_error_status: 404`, `terminal_reason: "api_error"`. Stderr is one line. |
| `grep-glob-outside-denied.jsonl` | `--add-dir <repo>/plugins/dev-team/knowledge --restricted`, system prompt `You are a file inspector.` | Prompt asks for `Grep` of `expectedStatus` and `Glob` of `*.json` in `<repo>/evals/expected`. Both are denied: each call has a `system`/`permission_denied` event (`decision_reason` `--restricted: path outside the working directory`) and a `tool_result` with `is_error: true`. `result.permission_denials` lists both calls. The model reports that neither tool returned content. |

## Notes

- Without `< /dev/null`, `claude -p` waits 3 s for stdin and prints a warning on stderr. `no-stdin.stderr.txt` captures it. It came from `claude -p "Reply with the single word ok." --model haiku --effort low --tools "" --restricted` with stdin held open by `sleep 8 |`. Run trials with stdin set to `DEVNULL`.
- The tool call is `event["message"]["content"][i]` with `type == "tool_use"`, and the tool name is the `name` field. Only `assistant` events carry it.
- The `result` event carries `result`, `is_error`, `subtype`, `total_cost_usd`, `modelUsage` (keyed by full model ID, for example `claude-haiku-5-5`), `permission_denials`, `terminal_reason` and `api_error_status`.
- `rate_limit_event` lines appear mid-stream and must be ignored by the parser.

## Scrub rules

Applied to every file here:

- Home paths: the user's home directory becomes `/Users/USER`.
- Temp dir: the per-run cwd (`/var/folders/.../meab-XXXXXX`, with and without the `/private` prefix) becomes `/private/var/folders/XX/T/meab-XXXXXX`. The recordings used the prefix `meab-`, not the harness's `model-effort-ab-` (`TEMP_DIR_PREFIX` in `scripts/lib/model_effort/runner.py`).
- Session IDs and UUIDs: replaced by `00000000-0000-0000-0000-<n>`, numbered in order of first appearance. Tool-use IDs (`toolu_...`) are kept.
- Thinking signatures: replaced by `SCRUBBED`.
- API IDs: `request_id` and message `id` values (`req_...`, `msg_...`) become `req_<12 digits>` and `msg_<12 digits>`, numbered per file.
- Plugin inventory in `system`/`init`: builtin plugins and `dev-team` keep their entries (the `dev-team` path is under `/Users/USER`). Every other plugin becomes `plugin-<n>` with a placeholder path, source and version (`0.0.0`). Array length is unchanged.
- `agents`, `skills` and `slash_commands` in `system`/`init`: builtin names and `dev-team:*` names are kept. Other names become `agent-<n>`, `skill-<n>` and `command-<n>`.
- Rate-limit info: in `rate_limit_event`, `status`, `rateLimitType` and `isUsingOverage` are kept. Other strings become `placeholder` and numbers become `0`. All keys stay.
