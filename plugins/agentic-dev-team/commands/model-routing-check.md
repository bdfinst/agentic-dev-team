---
name: model-routing-check
description: >-
  Read-only diagnostic for environment-aware model routing. Prints the
  effective tier → snapshot map (defaults plus any overrides), the
  contents of any override file, the most recent tier-bump events from
  the resolver log, and whether the probe endpoint applies. Touches no
  files; no side effects.
user-invocable: true
allowed-tools: Read, Bash
---

# Model Routing Check

Role: worker. This command is **read-only** and produces **no side
effects** — it never writes, creates, or modifies files. Safe to run
during triage at any time.

You have been invoked with the `/model-routing-check` command.

## What it shows

Four sections, in order:

1. **Effective tier → snapshot map** — the result of merging
   `knowledge/model-routing.json` (plugin defaults) with any
   `tier_aliases` in `.claude/model-overrides.json` (per-user).
2. **Overrides** — whether `.claude/model-overrides.json` exists and, if
   so, its raw contents. `Overrides: none` when the file is absent.
3. **Recent tier bumps** — the last `N` (default 10) JSONL events from
   `.claude/metrics/model-routing.log`, formatted as
   `<ts>  <requested> → <served>  [<reason>]  caller=<caller>`. Raise
   `MODEL_BUMP_TAIL` to see more.
4. **Probe applicability** — whether the `/init-dev-team` probe shape
   applies to the current `ANTHROPIC_BASE_URL`. `*.anthropic.com` is
   probe-supported; Bedrock, Vertex, and any other host is
   probe-skipped (manual override file recommended).

## How to fix common findings

- **Bumps appearing in the log** — the resolver is silently rerouting a
  tier. Inspect `.claude/model-overrides.json` (or remove it to restore
  defaults).
- **`All model tiers exhausted`** — your override file marks the top
  tier as `unavailable`. Edit it to point at a working tier.
- **`Probe skipped` on Bedrock/Vertex** — write `.claude/model-overrides.json`
  by hand. See `docs/model-routing.md`.

## Execution

The exec block below is the literal script the command runs.

<!-- BEGIN EXEC -->
```bash
#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="${MODEL_ROUTING_PLUGIN_DIR:-$SCRIPT_DIR/..}"
RESOLVER="${MODEL_ROUTING_RESOLVER:-$PLUGIN_DIR/hooks/lib/model-resolve.sh}"
OVERRIDES_PATH="${MODEL_OVERRIDES_JSON:-.claude/model-overrides.json}"
BUMP_LOG_PATH="${MODEL_BUMP_LOG:-.claude/metrics/model-routing.log}"
TAIL_N="${MODEL_BUMP_TAIL:-10}"

echo "Model Routing Check"
echo "==================="
echo
echo "Effective tier → snapshot map:"
bash "$RESOLVER" --dump-map
echo

# Overrides section
if [[ -f "$OVERRIDES_PATH" ]]; then
  echo "Overrides: from $OVERRIDES_PATH"
  if jq -e . "$OVERRIDES_PATH" >/dev/null 2>&1; then
    jq . "$OVERRIDES_PATH" | sed 's/^/  /'
  else
    echo "  (file is not valid JSON — run /model-routing-check fails fast on dispatch)"
  fi
else
  echo "Overrides: none"
fi
echo

# Recent bumps
if [[ -f "$BUMP_LOG_PATH" ]]; then
  total=$(wc -l < "$BUMP_LOG_PATH" | tr -d ' ')
  echo "Recent tier bumps: $total events"
  tail -n "$TAIL_N" "$BUMP_LOG_PATH" | jq -r '"  \(.ts)  \(.requested) → \(.served)  [\(.reason)]  caller=\(.caller // "")"' 2>/dev/null || true
  if (( total > TAIL_N )); then
    echo "  Showing last $TAIL_N of $total bump events; raise MODEL_BUMP_TAIL to see more."
  fi
else
  echo "Recent tier bumps: none recorded"
fi
echo

# Probe applicability
base_url="${ANTHROPIC_BASE_URL:-}"
if [[ -z "$base_url" ]]; then
  host=""
else
  host=$(echo "$base_url" | sed -E 's|^https?://||; s|/.*$||')
fi
case "$host" in
  ""|api.anthropic.com|*.anthropic.com)
    echo "Probe applicability: standard Anthropic endpoint (probe supported)"
    ;;
  *)
    echo "Probe applicability: non-Anthropic endpoint (probe skipped)"
    ;;
esac
echo "  ANTHROPIC_BASE_URL=${base_url:-unset}"
```
<!-- END EXEC -->

## Notes

- Defaults to `N=10` bump events in the tail. Override with
  `MODEL_BUMP_TAIL=<n>`.
- `MODEL_ROUTING_PLUGIN_DIR`, `MODEL_ROUTING_RESOLVER`,
  `MODEL_OVERRIDES_JSON`, and `MODEL_BUMP_LOG` are **test-only**
  injection seams. Do not set them by hand in normal use.
- For tier-bump explanations and Bedrock/Vertex setup, see
  `docs/model-routing.md`.
