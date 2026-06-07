#!/usr/bin/env bash
# eval_semver_classify.sh — the eval corpus IS the semver contract (issue #101).
#
# An agent's observable surface is its behavior under inputs, which is exactly
# what evals/expected/*.json pins down. So a change to the corpus classifies
# the behavioral change, and the conventional-commit type must match:
#
#   GREEN-preserving  (no expected/*.json changed)        -> patch  (fix/chore/…)
#   expectation-ADDITIVE (only new expected files added)  -> minor  (feat:)
#   threshold-ONLY edit  (M, but only tolerances changed) -> minor  (feat:)
#   expectation-EDITING  (M flips a verdict, or D/R)       -> major  (feat! / BREAKING CHANGE)
#
# The script diffs evals/expected/ across a base..head range, classifies the
# change, derives the minimum required commit bump, and asserts the strongest
# commit type in the range meets or exceeds it. A PR that edits an existing
# expected value without a major-bump commit type fails (exit 1).
#
# Threshold-only vs. expectation flip (issue #136): a modified expected file is
# not automatically breaking. We compare each modified file's *expectation
# identity* — its `applicableAgents` set and per-agent `expectedStatus` verdicts
# — across base..head. If that identity is unchanged and only tolerances
# (issueCount/severities ranges) or prose moved, it is a threshold-only edit
# (minor); only a verdict flip, a delete, or a rename is breaking (major).
#
# New-agent policy (issue #136): a newly-added review agent (a `*-review.md`
# file under agents/) that no expected fixture references is flagged as a
# failure — the behavior-defining agent must ship pinned by at least one
# fixture, not land unpinned as a silent patch.
#
# Reconciliation with release-please: release-please reads the same
# conventional-commit types to compute the version bump. This gate ensures the
# committed type is *honest* about the behavioral change the corpus records, so
# the version release-please cuts reflects the real prompt contract change.
#
# Sourceable: when sourced (BASH_SOURCE != $0) only the pure functions are
# defined, for unit testing. When executed, main() runs the git-backed flow.

set -uo pipefail

# --------------------------------------------------------------------------
# Pure functions (unit-testable; no git, no IO beyond stdin/stdout).
# --------------------------------------------------------------------------

# Read `git diff --name-status` lines (already scoped to evals/expected/) on
# stdin; echo the change class: none | additive | editing.
classify_change_class() {
  local saw_add="" saw_edit="" status rest
  while IFS=$'\t' read -r status rest; do
    [ -z "$status" ] && continue
    case "$status" in
      A) saw_add=1 ;;
      M|D) saw_edit=1 ;;
      R*|C*) saw_edit=1 ;;   # rename/copy of an existing expectation == edit
      *) saw_edit=1 ;;       # unknown status: treat conservatively as edit
    esac
  done
  if [ -n "$saw_edit" ]; then
    echo "editing"
  elif [ -n "$saw_add" ]; then
    echo "additive"
  else
    echo "none"
  fi
}

# Map change class -> minimum required commit bump.
class_to_min_bump() {
  case "$1" in
    editing) echo "major" ;;
    additive|threshold) echo "minor" ;;
    none) echo "patch" ;;
    *) echo "patch" ;;
  esac
}

# Expectation identity of an expected/*.json read on stdin: the canonical
# (sorted) applicableAgents set plus each agent's expectedStatus verdict. Two
# files with the same identity assert the same behavioral contract; tolerance
# ranges (issueCount/severities) and prose (description) are deliberately
# excluded. Emits a stable string, or "PARSE_ERROR" if jq can't read it.
expectation_identity() {
  jq -Sc '{
    aa: ((.applicableAgents // []) | sort),
    st: ((.agents // {}) | to_entries
         | map({key: .key, status: (.value.expectedStatus // null)})
         | sort_by(.key))
  }' 2>/dev/null || echo "PARSE_ERROR"
}

# Classify a modification to an expected file given its base and head content
# (passed as the two args). Echoes "flip" when the expectation identity changed
# (a verdict flip or an agent added/removed from the contract) and "threshold"
# when only tolerances/prose changed. A parse error is treated conservatively
# as a flip.
classify_expected_edit() {
  local base_json="$1" head_json="$2" base_id head_id
  base_id=$(printf '%s' "$base_json" | expectation_identity)
  head_id=$(printf '%s' "$head_json" | expectation_identity)
  if [ "$base_id" = "PARSE_ERROR" ] || [ "$head_id" = "PARSE_ERROR" ]; then
    echo "flip"
  elif [ "$base_id" = "$head_id" ]; then
    echo "threshold"
  else
    echo "flip"
  fi
}

# Numeric rank for comparison.
bump_rank() {
  case "$1" in
    major) echo 2 ;;
    minor) echo 1 ;;
    patch) echo 0 ;;
    *) echo 0 ;;
  esac
}

# Read commit text (subjects and bodies) on stdin; echo the strongest bump
# expressed by conventional-commit syntax: major | minor | patch.
detect_commit_bump() {
  local line strongest="patch"
  while IFS= read -r line; do
    # BREAKING CHANGE anywhere, or a `type!:` / `type(scope)!:` subject -> major.
    if [[ "$line" == *"BREAKING CHANGE"* ]] \
       || [[ "$line" =~ ^[a-zA-Z]+(\([^\)]*\))?!: ]]; then
      echo "major"
      return 0
    fi
    # feat: / feat(scope): -> minor (keep scanning for a possible major).
    if [[ "$line" =~ ^feat(\([^\)]*\))?: ]]; then
      strongest="minor"
    fi
  done
  echo "$strongest"
}

