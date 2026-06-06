#!/usr/bin/env bash
# eval_semver_classify.sh — the eval corpus IS the semver contract (issue #101).
#
# An agent's observable surface is its behavior under inputs, which is exactly
# what evals/expected/*.json pins down. So a change to the corpus classifies
# the behavioral change, and the conventional-commit type must match:
#
#   GREEN-preserving  (no expected/*.json changed)        -> patch  (fix/chore/…)
#   expectation-ADDITIVE (only new expected files added)  -> minor  (feat:)
#   expectation-EDITING  (existing expected file M/D/R)    -> major  (feat! / BREAKING CHANGE)
#
# The script diffs evals/expected/ across a base..head range, classifies the
# change, derives the minimum required commit bump, and asserts the strongest
# commit type in the range meets or exceeds it. A PR that edits an existing
# expected value without a major-bump commit type fails (exit 1).
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
    additive) echo "minor" ;;
    none) echo "patch" ;;
    *) echo "patch" ;;
  esac
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

  local name_status class min_bump commits detected
  name_status=$(git diff --name-status "$base" "$head" -- evals/expected/ 2>/dev/null)
  class=$(printf '%s\n' "$name_status" | classify_change_class)
  min_bump=$(class_to_min_bump "$class")

  commits=$(git log --format='%s%n%b' "$base..$head" 2>/dev/null)
  detected=$(printf '%s\n' "$commits" | detect_commit_bump)

  echo "Eval-semver classifier (issue #101)"
  echo "  base..head:        $base..$head"
  echo "  corpus change:     $class"
  echo "  required min bump: $min_bump"
  echo "  commit type bump:  $detected"

  # Informational: behavior-bearing source changed but the corpus did not.
  local src_changed
  src_changed=$(git diff --name-only "$base" "$head" -- \
    plugins/dev-team/agents/ plugins/dev-team/skills/ \
    plugins/dev-team/knowledge/ 2>/dev/null)
  if [ "$class" = "none" ] && [ -n "$src_changed" ]; then
    echo "  note: agents/skills/knowledge changed but no expected/*.json did —" \
         "consider adding/updating fixtures to pin the new behavior."
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
