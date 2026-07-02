#!/usr/bin/env bats
# #574 — Python hook contract doc exists with required sections. The
# settings-toggle mechanism was retired in #618 (epic #572 close), so its
# doc + tests are gone; the contract doc itself survives as historical
# reference + the still-authoritative statement of exit codes / stdin /
# stderr / authoring rules for shipped Python hooks.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
CONTRACT="$REPO_ROOT/docs/python-hook-contract.md"

@test "python-hook contract file exists at docs/python-hook-contract.md" {
  [ -f "$CONTRACT" ]
}

@test "contract: names stdin JSON schema" {
  grep -qE "^## stdin" "$CONTRACT"
}

@test "contract: names stdout format" {
  grep -qE "^## stdout" "$CONTRACT"
}

@test "contract: names exit codes 0/1/2/≥3" {
  grep -qE "^## Exit codes" "$CONTRACT"
  grep -qE "\b0\b" "$CONTRACT"
  grep -qE "\b1\b" "$CONTRACT"
  grep -qE "\b2\b" "$CONTRACT"
}

@test "contract: names environment variables" {
  grep -qE "^## Environment variables" "$CONTRACT"
  grep -q "CLAUDE_PROJECT_DIR" "$CONTRACT"
}

@test "contract: names stderr conventions" {
  grep -qE "^## stderr" "$CONTRACT"
}

@test "contract: names Python authoring rules (stdlib-only, 3.8+)" {
  grep -qE "^## Python authoring rules" "$CONTRACT"
  grep -qi "stdlib" "$CONTRACT"
  grep -qE "3\.8" "$CONTRACT"
}
