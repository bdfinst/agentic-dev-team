#!/usr/bin/env bats
# Slice 3 — progress_guardian.py
# Covers checkbox parsing, git-log cross-reference, uncommitted-change check,
# pre-PR flag, and scope creep.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
PG="$REPO_ROOT/scripts/progress_guardian.py"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

make_plan() {
  # Usage: make_plan <file> <content>
  printf '%s\n' "$2" > "$1"
}

# ---------------------------------------------------------------------------
# Step 3.1 — Checkbox state parser
# ---------------------------------------------------------------------------

@test "3.1a: done checkbox [x] is parsed as done=True with header captured" {
  T="$(mktemp -d)"
  PLAN="$T/plan.md"
  make_plan "$PLAN" "- [x] Step 1.1: Do something"

  cd "$T"
  git init -q
  git config user.email "test@test.com"
  git config user.name "Test"
  git commit -q --allow-empty -m "initial commit"

  run python3 "$PG" --plan "$PLAN" --skip-llm
  rm -rf "$T"
  # [x] step present, no matching commit → exit 1 naming the step
  [ "$status" -eq 1 ]
  echo "$output" | python3 -c "import sys,json; d=json.load(sys.stdin); assert any('Do something' in i['message'] for i in d['issues']), d"
}

@test "3.1b: undone checkbox [ ] is parsed as done=False (no error for it)" {
  T="$(mktemp -d)"
  PLAN="$T/plan.md"
  make_plan "$PLAN" "- [ ] Step 1.2: Another thing"

  cd "$T"
  git init -q
  git config user.email "test@test.com"
  git config user.name "Test"
  git commit -q --allow-empty -m "initial commit"

  run python3 "$PG" --plan "$PLAN" --skip-llm
  rm -rf "$T"
  # [ ] step is not done — no commit-discipline error, but may get llm-skipped warning
  # status should NOT be 1 (fail) because the step is unchecked
  [ "$status" -ne 1 ]
}

@test "3.1c: plan file with no checkboxes exits 1 with file name in output" {
  T="$(mktemp -d)"
  PLAN="$T/plan.md"
  make_plan "$PLAN" "# Plan\n\nSome text without any checkboxes."

  cd "$T"
  git init -q
  git config user.email "test@test.com"
  git config user.name "Test"
  git commit -q --allow-empty -m "initial commit"

  run python3 "$PG" --plan "$PLAN" --skip-llm
  rm -rf "$T"
  [ "$status" -eq 1 ]
  echo "$output" | python3 -c "import sys,json; d=json.load(sys.stdin); assert any('plan.md' in i['message'] or 'plan.md' in i['file'] for i in d['issues']), d"
}

# ---------------------------------------------------------------------------
# Step 3.2 — Git-log cross-reference and uncommitted change check
# ---------------------------------------------------------------------------

@test "3.2a: [x] step with matching commit exits 0 (clean tree)" {
  T="$(mktemp -d)"
  PLAN="$T/plan.md"
  make_plan "$PLAN" "- [x] Step 1.1: add checkbox parser"

  cd "$T"
  git init -q
  git config user.email "test@test.com"
  git config user.name "Test"
  git commit -q --allow-empty -m "feat: add checkbox parser"
  git add plan.md
  git commit -q -m "add plan"

  run python3 "$PG" --plan "$T/plan.md" --skip-llm
  rm -rf "$T"
  [ "$status" -eq 0 ]
}

@test "3.2b: [x] step with no matching commit exits 1 naming the step header" {
  T="$(mktemp -d)"
  PLAN="$T/plan.md"
  make_plan "$PLAN" "- [x] Step 1.1: Add something specific"

  cd "$T"
  git init -q
  git config user.email "test@test.com"
  git config user.name "Test"
  git commit -q --allow-empty -m "feat: something unrelated"

  run python3 "$PG" --plan "$PLAN" --skip-llm
  rm -rf "$T"
  [ "$status" -eq 1 ]
  echo "$output" | python3 -c "import sys,json; d=json.load(sys.stdin); assert any('Add something specific' in i['message'] for i in d['issues']), d"
}

