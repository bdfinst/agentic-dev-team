---
name: benchmark
description: >-
  Capture runtime performance metrics (Core Web Vitals, resource sizes, load
  times) for web pages. Compare against baselines and performance budgets.
  Use when the user says "benchmark", "check performance", "page speed",
  "web vitals", "performance regression", or "how fast is this page".
argument-hint: "<url> [--baseline] [--budget] [--trend] [--mobile] [--3g] [--runs <n>]"
user-invocable: true
allowed-tools: Read, Write, Glob, Grep, Bash(npx playwright *), Bash(node *), Bash(mkdir *), Bash(date *), Bash(cat *)
---

# Benchmark

Role: worker. This command measures runtime performance of web pages using Playwright.

You have been invoked with the `/benchmark` command.

## Parse Arguments

Arguments: $ARGUMENTS

- Positional: URL to benchmark (required). Can be a full URL or a path (prefixed with the dev server URL).
- `--baseline`: Capture current metrics as the new baseline (overwrites existing)
- `--budget`: Check against performance budgets in `performance-budget.json`
- `--trend`: Show performance trends from historical data
- `--mobile`: Simulate mobile device (375×812 viewport, 4x CPU throttle)
- `--3g`: Simulate slow 3G network (400 Kbps, 400ms latency, 4x CPU)
- `--runs <n>`: Number of measurement runs (default: 3, median reported)

If no URL is provided, look for a `performance-budget.json` file and benchmark all paths listed there.

## Prerequisites Check

1. Verify Playwright is installed: `npx playwright --version`. If not installed, tell the user: "Playwright is required. Run `npx playwright install chromium` first."
2. If the URL is localhost, verify the dev server is running by attempting a fetch. If not running, tell the user: "Dev server doesn't appear to be running at <url>. Start it first."

## Steps

### 1. Load the skill

Read `skills/performance-benchmark/SKILL.md` for the full metric definitions, output format, and collection methodology. Read `skills/performance-benchmark/references/benchmark-script.md` for the Playwright script template.

### 2. Generate and run the benchmark script

Generate a Node.js script based on the template that:
- Navigates to the target URL
- Collects Core Web Vitals (LCP, FCP, CLS, INP) via Performance Observer
- Collects Navigation Timing (TTFB, DOM Interactive, Load Complete)
- Collects Resource metrics (transfer sizes by type, request count, largest resource)
- Captures console errors during load
- Runs the specified number of times (default 3)
- Computes median and p95 for each metric

Run the script with `node` and capture the JSON output.

### 3. Compare against baseline (unless --baseline)

If `--baseline` is set:
- Save the metrics to `benchmarks/<page-slug>/baseline.json`
- Create the directory if needed
- Report: "Baseline saved for <url>"

If `--baseline` is NOT set:
- Read `benchmarks/<page-slug>/baseline.json` if it exists
- Compare each metric: regression (>10% worse) → `fail`, degradation (5-10%) → `warn`, stable (±5%) → `pass`, improvement (>10% better) → noted
- If no baseline exists, report metrics without comparison and suggest: "No baseline found. Run `/benchmark <url> --baseline` to establish one."

### 4. Check performance budgets (if --budget or budget file exists)

Read `performance-budget.json` from the project root. Match the benchmarked URL path against budget entries. Flag any metric that exceeds its budget.

### 5. Append to trend history

Append the current metrics to `benchmarks/<page-slug>/history.jsonl` (one JSON object per line, with timestamp).

If `--trend` is set, read the history file and produce a trend summary showing metric changes over the last 10 entries.

### 6. Generate report

Write a markdown report to `benchmarks/<page-slug>/report.md` using the report format from the skill file.

Display in chat:
- Core Web Vitals table with pass/warn/fail status
- Resource budget table
- Any regressions with severity
- Overall verdict

## Integration

- Complements the `performance-review` agent (static code analysis) with runtime measurement
- Uses Playwright infrastructure shared with `/browse` and the Browser Testing skill
- QA Engineer invokes this for performance validation
- DevOps/SRE Engineer uses baselines for SLI/SLO definition
- Can be run as part of `/build` for performance-critical plan steps
