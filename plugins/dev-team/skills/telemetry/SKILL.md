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

# Telemetry (#106)

Role: worker. Manages consent for and reports the local, opt-in telemetry
beacon. The beacon (`hooks/telemetry.sh`) records MINIMAL events — a command
NAME, a gate name + outcome, and the plugin version — to
`metrics/telemetry.jsonl`. No prompts, paths, code, or payloads are ever
recorded, and there is **no network egress**: everything stays local.

Telemetry is **OFF by default**. It activates only when
`.claude/telemetry.json` contains `{"enabled": true}` or the env var
`DEV_TEAM_TELEMETRY=on` is set.

## Argument: $ARGUMENTS

- `status` (default): report whether telemetry is enabled and what's collected.
- `on`: enable by writing `.claude/telemetry.json` with `{"enabled": true}`
  (confirm with the user first — this starts local recording).
- `off`: disable by writing `{"enabled": false}` (recording stops; the existing
  log is left in place for the user to inspect or delete).
- `report`: print the usage summary.

## Steps

1. **status** — check `.claude/telemetry.json` and `DEV_TEAM_TELEMETRY`; state
   on/off, and list exactly what is and isn't collected (events: command/skill
   name, gate fired/bypassed, plugin version; never: prompt text, paths, code,
   network).

2. **on / off** — write `.claude/telemetry.json`:
   ```json
   { "enabled": true }
   ```
   For `on`, confirm consent first. Note the file is gitignored-by-convention
   (project-local); recording is local-only.

3. **report** — summarize the event log:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/hooks/lib/telemetry_report.py \
     --log metrics/telemetry.jsonl
   ```
   Shows command/skill usage counts and the pre-commit review gate's bypass
   rate. If the log doesn't exist, the report says telemetry is off and nothing
   has left the machine.

Report exactly what the tool emits; do not invent counts.
