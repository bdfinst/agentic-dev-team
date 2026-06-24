# Ship Arm Manual Run Prompt

**Purpose:** Run the `ship` arm of the "when-does-TDD-pay-off" experiment in an
environment with no dispatch timeout. The automated second run (`run2-2026-06-24`)
recorded all ship trials as timeouts because the `/specs`→`/plan`→`/build` pipeline
exceeds the 900-second dispatch limit in CCR. This prompt lets you run those trials
interactively so the results can be compared against the other arms.

**RQ-D pre-registration:** Does `ship`'s explicit acceptance-criteria synthesis
(`/specs`→`/plan`→`/build`) resolve ambiguity as well as or better than
`tdd-refactor`'s failing-test-as-specification approach? Null: `/specs` makes the
same happy-path assumptions as any other arm and does not reliably surface EDGE
decisions under a vague spec.

**Related files:**
- `docs/experiments/when-tdd-pays-report.md` — full report and pre-registration
- `docs/experiments/experiment-prompt-when-tdd-pays.md` — experiment design
- `docs/experiments/data/tdd-pays-*-run2-2026-06-24.jsonl` — second-run data
  (ship rows all have `"timeout": true`)
- `evals/fixtures/exp-tdd-pays-{pricing,notifier,report-render,event-store}/` —
  specs, change files, and grading tests

---

## Prerequisites

- `dev-team@bfinster` plugin installed (`claude plugin install dev-team@bfinster`)
- Python 3 with pytest (`pip install pytest`)

---

## Instructions

**Design:** 4 tasks × 3 trials × 4 stages (stage0 + 3 changes) = 48 cells.

**Per trial:**
1. Create a **fresh empty directory** — never reuse between trials.
2. Copy the vague spec in as `spec.md`.
3. Run the **stage0 prompt** autonomously (full `/specs`→`/plan`→`/build`).
4. Grade with `acc_core.py` and `acc_edge.py` (copy from `evals/fixtures/…`).
5. Apply changes 1–3 in sequence using the **change prompt**, keeping tests green.
6. Grade `acc_core.py` after each change (`edge_passed` is null for change stages).
7. Record one JSON row per stage in `ship-arm-results.jsonl`.

**Stage0 prompt** (paste into the session, with `spec.md` present):

> You are operating FULLY AUTONOMOUSLY with no human reviewer present. Use the
> dev-team plugin's full pipeline to implement the spec in spec.md: run /specs to
> author explicit acceptance criteria from the spec (including every edge-case
> decision the spec omitted — you must state your choices), then IMMEDIATELY approve
> your own specs yourself and run /plan, then IMMEDIATELY approve your own plan
> yourself and run /build to implement with RED-GREEN-REFACTOR and inline review
> checkpoints. NEVER stop to ask for approval or confirmation — approve and proceed
> every time. Make the acceptance behavior correct. Write your tests as pytest tests
> in a file named test_*.py so they run with `python -m pytest -q`. Put production
> code in the module named in the spec.

**Change prompt** (paste with `change.md` present, replace CHANGE.md with filename):

> You are operating FULLY AUTONOMOUSLY with no human reviewer present. This is an
> existing feature in the working directory. Apply the change described in change.md
> using the dev-team pipeline: run /plan to plan the change, IMMEDIATELY approve
> your own plan, then run /build with RED-GREEN-REFACTOR. Keep the existing test
> suite green. NEVER stop to ask for approval — approve and proceed every time.
> Write your tests as pytest tests in a file named test_*.py so they run with
> `python -m pytest -q`. Put production code in the module named in the spec.

---

## Result row format

Append one JSON object per stage to `ship-arm-results.jsonl`:

```json
{"ts": "<ISO-8601 UTC>", "task": "exp-tdd-pays-<task>", "arm": "ship", "clarity": "vague", "trial": 1, "stage": "stage0", "model": "<model-id>", "core_passed": true, "edge_passed": false, "note": "optional observations"}
{"ts": "...", "task": "exp-tdd-pays-<task>", "arm": "ship", "clarity": "vague", "trial": 1, "stage": "change1", "model": "...", "core_passed": true, "edge_passed": null, "note": "..."}
```

