#!/usr/bin/env bats
# End-to-end proof for issue #546: a full pre-push run against a real git
# push leaves refs stable.
#
# Depends on: slices 1 (hermetic helper), 2 (ci-local env scrub), 4 (ref
# guard). This test drives a real `git push` inside a hermetic scratch
# repo — the same class of operation that caused the original incident —
# so it is guarded from itself by hermetic_setup and only enabled after
# slices 1-4 land. See docs/specs/pre-push-hook-hermetic-fixtures.md.

REPO_ROOT="$BATS_TEST_DIRNAME/../.."
REAL_HOOK="$REPO_ROOT/.husky/pre-push"

load '../lib/hermetic'

setup() {
  hermetic_setup
}

teardown() {
  hermetic_teardown
}

@test "e2e: real git push through the shipped pre-push hook leaves refs stable" {
  # Build a scratch bare + worktree scaffold.
  BARE="$HERMETIC_ROOT/remote.git"
  WORK="$HERMETIC_ROOT/work"
  mkdir -p "$BARE" && ( cd "$BARE" && git init -q --bare -b main )

  git init -q -b main "$WORK"
  cd "$WORK"
  git config user.email "t@t"
  git config user.name "T"
  git commit -q --allow-empty -m "seed"
  git remote add origin "$BARE"
  git push -q origin main

  git checkout -q -b feature
  git commit -q --allow-empty -m "feat"

  # Install the real hook + a fast-passing ci-local.sh stub. The stub is
  # necessary because the shipped ci-local.sh runs the entire suite —
  # too heavy for this test. We are asserting on ref-stability under
  # the *shipped hook framework*, not re-running the CI mirror.
  mkdir -p "$WORK/.husky" "$WORK/scripts"
  cp "$REAL_HOOK" "$WORK/.husky/pre-push"
  cat > "$WORK/scripts/ci-local.sh" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB
  chmod +x "$WORK/scripts/ci-local.sh"

  # Configure the local hooks path (the real repo uses husky's .husky/_,
  # which resolves relatively; for the scratch, wire the hook directly).
  git config core.hooksPath "$WORK/.husky"

  # Snapshot refs on BOTH the bare and the worktree BEFORE the push.
  PRE_BARE="$(git --git-dir="$BARE" for-each-ref --format='%(refname) %(objectname)' refs/heads/)"
  PRE_WORK="$(git for-each-ref --format='%(refname) %(objectname)' refs/heads/)"

  # Drive the push. HUSKY_RUN_EVALS=0 short-circuits the live-eval prompt.
  HUSKY_RUN_EVALS=0 git push -q origin feature

  # Snapshot after.
  POST_BARE="$(git --git-dir="$BARE" for-each-ref --format='%(refname) %(objectname)' refs/heads/)"
  POST_WORK="$(git for-each-ref --format='%(refname) %(objectname)' refs/heads/)"

  # The bare's feature ref DID advance (that was the push's purpose).
  # But the worktree's local refs must be byte-identical before and after.
  [ "$PRE_WORK" = "$POST_WORK" ]
  # And the bare's `main` (unrelated to the push) must be unchanged.
  # Scratch files live under $HERMETIC_ROOT so parallel bats workers can't
  # race and hermetic_teardown reclaims them with the rest of the tempdir.
  echo "$PRE_BARE" | grep 'refs/heads/main' > "$HERMETIC_ROOT/e2e-pre-main"
  echo "$POST_BARE" | grep 'refs/heads/main' > "$HERMETIC_ROOT/e2e-post-main"
  diff "$HERMETIC_ROOT/e2e-pre-main" "$HERMETIC_ROOT/e2e-post-main"
}

@test "e2e: shipped pre-push refuses to complete if a ref moves during the hook" {
  # Build a scratch worktree + bare.
  BARE="$HERMETIC_ROOT/remote.git"
  WORK="$HERMETIC_ROOT/work"
  mkdir -p "$BARE" && ( cd "$BARE" && git init -q --bare -b main )

  git init -q -b main "$WORK"
  cd "$WORK"
  git config user.email "t@t"
  git config user.name "T"
  git commit -q --allow-empty -m "seed"
  git remote add origin "$BARE"
  git push -q origin main

  git checkout -q -b feature
  git commit -q --allow-empty -m "feat"

  # Install the real hook + an evil ci-local.sh stub that mutates
  # refs/heads/main during the hook (simulating a fixture bug).
  mkdir -p "$WORK/.husky" "$WORK/scripts"
  cp "$REAL_HOOK" "$WORK/.husky/pre-push"
  cat > "$WORK/scripts/ci-local.sh" <<STUB
#!/usr/bin/env bash
cd "$WORK"
git checkout -q main
git commit -q --allow-empty -m evil
git update-ref refs/heads/main HEAD
git checkout -q feature
exit 0
STUB
  chmod +x "$WORK/scripts/ci-local.sh"

  git config core.hooksPath "$WORK/.husky"

  # Attempt the push. The ref-guard should refuse it.
  run env HUSKY_RUN_EVALS=0 git push -q origin feature
  [ "$status" -ne 0 ]

  # Assert the guard fired for the RIGHT reason — the diagnostic must
  # name the drifted ref and mention the "changed during hook" wording.
  [[ "$output" == *"refs/heads/main"* ]]
  [[ "$output" == *"changed during hook"* ]]

  # The bare's feature ref must NOT have been created (push refused).
  ! git --git-dir="$BARE" show-ref --verify refs/heads/feature 2>/dev/null
}
