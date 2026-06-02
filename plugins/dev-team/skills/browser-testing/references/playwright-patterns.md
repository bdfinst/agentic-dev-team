# Playwright Patterns Reference

## Interaction Patterns

### Navigation

```javascript
// Basic navigation — waits for network to settle
await page.goto('http://localhost:3000', { waitUntil: 'networkidle', timeout: 30000 });

// Wait for a specific element before proceeding
await page.waitForSelector('[data-testid="app-loaded"]', { timeout: 10000 });

// Wait for navigation after a click
await Promise.all([
  page.waitForNavigation({ waitUntil: 'networkidle' }),
  page.click('a[href="/dashboard"]')
]);
```

### Form Interaction

```javascript
// Fill a text input
await page.fill('input[name="email"]', 'user@example.com');

// Fill and submit a form
await page.fill('input[name="username"]', 'testuser');
await page.fill('input[name="password"]', 'testpass');
await page.click('button[type="submit"]');

// Select from a dropdown
await page.selectOption('select#country', 'US');

// Check a checkbox
await page.check('input[type="checkbox"]#agree');

// Upload a file
await page.setInputFiles('input[type="file"]', '/path/to/file.pdf');
```

### Click and Interact

```javascript
// Click a button
await page.click('button.submit');

// Click by text content
await page.click('text=Sign In');

// Double-click
await page.dblclick('.editable-cell');

// Right-click
await page.click('.context-menu-target', { button: 'right' });

// Hover
await page.hover('.tooltip-trigger');
```

### Screenshots

```javascript
// Full page screenshot
await page.screenshot({ path: 'tmp/screenshots/full.png', fullPage: true });

// Viewport-only screenshot
await page.screenshot({ path: 'tmp/screenshots/viewport.png' });

// Element screenshot
const element = await page.locator('.hero-section');
await element.screenshot({ path: 'tmp/screenshots/hero.png' });

// Screenshot with custom clip region
await page.screenshot({
  path: 'tmp/screenshots/region.png',
  clip: { x: 0, y: 0, width: 800, height: 600 }
});
```

### Waiting Strategies

```javascript
// Wait for element to appear
await page.waitForSelector('.results-loaded');

// Wait for element to disappear (e.g., loading spinner)
await page.waitForSelector('.spinner', { state: 'hidden' });

// Wait for specific text
await page.waitForSelector('text=Results found');

// Wait for network request to complete
await page.waitForResponse(resp =>
  resp.url().includes('/api/data') && resp.status() === 200
);

// Fixed delay (use sparingly — prefer selector/response waits)
await page.waitForTimeout(2000);
```

### Extracting Information

```javascript
// Get text content
const heading = await page.textContent('h1');

// Get attribute
const href = await page.getAttribute('a.primary', 'href');

// Get input value
const value = await page.inputValue('input[name="search"]');

// Count elements
const count = await page.locator('.list-item').count();

// Get all text from a list
const items = await page.locator('.list-item').allTextContents();

// Check visibility
const isVisible = await page.locator('.error-message').isVisible();
```

## Script Template

Full template for a `/browse` action script:

```javascript
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    // Uncomment for mobile testing:
    // ...require('playwright').devices['iPhone 13']
  });
  const page = await context.newPage();

  // Capture console messages for debugging
  page.on('console', msg => {
    if (msg.type() === 'error') console.log('CONSOLE ERROR:', msg.text());
  });

  // Capture uncaught errors
  page.on('pageerror', err => console.log('PAGE ERROR:', err.message));

  try {
    await page.goto('TARGET_URL', { waitUntil: 'networkidle', timeout: 30000 });

    // --- Actions go here ---

    await page.screenshot({ path: 'SCREENSHOT_PATH', fullPage: true });
    console.log('Page title:', await page.title());
    console.log('Page URL:', page.url());
  } catch (err) {
    console.error('Error:', err.message);
    try {
      await page.screenshot({ path: 'SCREENSHOT_PATH', fullPage: true });
    } catch {}
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
```

## Error Handling

| Error | Cause | Resolution |
|-------|-------|------------|
| `TimeoutError: page.goto` | Server not running or URL wrong | Check if dev server is up; verify URL |
| `TimeoutError: waiting for selector` | Element doesn't exist or is hidden | Inspect page HTML; check selector syntax |
| `net::ERR_CONNECTION_REFUSED` | No server at the target port | Start the dev server first |
| `Protocol error: Target closed` | Page crashed or browser closed | Simplify the script; check for infinite loops |

## CAPTCHA and Authentication Handoff

When automated browsing hits a CAPTCHA, MFA, or OAuth login wall:

1. **Detect**: Page contains CAPTCHA iframe, MFA form, or redirected to OAuth provider
2. **Report**: Tell the user what was encountered and where
3. **Handoff**: Instruct the user to complete the challenge manually in their browser
4. **Resume**: After manual completion, re-run `/browse` from the authenticated state

For recurring auth needs, suggest the user:
- Set up a test account with MFA disabled
- Use session cookies via Playwright's `storageState`
- Pre-authenticate and save state: `await context.storageState({ path: 'auth.json' })`
- Load saved state: `browser.newContext({ storageState: 'auth.json' })`
