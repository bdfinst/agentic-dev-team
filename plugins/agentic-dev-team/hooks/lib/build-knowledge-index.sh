#!/usr/bin/env bash
# build-knowledge-index.sh — builds plugins/agentic-dev-team/knowledge/index.json
# from knowledge/**.md and skills/**/SKILL.md.
#
# The index maps each corpus file to its H2/H3 sections, each entry holding
# a one-sentence summary and a slugified GitHub-style anchor. Output is
# deterministic, byte-identical across rebuilds with unchanged sources —
# the freshness gate diffs the output and complains on any change.
#
# Modes:
#   (no args)   rebuild knowledge/index.json in place
#   --check     verify the on-disk index matches a fresh build, exit
#               non-zero with a unified diff on stderr if it doesn't.
#               Writes no file.
#
# Env vars (TEST-ONLY injection seams — DO NOT set in production callers,
# DO NOT document as user-facing config):
#   KNOWLEDGE_INDEX_CORPUS_ROOTS  override the corpus root (default: the
#                                 plugin source tree resolved via BASH_SOURCE)
#   KNOWLEDGE_INDEX_OUTPUT        override the output index path
#                                 (default: <plugin>/knowledge/index.json)
#
# Requirements:
#   jq >= 1.6  (Step 9.5 enforces this; without the floor, output
#               formatting can flap the freshness gate)

set -uo pipefail

# -----------------------------------------------------------------------------
# _resolve_paths — populate the corpus root and output path from env vars,
# falling back to plugin defaults via BASH_SOURCE.
# -----------------------------------------------------------------------------
_resolve_paths() {
  local lib_dir plugin_dir
  lib_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  plugin_dir="$(cd "$lib_dir/../.." && pwd)"
  : "${KNOWLEDGE_INDEX_CORPUS_ROOTS:="$plugin_dir"}"
  : "${KNOWLEDGE_INDEX_OUTPUT:="$plugin_dir/knowledge/index.json"}"
}

# -----------------------------------------------------------------------------
# _slugify <text>
# Lowercase, spaces → hyphens, non-alnum stripped. Matches GitHub anchor style.
# -----------------------------------------------------------------------------
_slugify() {
  echo "$1" \
    | tr '[:upper:]' '[:lower:]' \
    | sed -E 's/[^a-z0-9 -]+//g; s/ +/-/g; s/-+/-/g; s/^-+|-+$//g'
}

# -----------------------------------------------------------------------------
# _first_sentence <text>
# Returns the first sentence (extends in Step 4 to the operational
# boundary rule; Step 1 happy path uses a minimal heuristic).
# -----------------------------------------------------------------------------
_first_sentence() {
  # Step 1 minimal: everything up to the first period followed by space or EOL.
  # Step 4 will replace with the full abbreviation-aware rule.
  echo "$1" | sed -E 's/^[[:space:]]+//; s/^([^.!?]+[.!?])[[:space:]].*$/\1/; s/^([^.!?]+[.!?])$/\1/'
}

# -----------------------------------------------------------------------------
# _emit_section <header_text> <summary_text>
# Echoes one JSON object for a section (called per section, joined later).
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# _extract_sections_for_file <abs_path>
# Walks one markdown file and prints "header_text\tsummary\tanchor" lines.
# Step 1 minimal: handles a single H2 followed by a one-line body.
# Step 2 extends to full H2/H3 walk + ordering + slug disambiguation.
# -----------------------------------------------------------------------------
_extract_sections_for_file() {
  local abs="$1"
  # Use awk to find each H2 and its first body line. Minimal Step 1
  # implementation — Step 2 expands to multi-section + H3.
  awk '
    /^## / {
      header = substr($0, 4)
      getline body
      while (body == "" && getline body > 0) {}
      print header "\t" body
      exit
    }
  ' "$abs"
}

# -----------------------------------------------------------------------------
# _build_index — emit the JSON object on stdout.
# -----------------------------------------------------------------------------
_build_index() {
  local roots="$KNOWLEDGE_INDEX_CORPUS_ROOTS"

  # Discover corpus files. Top-level knowledge .md and per-skill SKILL.md.
  local -a files=()
  if [[ -d "$roots/knowledge" ]]; then
    while IFS= read -r -d '' f; do
      files+=("$f")
    done < <(find "$roots/knowledge" -maxdepth 1 -name '*.md' -type f -print0)
  fi
  if [[ -d "$roots/skills" ]]; then
    while IFS= read -r -d '' f; do
      files+=("$f")
    done < <(find "$roots/skills" -mindepth 2 -maxdepth 2 -name 'SKILL.md' -type f -print0)
  fi

  # Build an array of entries, one per file. Each entry is a JSON object
  # mapping section header → {summary, anchor}.
  local entries=()
  local f
  for f in ${files[@]+"${files[@]}"}; do
    local rel
    rel="${f#"$roots/"}"
    # Prefix back the plugin-rooted segment so the key is repo-relative.
    rel="plugins/agentic-dev-team/$rel"

    local section_data
    section_data="$(_extract_sections_for_file "$f")"
    if [[ -z "$section_data" ]]; then
      continue
    fi

    # Build a jq filter that constructs {<header>: {summary, anchor}}.
    local header body summary anchor
    IFS=$'\t' read -r header body <<<"$section_data"
    summary="$(_first_sentence "$body")"
    anchor="$(_slugify "$header")"

    local file_entry
    file_entry=$(jq -n \
      --arg rel "$rel" \
      --arg header "$header" \
      --arg summary "$summary" \
      --arg anchor "$anchor" \
      '{($rel): {($header): {summary: $summary, anchor: $anchor}}}')
    entries+=("$file_entry")
  done

  # Merge all entries into one object. Empty case → empty object.
  if [[ "${#entries[@]}" -eq 0 ]]; then
    echo '{}'
    return 0
  fi
  printf '%s\n' "${entries[@]}" | jq -s 'add'
}

# -----------------------------------------------------------------------------
# main
# -----------------------------------------------------------------------------
main() {
  _resolve_paths
  local mode="${1:-write}"
  case "$mode" in
    --check)
      local actual expected
      actual=$(_build_index)
      if [[ ! -f "$KNOWLEDGE_INDEX_OUTPUT" ]]; then
        echo "[knowledge-index] index file missing: $KNOWLEDGE_INDEX_OUTPUT" >&2
        return 1
      fi
      expected=$(cat "$KNOWLEDGE_INDEX_OUTPUT")
      if [[ "$actual" != "$expected" ]]; then
        diff -u <(echo "$expected") <(echo "$actual") >&2 || true
        return 1
      fi
      return 0
      ;;
    write|"")
      _build_index > "$KNOWLEDGE_INDEX_OUTPUT"
      ;;
    *)
      echo "Unknown mode: $mode" >&2
      return 2
      ;;
  esac
}

main "$@"
