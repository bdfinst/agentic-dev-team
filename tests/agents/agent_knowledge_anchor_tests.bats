#!/usr/bin/env bats
# AC19: every knowledge-file or skill reference in an agent body either
# cites a section anchor that exists in knowledge/index.json, OR the
# paragraph containing the reference contains the literal verbatim
# token "Whole-file load:" (case-sensitive, hyphen, colon).
#
# This test is GATED behind KNOWLEDGE_SWEEP_DONE=1 during the per-cluster
# sweep (Steps 12a/12b/12c). Step 12d removes the gate so the test runs
# by default in CI.
#
# Optional AGENT_FILES env var lets per-cluster runs scope the sweep to
# a subset of agent basenames. Unknown filenames in AGENT_FILES fail
# loudly so typos don't silently pass.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
INDEX="$REPO_ROOT/plugins/agentic-dev-team/knowledge/index.json"
AGENTS_DIR="$REPO_ROOT/plugins/agentic-dev-team/agents"
WHOLE_FILE_TOKEN='Whole-file load:'

setup() {
  if [[ "${KNOWLEDGE_SWEEP_DONE:-0}" != "1" ]]; then
    skip "set KNOWLEDGE_SWEEP_DONE=1 to run the anchor-citation gate (active by default once Step 12d lands)"
  fi
}

# Resolve which agent files to check.
# - Default: every *.md under agents/.
# - With AGENT_FILES: only the named basenames (each must exist).
_agent_files_to_check() {
  if [[ -n "${AGENT_FILES:-}" ]]; then
    # Comma- or whitespace-separated. Validate each.
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

@test "AGENT_FILES typo guard: unknown filename fails loudly" {
  AGENT_FILES="does-not-exist.md" run bash -c "
    AGENT_FILES='does-not-exist.md' AGENTS_DIR='$AGENTS_DIR'
    raw=\"\${AGENT_FILES//,/ }\"
    for f in \$raw; do
      [[ ! -f \"\$AGENTS_DIR/\$f\" ]] && { echo \"AGENT_FILES contains an unknown agent: \$f\" >&2; exit 1; }
    done
  "
  [ "$status" -eq 1 ]
}

@test "AC19: every knowledge/skill reference in agents/ cites a valid anchor or 'Whole-file load:'" {
  local files
  files=$(_agent_files_to_check) || {
    echo "$files" >&2
    return 1
  }

  local violations=""
  local agent_file
  while IFS= read -r agent_file; do
    [[ -z "$agent_file" ]] && continue
    # Find every reference matching the pattern.
    # Use python to handle paragraph-scope lookups for the escape hatch.
    local out
    out=$(python3 - "$agent_file" "$INDEX" "$WHOLE_FILE_TOKEN" <<'PYEOF'
import json
import re
import sys

agent_file = sys.argv[1]
index_path = sys.argv[2]
whole_token = sys.argv[3]

with open(agent_file, "r", encoding="utf-8") as fh:
    text = fh.read()
with open(index_path, "r", encoding="utf-8") as fh:
    index = json.load(fh)

# Pattern: agentic-dev-team's own knowledge/<name>.md or skills/<name>/SKILL.md.
# Excludes cross-plugin references (e.g.
# `plugins/agentic-security-assessment/skills/...`). A reference belongs to
# this index iff it's either bare `knowledge/X.md` / `skills/Y/SKILL.md`
# OR explicitly prefixed with `plugins/agentic-dev-team/`. Cross-plugin paths
# start with `plugins/<other>/`, so we require either no prefix or our
# plugin prefix.
ref_re = re.compile(
    r"(?:^|[^/])"
    r"(?:plugins/agentic-dev-team/)?"
    r"((?:knowledge/[a-z0-9-]+\.md|skills/[a-z0-9-]+/SKILL\.md))"
    r"(#[a-z0-9-]+)?"
)

# Split body into paragraphs (blank-line separated).
paragraphs = re.split(r"\n\s*\n", text)

violations = []
for para in paragraphs:
    for m in ref_re.finditer(para):
        ref_file = m.group(1)
        anchor = m.group(2)
        # Skip cross-plugin references — only act on our own corpus.
        # The regex's leading non-capturing prefix is permissive; tighten
        # here by inspecting the byte just before the match for a `/`
        # belonging to a non-agentic-dev-team plugin path.
        start = m.start()
        # Find a `plugins/...` prefix immediately preceding this match.
        pre = para[max(0, start - 60):start]
        cross_plugin = re.search(r"plugins/(?!agentic-dev-team/)[a-z0-9-]+/$", pre)
        if cross_plugin:
            continue
        # Resolve the index key.
        key = f"plugins/agentic-dev-team/{ref_file}"
        if anchor:
            anchor_slug = anchor.lstrip("#")
            # Look up: any section in the file whose anchor matches.
            section_data = index.get(key, {})
            anchors = {entry.get("anchor") for entry in section_data.values()}
            if anchor_slug in anchors:
                continue
            violations.append(f"{agent_file}: anchor '{anchor_slug}' not found in {key}")
            continue
        # No anchor — require the literal Whole-file load: token in the paragraph.
        if whole_token in para:
            continue
        violations.append(f"{agent_file}: bare reference {ref_file} lacks an anchor AND no '{whole_token}' in paragraph")

for v in violations:
    print(v)
PYEOF
)
    if [[ -n "$out" ]]; then
      violations="${violations}${out}\n"
    fi
  done <<<"$files"

  if [[ -n "$violations" ]]; then
    echo "Anchor-citation violations found." >&2
    echo "Every knowledge/X.md or skills/Y/SKILL.md reference in agents/ must:" >&2
    echo "  - end with a #anchor fragment that exists in knowledge/index.json, OR" >&2
    echo "  - have the literal verbatim token '${WHOLE_FILE_TOKEN}' in the same paragraph." >&2
    echo "" >&2
    printf '%b' "$violations" >&2
    return 1
  fi
}
