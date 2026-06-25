# refactor-granularity — live campaign progress

_Auto-generated read-only mirror. Last update: **2026-06-25T21:50:47Z**_

Experiment RQ-F: does *how* you refactor (granularity), *whether tests are frozen* during it, and *who writes the tests* (authorship) change code changeability and test quality? 9 arms x 4 tasks x 13 trials, clear specs, build + 3-change chain.

## Overall: 33 / 468 cells complete (7.1%)

- build CORE pass: 33/33 (100%)
- build EDGE pass: 33/33 (100%)
- change-stage pass: 99/99 (100%)
- API-equivalent cost so far: **$35.68**

## Per-arm progress

| arm | granularity x protection x authorship | cells | cost |
|---|---|---:|---:|
| `tdd-refactor` | | 3/52 | $4.52 |
| `test-after-continuous` | | 4/52 | $3.27 |
| `test-after-continuous-frozen` | | 5/52 | $4.18 |
| `test-after-continuous-frozen-split` | | 3/52 | $3.97 |
| `test-after-continuous-split` | | 3/52 | $4.12 |
| `test-after-refactor` | | 4/52 | $3.38 |
| `test-after-refactor-frozen` | | 5/52 | $4.09 |
| `test-after-refactor-frozen-split` | | 3/52 | $3.92 |
| `test-after-refactor-split` | | 3/52 | $4.22 |

Final merged data and the analysis report land in `docs/experiments/` on completion.
