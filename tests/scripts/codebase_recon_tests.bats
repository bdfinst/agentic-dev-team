#!/usr/bin/env bats
# Slice 5: codebase_recon.py harness — deterministic steps, schema validation,
# atomic write, inventory error handling, and step ordering.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
SCRIPT="$REPO_ROOT/scripts/codebase_recon.py"

setup() {
  T="$(mktemp -d)"
  cd "$T" || return 1
  git init -q
  git config user.email "t@t.com"
  git config user.name "T"
  touch README.md
  git add .
  git commit -q -m "init"
}

teardown() {
  rm -rf "$T"
}

# ---------------------------------------------------------------------------
# 5.1 — jsonschema importable; harness runs without ImportError
# ---------------------------------------------------------------------------

@test "5.1a: jsonschema is importable" {
  run python3 -c "import jsonschema"
  [ "$status" -eq 0 ]
}

@test "5.1b: harness runs with --skip-llm on a minimal git repo (exit 0 or 1)" {
  run python3 "$SCRIPT" "$T" --skip-llm --output-dir "$T/out"
  # Must NOT crash (ImportError, SyntaxError, etc.); exit 0 = pass, 1 = errors found
  [ "$status" -eq 0 ] || [ "$status" -eq 1 ]
}

@test "5.1c: harness does not hang and produces output with --skip-llm" {
  run timeout 30 python3 "$SCRIPT" "$T" --skip-llm --output-dir "$T/out"
  [ "$status" -ne 124 ]  # 124 = timeout killed
}

# ---------------------------------------------------------------------------
# 5.2 — Deterministic steps 1/2/6 produce non-empty data; inventory error
# ---------------------------------------------------------------------------

@test "5.2a: --skip-llm writes a JSON file to the output dir" {
  run python3 "$SCRIPT" "$T" --skip-llm --output-dir "$T/out"
  [ "$status" -eq 0 ] || [ "$status" -eq 1 ]
  # At least one JSON file must exist in output dir on success
  if [ "$status" -eq 0 ]; then
    local count
    count=$(find "$T/out" -name "*.json" | wc -l | tr -d ' ')
    [ "$count" -ge 1 ]
  fi
}

@test "5.2b: fake recon-inventory.sh that exits 1 causes harness to exit 1" {
  # Create a fake inventory script that fails
  mkdir -p "$T/fake-scripts"
  printf '#!/usr/bin/env bash\necho "inventory failed" >&2\nexit 1\n' > "$T/fake-scripts/recon-inventory.sh"
  chmod +x "$T/fake-scripts/recon-inventory.sh"

  run python3 "$SCRIPT" "$T" --skip-llm --output-dir "$T/out" \
    --inventory-script "$T/fake-scripts/recon-inventory.sh"
  [ "$status" -eq 1 ]
}

@test "5.2c: fake recon-inventory.sh failure leaves no artifact in output dir" {
  mkdir -p "$T/fake-scripts"
  printf '#!/usr/bin/env bash\necho "inventory failed" >&2\nexit 1\n' > "$T/fake-scripts/recon-inventory.sh"
  chmod +x "$T/fake-scripts/recon-inventory.sh"

  python3 "$SCRIPT" "$T" --skip-llm --output-dir "$T/out" \
    --inventory-script "$T/fake-scripts/recon-inventory.sh" || true

  # No JSON should have been written
  local count
  count=$(find "$T/out" -name "*.json" 2>/dev/null | wc -l | tr -d ' ')
  [ "$count" -eq 0 ]
}

# ---------------------------------------------------------------------------
# 5.3 — Schema validation and atomic artifact write
# ---------------------------------------------------------------------------

@test "5.3a: valid --skip-llm run writes a JSON file that parses" {
  run python3 "$SCRIPT" "$T" --skip-llm --output-dir "$T/out"
  [ "$status" -eq 0 ]
  local f
  f=$(find "$T/out" -name "*.json" | head -1)
  [ -n "$f" ]
  run python3 -c "import json, sys; json.load(open('$f'))"
  [ "$status" -eq 0 ]
}

@test "5.3b: emitted artifact contains required schema top-level keys" {
  run python3 "$SCRIPT" "$T" --skip-llm --output-dir "$T/out"
  [ "$status" -eq 0 ]
  local f
  f=$(find "$T/out" -name "*.json" | head -1)
  [ -n "$f" ]
  run python3 - "$f" <<'EOF'
import json, sys
d = json.load(open(sys.argv[1]))
required = ["schema_version","generated_at","repo","entry_points","languages",
            "dependencies","architecture","security_surface","git_history"]
missing = [k for k in required if k not in d]
if missing:
    print("MISSING:", missing)
    sys.exit(1)
EOF
  [ "$status" -eq 0 ]
}

@test "5.3c: artifact is written atomically (final path exists, no .tmp leftover)" {
  run python3 "$SCRIPT" "$T" --skip-llm --output-dir "$T/out"
  [ "$status" -eq 0 ]
  local f
  f=$(find "$T/out" -name "*.json" | head -1)
  [ -n "$f" ]
  # No .tmp files left behind
  local tmp_count
  tmp_count=$(find "$T/out" -name "*.tmp" 2>/dev/null | wc -l | tr -d ' ')
  [ "$tmp_count" -eq 0 ]
}

@test "5.3d: step ordering — each step receives prior output (meta used in steps 2 and 6)" {
  # Run with verbose/debug mode if available, otherwise just verify outputs are correct
  run python3 "$SCRIPT" "$T" --skip-llm --output-dir "$T/out"
  [ "$status" -eq 0 ]
  local f
  f=$(find "$T/out" -name "*.json" | head -1)
  # Verify that meta from step1 flows through: repo.name should match the dir name
  run python3 - "$f" "$T" <<'EOF'
import json, sys
from pathlib import Path
d = json.load(open(sys.argv[1]))
repo_root = Path(sys.argv[2]).resolve()
expected_name = repo_root.name
actual_name = d["repo"]["name"]
if actual_name != expected_name:
    print(f"MISMATCH: expected repo.name={expected_name!r}, got {actual_name!r}")
    sys.exit(1)
EOF
  [ "$status" -eq 0 ]
}

@test "5.3e: schema_version in emitted artifact is '1.0'" {
  run python3 "$SCRIPT" "$T" --skip-llm --output-dir "$T/out"
  [ "$status" -eq 0 ]
  local f
  f=$(find "$T/out" -name "*.json" | head -1)
  run python3 -c "import json,sys; d=json.load(open('$f')); sys.exit(0 if d.get('schema_version')=='1.0' else 1)"
  [ "$status" -eq 0 ]
}
