# refactor-granularity — live campaign progress

_Auto-generated read-only mirror. Last update: **2026-06-25T21:50:07Z**_

Experiment RQ-F: does *how* you refactor (granularity), *whether tests are frozen* during it, and *who writes the tests* (authorship) change code changeability and test quality? 9 arms x 4 tasks x 13 trials, clear specs, build + 3-change chain.

## Overall: 28 / 468 cells complete (6.0%)

- build CORE pass: 28/28 (100%)
- build EDGE pass: 28/28 (100%)
- change-stage pass: 84/84 (100%)
- API-equivalent cost so far: **$29.23**

## Per-arm progress

| arm | granularity x protection x authorship | cells | cost |
|---|---|---:|---:|
| `tdd-refactor` | | 2/52 | $3.04 |
| `test-after-continuous` | | 4/52 | $3.27 |
| `test-after-continuous-frozen` | | 4/52 | $3.30 |
| `test-after-continuous-frozen-split` | | 3/52 | $3.97 |
| `test-after-continuous-split` | | 2/52 | $2.85 |
| `test-after-refactor` | | 4/52 | $3.38 |
| `test-after-refactor-frozen` | | 5/52 | $4.09 |
| `test-after-refactor-frozen-split` | | 2/52 | $2.58 |
| `test-after-refactor-split` | | 2/52 | $2.73 |

Final merged data and the analysis report land in `docs/experiments/` on completion.
