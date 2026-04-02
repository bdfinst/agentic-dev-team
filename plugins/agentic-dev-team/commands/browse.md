---
name: browse
description: >-
  Launch a browser to navigate URLs, take screenshots, click elements, and fill
  forms. Use for visual verification, e2e testing, and interactive debugging.
argument-hint: "<url> [--screenshot <path>] [--click <selector>] [--fill <selector> <value>] [--wait <ms>] [--viewport <WxH>]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash(npx playwright *), Bash(node *)
---

# Browse

Role: worker. This command provides browser-based interaction for visual verification and e2e testing.

You have been invoked with the `/browse` command.

## Parse Arguments

Arguments: $ARGUMENTS

- Positional: `<url>` (required) — the URL to navigate to
- `--screenshot <path>`: Save screenshot to this path (default: `tmp/screenshots/<timestamp>.png`)
- `--click <selector>`: CSS selector to click after page load
- `--fill <selector> <value>`: CSS selector and value for form input (can be repeated)
- `--wait <ms>`: Wait this many milliseconds after page load (default: 1000)
- `--viewport <WxH>`: Viewport dimensions (default: `1280x720`)

## Steps

### 1. Check Playwright availability

Run:
```bash
npx playwright --version 2>/dev/null
```

If Playwright is not available, ask the user:
> Playwright is required for browser interaction. Install it now?
> ```
> npx playwright install chromium
> ```

Do not proceed until Playwright is confirmed available.

### 2. Ensure screenshot directory exists

```bash
mkdir -p tmp/screenshots
```

### 3. Execute browser action

Write a temporary Node.js script and execute it with `node`. Use Playwright's API directly for reliable, scriptable interaction.

**Template** (adapt based on parsed arguments):

```javascript
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: VIEWPORT_WIDTH, height: VIEWPORT_HEIGHT }
  });
  const page = await context.newPage();

  try {
    await page.goto('URL', { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(WAIT_MS);

    // -- Click actions (if --click provided) --
    // await page.click('SELECTOR');

    // -- Fill actions (if --fill provided) --
    // await page.fill('SELECTOR', 'VALUE');

    // -- Screenshot --
    await page.screenshot({ path: 'SCREENSHOT_PATH', fullPage: true });

    console.log('Screenshot saved to: SCREENSHOT_PATH');
    console.log('Page title:', await page.title());
    console.log('Page URL:', page.url());
  } catch (err) {
    console.error('Browser error:', err.message);
    // Take a screenshot of the error state if possible
    try {
      await page.screenshot({ path: 'SCREENSHOT_PATH', fullPage: true });
      console.log('Error-state screenshot saved to: SCREENSHOT_PATH');
    } catch {}
  } finally {
    await browser.close();
  }
})();
```

Write the script to a temp file, execute it, then clean up:
```bash
node /tmp/browse-action.js && rm /tmp/browse-action.js
```

### 4. Read and describe the screenshot

Use the Read tool to view the screenshot image. Claude's multimodal capabilities will interpret the visual content.

Describe what you see:
- Page layout and structure
- Key visible content (headings, text, images)
- State of interactive elements (forms, buttons, error messages)
- Anything that looks broken, misaligned, or unexpected

### 5. Report results

Provide a summary:
```
## Browse Results
- **URL**: <final URL after any redirects>
- **Title**: <page title>
- **Viewport**: <width>x<height>
- **Screenshot**: <path to screenshot>
- **Actions performed**: <list of click/fill actions, or "none">
- **Observations**: <what you see in the screenshot>
```

If the user's goal appears to be testing or verification, note any issues found and suggest next steps.

## Error Handling

- **Navigation timeout**: Report the URL that failed and suggest checking if the server is running
- **Element not found**: Report the selector that failed and suggest inspecting the page structure
- **CAPTCHA or auth wall**: Report that manual intervention is needed — instruct the user to complete the challenge in their browser, then re-run `/browse` to continue
- **Playwright not installed**: Guide the user through `npx playwright install chromium`

## Automated Smoke Test Mode

When invoked non-interactively by the inline review pipeline (Stage 3 browser verification), the caller provides:

- **URL**: The dev server URL for the page under test
- **Selectors to verify**: CSS selectors that should be visible after the change (e.g., `[data-testid="user-list"]`, `.dashboard-header`)
- **Expected state**: Brief description of what the page should look like

In this mode:

1. Navigate to the URL with a 30-second timeout
2. Wait for network idle
3. For each selector, verify it exists and is visible
4. Take a full-page screenshot as verification evidence
5. Return a structured result:
   ```
   - url: <final URL>
   - selectors_found: [list of selectors that were visible]
   - selectors_missing: [list of selectors that were not found or not visible]
   - screenshot: <path to screenshot>
   - status: pass | fail
   - issues: [description of any rendering problems observed]
   ```

If the connection times out or refuses (dev server not running), return:
```
- status: skipped
- reason: "Dev server not reachable at <URL>"
```

This result feeds into the review loop — `fail` triggers correction iterations (max 2), `skipped` is logged as a warning and does not block the build.

## Multi-Step Interactions

For complex flows (login → navigate → fill form → submit), chain actions in a single script rather than multiple `/browse` invocations. Build the full action sequence in the Node.js script.

If the user describes a multi-step flow conversationally, translate it into the appropriate Playwright action sequence.
