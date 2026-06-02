---
name: browser-testing
description: >-
  Patterns and templates for browser-based QA using Playwright. Covers
  navigation, form interaction, screenshot capture, visual verification,
  and CAPTCHA/auth handoff.
role: worker
user-invocable: false
---

# Browser Testing Skill

## Overview

This skill provides reusable patterns for browser-based testing and visual verification using Playwright. Agents load this skill when they need to interact with a running application through a real browser.

## Prerequisites

Playwright must be installed with at least the Chromium browser:
```bash
npx playwright install chromium
```

## Playwright Patterns

| Category | Description |
|----------|-------------|
| Navigation | `goto`, `waitForSelector`, `waitForNavigation` with network-idle |
| Form Interaction | `fill`, `selectOption`, `check`, `setInputFiles`, submit |
| Click Actions | Click by selector/text, double-click, right-click, hover |
| Screenshots | Full page, viewport, element, and clipped region captures |
| Waiting Strategies | Selector appear/disappear, text match, network response |
| Data Extraction | `textContent`, `getAttribute`, `inputValue`, `count`, `isVisible` |
| Script Template | Full `/browse` boilerplate with error capture and console logging |
| Error Handling | Common timeout, connection, and protocol errors with resolutions |
| CAPTCHA/Auth Handoff | Detect walls, report to user, resume from `storageState` |

See `references/playwright-patterns.md` for full code examples, the script template, and the error handling table.

## Visual Verification Guidelines

When interpreting screenshots, describe:

1. **Layout**: Is the page structure correct? Any overlapping elements, broken grids, or overflow?
2. **Content**: Is the expected text/data visible? Any placeholder text or missing images?
3. **State**: Are interactive elements in the right state? (buttons enabled/disabled, forms populated, etc.)
4. **Responsiveness**: At the given viewport, does the layout adapt correctly?
5. **Errors**: Any visible error messages, 404 pages, or console errors captured?

Compare observations against acceptance criteria when available. Flag discrepancies as findings.
