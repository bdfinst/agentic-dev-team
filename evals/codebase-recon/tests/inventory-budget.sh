#!/usr/bin/env bash
# AC-11: canonical script on the polyglot fixture must complete in <200 ms
# p95 on commodity hardware. Measures 5 runs, asserts the 4th-highest wall
# time (~p95 on n=5) is under the budget.
#
# Budget is overridable via RECON_INVENTORY_BUDGET_MS (CI headroom).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
SCRIPT="$REPO_ROOT/plugins/agentic-dev-team/scripts/recon-inventory.sh"
FIXTURE_SRC="$REPO_ROOT/evals/codebase-recon/fixtures/polyglot"

BUDGET_MS="${RECON_INVENTORY_BUDGET_MS:-200}"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

SCRATCH="$TMP/polyglot"
mkdir -p "$SCRATCH"
(
  cd "$FIXTURE_SRC"
  tar --exclude='expected-inventory.txt' --exclude='expected-file-inventory.json' -cf - . \
    | (cd "$SCRATCH" && tar -xf -)
)
(
  cd "$SCRATCH"
  git init -q
  git -c user.email=t@example.com -c user.name=T add .
  git -c user.email=t@example.com -c user.name=T commit -q -m seed
) >/dev/null

# Run N=5 times and collect wall times in ms.
runs=()
for i in 1 2 3 4 5; do
  MAIN_OUT="$TMP/main-$i.json"
  START_NS=$(python3 -c 'import time; print(time.perf_counter_ns())')
  "$SCRIPT" "$SCRATCH" --slug polyglot --emit-main-inventory-json "$MAIN_OUT" >/dev/null 2>&1
  END_NS=$(python3 -c 'import time; print(time.perf_counter_ns())')
  ELAPSED_MS=$(python3 -c "print(($END_NS - $START_NS)/1e6)")
  runs+=("$ELAPSED_MS")
done

# Compute p95 as the 4th-highest of 5 (index 1 from the top, 0-based index 3
# of the sorted-ascending list).
P95=$(printf '%s\n' "${runs[@]}" | LC_ALL=C sort -n | awk 'NR==4{print; exit}')

printf 'runs (ms): %s\n' "${runs[*]}"
printf 'p95 (4th of 5, ms): %s\n' "$P95"
printf 'budget (ms): %s\n' "$BUDGET_MS"

# Compare as floats.
python3 - "$P95" "$BUDGET_MS" <<'PY'
import sys
p95 = float(sys.argv[1])
budget = float(sys.argv[2])
if p95 > budget:
    print(f"[FAIL] p95={p95:.2f}ms exceeds budget={budget:.2f}ms", file=sys.stderr)
    sys.exit(1)
print(f"[ok]   p95={p95:.2f}ms <= budget={budget:.2f}ms")
PY
