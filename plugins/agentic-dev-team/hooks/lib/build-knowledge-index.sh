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
# Walks one markdown file and prints "header\tbody_first_line" pairs, one
# per H2/H3 section, in source order. H1 and H4+ are skipped. The caller
# is responsible for slugify, summary extraction, and slug
# disambiguation across sections within the file.
# -----------------------------------------------------------------------------
_extract_sections_for_file() {
  local abs="$1"
  awk '
    /^### / {
      _flush()
      header = substr($0, 5)
      collecting = 1
      body = ""
      next
    }
    /^## / {
      _flush()
      header = substr($0, 4)
      collecting = 1
      body = ""
      next
    }
    /^#### / {
      # H4+ — stop collecting body for the enclosing section but do not
      # emit anything for the H4.
      _flush()
      collecting = 0
      next
    }
    /^# / {
      # H1 — skipped entirely. Resets state.
      _flush()
      collecting = 0
      next
    }
    collecting == 1 && body == "" && /[^[:space:]]/ {
      body = $0
    }
    END { _flush() }
    function _flush() {
      if (header != "") {
        print header "\t" body
        header = ""
        body = ""
      }
    }
  ' "$abs"
}

# -----------------------------------------------------------------------------
# _disambiguate_anchor <anchor> <file_path>
# GitHub-style: first occurrence gets the bare slug; second gets `-1`;
# third `-2`; etc. State is per-file via a bash associative array passed
# by name. Sourced into _build_index's scope.
# -----------------------------------------------------------------------------

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
  # mapping section header → {summary, anchor}, preserving source order.
  local entries=()
  local f
  for f in ${files[@]+"${files[@]}"}; do
    local rel
    rel="${f#"$roots/"}"
    # Prefix back the plugin-rooted segment so the key is repo-relative.
    rel="plugins/agentic-dev-team/$rel"

    # Collect all sections for this file. Each line: header\tbody.
    local section_data
    section_data="$(_extract_sections_for_file "$f")"
    if [[ -z "$section_data" ]]; then
      continue
    fi

    # Per-file collision tracking. macOS ships bash 3.2 (no
    # associative arrays), so we use newline-delimited string lookups:
    # one "seen" record per slug or header, count derived by grep.
    local slug_seen=""
    local header_seen=""

    # Build the per-section JSON objects in source order, then merge.
    local section_objs=()
    while IFS=$'\t' read -r header body; do
      [[ -z "$header" ]] && continue
      local base_slug summary anchor n key hcount
      base_slug="$(_slugify "$header")"

      # Slug disambiguation: github-style overview / overview-1 / overview-2
      n=$(printf '%s\n' "$slug_seen" | grep -cFx "$base_slug" || true)
      if (( n == 0 )); then
        anchor="$base_slug"
      else
        anchor="${base_slug}-${n}"
      fi
      slug_seen="${slug_seen}${base_slug}"$'\n'

      # Header key disambiguation: JSON requires unique keys.
      hcount=$(printf '%s\n' "$header_seen" | grep -cFx "$header" || true)
      if (( hcount == 0 )); then
        key="$header"
      else
        key="${header} ($((hcount + 1)))"
      fi
      header_seen="${header_seen}${header}"$'\n'

      summary="$(_first_sentence "$body")"
      section_objs+=("$(jq -n \
        --arg key "$key" \
        --arg summary "$summary" \
        --arg anchor "$anchor" \
        '{($key): {summary: $summary, anchor: $anchor}}')")
    done <<<"$section_data"

    # Merge sections in source order using jq's `add` (preserves
    # insertion order, which is what jq emits as keys_unsorted).
    local file_obj
    file_obj=$(printf '%s\n' "${section_objs[@]}" | jq -s 'add')

    local file_entry
    file_entry=$(jq -n \
      --arg rel "$rel" \
      --argjson file_obj "$file_obj" \
      '{($rel): $file_obj}')
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