- `core_passed`: `acc_core.py` exits 0 **and** the agent's own test suite passes.
- `edge_passed`: `acc_edge.py` exits 0 (stage0 only; `null` for change stages).
- `model`: the Claude model ID used (e.g. `claude-sonnet-4-6`).

The key comparison for RQ-D is **EDGE pass rate at stage0** — whether `/specs`
forces the model to state the omitted decisions before writing any code.

---

## Task 1: Pricing Engine

**Module:** `pricing.py` | **Classes:** `PricingEngine`, `Discount`

**Vague spec** (save as `spec.md`):

```
# Pricing Engine

Build a `PricingEngine` class in `pricing.py` that calculates the total cost of
a shopping cart after applying one or more discounts.

## Public API

from pricing import PricingEngine, Discount
engine = PricingEngine()
engine.add_discount(discount)
total = engine.calculate(items)

### Items
items is a list of dicts. Each dict has:
- price (float): unit price
- qty (int, optional, default 1): quantity
- category (str, optional): product category label

### Discount
Discount(discount_type, value)
- discount_type: "percent" or "fixed"
- value: non-negative number

## Behavior
- calculate(items) returns total after all discounts, rounded to 2dp
- Multiple discounts all apply
- Total cannot go below zero
```

Full spec: `evals/fixtures/exp-tdd-pays-pricing/spec_vague.md`

**Grading:** `evals/fixtures/exp-tdd-pays-pricing/acc_core.py` and `acc_edge.py`

**EDGE traps** (decisions the vague spec omits):
- Discount priority ordering (higher priority applies first)
- Exclusive discount groups (only highest-priority member applies)
- Tie-breaking within a group (first-inserted wins)

**Changes** (full text in `evals/fixtures/exp-tdd-pays-pricing/`):

- **change1.md** — `min_qty` parameter on `Discount`: skip discount when total cart
  qty < `min_qty`
- **change2.md** — `category` parameter on `Discount` (TRAP): applies discount only
  to the subtotal of matching-category items, not the full cart total
- **change3.md** — `max_discount_pct` on `PricingEngine`: cap total savings as a
  percentage of the original subtotal

---

## Task 2: Notification Service

**Module:** `notifier.py` | **Class:** `NotificationService`

**Vague spec** (save as `spec.md`):

```
# Notification Service

Build a `NotificationService` class in `notifier.py` that dispatches notifications
to recipients through registered channels.

## Public API

from notifier import NotificationService
svc = NotificationService()
svc.register_channel(name, handler)
svc.send(recipient, message, channels=None)
results = svc.send_bulk(recipients, message, channels=None)

### Channel handlers
def handler(recipient: str, message: str) -> bool: ...

### Behaviour
- register_channel(name, handler) registers a channel by name
- send(recipient, message, channels=None) dispatches to all channels (or listed)
  Returns dict: channel_name -> bool
- send_bulk(recipients, message, channels=None) returns dict: recipient -> result dict
- Requesting unregistered channel raises ValueError
- Handler returning False is recorded but does not raise
```

Full spec: `evals/fixtures/exp-tdd-pays-notifier/spec_vague.md`

**Grading:** `evals/fixtures/exp-tdd-pays-notifier/acc_core.py` and `acc_edge.py`

**EDGE traps** (decisions the vague spec omits):
- Per-channel priority ordering when channels=None
- Exception from handler treated as False vs re-raised

**Changes** (full text in `evals/fixtures/exp-tdd-pays-notifier/`):

- **change1.md** — `fallback_for` parameter on `register_channel`: auto-retry via
  fallback channel when primary fails
- **change2.md** — `max_retries` parameter on `register_channel` (TRAP): retry
  failed handlers up to N times
- **change3.md** — `get_audit_log()` / `clear_audit_log()`: in-memory log of every
  send attempt including retries and fallbacks

---

## Task 3: Report Renderer

**Module:** `report_render.py` | **Class:** `ReportRenderer`

**Vague spec** (save as `spec.md`):

