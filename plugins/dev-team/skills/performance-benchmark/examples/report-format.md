# Report Format Example

Human-readable benchmark report (emitted by `/benchmark` in prose mode).

```markdown
# Performance Benchmark: <URL>

**Date**: <timestamp>
**Device**: desktop | mobile
**Runs**: 3 (median reported)

## Core Web Vitals

| Metric | Value | Budget | Baseline | Change | Status |
|--------|-------|--------|----------|--------|--------|
| LCP    | 1850ms | ≤2500ms | 1600ms | +15.6% | FAIL |
| FCP    | 920ms  | —      | 900ms  | +2.2%  | PASS |
| CLS    | 0.05   | ≤0.1   | 0.04   | +25%   | PASS |
| INP    | 120ms  | ≤200ms | 115ms  | +4.3%  | PASS |

## Resource Budget

| Resource | Size | Budget | Status |
|----------|------|--------|--------|
| Total    | 342KB | ≤500KB | PASS |
| JS       | 156KB | ≤200KB | PASS |
| CSS      | 28KB  | ≤50KB  | PASS |
| Images   | 98KB  | ≤300KB | PASS |
| Requests | 34    | ≤50    | PASS |

## Slowest Resources

| Resource | Size | Time |
|----------|------|------|
| /assets/main.js | 95KB | 450ms |
| ...

## Regressions

- **LCP**: +15.6% (1600ms → 1850ms) — investigate main.js growth

## Verdict: WARN (1 regression detected)
```
