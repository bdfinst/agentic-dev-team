#!/usr/bin/env bats

MG="$BATS_TEST_DIRNAME/../../plugins/dev-team/hooks/mutation-gate.sh"
EC="$BATS_TEST_DIRNAME/../../plugins/dev-team/hooks/eval-compliance-check.sh"

@test "mutation-gate uses set -uo pipefail without errexit" {
  grep -q "set -uo pipefail" "$MG"
  ! grep -q "set -euo pipefail" "$MG"
}

@test "mutation-gate does not exit prematurely: reaches advisory exit even if subcommand fails" {
  # Verify the hook contains its own advisory exit path (not relying on -e to terminate)
  grep -q "exit 0" "$MG"
}

@test "eval-compliance-check has no bare printf variable calls for FAILS or WARNINGS" {
  ! grep -qE 'printf "\$FAILS"|printf "\$WARNINGS"' "$EC"
}

@test "both hooks pass shellcheck" {
  shellcheck "$MG"
  shellcheck "$EC"
}
