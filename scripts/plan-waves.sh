#!/usr/bin/env bash
# plan-waves.sh — compute parallel build waves from a plan's slice dependency graph.
#
# Parses each slice's `Depends-on`, topologically layers the DAG into waves (wave 1
# = slices with no prerequisites, etc.), detects same-wave file collisions, and
# emits a stable JSON contract (schema "plan-waves/v1") on stdout:
#
#   { "schema", "waves": [[id,...],...], "slices": {id:{depends_on,files,wave}},
#     "collisions": [{wave, slices:[a,b], file}] }
#
# Rejects (exit 2, message on stderr) a dependency cycle, a slice missing its
# Depends-on declaration (with the `Depends-on: none` remedy), and an unknown
# dependency reference — naming the offender in each case.
#
# Usage: plan-waves.sh <plan.md>

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/plan-parse.sh
. "$HERE/lib/plan-parse.sh"

FILE="${1:-}"
{ [ -n "$FILE" ] && [ -f "$FILE" ]; } || { echo "usage: plan-waves.sh <plan.md>" >&2; exit 2; }

# Python core reads the parser's TSV from stdin (script via -c, data via the pipe).
read -r -d '' PYSRC <<'PY'
import sys, json, re

slices, order = {}, []
for line in sys.stdin:
    if not line.strip():
        continue
    parts = line.rstrip("\n").split("\t")
    sid = parts[0]
    deps_raw = parts[1] if len(parts) > 1 else "__MISSING__"
    files_raw = parts[2] if len(parts) > 2 else ""
    files = [f for f in re.split(r"[,\s]+", files_raw) if f]
    slices[sid] = {"deps_raw": deps_raw, "files": files}
    order.append(sid)

def die(msg):
    sys.stderr.write("plan-waves: " + msg + "\n")
    sys.exit(2)

if not slices:
    die("no slices found (expected '### Slice <id>: ...' headings)")

for sid in order:
    if slices[sid]["deps_raw"] == "__MISSING__":
        die("slice %r is missing its Depends-on declaration — "
            "add 'Depends-on: none' if it has no prerequisites." % sid)
    raw = slices[sid]["deps_raw"].strip()
    slices[sid]["deps"] = [] if raw.lower() == "none" or raw == "" \
        else [d for d in re.split(r"[,\s]+", raw) if d]

for sid in order:
    for d in slices[sid]["deps"]:
        if d not in slices:
            die("slice %r depends on unknown slice %r." % (sid, d))

# Kahn layering: each pass takes all slices whose deps are already placed.
remaining = {s: set(slices[s]["deps"]) for s in order}
waves, placed = [], set()
while remaining:
    ready = sorted(s for s, d in remaining.items() if d <= placed)
    if not ready:
        die("dependency cycle among slices: " + ", ".join(sorted(remaining)) + ".")
    waves.append(ready)
    for s in ready:
        placed.add(s)
        del remaining[s]

wave_of = {s: i for i, w in enumerate(waves, 1) for s in w}

collisions = []
for i, w in enumerate(waves, 1):
    for a in range(len(w)):
        for b in range(a + 1, len(w)):
            for f in sorted(set(slices[w[a]]["files"]) & set(slices[w[b]]["files"])):
                collisions.append({"wave": i, "slices": [w[a], w[b]], "file": f})

print(json.dumps({
    "schema": "plan-waves/v1",
    "waves": waves,
    "slices": {s: {"depends_on": slices[s]["deps"], "files": slices[s]["files"],
                   "wave": wave_of[s]} for s in order},
    "collisions": collisions,
}, indent=2, sort_keys=True))
PY

plan_parse "$FILE" | python3 -c "$PYSRC"
