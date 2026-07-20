# Plan: add-rate-limiter

**Files:** `src/rate-limiter.ts`, `tests/rate-limiter.test.ts`

## Steps

- [x] Step 1 — Add `TokenBucket` class skeleton with `take()` stub.
- [x] Step 2 — Implement `take()` refill math (RED test first, then GREEN).
- [x] Step 3 — Enforce the per-key limit in the middleware.
- [ ] Step 4 — Wire the limiter into the router.

## Git log (most recent first)

```
a1b2c3d  Step 2: implement TokenBucket.take() refill (tests/rate-limiter.test.ts, src/rate-limiter.ts)
d4e5f6a  Step 1: add TokenBucket skeleton (src/rate-limiter.ts)
```

## Working tree

```
M src/rate-limiter.ts        # unstaged edits to enforce the per-key limit
```

## Notes

Step 3 is marked complete `[x]`, but there is no commit referencing Step 3 in the
git log above, and no test was added for the per-key enforcement path — the only
test file change belongs to Step 2. The enforcement edit is sitting uncommitted
in the working tree. "Marked complete" is not "demonstrated complete": Step 3's
acceptance criterion (a RED-then-GREEN test proving the per-key limit rejects the
N+1th request) has no evidence.
