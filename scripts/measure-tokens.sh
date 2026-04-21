#!/usr/bin/env bash
# measure-tokens.sh — count tokens in files referenced by the Baseline Budget
# section of plugins/agentic-dev-team/CLAUDE.md.
#
# Modes:
#   (bare)      Print per-file measurements as table rows
#   --verify    Parse Baseline Budget claims from CLAUDE.md and compare against
#               measurements. Exit non-zero if any file deviates > 10%.
#   --help      Usage
#
# Tokenizer selection (first available wins):
#   1. tiktoken (Python, cl100k_base) — industry-standard approximation of
#      Claude tokenizer behavior
#   2. Character-count heuristic (chars / 4) — coarse fallback; clearly marked
#      as approximate in output
#
# Ownership of exact-tokenizer accuracy: the Claude Code harness's own context
# accounting is authoritative. This script is a development aid for the
# agentic-dev-team plugin's Baseline Budget table. Cross-check one file against
# a live sub-agent dispatch to record any systematic delta in CLAUDE.md's
# tokenizer footnote (see P1 Step 1 REFACTOR).
#
# Part of plans/opus-4-7-alignment.md Stage 1 execution. See also:
# plans/combined-plan-opus-4-7-security-review.md.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLAUDE_MD="${REPO_ROOT}/plugins/agentic-dev-team/CLAUDE.md"
DEVIATION_THRESHOLD_PCT=10

usage() {
  cat <<EOF
usage: measure-tokens.sh [--verify | --help] [PATH ...]

Without args: measures every file referenced in CLAUDE.md's Baseline Budget
              section and prints per-file counts.

With PATH(s): measures those paths instead. (Useful for ad-hoc checks.)

--verify     Compare measurements against the claimed counts in CLAUDE.md's
             Baseline Budget table. Exit non-zero if any file deviates more
             than ${DEVIATION_THRESHOLD_PCT}%.

--help       Show this message.
EOF
}

# ---- tokenizer selection ------------------------------------------------------

TOKENIZER=""
TOKENIZER_NOTE=""

detect_tokenizer() {
  if command -v python3 >/dev/null 2>&1 \
     && python3 -c "import tiktoken" >/dev/null 2>&1; then
    TOKENIZER="tiktoken"
    TOKENIZER_NOTE="tiktoken cl100k_base (approximation of Claude tokenizer)"
    return
  fi
  TOKENIZER="heuristic"
  TOKENIZER_NOTE="character-count heuristic (chars / 4) — APPROXIMATE. Install tiktoken for better accuracy: pip install tiktoken"
}

count_tokens() {
  local file="$1"
  if [[ ! -f "$file" ]]; then
    echo "0"
    return
  fi
  case "$TOKENIZER" in
    tiktoken)
      python3 - "$file" <<'PY'
import sys, tiktoken
enc = tiktoken.get_encoding("cl100k_base")
with open(sys.argv[1], "r", encoding="utf-8", errors="replace") as f:
    print(len(enc.encode(f.read())))
PY
      ;;
    heuristic)
      local chars
      chars=$(wc -c < "$file" | tr -d '[:space:]')
      echo $(( chars / 4 ))
      ;;
  esac
}

# ---- file discovery ----------------------------------------------------------

# When called without PATH args, derive the set of files to measure from the
# Baseline Budget section of CLAUDE.md. We keep this narrow on purpose — the
# budget section is the source of truth for what the plugin claims to load per
# session.

