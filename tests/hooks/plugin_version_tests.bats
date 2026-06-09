#!/usr/bin/env bats
# Tests for hooks/lib/plugin-version.sh — the mechanical plugin version resolver.

RESOLVER="$BATS_TEST_DIRNAME/../../plugins/dev-team/hooks/lib/plugin-version.sh"

setup() {
  TMP="$(mktemp -d)"
  JSON="$TMP/installed_plugins.json"
}

teardown() {
  rm -rf "$TMP"
}

@test "reports user-scoped install when no project install matches cwd" {
  cat > "$JSON" <<EOF
{"version":2,"plugins":{"dev-team@bfinster":[
  {"scope":"user","installPath":"/nonexistent","version":"6.7.0"}
]}}
EOF
  run env UPGRADE_INSTALLED_JSON="$JSON" bash "$RESOLVER"
  [ "$status" -eq 0 ]
  [[ "$output" == "dev-team@bfinster v6.7.0 (scope: user)" ]]
}

@test "project-scoped install for the current directory wins over user scope" {
  cat > "$JSON" <<EOF
{"version":2,"plugins":{"dev-team@bfinster":[
  {"scope":"user","installPath":"/nonexistent","version":"6.7.0"},
  {"scope":"project","projectPath":"$PWD","installPath":"/nonexistent","version":"9.9.9"}
]}}
EOF
  run env UPGRADE_INSTALLED_JSON="$JSON" bash "$RESOLVER"
  [ "$status" -eq 0 ]
  [[ "$output" == "dev-team@bfinster v9.9.9 (scope: project, this project)" ]]
}

@test "project-scoped install matches when run from a SUBDIRECTORY of the project root" {
  proj="$TMP/proj"
  mkdir -p "$proj/sub/dir"
  cat > "$JSON" <<EOF
{"version":2,"plugins":{"dev-team@bfinster":[
  {"scope":"user","installPath":"/nonexistent","version":"6.7.0"},
  {"scope":"project","projectPath":"$proj","installPath":"/nonexistent","version":"9.9.9"}
]}}
EOF
  run env UPGRADE_INSTALLED_JSON="$JSON" bash -c "cd '$proj/sub/dir' && bash '$RESOLVER'"
  [ "$status" -eq 0 ]
  [[ "$output" == "dev-team@bfinster v9.9.9 (scope: project, this project)" ]]
}

@test "project install for a DIFFERENT path does not match; falls back to user" {
  cat > "$JSON" <<EOF
{"version":2,"plugins":{"dev-team@bfinster":[
  {"scope":"user","installPath":"/nonexistent","version":"6.7.0"},
  {"scope":"project","projectPath":"/some/other/project","installPath":"/nonexistent","version":"9.9.9"}
]}}
EOF
  run env UPGRADE_INSTALLED_JSON="$JSON" bash "$RESOLVER"
  [ "$status" -eq 0 ]
  [[ "$output" == "dev-team@bfinster v6.7.0 (scope: user)" ]]
}

@test "prefers the on-disk plugin.json version at installPath over the record" {
  install_dir="$TMP/install/.claude-plugin"
  mkdir -p "$install_dir"
  echo '{"name":"dev-team","version":"7.0.0"}' > "$install_dir/plugin.json"
  cat > "$JSON" <<EOF
{"version":2,"plugins":{"dev-team@bfinster":[
  {"scope":"user","installPath":"$TMP/install","version":"6.7.0"}
]}}
EOF
  run env UPGRADE_INSTALLED_JSON="$JSON" bash "$RESOLVER"
  [ "$status" -eq 0 ]
  [[ "$output" == "dev-team@bfinster v7.0.0 (scope: user)" ]]
}

@test "exits 1 when the plugin is not recorded as installed" {
  echo '{"version":2,"plugins":{}}' > "$JSON"
  run env UPGRADE_INSTALLED_JSON="$JSON" bash "$RESOLVER"
  [ "$status" -eq 1 ]
}

@test "exits 2 when the install record file is missing" {
  run env UPGRADE_INSTALLED_JSON="$TMP/does-not-exist.json" bash "$RESOLVER"
  [ "$status" -eq 2 ]
  [[ "$output" == *"not found"* ]]
}

@test "resolves an alternate plugin name passed as an argument" {
  cat > "$JSON" <<EOF
{"version":2,"plugins":{"security-assessment@bfinster":[
  {"scope":"user","installPath":"/nonexistent","version":"2.1.0"}
]}}
EOF
  run env UPGRADE_INSTALLED_JSON="$JSON" bash "$RESOLVER" security-assessment
  [ "$status" -eq 0 ]
  [[ "$output" == "security-assessment@bfinster v2.1.0 (scope: user)" ]]
}
