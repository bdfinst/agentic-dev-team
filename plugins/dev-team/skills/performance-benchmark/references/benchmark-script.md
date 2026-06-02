# Playwright Benchmark Script Template

## Full Collection Script

This script template collects all performance metrics for a single page. The `/benchmark` command generates and runs a version of this script for each target URL.

```javascript
const { chromium } = require('playwright');

async function benchmark(url, options = {}) {
  const { runs = 3, device = 'desktop', throttle = false } = options;
  const results = [];

  for (let i = 0; i < runs; i++) {
    const browser = await chromium.launch({
      args: ['--disable-gpu', '--disable-extensions', '--no-sandbox']
    });

    const context = await browser.newContext({
      viewport: device === 'mobile'
        ? { width: 375, height: 812 }
        : { width: 1280, height: 720 },
      userAgent: device === 'mobile'
        ? 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) Mobile'
        : undefined
    });

    if (throttle) {
      const cdp = await context.newCDPSession(await context.newPage());
      await cdp.send('Network.emulateNetworkConditions', {
        offline: false,
        downloadThroughput: 1.5 * 1024 * 1024 / 8, // 1.5 Mbps
        uploadThroughput: 750 * 1024 / 8,            // 750 Kbps
        latency: 40
      });
      await cdp.send('Emulation.setCPUThrottlingRate', { rate: 4 });
    }

    const page = await context.newPage();

    // Inject Performance Observer before navigation
    await page.addInitScript(() => {
      window.__perfMetrics = {};
      new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          if (entry.entryType === 'largest-contentful-paint') {
            window.__perfMetrics.LCP = entry.startTime;
          }
          if (entry.entryType === 'paint' && entry.name === 'first-contentful-paint') {
            window.__perfMetrics.FCP = entry.startTime;
          }
          if (entry.entryType === 'layout-shift' && !entry.hadRecentInput) {
            window.__perfMetrics.CLS = (window.__perfMetrics.CLS || 0) + entry.value;
          }
        }
      }).observe({ type: 'largest-contentful-paint', buffered: true });

      new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          if (entry.name === 'first-contentful-paint') {
            window.__perfMetrics.FCP = entry.startTime;
          }
        }
      }).observe({ type: 'paint', buffered: true });

      new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          if (!entry.hadRecentInput) {
            window.__perfMetrics.CLS = (window.__perfMetrics.CLS || 0) + entry.value;
          }
        }
      }).observe({ type: 'layout-shift', buffered: true });
    });

    // Navigate and wait for network idle
    await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });

    // Wait for metrics to stabilize
    await page.waitForTimeout(2000);

    // Collect all metrics
    const metrics = await page.evaluate(() => {
      const timing = performance.timing;
      const resources = performance.getEntriesByType('resource');

      const jsResources = resources.filter(r => r.name.endsWith('.js') || r.initiatorType === 'script');
      const cssResources = resources.filter(r => r.name.endsWith('.css') || r.initiatorType === 'link');
      const imgResources = resources.filter(r =>
        r.initiatorType === 'img' || /\.(png|jpg|jpeg|gif|svg|webp|avif)/.test(r.name)
      );

      return {
        vitals: {
          LCP: window.__perfMetrics.LCP || null,
          FCP: window.__perfMetrics.FCP || null,
          CLS: window.__perfMetrics.CLS || 0,
          TTFB: timing.responseStart - timing.navigationStart,
          domInteractive: timing.domInteractive - timing.navigationStart,
          loadComplete: timing.loadEventEnd - timing.navigationStart
        },
        resources: {
          totalTransferSize: resources.reduce((sum, r) => sum + (r.transferSize || 0), 0),
          jsSize: jsResources.reduce((sum, r) => sum + (r.transferSize || 0), 0),
          cssSize: cssResources.reduce((sum, r) => sum + (r.transferSize || 0), 0),
          imageSize: imgResources.reduce((sum, r) => sum + (r.transferSize || 0), 0),
          requestCount: resources.length,
          largestResource: resources.reduce((max, r) =>
            (r.transferSize || 0) > (max.size || 0)
              ? { url: r.name, size: r.transferSize }
              : max,
            { url: '', size: 0 }
          )
        }
      };
    });

    results.push(metrics);
    await browser.close();
  }

  return results;
}

// Compute median across runs
function median(values) {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function p95(values) {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.ceil(sorted.length * 0.95) - 1];
}

module.exports = { benchmark, median, p95 };
```

## Usage in /benchmark Command

The command generates a runner script that:

1. Imports the template functions
2. Calls `benchmark(url, options)` for each target URL
3. Computes median/p95 across runs
4. Compares against baseline (if exists)
5. Checks against budget (if exists)
6. Outputs structured JSON

## CPU Throttling Profiles

| Profile | CPU Rate | Network | Use Case |
|---------|----------|---------|----------|
| Desktop (default) | 1x | No throttle | Standard desktop experience |
| Mobile (`--mobile`) | 4x | 1.5 Mbps / 40ms | Mobile device simulation |
| Slow 3G (`--3g`) | 4x | 400 Kbps / 400ms | Worst-case mobile |

## Console Error Capture

The script also captures console errors during page load — a console error during benchmark indicates a broken page, not just a slow one:

```javascript
const consoleErrors = [];
page.on('console', msg => {
  if (msg.type() === 'error') consoleErrors.push(msg.text());
});
```

Console errors are included in the output as `"errors": [...]` for the report.
