#!/usr/bin/env bats
# #226 — git-origin-host.sh classifies the origin remote: github | other | none.
# github.com + enterprise GHE => github; lookalikes => other; no remote => none.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
HOSTC="$REPO_ROOT/plugins/dev-team/scripts/git-origin-host.sh"

@test "github.com over https is github" {
  [ "$("$HOSTC" 'https://github.com/o/r')" = "github" ]
}

@test "github.com over scp-style ssh is github" {
  [ "$("$HOSTC" 'git@github.com:o/r.git')" = "github" ]
}

@test "github.com over ssh:// is github" {
  [ "$("$HOSTC" 'ssh://git@github.com/o/r')" = "github" ]
}

@test "enterprise GHE host (github.<corp>) is github" {
  [ "$("$HOSTC" 'https://github.example.com/o/r')" = "github" ]
  [ "$("$HOSTC" 'git@github.mycorp.com:o/r.git')" = "github" ]
}

@test "lookalike notgithub.example.com is other" {
  [ "$("$HOSTC" 'https://notgithub.example.com/o/r')" = "other" ]
}

@test "lookalike mygithub.com is other" {
  [ "$("$HOSTC" 'git@mygithub.com:o/r.git')" = "other" ]
}

@test "a non-github host is other" {
  [ "$("$HOSTC" 'https://gitlab.com/o/r')" = "other" ]
}

@test "a repo with no origin remote is none (fail-open)" {
  TMP="$(mktemp -d)"
  git -C "$TMP" init -q
  run bash -c "cd '$TMP' && '$HOSTC'"
  rm -rf "$TMP"
  [ "$status" -eq 0 ]
  [ "$output" = "none" ]
}