@test "3.2c: staged file with a [x] step exits 1 (uncommitted work)" {
  T="$(mktemp -d)"
  PLAN="$T/plan.md"
  make_plan "$PLAN" "- [x] Step 1.1: add checkbox parser"

  cd "$T"
  git init -q
  git config user.email "test@test.com"
  git config user.name "Test"
  git commit -q --allow-empty -m "feat: add checkbox parser"
  # Stage an extra file
  echo "staged content" > staged.txt
  git add staged.txt

  run python3 "$PG" --plan "$T/plan.md" --skip-llm
  rm -rf "$T"
  [ "$status" -eq 1 ]
  echo "$output" | python3 -c "import sys,json; d=json.load(sys.stdin); assert any('uncommit' in i['message'].lower() for i in d['issues']), d"
}

@test "3.2d: unstaged modification with a [x] step exits 1 (uncommitted work)" {
  T="$(mktemp -d)"
  PLAN="$T/plan.md"

  cd "$T"
  git init -q
  git config user.email "test@test.com"
  git config user.name "Test"
  # Create and commit a file, then modify it
  echo "original" > tracked.txt
  git add tracked.txt
  git commit -q -m "feat: add checkbox parser"
  echo "modified" > tracked.txt

  make_plan "$PLAN" "- [x] Step 1.1: add checkbox parser"

  run python3 "$PG" --plan "$PLAN" --skip-llm
  rm -rf "$T"
  [ "$status" -eq 1 ]
  echo "$output" | python3 -c "import sys,json; d=json.load(sys.stdin); assert any('uncommit' in i['message'].lower() for i in d['issues']), d"
}

# ---------------------------------------------------------------------------
# Step 3.3 — Pre-PR flag, scope creep, and agent update
# ---------------------------------------------------------------------------

@test "3.3a: --pre-pr with all [x] steps + matching commits + clean tree exits 0" {
  T="$(mktemp -d)"
  PLAN="$T/plan.md"
  make_plan "$PLAN" "- [x] Step 1.1: add checkbox parser
- [x] Step 1.2: add git log check"

  cd "$T"
  git init -q
  git config user.email "test@test.com"
  git config user.name "Test"
  git commit -q --allow-empty -m "feat: add checkbox parser"
  git commit -q --allow-empty -m "feat: add git log check"

  run python3 "$PG" --plan "$PLAN" --pre-pr --skip-llm
  rm -rf "$T"
  [ "$status" -eq 0 ]
}

@test "3.3b: --pre-pr with a [ ] (undone) step exits 1" {
  T="$(mktemp -d)"
  PLAN="$T/plan.md"
  make_plan "$PLAN" "- [x] Step 1.1: add checkbox parser
- [ ] Step 1.2: add git log check"

  cd "$T"
  git init -q
  git config user.email "test@test.com"
  git config user.name "Test"
  git commit -q --allow-empty -m "feat: add checkbox parser"

  run python3 "$PG" --plan "$PLAN" --pre-pr --skip-llm
  rm -rf "$T"
  [ "$status" -eq 1 ]
  echo "$output" | python3 -c "import sys,json; d=json.load(sys.stdin); assert any('incomplete' in i['message'].lower() or 'unchecked' in i['message'].lower() or 'not done' in i['message'].lower() for i in d['issues']), d"
}

@test "3.3c: --skip-llm with out-of-plan staged file adds warning finding (exit 2)" {
  T="$(mktemp -d)"
  PLAN="$T/plan.md"
  # Plan declares no file paths; extra.py is out-of-plan
  make_plan "$PLAN" "- [x] Step 1.1: add checkbox parser"

  cd "$T"
  git init -q
  git config user.email "test@test.com"
  git config user.name "Test"
  git commit -q --allow-empty -m "feat: add checkbox parser"
  # Stage an out-of-plan file
  echo "extra code" > extra.py
  git add extra.py

  run python3 "$PG" --plan "$PLAN" --skip-llm
  rm -rf "$T"
  # Uncommitted staged file → exit 1 (uncommitted check fires before scope check)
  # But we want to confirm scope check is included. The uncommitted check should fire.
  [ "$status" -eq 1 ]
}

