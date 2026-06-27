#!/usr/bin/env bats
# Markdown reference sensor. A skill/agent/knowledge file that names another repo
# file by a path which resolves to the wrong place (a rename left behind, a bare
# `knowledge/x.md` from a subdir that the runtime reads file-relative) dangles
# silently until something reads it and fails — the class that broke /ship's
# decision-defaults screen. scripts/check_md_references.py fails loudly on it, and
# is self-maintaining: it keys off the live `git` file tree, so references to
# things that are not repo files (runtime artifacts, placeholders) need no
# allowlist and are ignored automatically.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
CHECK="$REPO_ROOT/scripts/check_md_references.py"

# A minimal synthetic plugin tree the checker can scan in isolation. Not a git
# repo, so the checker's filesystem-walk fallback builds the real-file index.
setup() {
  FIX="${BATS_TEST_TMPDIR:-$BATS_TMPDIR}/fixture"
  rm -rf "$FIX"
  mkdir -p "$FIX/plugins/dev-team/skills/demo"
  mkdir -p "$FIX/plugins/dev-team/knowledge/aa"
  printf 'real knowledge file\n' > "$FIX/plugins/dev-team/knowledge/aa/bb.md"
}

skill() { printf '%b' "$1" > "$FIX/plugins/dev-team/skills/demo/SKILL.md"; }

@test "the real repository tree has no misrouted references" {
  run python3 "$CHECK" --root "$REPO_ROOT"
  [ "$status" -eq 0 ]
}

@test "a correctly-routed file-relative reference passes" {
  skill 'See [bb](../../knowledge/aa/bb.md) for details.\n'
  run python3 "$CHECK" --root "$FIX"
  [ "$status" -eq 0 ]
}

@test "a bare plugin-root-relative reference passes (the kept convention)" {
  # Resolves at the module root, so it is not a broken link.
  skill 'See `knowledge/aa/bb.md` for details.\n'
  run python3 "$CHECK" --root "$FIX"
  [ "$status" -eq 0 ]
}

@test "a misrouted reference to a real file fails" {
  # `aa/bb.md` resolves nowhere from skills/demo, yet a real file ends with /aa/bb.md.
  skill 'See `aa/bb.md` for details.\n'
  run python3 "$CHECK" --root "$FIX"
  [ "$status" -eq 1 ]
  [[ "$output" == *"aa/bb.md"* ]]
}

@test "a reference to a tracked path resolves even if the filesystem can't (symlink)" {
  # Reproduces the macOS-vs-CI split: a tracked symlink (e.g. .claude/evals/fixtures
  # -> evals/…) that a CI checkout leaves unmaterialized reads as dangling via
  # os.path but IS a real tracked path. A broken symlink to a directory models
  # that — the walk lists it (so it counts as tracked) yet os.path.isdir is false.
  mkdir -p "$FIX/data"
  ln -s nonexistent-target "$FIX/data/store"
  skill 'Fixtures live in `data/store/` at runtime.\n'
  run python3 "$CHECK" --root "$FIX"
  [ "$status" -eq 0 ]
}

@test "a reference that names nothing real is ignored (runtime artifact)" {
  skill 'State is written to `memory/decisions.md` at runtime.\n'
  run python3 "$CHECK" --root "$FIX"
  [ "$status" -eq 0 ]
}

@test "a placeholder path is ignored" {
  skill 'A knowledge file (`knowledge/X.md`) is read on demand.\n'
  run python3 "$CHECK" --root "$FIX"
  [ "$status" -eq 0 ]
}

@test "a backtick link label is not checked, only the link target" {
  # Label text `aa/bb.md` would be a misroute if checked, but it is display text;
  # the actual target resolves, so the line is clean.
  skill 'See [`aa/bb.md`](../../knowledge/aa/bb.md).\n'
  run python3 "$CHECK" --root "$FIX"
  [ "$status" -eq 0 ]
}

@test "a fenced code block is not scanned" {
  skill '```\nexample: `aa/bb.md` shown as a sample\n```\n'
  run python3 "$CHECK" --root "$FIX"
  [ "$status" -eq 0 ]
}

@test "an external URL is ignored" {
  skill 'Docs at https://example.com/aa/bb.md are external.\n'
  run python3 "$CHECK" --root "$FIX"
  [ "$status" -eq 0 ]
}
