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

Measures **runtime performance** (what the user experiences) — complements the static `performance-review` agent. Uses Playwright + Chromium to load pages, collect timing via the Performance API, measure resource sizes, and compare against baselines and budgets.

## Prerequisites

Installed by `/project-init` for frontend projects, or install manually:

```bash
npx playwright install chromium
```

A running dev server (or accessible URL) for the pages being benchmarked.

## Metrics collected

### Core Web Vitals

| Metric | API | Budget Default | Measures |
|---|---|---|---|
| **LCP** (Largest Contentful Paint) | `PerformanceObserver('largest-contentful-paint')` | ≤ 2500ms | When main content is visible |
| **FID** (First Input Delay) | `PerformanceObserver('first-input')` | ≤ 100ms | First-interaction responsiveness |
| **CLS** (Cumulative Layout Shift) | `PerformanceObserver('layout-shift')` | ≤ 0.1 | Visual stability during load |
| **INP** (Interaction to Next Paint) | `PerformanceObserver('event')` | ≤ 200ms | Responsiveness across lifecycle |

### Navigation Timing

| Metric | API | Measures |
|---|---|---|
| **TTFB** | `performance.timing.responseStart - navigationStart` | Server response time |
| **FCP** (First Contentful Paint) | `PerformanceObserver('paint')` | When first content appears |
| **DOM Interactive** | `performance.timing.domInteractive` | When DOM is parseable |
| **Load Complete** | `performance.timing.loadEventEnd` | Page fully loaded |

### Resource metrics

| Metric | Collection | Budget Default |
|---|---|---|
| **Total transfer size** | `performance.getEntriesByType('resource')` sum | ≤ 500KB |
| **JS bundle size** | Resources with `.js` extension | ≤ 200KB |
| **CSS bundle size** | Resources with `.css` extension | ≤ 50KB |
| **Image payload** | Resources with image MIME types | ≤ 300KB |
| **Request count** | Resource entry count | ≤ 50 |
| **Largest resource** | Max single transfer size | ≤ 150KB |

## Collection procedure

Run a Playwright script that:

1. Launches headless Chromium with consistent viewport (1280×720) and CPU throttling (4x for mobile, 1x for desktop)
2. Navigates with `waitUntil: 'networkidle'`
3. Injects a Performance Observer for Web Vitals
4. Waits 2s after load for metrics to stabilize
5. Collects all `performance.getEntriesByType('resource')` entries
6. Returns structured JSON

Full script template: `references/benchmark-script.md`.

**Reliability**: run each page **3 times**, take the **median**. Use `--disable-gpu` and `--disable-extensions`. Clear cookies and use a fresh context per run. No network throttling by default; `--3g` flag for mobile simulation.

## Modes

### Baseline (`--baseline`)

Capture current metrics and save as the baseline:

```
benchmarks/<slug>/baseline.json
```

Commit baselines so the team shares a reference point.

### Compare (default)

Run and compare against the saved baseline:

| Change | Status |
|---|---|
| Metric worsened > 10% | `fail` (regression) |
| Metric worsened 5–10% | `warn` (degradation) |
| Metric improved > 10% | noted in report |
| Within ±5% | `pass` (stable) |

### Budget (`--budget`)

Check absolute budgets from `performance-budget.json` at the project root:

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
      "metrics": { "LCP": 3000, "totalTransferSize": 800000 }
    }
  ]
}
```

If no budget file, fall back to defaults above.

### Trend (`--trend`)

Read `benchmarks/<slug>/history.jsonl` and produce a trend summary across the last N runs.

## Output format (JSON)

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
  "budget": { "status": "pass", "violations": [] },
  "status": "pass|warn|fail"
}
```

Human-readable report template: [`examples/report-format.md`](examples/report-format.md).

## File storage

```
benchmarks/
├── <page-slug>/
│   ├── baseline.json        # Committed — shared baseline
│   └── history.jsonl        # Committed — trend data (append-only)
└── performance-budget.json  # Committed — budget definitions
```

Page slug derived from the URL path: `/dashboard` → `dashboard`, `/` → `index`.
