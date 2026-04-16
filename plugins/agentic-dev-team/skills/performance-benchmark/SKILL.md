---
name: performance-benchmark
description: >-
  Capture runtime performance metrics (Core Web Vitals, resource sizes, load
  times) against defined budgets. Compare to baselines, flag regressions, and
  maintain trend history. Complements the code-level performance-review agent
  with actual runtime measurement.
role: worker
user-invocable: false
---

# Performance Benchmark Skill

## Overview

This skill measures **runtime performance** — what the user actually experiences — as opposed to the `performance-review` agent which analyzes code patterns statically. It uses Playwright to load pages in a real browser, collect timing metrics via the Performance API, measure resource sizes, and compare results against baselines and budgets.

## When to Use

- Before and after performance-sensitive changes to detect regressions
- As part of a pre-PR quality gate for frontend changes
- To establish baselines for new pages or features
- To track performance trends over time across releases
- When the plan flags a step as performance-critical

## Prerequisites

Playwright with Chromium:
```bash
npx playwright install chromium
```

A running dev server (or accessible URL) for the pages being benchmarked.

## Metrics Collected

### Core Web Vitals

| Metric | API | Budget Default | What It Measures |
|--------|-----|---------------|-----------------|
| **LCP** (Largest Contentful Paint) | `PerformanceObserver('largest-contentful-paint')` | ≤ 2500ms | When the main content is visible |
| **FID** (First Input Delay) | `PerformanceObserver('first-input')` | ≤ 100ms | Responsiveness to first interaction |
| **CLS** (Cumulative Layout Shift) | `PerformanceObserver('layout-shift')` | ≤ 0.1 | Visual stability during load |
| **INP** (Interaction to Next Paint) | `PerformanceObserver('event')` | ≤ 200ms | Responsiveness throughout lifecycle |

### Navigation Timing

| Metric | API | What It Measures |
|--------|-----|-----------------|
| **TTFB** (Time to First Byte) | `performance.timing.responseStart - navigationStart` | Server response time |
| **FCP** (First Contentful Paint) | `PerformanceObserver('paint')` | When first content appears |
| **DOM Interactive** | `performance.timing.domInteractive` | When DOM is parseable |
| **Load Complete** | `performance.timing.loadEventEnd` | When page is fully loaded |

### Resource Metrics

| Metric | How Collected | Budget Default |
|--------|--------------|---------------|
| **Total transfer size** | `performance.getEntriesByType('resource')` sum | ≤ 500KB |
| **JS bundle size** | Filter resources by `.js` extension | ≤ 200KB |
| **CSS bundle size** | Filter resources by `.css` extension | ≤ 50KB |
| **Image payload** | Filter resources by image MIME types | ≤ 300KB |
| **Request count** | Resource entry count | ≤ 50 |
| **Largest resource** | Max single transfer size | ≤ 150KB |

## Collection Script Template

The benchmark runs a single Node.js script via Playwright that:

1. Launches headless Chromium with consistent viewport (1280×720) and CPU throttling (4x slowdown for mobile simulation, or 1x for desktop)
2. Navigates to the target URL with `waitUntil: 'networkidle'`
3. Injects a Performance Observer to capture Web Vitals
4. Waits for metrics to stabilize (2s after load)
5. Collects all `performance.getEntriesByType('resource')` entries
6. Returns structured JSON

See `references/benchmark-script.md` for the full script template.

### Measurement Reliability

To reduce variance:
- Run each page **3 times** and take the **median** for each metric
- Use `--disable-gpu` and `--disable-extensions` flags
- Clear browser cache between runs (`context.clearCookies()`, fresh context per run)
- Use consistent network conditions (no throttling by default; `--3g` flag for mobile simulation)

## Modes

### Baseline Mode (`--baseline`)

Captures current metrics and saves them as the baseline for future comparisons:

```
benchmarks/<slug>/baseline.json
```

Baseline files are committed to the repo so the team shares a common reference point.

### Compare Mode (default)

Runs the benchmark and compares against the saved baseline:

- **Regression**: Metric worsened by > 10% → `fail`
- **Degradation**: Metric worsened by 5-10% → `warn`
- **Improvement**: Metric improved by > 10% → noted in report
- **Stable**: Within ±5% → `pass`

### Budget Mode (`--budget`)

Checks against absolute performance budgets defined in a `performance-budget.json` file at the project root:

```json
{
  "budgets": [
    {
      "path": "/",
      "metrics": {
        "LCP": 2500,
        "CLS": 0.1,
        "totalTransferSize": 500000,
        "jsSize": 200000
      }
    },
    {
      "path": "/dashboard",
      "metrics": {
        "LCP": 3000,
        "totalTransferSize": 800000
      }
    }
  ]
}
```

If no budget file exists, use the defaults from the tables above.

### Trend Mode (`--trend`)

Reads historical benchmark results from `benchmarks/<slug>/history.jsonl` and produces a trend summary showing how metrics have changed over the last N runs.

## Output Format

```json
{
  "url": "http://localhost:3000/dashboard",
  "timestamp": "2026-04-10T14:30:00Z",
  "runs": 3,
  "device": "desktop",
  "metrics": {
    "LCP": {"median": 1850, "p95": 2100, "unit": "ms"},
    "FCP": {"median": 920, "p95": 1050, "unit": "ms"},
    "CLS": {"median": 0.05, "p95": 0.08, "unit": "score"},
    "INP": {"median": 120, "p95": 180, "unit": "ms"},
    "TTFB": {"median": 210, "p95": 280, "unit": "ms"},
    "loadComplete": {"median": 2400, "p95": 2800, "unit": "ms"}
  },
  "resources": {
    "totalTransferSize": 342000,
    "jsSize": 156000,
    "cssSize": 28000,
    "imageSize": 98000,
    "requestCount": 34,
    "largestResource": {"url": "/assets/main.js", "size": 95000}
  },
  "comparison": {
    "baseline": "2026-04-08T10:00:00Z",
    "regressions": [
      {"metric": "LCP", "baseline": 1600, "current": 1850, "change": "+15.6%", "severity": "fail"}
    ],
    "improvements": [],
    "stable": ["FCP", "CLS", "INP", "TTFB"]
  },
  "budget": {
    "status": "pass",
    "violations": []
  },
  "status": "pass|warn|fail"
}
```

## Report Format

When writing a human-readable report (for `/benchmark` command output):

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

## Integration Points

- **QA Engineer**: Invokes this skill for performance and load testing
- **Ops Engineer**: Uses baselines for SLI/SLO definition
- **`/build` command**: Can be triggered after performance-critical steps (when step metadata includes `performance-sensitive: true`)
- **`/code-review`**: The `performance-review` agent flags code patterns; this skill validates the runtime impact
- **Browser Testing skill**: Shares Playwright infrastructure and patterns

## File Storage

```
benchmarks/
├── <page-slug>/
│   ├── baseline.json        # Committed — shared baseline
│   └── history.jsonl        # Committed — trend data (append-only)
└── performance-budget.json  # Committed — budget definitions
```

Page slug is derived from the URL path: `/dashboard` → `dashboard`, `/` → `index`.
