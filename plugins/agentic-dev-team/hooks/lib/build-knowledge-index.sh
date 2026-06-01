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
# _check_jq_version — exit non-zero if jq is missing or below 1.6.
# `jq -c` output formatting changed across early versions; pinning the
# floor keeps the deterministic index byte-identical across CI/local.
# -----------------------------------------------------------------------------
_check_jq_version() {
  local raw major minor
  raw=$(jq --version 2>/dev/null || true)
  if [[ -z "$raw" ]]; then
    echo "[knowledge-index] jq not found on PATH; requires jq >= 1.6" >&2
    exit 1
  fi
  # `raw` looks like `jq-1.7.1` or `jq-1.5`. Strip the prefix.
  local v="${raw#jq-}"
  IFS='.' read -r major minor _ <<<"$v"
  # Accept 2.x+, 1.6+, or anything with a higher major.
  if [[ "$major" -gt 1 ]]; then
    return 0
  fi
  if [[ "$major" -eq 1 && "$minor" -ge 6 ]]; then
    return 0
  fi
  echo "[knowledge-index] jq version $v below required 1.6" >&2
  exit 1
}
_check_jq_version

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
# Returns the first sentence per the spec's operational boundary rule:
#   - Terminates at the first `.`, `!`, or `?` followed by whitespace or
#     end-of-line.
#   - NOT preceded by a single uppercase letter (e.g. `J. Doe`).
#   - NOT preceded by one of the abbreviation tokens: e.g, i.e, etc, vs,
#     Mr, Mrs, Ms, Dr, Jr, Sr, St, No, cf.
#   - If no terminator is found within 240 characters, truncate at the
#     last whitespace before 240 chars and append `…`.
# Python is a hard dependency of the plugin (jq + python3 enforced by
# /init-dev-team), so use it for the regex precision shell can't match.
# -----------------------------------------------------------------------------
_first_sentence() {
  python3 - "$1" <<'PYEOF'
import re
import sys

ABBREVS = {"e.g", "i.e", "etc", "vs", "Mr", "Mrs", "Ms", "Dr", "Jr", "Sr", "St", "No", "cf"}
MAX_LEN = 240

text = sys.argv[1].lstrip()
# Walk the text, looking for terminator candidates.
i = 0
end = None
while i < len(text):
    ch = text[i]
    if ch in ".!?":
        # Boundary condition 1: followed by whitespace or end-of-string.
        after = text[i + 1] if i + 1 < len(text) else ""
        if not (after == "" or after.isspace()):
            i += 1
            continue
        # Boundary condition 2: not preceded by a single uppercase letter.
        # (Detect `X.` initial: previous char uppercase, char before that
        # is whitespace, start-of-string, or another `.`.)
        if i >= 1 and text[i - 1].isupper():
            prev2 = text[i - 2] if i - 2 >= 0 else ""
            if prev2 == "" or prev2.isspace() or prev2 == ".":
                i += 1
                continue
        # Boundary condition 3: not preceded by a known abbreviation token.
        # Find the token immediately before this terminator.
        j = i - 1
        while j >= 0 and not text[j].isspace():
            j -= 1
        token = text[j + 1:i]
        if token in ABBREVS:
            i += 1
            continue
        end = i + 1
        break
    i += 1

if end is not None:
    sys.stdout.write(text[:end])
else:
    # No terminator found. Truncate at 240 chars (last whitespace ≤ 240)
    # and append the horizontal-ellipsis.
    if len(text) <= MAX_LEN:
        sys.stdout.write(text)
    else:
        cut = text[:MAX_LEN].rstrip()
        last_ws = cut.rfind(" ")
        if last_ws > 0:
            cut = cut[:last_ws]
        sys.stdout.write(cut + "…")
PYEOF
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
  # First pass: emit raw section records as `level\theader\tbody`.
  # Second pass (below): post-process to backfill empty bodies from the
  # next child section.
  local raw
  raw=$(awk '
    /^```/ { in_code = !in_code; next }
    in_code == 1 { next }

    /^#### / {
      _flush()
      collecting = 0
      next
    }
    /^### / {
      _flush()
      header = substr($0, 5)
      level = 3
      collecting = 1
      body = ""
      next
    }
    /^## / {
      _flush()
      header = substr($0, 4)
      level = 2
      collecting = 1
      body = ""
      next
    }
    /^# / {
      _flush()
      collecting = 0
      next
    }
    collecting == 1 && body == "" && /[^[:space:]]/ {
      if (match($0, /^[[:space:]]*[-*+][[:space:]]+/)) {
        body = substr($0, RLENGTH + 1)
      } else {
        body = $0
      }
    }
    END { _flush() }
    function _flush() {
      if (header != "") {
        print level "\t" header "\t" body
        header = ""
        body = ""
      }
    }
  ' "$abs")

  # Second pass: backfill empty bodies from the next section in source
  # order. Write the raw rows to a tempfile and pass the path as argv —
  # avoids both shell-interpolation hazards (no `"""$raw"""` escape
  # collisions) and the bash-3.2 redirection conflict between heredoc
  # and pipe stdin.
  local raw_file
  raw_file=$(mktemp)
  printf '%s' "$raw" > "$raw_file"
  python3 - "$raw_file" <<'PYEOF'
import sys

with open(sys.argv[1], "r", encoding="utf-8") as fh:
    data = fh.read()

rows = []
for line in data.splitlines():
    if not line:
        continue
    parts = line.split("\t", 2)
    while len(parts) < 3:
        parts.append("")
    rows.append(parts)

# Backfill empty bodies from the next row's body (regardless of level).
for i in range(len(rows)):
    if not rows[i][2].strip():
        for j in range(i + 1, len(rows)):
            if rows[j][2].strip():
                rows[i][2] = rows[j][2]
                break

for level, header, body in rows:
    sys.stdout.write(f"{header}\t{body}\n")
PYEOF
  rm -f "$raw_file"
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
  # File order is determinism-critical (the index uses keys_unsorted),
  # so we sort explicitly under LC_ALL=C regardless of `find`'s native
  # platform behavior.
  local -a files=()
  local sorted_list
  sorted_list=$(
    {
      [[ -d "$roots/knowledge" ]] && find "$roots/knowledge" -maxdepth 1 -name '*.md' -type f
      [[ -d "$roots/skills" ]] && find "$roots/skills" -mindepth 2 -maxdepth 2 -name 'SKILL.md' -type f
    } | LC_ALL=C sort
  )
  while IFS= read -r f; do
    [[ -n "$f" ]] && files+=("$f")
  done <<<"$sorted_list"

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