```
# Report Renderer

Build a `ReportRenderer` class in `report_render.py` that renders tabular data
into different output formats via registered format handlers.

## Public API

from report_render import ReportRenderer
renderer = ReportRenderer()
renderer.register_format(name, handler)
output = renderer.render(data, format_name, **options)
names = renderer.available_formats()

### Data
data is a list of dicts (rows, keys are column names).

### Format handlers
def handler(data: list[dict], **options) -> str: ...

### Behaviour
- register_format(name, handler) registers a handler by name
- render(data, format_name, **options) calls the handler and returns a string
- available_formats() returns list of registered names
- Unknown format raises ValueError
- Empty data is valid; handlers receive empty list
```

Full spec: `evals/fixtures/exp-tdd-pays-report-render/spec_vague.md`

**Grading:** `evals/fixtures/exp-tdd-pays-report-render/acc_core.py` and `acc_edge.py`

**EDGE traps** (decisions the vague spec omits):
- Whether `available_formats()` returns a copy or a live reference
- How unknown format names are detected (exact match vs case-insensitive)

**Changes** (full text in `evals/fixtures/exp-tdd-pays-report-render/`):

- **change1.md** — `row_limit` keyword on `render()`: truncate data to first N rows
  before passing to handler (not forwarded to handler)
- **change2.md** — `register_alias(alias, existing_format)`: alternative name
  pointing to the same handler; chaining allowed
- **change3.md** — `render_stream()` (TRAP): returns iterator of string chunks;
  handlers without streaming support fall back to single-chunk yield

---

## Task 4: Event Store

**Module:** `event_store.py` | **Classes:** `EventStore`, `OptimisticConcurrencyError`

**Vague spec** (save as `spec.md`):

```
# Event Store

Build an `EventStore` class in `event_store.py` that stores events organised by
stream and allows projecting them into application state.

## Public API

from event_store import EventStore, OptimisticConcurrencyError
store = EventStore()
store.append(stream_id, event_type, data)
events = store.load(stream_id)
state = store.project(stream_id, projection_fn)

### Events
Each event dict has: stream_id, event_type, data, version (1-based)

### append(stream_id, event_type, data)
Returns the event dict as stored.

### load(stream_id)
Returns list of events in order. Non-existent stream returns [].

### project(stream_id, projection_fn)
Calls projection_fn(state, event) for each event starting from state=None.
Non-existent stream returns None.

### OptimisticConcurrencyError
Custom exception (subclass of Exception) for version conflicts.
```

Full spec: `evals/fixtures/exp-tdd-pays-event-store/spec_vague.md`

**Grading:** `evals/fixtures/exp-tdd-pays-event-store/acc_core.py` and `acc_edge.py`

**EDGE traps** (decisions the vague spec omits):
- Optimistic concurrency: `append(expected_version=N)` raises
  `OptimisticConcurrencyError` if stream length ≠ N
- Whether `load()` returns a copy or a live reference to internal storage

**Changes** (full text in `evals/fixtures/exp-tdd-pays-event-store/`):

- **change1.md** — `metadata` parameter on `append()`: optional dict stored
  verbatim alongside event data; field present even when `None`
- **change2.md** — `load_all()`: flat list of all events across all streams in
  global insertion order
- **change3.md** — `snapshot()` / `get_snapshot()` (TRAP): store pre-computed
  projection state at a version; `project()` starts from snapshot instead of
  replaying from version 1

---

## After collecting results

Merge `ship-arm-results.jsonl` with the existing second-run data:

```bash
cat ship-arm-results.jsonl >> docs/experiments/data/tdd-pays-<task>-run2-2026-06-24.jsonl
```

Or keep as a separate file and pass both to the analysis:

```bash
python3 scripts/analyze_tdd_pays.py \
  --data \
    docs/experiments/data/tdd-pays-*-2026-06-23.jsonl \
    docs/experiments/data/tdd-pays-*-run2-2026-06-24.jsonl \
    ship-arm-results.jsonl
```

The analysis will replace the timeout rows with real results for RQ-D.