@test "3.3d: --skip-llm with clean tree but out-of-plan file in committed diff emits warning (exit 2)" {
  T="$(mktemp -d)"
  PLAN="$T/plan.md"
  # Plan declares no backtick-paths; extra.py is out-of-plan
  make_plan "$PLAN" "- [x] Step 1.1: add checkbox parser"

  cd "$T"
  git init -q
  git config user.email "test@test.com"
  git config user.name "Test"
  git commit -q --allow-empty -m "initial"
  # Commit plan
  git add plan.md
  git commit -q -m "feat: add checkbox parser"
  # Commit extra out-of-plan file
  echo "extra code" > extra.py
  git add extra.py
  git commit -q -m "feat: add checkbox parser extra"

  run python3 "$PG" --plan plan.md --skip-llm
  rm -rf "$T"
  # With clean tree and [x] steps + matching commits, scope check fires → llm-skipped warning → exit 2
  [ "$status" -eq 2 ]
  echo "$output" | python3 -c "import sys,json; d=json.load(sys.stdin); assert any(i.get('rule_id') == 'llm-skipped' for i in d['issues']), d"
}

# ---------------------------------------------------------------------------
# Step 4.1 — Issue #525 regressions: origin/main preference
# Bug: check_scope's branch tuple was ("main", "master", "origin/main",
# "origin/master") — preferring stale local main. When local main lags
# origin/main, the resulting merge-base sweeps in every commit landed on
# trunk while the contributor was working.
# ---------------------------------------------------------------------------

# Helper: set up a tmp dir with a bare "remote" repo and a working clone where
# origin/main is exactly one commit ahead of local main. Both refs are real;
# the test exercises check_scope's branch-resolution order.
#
# Usage: setup_stale_main_repo <work_dir> <ahead_commit_file>
# After this returns, <work_dir> is a git repo with:
#   - origin/main pointing at HEAD~1 + an "ahead" commit on the remote
#   - local main pointing at HEAD~1 (the shared base) — lagging by 1
#   - HEAD on a feature branch off origin/main
setup_stale_main_repo() {
  local work="$1"
  local ahead_file="$2"
  local remote="$work/../remote.git"
  # Bare remote
  git init -q --bare "$remote"
  # Working clone seeded with an initial commit
  git init -q "$work"
  cd "$work"
  git config user.email "test@test.com"
  git config user.name "Test"
  git remote add origin "$remote"
  git checkout -q -b main
  echo "seed" > seed.txt
  git add seed.txt
  git commit -q -m "chore: seed"
  git push -q origin main
  # Advance the remote with an ahead-commit touching <ahead_file>, via a
  # sibling clone so this clone's local main stays at the seed.
  local sibling
  sibling="$(mktemp -d)/sibling"
  git clone -q "$remote" "$sibling"
  cd "$sibling"
  git config user.email "test@test.com"
  git config user.name "Test"
  echo "ahead" > "$ahead_file"
  git add "$ahead_file"
  git commit -q -m "feat: ahead on main"
  git push -q origin main
  # Back to the working clone; fetch so origin/main moves but local main stays.
  cd "$work"
  git fetch -q origin
  # Cut the feature branch off origin/main (the new tip).
  git checkout -q -b feature origin/main
}

@test "4.1a: local main lags origin/main by one commit; on-branch file is not reported as out-of-plan" {
  T="$(mktemp -d)"
  WORK="$T/work"
  setup_stale_main_repo "$WORK" "unrelated.py"
  # Commit a.py on the feature branch.
  cd "$WORK"
  echo "branch work" > a.py
  git add a.py
  # Slice 1 isolates scope-check; the commit subject must substring-match
  # the slice header so commit-discipline passes and only scope-check is
  # under test. (Slice 2 covers the Conventional-Commits scenario where
  # subject and header don't substring-match.)
  git commit -q -m "feat: write a.py for the slice"
  PLAN="$WORK/plan.md"
  printf '%s\n' "- [x] write a.py for the slice" "" "**Files:** \`a.py\`" > "$PLAN"

  run python3 "$PG" --plan "$PLAN" --skip-llm
  rm -rf "$T"
  [ "$status" -eq 0 ]
  echo "$output" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['issues']==[], d"
}

