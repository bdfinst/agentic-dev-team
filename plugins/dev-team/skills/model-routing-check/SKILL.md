---
name: model-routing-check
description: >-
  Read-only diagnostic for effort-band model routing. Prints the effective
  band → model map (shipped defaults or the per-environment ladder), the
  ladder file (or a ready-to-edit starter when none exists), the captured
  session model, and the most recent routing-bump events from the resolver
  log. Touches no files; no side effects.
user-invocable: true
allowed-tools: Read, Bash
---

# Model Routing Check

Role: worker. This command is **read-only** and produces **no side
effects** — it never writes, creates, or modifies files. Safe to run
during triage at any time.

You have been invoked with the `/model-routing-check` command.

Arguments: none.

## Worker constraints

1. Read-only diagnostic; touch no files, no side effects.
2. Report resolved state only; do not change routing.
3. **Be concise.** Tables only, no narration.

## What it shows

Five sections, in order:

1. **Effective band → model map** — the result of resolving each effort
   band (`low`, `medium`, `high`) through the shipped default map in
   `knowledge/model-routing.json` or, when present and valid, the
   per-environment ladder `.claude/model-ladder.json`.
2. **Ladder** — whether `.claude/model-ladder.json` exists and, if so, its
   raw contents. When absent, a **ready-to-edit starter ladder** seeded from
   the shipped defaults is printed, along with the path to create it at.
3. **Session model** — the model captured at session start
   (`.claude/session-model`), used as the fallback for an unmappable model
   and the reference for upgrade flags. `unknown` when not captured.
4. **Recent routing bumps** — the last `N` (default 10) JSONL events from
   `.claude/metrics/model-routing.log`, formatted as
   `<ts>  <band> → <served>  [<reason>]  session=<session>  caller=<caller>`.
   Raise `MODEL_BUMP_TAIL` to see more.
