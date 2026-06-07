#!/usr/bin/env bash
# review-gate-hash.sh — the single source of truth for the .review-passed gate
# hash (#193).
#
# The gate binds to the STAGED CONTENT (the cached patch), not just the staged
# file PATHS. Hashing paths alone let a reviewed file's content change and still
# commit unreviewed (a TOCTOU gap, reproduced in
# tests/repo/multiplayer_collision_tests.bats). Hashing `git diff --cached`
# captures both which files are staged AND their staged content — so any edit
# after review invalidates the gate and forces a re-review.
#
# Both the writer (`/code-review` step 9) and the reader (pre-commit-review.sh)
# MUST compute the hash identically, so both call this one function. The patch
# already embeds blob SHAs (the `index <old>..<new>` lines), so the output is
# deterministic for a given staged state.
#
# Usage:
#   source review-gate-hash.sh && h=$(review_gate_hash)   # from another script
#   bash review-gate-hash.sh > .review-passed             # run directly to write

review_gate_hash() {
  git diff --cached --no-color 2>/dev/null \
    | { shasum -a 256 2>/dev/null || sha256sum 2>/dev/null; } \
    | cut -d' ' -f1
}

# When executed directly (not sourced), print the hash.
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
  review_gate_hash
fi
