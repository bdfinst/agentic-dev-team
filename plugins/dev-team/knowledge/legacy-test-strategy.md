# Legacy Test Strategy — Where to Test & How to Edit Safely

Reference file for the `legacy-code` and `test-design-advisor` skills. Breaking a dependency (`dependency-breaking-techniques.md`) gets code *into* a harness; this file answers the two questions that come before and after: **where do I put the tests** (so they actually sense the change I'm making) and **how do I edit without breaking anything** while I get there. This is the legacy-code counterpart of test-architecture design — placing verification where it has leverage.

Source: Michael Feathers, *Working Effectively with Legacy Code* (2005) — Ch. 11 *What Methods Should I Test?*, Ch. 12 *I Need to Make Many Changes in One Area*, Ch. 13 *Characterization Tests*, Ch. 23 *How Do I Know That I'm Not Breaking Anything?*. Language-agnostic.

Core principle: **reason about effects before you write a test.** In tangled code with no tests, knowing *what your change can affect* and *where you can observe it* is the skill everything else depends on.

---

## 1. Reason about effects

Every functional change has a chain of effects that propagates outward — through the methods that call the changed code — until it reaches a place you can observe, or stops because nothing downstream depends on it. To decide what to test, trace that chain.

For a piece of code, list **everything that, if changed, would change a result returned by any of its methods**:

- mutable state held by reference (a collection passed to a constructor and kept — callers can mutate it later),
- objects in that state that can themselves be altered or replaced,
- and *exclude* what genuinely can't change the outcome (e.g. an immutable string field — `getName` always returns the same value).

This is **effect reasoning**: a learnable skill, done without tools, that tells you which methods are worth testing for a given change.

## 2. Draw an effect sketch

An **effect sketch** is a small directed graph: bubbles for data and methods, arrows from a cause to what it affects. Sketch it for the change you intend to make. The sketch reveals:

- **Fan-out** — one piece of data affecting several methods. You can then *choose* which method to test through. Prefer the one that exercises the most behavior (the richest endpoint), so fewer tests cover more.
- **Hidden classes** — clusters of methods/fields that only talk to each other form a natural encapsulation boundary and suggest an Extract Class.
- **Simplification feedback** — removing tiny duplication often collapses endpoints (a method that starts calling another internally now gets exercised whenever the other is tested), making testing decisions easier.

> Encapsulation is a tool for understanding, not an end in itself. Several dependency-breaking techniques *reduce* encapsulation; when encapsulation and test coverage conflict, bias toward coverage — good tests let you reason about the code more directly, and you can often recover encapsulation later.

## 3. Find interception & pinch points

- **Interception point** — any point where you can detect the effect of a change. Start at the change point and trace effects outward; each observable spot is a candidate. The nearest one isn't always the best — judgment call.
- **Pinch point** — a *narrowing* in the effect sketch: a place where tests against one or two methods detect changes across many. It's a natural encapsulation boundary and the ideal place to anchor characterization tests before invasive work — write tests there, carve out an "oasis," then change freely behind it.
- **Key question** for any candidate: *"If I break this method, will I be able to sense it here?"* If yes, it's a usable interception point.
- **When no pinch point exists** (the sketch is a tangled tree): you're probably changing too much at once. Narrow to one or two change points, or test individual changes as close to the change as you can.
- **Pinch-point trap** — don't let characterization tests anchored at a high pinch point *stay* as mini-integration tests. They're scaffolding to enable change; once the area is malleable, push verification down into narrower unit tests and let the broad tests go.

## 4. Write the characterization tests

A characterization test documents what the code **actually does**, not what it *should* do. The heuristic:

1. Write tests for the area where you'll make the change — as many cases as you need to understand current behavior.
2. Then target the **specific things you're about to change** and write tests that pin them.
3. If you're extracting or moving functionality, write tests that verify those behaviors **exist and are connected** on a case-by-case basis — confirm you're exercising the code you'll move and that it's wired correctly (exercise the conversions).

Procedure for one test: call the code, let it fail, read the actual output from the failure, then set the assertion to that observed value. Repeat until the change area and its immediate dependencies are covered. (The fuller procedure lives in the `legacy-code` skill.)

---

## 5. Edit safely while getting there (Ch. 23)

Before tests are in place, these habits keep behavior intact:

| Technique | The discipline | Why it helps |
|-----------|----------------|--------------|
| **Lean on the Compiler** | Make a declaration change (rename/retype) and let compile errors enumerate every site that must change | Turns the compiler into a worklist; you can't forget a usage |
| **Preserve Signatures** | When extracting/moving code, keep parameter lists identical — copy whole signatures rather than retyping | Avoids transcription errors; lets you cut-and-paste blocks wholesale during invasive refactoring |
| **Single-Goal Editing** | Do exactly one thing at a time; when you notice another change, write it on a list and finish the current one first | "Programming is the art of doing one thing at a time" — prevents the half-finished-thrash that breaks integration |
| **Hyperaware Editing** | Know whether each keystroke changes behavior or not; pair programming and a sub-second test loop sustain this flow state | The feedback loop that makes change-without-tests survivable until tests exist |

---

## How this connects to the rest of the toolkit

- **`dependency-breaking-techniques.md`** — once effect reasoning tells you *where* to intercept, those techniques create the seam to put a test there.
- **`legacy-code` skill** — owns the Legacy Code Change Algorithm and characterization-test procedure; this file deepens its "find test points" step.
- **`test-design-advisor` skill** — uses effect/pinch reasoning to recommend the lowest-leverage-cost place to verify hard-to-test code.
- **`test-automation-principles.md`** — *Verify One Condition per Test* and Defect Localization are why you push pinch-point tests down to narrow units once the area is malleable.
