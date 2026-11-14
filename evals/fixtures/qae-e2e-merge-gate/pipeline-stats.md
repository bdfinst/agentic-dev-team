# PR pipeline, last 30 days

- Median PR pipeline time: 38 min (unit tests: 40 s; compose up: 9 min; Playwright: 26 min)
- PRs re-run at least once because of a red E2E job: 41%
- E2E failures later judged "not a real bug": 87%
- Typical cause noted in retros: tax-service slow to start; shared staging DB
  row `sku-991` restocked by another team's test run
- Team has stopped reading E2E failures and just clicks "re-run"
- The tax calculation lives in `pricing/tax.ts` and has no unit or component tests