# --------------------------------------------------------------------------
# git-backed driver.
# --------------------------------------------------------------------------

main() {
  local base="${1:-origin/main}" head="${2:-HEAD}"

  if ! git rev-parse --verify "$base" >/dev/null 2>&1; then
    echo "error: base ref '$base' not found (fetch it or pass an existing ref)" >&2
    return 2
  fi

  # Content-aware classification: walk each changed expected/*.json and decide
  # whether a modification flips a verdict (breaking) or only moves a tolerance
  # (non-breaking). A→additive, D/R→flip(breaking), M→inspect content (#136).
  local name_status status path saw_add="" saw_threshold="" saw_flip="" class
  name_status=$(git diff --name-status "$base" "$head" -- evals/expected/ 2>/dev/null)
  while IFS=$'\t' read -r status path _rest; do
    [ -z "$status" ] && continue
    case "$status" in
      A) saw_add=1 ;;
      M)
        local base_json head_json edit
        base_json=$(git show "$base:$path" 2>/dev/null)
        head_json=$(git show "$head:$path" 2>/dev/null)
        edit=$(classify_expected_edit "$base_json" "$head_json")
        if [ "$edit" = "threshold" ]; then saw_threshold=1; else saw_flip=1; fi
        ;;
      *) saw_flip=1 ;;   # D, R*, C*, unknown: a removed/renamed expectation is breaking
    esac
  done < <(printf '%s\n' "$name_status")

  if [ -n "$saw_flip" ]; then
    class="editing"
  elif [ -n "$saw_threshold" ]; then
    class="threshold"
  elif [ -n "$saw_add" ]; then
    class="additive"
  else
    class="none"
  fi

  local min_bump commits detected
  min_bump=$(class_to_min_bump "$class")

  commits=$(git log --format='%s%n%b' "$base..$head" 2>/dev/null)
  detected=$(printf '%s\n' "$commits" | detect_commit_bump)

  echo "Eval-semver classifier (issues #101, #136)"
  echo "  base..head:        $base..$head"
  echo "  corpus change:     $class"
  echo "  required min bump: $min_bump"
  echo "  commit type bump:  $detected"
  # Mechanical reconciliation note: release-please cuts the version from the
  # same conventional-commit types this gate reads, so the bump it will cut is
  # exactly the detected bump below — and the gate fails unless that bump
  # honestly covers the corpus change class.
  echo "  release-please will cut: $detected (from the same commit types)"

  # Informational: behavior-bearing source changed but the corpus did not.
  local src_changed
  src_changed=$(git diff --name-only "$base" "$head" -- \
    plugins/dev-team/agents/ plugins/dev-team/skills/ \
    plugins/dev-team/knowledge/ 2>/dev/null)
  if [ "$class" = "none" ] && [ -n "$src_changed" ]; then
    echo "  note: agents/skills/knowledge changed but no expected/*.json did —" \
         "consider adding/updating fixtures to pin the new behavior."
  fi

  # New-agent policy (#136): a newly-added review agent must ship pinned by at
  # least one eval fixture. A `*-review.md` added under agents/ that no
  # expected/*.json references is a contract-defining artifact shipped unpinned
  # — fail rather than let it land as a silent patch.
  local new_agents agent_path agent_name unpinned=""
  new_agents=$(git diff --name-status "$base" "$head" -- \
    'plugins/dev-team/agents/*-review.md' 2>/dev/null \
    | awk -F'\t' '$1=="A"{print $2}')
  if [ -n "$new_agents" ]; then
    while IFS= read -r agent_path; do
      [ -z "$agent_path" ] && continue
      agent_name=$(basename "$agent_path" .md)
      # Covered if its name appears in any expected/*.json at head.
      if ! git grep -q "\"$agent_name\"" "$head" -- 'evals/expected/*.json' 2>/dev/null; then
        unpinned="${unpinned}${unpinned:+, }${agent_name}"
      fi
    done < <(printf '%s\n' "$new_agents")
  fi
  if [ -n "$unpinned" ]; then
    echo
    echo "FAIL: new review agent(s) without any eval fixture: $unpinned" >&2
    echo "  A review agent defines reviewer behavior; ship it pinned by at" >&2
    echo "  least one evals/expected/*.json that lists it in applicableAgents." >&2
    return 1
  fi

  if [ "$(bump_rank "$detected")" -lt "$(bump_rank "$min_bump")" ]; then
    echo
    echo "FAIL: corpus change is '$class' which requires a '$min_bump' bump," \
         "but the commits only express a '$detected' bump." >&2
    case "$min_bump" in
      major) echo "  Use a 'feat!:' commit or a 'BREAKING CHANGE:' footer." >&2 ;;
      minor) echo "  Use a 'feat:' commit." >&2 ;;
    esac
    return 1
  fi

  echo
  echo "OK: commit type matches the corpus change class."
  return 0
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
