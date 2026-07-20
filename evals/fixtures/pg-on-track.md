# Plan: add-slug-helper

**Files:** `src/slug.ts`, `tests/slug.test.ts`

## Steps

- [x] Step 1 — Add a failing test for `slugify()` on unicode input (RED).
- [x] Step 2 — Implement `slugify()` to pass the test (GREEN).
- [ ] Step 3 — Add a failing test for the max-length truncation rule (RED).
- [ ] Step 4 — Implement truncation (GREEN).

## Git log (most recent first)

```
b7c6d5e  Step 2: implement slugify() (src/slug.ts, tests/slug.test.ts)
a1b2c3d  Step 1: add failing slugify() unicode test (tests/slug.test.ts)
```

## Working tree

```
(clean — nothing uncommitted)
```

## Notes

Steps are executed in order. Each completed step (`[x]`) has a matching commit
that references it by number, and the test for the behavior landed before the
implementation (RED before GREEN). Only files in the declared scope
(`src/slug.ts`, `tests/slug.test.ts`) were touched. The working tree is clean and
the remaining steps are honestly still unchecked. This is a plan on track — there
is nothing to flag.
