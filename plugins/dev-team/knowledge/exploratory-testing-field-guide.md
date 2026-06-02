# Exploratory Testing Field Guide

Source: *Explore It!* by Elisabeth Hendrickson (Pragmatic Programmers, 2013).
Reference for `skills/exploratory-testing/SKILL.md`. Protocol lives in the skill; frameworks live here.

---

## 1. Charter Quality (§2.3–2.4)

**Format**: `Explore [target] with [approach] to discover [concern]`

**Anti-patterns**:

| Anti-pattern | Example |
|-------------|---------|
| Too specific — becomes a test case | "Explore editing with value O'Malley to check apostrophe handling" |
| Too broad — infinite scope, never done | "Explore system security with all hacking tools to find any holes" |
| Missing "with" — no approach specified | "Explore /payments to find bugs" |
| Missing "to discover" — no risk hypothesis | "Explore auth with boundary inputs" |

Fix for too-broad charters: split into multiple focused charters, one area or concern each.

**Charter generation sources**:

| Source | Signal | Example |
|--------|--------|---------|
| Requirements discussions | Ambiguity, "I'll have to think about that" | "Explore username editing with invalid characters to discover if constraints are enforced" |
| Implicit expectations | Security model, performance, reliability — never stated | "Explore the new feature with high-volume inputs to discover performance regressions" |
| Stakeholder questions | Risk questions raised during design | "Explore billing with sequence variations to discover double-billing conditions" |
| Existing artifacts | Code comments, bug database, support logs | "Explore the payment flow with bug #4231 edge cases to discover if the fix holds" |
| Mid-session discoveries | Off-charter temptations — each is a new charter | "Explore /api/orders with the same error-format probe to discover cross-endpoint inconsistency" |

---

## 2. Exploration Without a GUI (Ch. 10)

All techniques apply to APIs, CLIs, batch programs, libraries — any interface.

**Variable identification (pre-probe)**:

| Dimension | What to vary |
|-----------|-------------|
| Parameters | Count, names, order |
| Values | Boundary, null/empty/zero, special characters |
| Data types | String, number, boolean, null, object, array, mixed |
| Sizes | Short, typical, very long, maximum |
| Character sets | ASCII, Unicode, accented, CJK, nonprinting, whitespace variants |
| Combinations | Valid × invalid, valid × boundary, multiple invalid at once |

**Type variation probes** (extends Goldilocks):

| Input | Finds |
|-------|-------|
| `null` | Missing null checks, NPE |
| `""` (empty string) | Empty-string handling distinct from null |
| `0` / `[]` / `{}` | Zero-value edge cases |
| Wrong type | Type coercion bugs, implicit conversion surprises |
| Very large value / long string | Performance degradation (O(n²)), buffer issues, truncation → triggers Telemetry Deepening |
| `Infinity`, `NaN`, `-0` | Numeric edge cases in calculations |
| Unicode / accented / CJK | Encoding bugs, collation issues |
| Nonprinting / whitespace variants | Trim/strip inconsistencies |

---

## 3. State Modeling (Ch. 8)

**State detection — Jorgensen's 3 questions** (ask after each probe):

1. Are there things I could do now that I could not do before?
2. Are there things I cannot do now that I could do before?
3. Do my actions have different results now than before?

**"While" language cue**: any sentence using *while* in requirements or comments identifies a state.
Examples: "while the account is suspended", "while the system is importing data".

**Event taxonomy**:

| Type | Description | Why it matters |
|------|-------------|----------------|
| User action | Explicit input triggering a transition | Most obvious; usually already tested |
| System-generated | Background activity completing (auth, data load, job) | Creates interstitial states — narrow windows of vulnerability |
| Time-based | Timeouts, expiry, scheduled operations | Hard to reproduce; race-condition source |

**State model strategies**:

| Strategy | Rule |
|----------|------|
| Narrow your focus | One target; if you can't name it simply, split it |
| Identify a perspective | User vs. system perspective → different states |
| Dial abstraction | Small target → map substates; large target → lump into one named state |

**Transition probe set** (Slice 2):

- Valid forward transitions
- Reverse transitions
- Skipped transitions (A → C, bypassing B)
- Invalid transitions (action valid only in another state)
- Time-based transitions (trigger timeout; probe during interstitial)

---

## 4. Iterative Probe-Learn-Probe

1. Identify variables — what can vary in this target?
2. Start obvious — confirm happy path before diverging
3. Follow surprises — vary the parameters that produced unexpected results
4. Off-charter temptations — record as new charters; stay in current session
5. Budget awareness — allocate remaining probes to highest-risk variables

---

## 5. Implicit Expectations

Stakeholders never state these because they assume they're obvious — highest-value adversarial targets:

| Implicit expectation | Adversarial lens |
|---------------------|-----------------|
| Security model applies to all features | Authorization bypass |
| Data operations must not corrupt state | Data integrity |
| System safe under concurrent use | Timing / ordering |
| Performance acceptable at scale | Size variation → Telemetry Deepening |
| Crashes never acceptable | Null / type variation |
