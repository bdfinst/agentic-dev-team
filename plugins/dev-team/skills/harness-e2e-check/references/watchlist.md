# Regression Watchlist

This is the living record of gaps `/harness-e2e-check` has found in the
harness itself. It exists so a run doesn't just re-confirm the same 8
behaviors forever — it also tracks whether previously-found gaps got fixed,
and gives every future run a place to add newly-found ones.

**On every run:**

1. For each `open` row below, re-check whether the gap is still present
   (each row says how). If it's fixed, flip its status to `closed (verified
   <date>, <run's issue/PR ref>)` and, if the row says "promote to a hard
   test on fix," do that promotion in the same run (see the row for where).
2. For anything newly found that isn't already a row here, file a follow-up
   issue in this repo (matching the pattern of #913-#917) and add a new row.
3. Never silently patch a finding into this file without also filing the
   issue — the file is a tracker, not a substitute for one.

## Open

| # | Found in | Description | How to re-check | On fix |
| --- | ---------- | -------------- | ------------------ | -------- |
| [#914](https://github.com/bdfinst/agentic-dev-team/issues/914) | Step 4 (refactor-freeze) | Bash guard's first-match-wins pattern order can miss a real `mv`/`cp` target when an earlier `redirect` match wins on a harmless part of the same compound command. | `tests/hooks/test_refactor_test_bash_guard.py::test_compound_command_dangerous_target_after_earlier_redirect_match` is marked `xfail(strict=True)` — it will flip to a hard failure (XPASS) the moment this is fixed. | Remove the `xfail` marker from that test — `strict=True` means CI itself will demand this the moment the fix lands. |
| [#915](https://github.com/bdfinst/agentic-dev-team/issues/915) | Step 3 (`/build` smoke test) | `/build` SKILL.md contradicts itself on when a slice's parent checkbox may flip to `[x]` (sub-step 5 says "immediately"; sub-steps 4.9/4.10 say "not until `/verify`+`Invariants` pass"). | Run `/harness-e2e-check` Step 3 with the `make_toy_repo.py` fixture (Slice 2 declares `Invariants`) and watch whether the parent checkbox flips before or after the invariants gate. | Re-run Step 3 once and confirm the contradiction is gone (no manual self-correction needed); no automatable pytest exists for SKILL.md prose — this stays a live-run check. |
| [#916](https://github.com/bdfinst/agentic-dev-team/issues/916) | Step 3 (`/build` smoke test) | Step 7's branch-base fallback chain (`git merge-base HEAD origin/HEAD` → `origin/main` → `main` → `master` → `develop`) has no path for a no-remote/single-branch repo — silently reports "0 changed test files" instead of flagging the resolution failure. | `make_toy_repo.py`'s fixture never creates/switches branches by design (bait for this exact gap) — re-run Step 3's Farley Score sub-step and check whether `<base>` resolves to `HEAD` itself. | Same as #915 — live-run check, no unit test (Step 7 has no backing script, it's SKILL.md prose). |
| [#917](https://github.com/bdfinst/agentic-dev-team/issues/917) | Step 3 (`/build` smoke test) | mypy diagnostic lane fails outright on a plain `src/`-layout project without `__init__.py` (`Source file found twice under different module names`). | `make_toy_repo.py`'s fixture is `src/`-layout with no `__init__.py` by design (bait for this exact gap) — re-run Step 3 and check whether the mypy lane runs or degrades. | Once fixed, re-run Step 3 and confirm mypy actually produces output for this fixture instead of degrading; consider adding a dedicated unit test in whichever module implements the fix. |

## Closed

| # | Found in | Description | Closed |
|---|----------|--------------|--------|
| [#913](https://github.com/bdfinst/agentic-dev-team/issues/913) | Step 4 (refactor-freeze) | `is_test_file()` had no Python (`test_*.py`/`*_test.py`) detection — Python test files got zero freeze protection. | closed (verified 2026-07-06, fix/913-python-test-file-detection) — added a `_PYTHON_NAME_RE` branch to `hooks/lib/test_file_classify.py::is_test_file`, a Python row in `knowledge/test-file-indicators.md`, and unit tests in `tests/hooks/test_test_file_classify.py`. |
