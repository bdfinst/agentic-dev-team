# Spike: multiplayer / concurrent-use collisions (#109 Phase 1)

> **Phase 1 (reproduce + characterize) — done.** Reproductions:
> `tests/repo/multiplayer_collision_tests.bats`.
>
> **Phase 2 — resolved (document, don't enforce).** The plugin documents the
> safe pattern — one git worktree per agent — in
> [`../../plugins/dev-team/docs/concurrent-use.md`](../../plugins/dev-team/docs/concurrent-use.md),
> rather than adding locks. The independent single-player gate bug (paths-not-
> content) is spun off to **#193**.

## Scope

"Designed for teams" implies more than one actor touching a repo. This spike asks
where the plugin's **local coordination state** breaks when N = 2. The artifacts:

| Artifact | Path | Tracked? | Writer |
|---|---|---|---|
| Review gate | `.review-passed` | gitignored (per-clone) | `/code-review`, consumed by `pre-commit-review.sh` |
| Model overrides | `.claude/model-overrides.json` | gitignored (per-clone) | `/harness-audit`, model-resolve hook |
| Plan / build progress | `plans/<name>.md` (Build Progress) | **tracked** | `/build` via Edit |

## The key distinction (it changes the verdict)

**Two separate clones / git worktrees → mostly SAFE.** `.review-passed` and
`model-overrides.json` are gitignored, so each working tree has its own. Plan
files are tracked, so two developers on two branches merge through normal git.
The standard team workflow (everyone has their own checkout) does **not** hit
these collisions. That is worth stating plainly: the "designed for teams" claim
holds for the normal case.

**Two agents sharing ONE working tree → real collisions.** Two background agents,
two terminals in the same directory, or a human + an agent in the same checkout
share one git index and one set of local state files. This is the untested,
unsafe configuration, and every collision below lives here.

## Reproduced collision modes

All four are demonstrated in `multiplayer_collision_tests.bats` against the real
`pre-commit-review.sh`.

1. **Gate overwrite → false block.** `.review-passed` is a single fixed-path file.
   Agent A passes review (writes the gate for its staged set); Agent B passes
   review for a different set and overwrites it. A now commits its own reviewed
   change and is **blocked**, because the gate holds B's hash. (Test 2.)

2. **Path-not-content binding → unreviewed commit (TOCTOU).** The gate stores a
   hash of the staged file **paths**, not their content. Review passes for
   `a.ts@v1`; the content is then changed to `v2` (same path) and committed — the
   hash still matches, so **unreviewed content commits**. This is a real weakness
   *independent of multiplayer*. (Test 3.)

3. **Content-blind to author.** Because the gate keys on paths, B's unreviewed
   edit to a path A reviewed rides A's gate straight through. (Test 4.)

4. **Shared git index.** Two writers in one tree share `.git/index`; concurrent
   `git add` interleaves their staged sets, so even a perfect gate would be
   reviewing a mixture. (Structural — noted, not separately tested.)

Adjacent, not separately reproduced: `model-overrides.json` is a single file with
last-writer-wins semantics (two `/harness-audit` writes race), and two `/build`
runs against the same plan file race on the same checkboxes via Edit.

## Recommendations (Phase 2 — needs a decision)

Two coherent directions; they are not mutually exclusive:

- **A. Document the constraint (cheap).** State that concurrent agents must use
  **separate git worktrees** (`git worktree add`), one per agent. This matches how
  the gitignored local state is already designed and needs no code — just a
  "Concurrent use" section in the docs and possibly a worktree helper.
- **B. Harden the gate (more work).** Namespace `.review-passed` by worktree/PID so
  two agents don't share one gate, **and** bind it to staged **content** (hash the
  diff, not the paths) — which also closes the path-not-content TOCTOU gap that
  exists even single-player. The model-overrides race would need a similar
  per-tree or locked-write treatment.

**Recommended:** ship **A** now (it makes the safe path explicit and is honest
about the boundary), and treat the **content-hash fix in B** as a standalone
correctness bug worth doing regardless of multiplayer — the TOCTOU gap (mode 2)
lets unreviewed content through for a *single* user today.

The choice between "enforce separate worktrees" and "make one shared tree safe"
is a product decision, which is why Phase 2 stops here for input.
