#!/usr/bin/env bats
# CI freshness gate. docs/skills.md is generated from each skills/<name>/SKILL.md
# frontmatter (name + description). It must match what a fresh build produces, so
# a skill added/removed/renamed — or a description edited — can never leave the
# catalog stale (the drift that left 14 skills uncatalogued before this gate).

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
BUILDER="$REPO_ROOT/plugins/dev-team/hooks/lib/build-skills-index.sh"

@test "docs/skills.md is current with the skills on disk" {
  cd "$REPO_ROOT"
  run bash "$BUILDER" --check
  [ "$status" -eq 0 ]
}

@test "every skill on disk appears in the generated catalog" {
  disk=$(ls -d "$REPO_ROOT"/plugins/dev-team/skills/*/ | xargs -n1 basename | sort)
  indexed=$(grep -oE 'skills/[A-Za-z0-9._-]+/SKILL.md' "$REPO_ROOT/plugins/dev-team/docs/skills.md" \
            | sed -E 's#skills/([^/]+)/SKILL.md#\1#' | sort -u)
  [ "$disk" = "$indexed" ]
}

@test "a new skill makes --check fail until the catalog is rebuilt" {
  FIX="${BATS_TEST_TMPDIR:-$BATS_TMPDIR}/skills-fix"
  rm -rf "$FIX"
  mkdir -p "$FIX/one" "$FIX/two"
  printf -- '---\nname: one\ndescription: First.\nuser-invocable: true\n---\n' > "$FIX/one/SKILL.md"
  printf -- '---\nname: two\ndescription: Second.\n---\n' > "$FIX/two/SKILL.md"
  OUT="$FIX/skills.md"

  SKILLS_INDEX_SKILLS_DIR="$FIX" SKILLS_INDEX_OUTPUT="$OUT" bash "$BUILDER"
  run env SKILLS_INDEX_SKILLS_DIR="$FIX" SKILLS_INDEX_OUTPUT="$OUT" bash "$BUILDER" --check
  [ "$status" -eq 0 ]

  # Add a skill without rebuilding -> the gate fails.
  mkdir -p "$FIX/three"
  printf -- '---\nname: three\ndescription: Third.\nuser-invocable: true\n---\n' > "$FIX/three/SKILL.md"
  run env SKILLS_INDEX_SKILLS_DIR="$FIX" SKILLS_INDEX_OUTPUT="$OUT" bash "$BUILDER" --check
  [ "$status" -eq 1 ]
  [[ "$output" == *"three"* ]]
}

@test "user-invocable skills render as slash commands, agent-loaded do not" {
  FIX="${BATS_TEST_TMPDIR:-$BATS_TMPDIR}/skills-render"
  rm -rf "$FIX"; mkdir -p "$FIX/cmd" "$FIX/lib"
  printf -- '---\nname: cmd\ndescription: A command.\nuser-invocable: true\n---\n' > "$FIX/cmd/SKILL.md"
  printf -- '---\nname: lib\ndescription: A module.\n---\n' > "$FIX/lib/SKILL.md"
  OUT="$FIX/skills.md"
  SKILLS_INDEX_SKILLS_DIR="$FIX" SKILLS_INDEX_OUTPUT="$OUT" bash "$BUILDER"
  grep -q '`/cmd`' "$OUT"
  grep -q '| lib |' "$OUT"
  ! grep -q '`/lib`' "$OUT"
}

@test "unparseable frontmatter fails the build loudly (no silent bad row)" {
  # An unquoted description with a bare ': ' is invalid YAML — the builder must
  # error naming the file, not emit an empty/miscategorized row.
  FIX="${BATS_TEST_TMPDIR:-$BATS_TMPDIR}/skills-bad"
  rm -rf "$FIX"; mkdir -p "$FIX/bad"
  printf -- '---\nname: bad\ndescription: refers to foo: bar inline\nuser-invocable: true\n---\n' > "$FIX/bad/SKILL.md"
  run env SKILLS_INDEX_SKILLS_DIR="$FIX" SKILLS_INDEX_OUTPUT="$FIX/o.md" bash "$BUILDER"
  [ "$status" -eq 1 ]
  [[ "$output" == *"bad/SKILL.md"* ]]
}

@test "a description with a pipe is escaped for the table" {
  FIX="${BATS_TEST_TMPDIR:-$BATS_TMPDIR}/skills-pipe"
  rm -rf "$FIX"; mkdir -p "$FIX/p"
  printf -- '---\nname: p\ndescription: alpha | beta\nuser-invocable: true\n---\n' > "$FIX/p/SKILL.md"
  OUT="$FIX/skills.md"
  SKILLS_INDEX_SKILLS_DIR="$FIX" SKILLS_INDEX_OUTPUT="$OUT" bash "$BUILDER"
  grep -q 'alpha \\| beta' "$OUT"
}

@test "catalog is grouped by capability, not by invocation type" {
  md="$REPO_ROOT/plugins/dev-team/docs/skills.md"
  grep -q '^## Specs & Planning' "$md"
  grep -q '^## Testing & Coverage' "$md"
  grep -q '^## Harness Governance & Tuning' "$md"
  # the old invocation-type sections are gone
  ! grep -q '^## User-invocable skills' "$md"
  ! grep -q '^## Agent-loaded skills' "$md"
}

@test "a skill outside the taxonomy lands in a trailing Other section" {
  FIX="${BATS_TEST_TMPDIR:-$BATS_TMPDIR}/skills-other"
  rm -rf "$FIX"; mkdir -p "$FIX/skills/known" "$FIX/skills/stray"
  printf -- '---\nname: known\ndescription: Known.\nuser-invocable: true\n---\n' > "$FIX/skills/known/SKILL.md"
  printf -- '---\nname: stray\ndescription: Stray.\nuser-invocable: true\n---\n' > "$FIX/skills/stray/SKILL.md"
  printf 'categories:\n  - name: Demo\n    skills: [known]\n' > "$FIX/cats.yaml"
  OUT="$FIX/skills.md"
  SKILLS_INDEX_SKILLS_DIR="$FIX/skills" SKILLS_INDEX_OUTPUT="$OUT" \
    SKILLS_INDEX_CATEGORIES="$FIX/cats.yaml" bash "$BUILDER"
  grep -q '^## Demo' "$OUT"
  grep -q '^## Other' "$OUT"
  grep -q '`/known`' "$OUT"
  grep -q '`/stray`' "$OUT"
}
