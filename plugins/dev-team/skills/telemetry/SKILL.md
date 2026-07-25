---
name: telemetry
description: >-
  Manage and report the opt-in, privacy-clean usage telemetry beacon. Use when
  the user asks to "enable/disable telemetry", "show telemetry", "usage stats",
  "which commands do I use", or "how often is the commit gate bypassed".
argument-hint: "[on|off|status|report]"
user-invocable: true
allowed-tools: >-
  Bash(python3 *, jq *, cat *, mkdir *, ls *), Read, Write
---

# Telemetry (#106, #1405)

Role: worker. Manages consent for and reports the local, opt-in telemetry
beacon. The beacon (`hooks/telemetry.py`) records MINIMAL events — a command
NAME, a skill NAME (including agent-/auto-invoked skills), a gate name +
outcome, and the plugin version — to `~/.claude/metrics/telemetry.jsonl`. No
prompts, paths, code, or payloads are ever recorded, and there is **no network
egress**: everything stays local.

Telemetry is **OFF by default**. It activates only when the user-level
`~/.claude/telemetry.json` contains `{"enabled": true}`. This is a
config-file-only, home-scoped switch: it is read and written at this one path
regardless of which project directory the command runs from.

## Scope — keep this small (#106)

This beacon is intentionally a **cheap, always-on local counter**: which
commands/skills run, how often the commit gate is bypassed. It is **not** the
self-improvement loop and must not grow into one. The loop is `/session-review`,
whose digest already extracts a superset of these signals (token, rework,
accuracy, utilization) from transcripts and routes suggestions to governed
machinery. Cross-machine aggregation also belongs to the **session-digest**
(Delta D / #178), not this beacon. If you find yourself adding analysis or
network egress here, that work belongs in `/session-review` instead.

## Argument: $ARGUMENTS

- `status` (default): report whether telemetry is enabled and what's collected.
- `on`: enable by writing `~/.claude/telemetry.json` with `{"enabled": true}`
  (confirm with the user first — this starts local recording).
- `off`: disable by writing `{"enabled": false}` (recording stops; the existing
  log is left in place for the user to inspect or delete).
- `report`: print the usage summary.

## Steps

1. **status** — check `~/.claude/telemetry.json`; state on/off, and list
   exactly what is and isn't collected (events: command/skill name, gate
   fired/bypassed, plugin version; never: prompt text, paths, code, network).

2. **on / off** — write `~/.claude/telemetry.json`:

   ```json
   { "enabled": true }
   ```

   For `on`, confirm consent first. Recording is local-only; the event log
   `~/.claude/metrics/telemetry.jsonl` lives outside any project directory so
   it can never be committed.

3. **report** — summarize the event log:

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/hooks/lib/telemetry_report.py \
     --log "$HOME/.claude/metrics/telemetry.jsonl"
   ```

   Shows command usage, skill usage (including agent-/auto-invoked skills,
   counted distinctly from user-typed commands), and the pre-commit review
   gate's bypass rate. If the log doesn't exist, the report says telemetry is
   off and nothing has left the machine.

Report exactly what the tool emits; do not invent counts.