@test "4.1b: local main equals origin/main; on-branch file is not reported as out-of-plan (no regression)" {
  T="$(mktemp -d)"
  WORK="$T/work"
  # Set up a repo where origin/main == local main (no remote advance).
  REMOTE="$T/remote.git"
  git init -q --bare "$REMOTE"
  git init -q "$WORK"
  cd "$WORK"
  git config user.email "test@test.com"
  git config user.name "Test"
  git remote add origin "$REMOTE"
  git checkout -q -b main
  echo "seed" > seed.txt
  git add seed.txt
  git commit -q -m "chore: seed"
  git push -q origin main
  git fetch -q origin
  # Branch off and commit a.py. Slice header substring-matches the commit
  # subject so commit-discipline passes and only scope-check is under test.
  git checkout -q -b feature
  echo "branch work" > a.py
  git add a.py
  git commit -q -m "feat: write a.py for the slice"
  PLAN="$WORK/plan.md"
  printf '%s\n' "- [x] write a.py for the slice" "" "**Files:** \`a.py\`" > "$PLAN"

  run python3 "$PG" --plan "$PLAN" --skip-llm
  rm -rf "$T"
  [ "$status" -eq 0 ]
  echo "$output" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['issues']==[], d"
}

# ---------------------------------------------------------------------------
# Step 4.2 — Issue #525 regressions: file-path matcher
# Bug: check_commit_discipline required a substring of the slice header in
# the commit subject. Conventional Commits (mandated by CLAUDE.md) never
# contain plan-step header text verbatim, so the gate fired on every
# normally-disciplined branch.
#
# Fix: parse each [x] slice's `**Files:**` line, then for each declared
# path check whether any commit on this branch touched it. Fall back to
# the substring matcher when no `**Files:**` line is declared (legacy
# plans + the existing 11 tests).
# ---------------------------------------------------------------------------

@test "4.2a: Conventional Commit on declared file satisfies the matcher" {
  T="$(mktemp -d)"
  cd "$T"
  git init -q
  git config user.email "test@test.com"
  git config user.name "Test"
  git commit -q --allow-empty -m "chore: initial"
  echo "branch work" > a.py
  git add a.py
  # Conventional Commit subject that does NOT substring-match the slice header.
  git commit -q -m "feat(scope): wording unrelated to the slice header"
  PLAN="$T/plan.md"
  printf '%s\n' "- [x] Slice 1: do thing" "" "**Files:** \`a.py\`" > "$PLAN"

  run python3 "$PG" --plan "$PLAN" --skip-llm
  rm -rf "$T"
  [ "$status" -eq 0 ]
  echo "$output" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['issues']==[], d"
}

@test "4.2b: commit touches one of multiple declared files (any-of semantics)" {
  T="$(mktemp -d)"
  cd "$T"
  git init -q
  git config user.email "test@test.com"
  git config user.name "Test"
  git commit -q --allow-empty -m "chore: initial"
  echo "branch work" > b.py
  git add b.py
  git commit -q -m "feat: anything"
  PLAN="$T/plan.md"
  printf '%s\n' "- [x] Slice 1: do thing" "" "**Files:** \`a.py\`, \`b.py\`" > "$PLAN"

  run python3 "$PG" --plan "$PLAN" --skip-llm
  rm -rf "$T"
  [ "$status" -eq 0 ]
  echo "$output" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['issues']==[], d"
}

@test "4.2c: commit modifies only undeclared files; matcher fails naming the slice" {
  T="$(mktemp -d)"
  cd "$T"
  git init -q
  git config user.email "test@test.com"
  git config user.name "Test"
  git commit -q --allow-empty -m "chore: initial"
  echo "branch work" > b.py
  git add b.py
  git commit -q -m "feat: anything"
  PLAN="$T/plan.md"
  printf '%s\n' "- [x] Slice 1: do thing" "" "**Files:** \`a.py\`" > "$PLAN"

  run python3 "$PG" --plan "$PLAN" --skip-llm
  rm -rf "$T"
  [ "$status" -eq 1 ]
  # Exactly one commit-discipline error whose message includes the slice header.
  echo "$output" | python3 -c "
import sys, json
d = json.load(sys.stdin)
errs = [i for i in d['issues'] if i['severity'] == 'error' and 'Slice 1: do thing' in i['message']]
assert len(errs) == 1, d
"
}
