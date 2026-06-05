# Screenshot / visual-regression testing

Overlay technique for `test-design-advisor`. Loaded only when the trigger matches.

**Trigger.** A behavior's correctness is **visual** — CSS layout, theming, charts/canvas, print/PDF rendering, responsive breakpoints — where the right markup can still *look* wrong and a DOM/text assertion can't catch it.

**What it is.** Render the component/page, capture an image, and diff it against an approved baseline image (approval testing for pixels). A visual change surfaces as an image diff to re-approve.

**When to use.** Design-system components, layout-critical pages, anything where appearance is the requirement. Pin a few representative states, not every page.

**Trade-offs / cost.** The most maintenance-heavy technique: baselines drift across OS/browser/font-rendering → false diffs. Mitigate with a consistent render environment (containerized/CI runner), tolerance thresholds, and masking dynamic regions. Baselines live in VCS and need review on every intended change.

**Minimal shape.** `await expect(page).toHaveScreenshot('cart-badge.png')`.

**Complements.** Component/E2E layer. Decision: **text/markup** correctness → `approval.md` (cheaper, stabler); **CSS/visual** fidelity → screenshot. Often the visual half of a Gate D / Gate C behavior (`test-layer-gates.md`). Tools: Playwright/Percy/Chromatic/Storybook test-runner, BackstopJS.
