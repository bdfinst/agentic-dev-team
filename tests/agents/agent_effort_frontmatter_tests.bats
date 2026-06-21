#!/usr/bin/env bats
# ADR 0008: every agent — current and future — must declare a valid `effort:`
# band in its YAML frontmatter. This gate fails CI if any agent file is missing
# the field or carries a value outside the allowed set, so the contract cannot
# silently rot the way `model: mid` did under the old vendor-named scheme.
#
# Allowed bands are the single source of truth below; extend here (and in the
# resolver) if a new band is added.
#
# Optional AGENT_FILES env var scopes the sweep to a subset of agent basenames
# (comma- or whitespace-separated); unknown filenames fail loudly so typos do
# not silently pass.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
AGENTS_DIR="$REPO_ROOT/plugins/dev-team/agents"
ALLOWED_BANDS="low medium high"

# Resolve which agent files to check.
# - Default: every *.md directly under agents/.
# - With AGENT_FILES: only the named basenames (each must exist).
_agent_files_to_check() {
  if [[ -n "${AGENT_FILES:-}" ]]; then
    local raw="${AGENT_FILES//,/ }"
    local f
    for f in $raw; do
      if [[ ! -f "$AGENTS_DIR/$f" ]]; then
        echo "AGENT_FILES contains an unknown agent: $f" >&2
        return 1
      fi
      echo "$AGENTS_DIR/$f"
    done
  else
    find "$AGENTS_DIR" -maxdepth 1 -name '*.md' -type f
  fi
}

# Extract the value of `effort:` from the leading YAML frontmatter block only
# (between the first two `---` fences). Prints the bare value, or nothing if the
# key is absent. Trailing inline comments and surrounding whitespace are
# stripped; quotes are removed.
_effort_value() {
  awk '
    NR == 1 && $0 != "---" { exit }       # no frontmatter at all
    NR == 1 { infm = 1; next }
    infm && $0 == "---" { exit }          # end of frontmatter
    infm && /^[[:space:]]*effort[[:space:]]*:/ {
      sub(/^[[:space:]]*effort[[:space:]]*:[[:space:]]*/, "")
      sub(/[[:space:]]*#.*$/, "")         # strip inline comment
      gsub(/^[\"'\''[:space:]]+|[\"'\''[:space:]]+$/, "")
      print
      exit
    }
  ' "$1"
}

@test "AGENT_FILES typo guard: unknown filename fails loudly" {
  run _agent_files_to_check
  AGENT_FILES="does-not-exist.md" run _agent_files_to_check
  [ "$status" -eq 1 ]
  [[ "$output" == *"unknown agent: does-not-exist.md"* ]]
}

@test "ADR 0008: every agent declares a valid effort: band" {
  local files
  files=$(_agent_files_to_check) || {
    echo "$files" >&2
    return 1
  }

  local missing="" invalid=""
  local agent_file value found
  while IFS= read -r agent_file; do
    [[ -z "$agent_file" ]] && continue
    value="$(_effort_value "$agent_file")"

    if [[ -z "$value" ]]; then
      missing="${missing}  ${agent_file#"$REPO_ROOT/"}"$'\n'
      continue
    fi

    found=0
    local band
    for band in $ALLOWED_BANDS; do
      [[ "$value" == "$band" ]] && { found=1; break; }
    done
    if [[ "$found" -eq 0 ]]; then
      invalid="${invalid}  ${agent_file#"$REPO_ROOT/"}: effort: ${value}"$'\n'
    fi
  done <<<"$files"

  if [[ -n "$missing" || -n "$invalid" ]]; then
    {
      echo "Agent effort-band contract violated (ADR 0008)."
      echo "Every agent must declare 'effort: <band>' where <band> is one of: ${ALLOWED_BANDS}."
      if [[ -n "$missing" ]]; then
        echo ""
        echo "Missing effort: field:"
        printf '%s' "$missing"
      fi
      if [[ -n "$invalid" ]]; then
        echo ""
        echo "Invalid effort: value:"
        printf '%s' "$invalid"
      fi
    } >&2
    return 1
  fi
}