5. **Recalibration staleness advisory** — **advisory only, never blocks
   dispatch** (fail-open, matching the model-resolution hook's contract).
   For every target with an entry in `knowledge/calibration-floors.json`
   (#880), compares its last calibration record's routing/ladder content
   hash (written by `/agent-eval --calibrate`, #882) against the current
   hash of `knowledge/model-routing.json` + `.claude/model-ladder.json`.
   Three states per target: `calibration-current` (hash matches),
   `calibration-stale` (hash drift since the last calibration — routing map
   or ladder changed), and `never-calibrated` (no record exists yet). Stale
   and never-calibrated rows point at `/agent-eval --calibrate --agent
   <target>`.

## How to fix common findings

- **Bumps appearing in the log** — the ladder or a session fallback is
  rerouting a band. Inspect `.claude/model-ladder.json` (or remove it to
  restore the shipped default map).
- **A band resolving to an unexpected model** — check the ladder ordering;
  `low` maps to the bottom, `high` to the top, `medium` to the rounded
  middle (`round_half_up`).
- **Restricted endpoint (Bedrock/Vertex/proxy)** — hand-write
  `.claude/model-ladder.json` listing only the models that endpoint has.
  See `docs/model-routing.md` and `docs/model-routing-overrides.md`.

## Execution

The exec block below is the literal script the command runs.

<!-- BEGIN EXEC -->
```bash
#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="${MODEL_ROUTING_PLUGIN_DIR:-$SCRIPT_DIR/..}"
RESOLVER="${MODEL_ROUTING_RESOLVER:-$PLUGIN_DIR/hooks/lib/model_resolve.py}"
ROUTING_PATH="${MODEL_ROUTING_JSON:-$PLUGIN_DIR/knowledge/model-routing.json}"
LADDER_PATH="${MODEL_LADDER_JSON:-.claude/model-ladder.json}"
SESSION_PATH="${SESSION_MODEL_FILE:-.claude/session-model}"
BUMP_LOG_PATH="${MODEL_BUMP_LOG:-.claude/metrics/model-routing.log}"
TAIL_N="${MODEL_BUMP_TAIL:-10}"
FLOORS_PATH="${CALIBRATION_FLOORS_JSON:-$PLUGIN_DIR/knowledge/calibration-floors.json}"
RECORDS_PATH="${CALIBRATION_RECORDS_JSON:-.claude/evals/calibration-records.json}"

echo "Model Routing Check"
echo "==================="
echo
echo "Effective band → model map:"
python3 "$RESOLVER" --dump-map
echo

# Ladder section
if [[ -f "$LADDER_PATH" ]] && jq -e 'type == "array" and length > 0 and all(.[]; type == "string")' "$LADDER_PATH" >/dev/null 2>&1; then
  echo "Ladder: from $LADDER_PATH"
  jq . "$LADDER_PATH" | sed 's/^/  /'
else
  if [[ -f "$LADDER_PATH" ]]; then
    echo "Ladder: present but invalid at $LADDER_PATH — using shipped defaults"
  else
    echo "Ladder: none — using shipped default map"
  fi
  if [[ -f "$ROUTING_PATH" ]]; then
    echo "  Starter ladder (copy to $LADDER_PATH and edit, capability-ascending):"
    jq -c '[.low, .medium, .high]' "$ROUTING_PATH" | sed 's/^/    /'
  fi
fi
echo

# Session model
if [[ -f "$SESSION_PATH" ]] && [[ -s "$SESSION_PATH" ]]; then
  echo "Session model: $(head -n 1 "$SESSION_PATH")"
else
  echo "Session model: unknown (not captured this session)"
fi
echo

# Recent routing bumps
if [[ -f "$BUMP_LOG_PATH" ]]; then
  total=$(wc -l < "$BUMP_LOG_PATH" | tr -d ' ')
  echo "Recent routing bumps: $total events"
  tail -n "$TAIL_N" "$BUMP_LOG_PATH" | jq -r '"  \(.ts)  \(.band) → \(.served)  [\(.reason)]  session=\(.session // "")  caller=\(.caller // "")"' 2>/dev/null || true
  if (( total > TAIL_N )); then
    echo "  Showing last $TAIL_N of $total bump events; raise MODEL_BUMP_TAIL to see more."
  fi
else
  echo "Recent routing bumps: none recorded"
fi
echo

# Recalibration staleness advisory (advisory only — never blocks dispatch;
# fail-open, matching the model-resolution hook's contract).
echo "Recalibration staleness advisory (advisory only — never blocks dispatch):"
python3 - "$ROUTING_PATH" "$LADDER_PATH" "$FLOORS_PATH" "$RECORDS_PATH" <<'PYEOF'
import hashlib
import json
import sys
from pathlib import Path

routing_path = Path(sys.argv[1])
ladder_path = Path(sys.argv[2])
floors_path = Path(sys.argv[3])
records_path = Path(sys.argv[4])


def routing_hash(routing_path, ladder_path):
    # Mirrors scripts/agent_calibrate.py's routing_hash() exactly: a
    # sha256 over routing bytes, a null separator, ladder bytes when the
    # ladder exists, and a trailing null separator.
    h = hashlib.sha256()
    for p in (routing_path, ladder_path):
        if p is not None and p.exists():
            try:
                h.update(p.read_bytes())
            except OSError:
                pass
        h.update(b"\0")
    return h.hexdigest()


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


floors = load_json(floors_path)
if not isinstance(floors, dict):
    floors = {}
targets = sorted(k for k in floors if not k.startswith("_"))

records = load_json(records_path)
if not isinstance(records, dict):
    records = {}

current_hash = routing_hash(routing_path, ladder_path if ladder_path.exists() else None)

if not targets:
    print("  no calibration-floors.json entries found")
else:
    for target in targets:
        record = records.get(target)
        if not isinstance(record, dict) or "routing_hash" not in record:
            print(f"  {target:<32} never-calibrated   -> run /agent-eval --calibrate --agent {target}")
        elif record["routing_hash"] != current_hash:
            print(f"  {target:<32} calibration-stale  -> run /agent-eval --calibrate --agent {target}")
        else:
            print(f"  {target:<32} calibration-current")
PYEOF
```
<!-- END EXEC -->

## Notes

- Defaults to `N=10` bump events in the tail. Override with
  `MODEL_BUMP_TAIL=<n>`.
- `MODEL_ROUTING_PLUGIN_DIR`, `MODEL_ROUTING_RESOLVER`, `MODEL_ROUTING_JSON`,
  `MODEL_LADDER_JSON`, `SESSION_MODEL_FILE`, `MODEL_BUMP_LOG`,
  `CALIBRATION_FLOORS_JSON`, and `CALIBRATION_RECORDS_JSON` are **test-only**
  injection seams. Do not set them by hand in normal use.
- For the ladder schema, resolution precedence, and restricted-endpoint
  setup, see `docs/model-routing.md` and `docs/model-routing-overrides.md`.
- The recalibration staleness advisory is read-only and fail-open: a missing
  `calibration-floors.json` or `calibration-records.json` is reported (empty
  or all-`never-calibrated`) rather than erroring, and it never affects
  `hooks/agent_model_resolve.py`'s dispatch behavior. See `docs/model-
  routing.md`'s "Recalibration staleness advisory" section and
  `skills/agent-eval/SKILL.md#calibration-mode` for `/agent-eval --calibrate`.