discover_budget_targets() {
  # Return a list of filesystem paths relative to REPO_ROOT. Paths are inferred
  # from the Baseline Budget bullets — not parsed syntactically (the table is
  # prose with inline paths like "knowledge/agent-registry.md").
  local targets=(
    "plugins/agentic-dev-team/CLAUDE.md"
    "plugins/agentic-dev-team/knowledge/agent-registry.md"
  )

  # All team agents
  for f in "${REPO_ROOT}/plugins/agentic-dev-team/agents"/*.md; do
    targets+=("${f#${REPO_ROOT}/}")
  done

  # All skills (count SKILL.md only — the skill frontmatter entry point)
  while IFS= read -r f; do
    targets+=("${f#${REPO_ROOT}/}")
  done < <(find "${REPO_ROOT}/plugins/agentic-dev-team/skills" -name "SKILL.md" 2>/dev/null | sort)

  # Knowledge files
  for f in "${REPO_ROOT}/plugins/agentic-dev-team/knowledge"/*.md; do
    [[ -f "$f" ]] || continue
    targets+=("${f#${REPO_ROOT}/}")
  done

  # Subagent prompt templates
  for f in "${REPO_ROOT}/plugins/agentic-dev-team/prompts"/*.md; do
    [[ -f "$f" ]] || continue
    targets+=("${f#${REPO_ROOT}/}")
  done

  printf '%s\n' "${targets[@]}" | sort -u
}

# ---- measurement output ------------------------------------------------------

print_header() {
  echo "# measure-tokens.sh output"
  echo "# tokenizer: ${TOKENIZER_NOTE}"
  echo "# repo root: ${REPO_ROOT}"
  echo "# date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo
  printf "%-70s %10s\n" "FILE" "TOKENS"
  printf "%-70s %10s\n" "----------------------------------------------------------------------" "----------"
}

measure_paths() {
  local total=0
  for rel in "$@"; do
    local abs="${REPO_ROOT}/${rel}"
    local tokens
    tokens=$(count_tokens "$abs")
    printf "%-70s %10d\n" "$rel" "$tokens"
    total=$(( total + tokens ))
  done
  printf "%-70s %10s\n" "----------------------------------------------------------------------" "----------"
  printf "%-70s %10d\n" "TOTAL" "$total"
}

# ---- --verify ---------------------------------------------------------------

verify_against_claude_md() {
  # NOTE: at Stage 1 this is allowed to exit non-zero — the actual baseline
  # numbers in CLAUDE.md are updated at Stage 7, after plans/security-review-
  # companion-plugin.md lands. The script's job here is to be correct; the
  # budget table is deferred by design.
  if [[ ! -f "$CLAUDE_MD" ]]; then
    echo "ERROR: CLAUDE.md not found at ${CLAUDE_MD}" >&2
    return 2
  fi

  # Extract the Baseline Budget block (lines between "### Baseline Budget" and
  # the next heading).
  local block
  block=$(awk '
    /^### Baseline Budget$/ { capturing=1; next }
    capturing && /^#{1,6} / { capturing=0 }
    capturing { print }
  ' "$CLAUDE_MD")

  if [[ -z "$block" ]]; then
    echo "ERROR: '### Baseline Budget' section not found in CLAUDE.md" >&2
    echo "       --verify requires the section to parse claimed values." >&2
    return 2
  fi

  # Pull out "- ... claim ~N tokens" lines. The current CLAUDE.md uses prose
  # bullets (e.g. "CLAUDE.md (always loaded): ~800 tokens") rather than a
  # structured table, so we regex-match on that shape.
  #
  # At Stage 1 this report is deliberately advisory — divergences are expected.
  local any_fail=0
  echo "# --verify mode"
  echo "# Comparing measurements to claims in '### Baseline Budget' section of CLAUDE.md"
  echo "# Threshold for fail: ±${DEVIATION_THRESHOLD_PCT}%"
  echo

  if ! grep -E '~[0-9,]+\s*(tokens|to[n]?ken)' <<<"$block" >/dev/null; then
    echo "WARN: Baseline Budget block contains no parseable '~N tokens' claims."
    echo "      Stage 1 expectation: this section hasn't been updated yet."
    echo "      Stage 7 will populate it. Exiting advisory non-zero."
    return 1
  fi

  # Crude line-by-line match. We don't try to resolve each claim to a specific
  # file at Stage 1 — the structured --verify comparison lands in Stage 7 when
  # the table moves to an actual file-vs-tokens mapping.
  while IFS= read -r line; do
    [[ "$line" =~ ~([0-9,]+) ]] || continue
    local claimed="${BASH_REMATCH[1]//,/}"
    echo "  claim: ${line}"
    echo "    (Stage 1: claims are not yet mapped to specific files; see Stage 7.)"
  done <<<"$block"

  echo
  echo "Stage 1 note: --verify produces an advisory report only. The structured"
  echo "file-vs-claim comparison is finalized at Stage 7 of"
  echo "plans/combined-plan-opus-4-7-security-review.md."
  return 1  # advisory non-zero per Stage 1 gate
}

# ---- entry point -------------------------------------------------------------

main() {
  detect_tokenizer

  local verify=0
  local -a paths=()

  while (( $# > 0 )); do
    case "$1" in
      --help|-h) usage; return 0 ;;
      --verify)  verify=1; shift ;;
      --)        shift; paths+=("$@"); break ;;
      -*)        echo "unknown flag: $1" >&2; usage; return 2 ;;
      *)         paths+=("$1"); shift ;;
    esac
  done

  if (( verify == 1 )); then
    verify_against_claude_md
    return $?
  fi

  print_header
  if (( ${#paths[@]} > 0 )); then
    measure_paths "${paths[@]}"
  else
    # shellcheck disable=SC2207
    local discovered=( $(discover_budget_targets) )
    measure_paths "${discovered[@]}"
  fi
}

main "$@"
