---
name: long-eval
description: >-
  Run an eval that takes longer than one cloud-session container lifetime —
  agent calibration, prompt A/B sweeps, judge-panel scoring — so it survives the
  frequent container recycles that kill in-process work. Use when the user says
  "run this long eval", "the eval keeps dying on restart", "make the eval
  survive restarts", "resume the eval", "keep the eval alive", or when a
  full-corpus calibration/benchmark will clearly outlast a single session. Ships
  a restart-durable engine + CLI so nothing is re-invented per eval.
argument-hint: "[status|ensure-alive] --module <file> --out <dir>"
user-invocable: true
allowed-tools: >-
  Bash(python3 *), Read, Glob
---

# Long (Restart-Durable) Eval

Role: worker + supervisor. Runs a checkpointed eval that resumes across
container recycles, and keeps it alive until it finishes.

## Why this exists

A cloud session runs in a container that is **recycled on a short cadence**
(often every few minutes). A recycle kills every running process but **keeps
the working tree**. So any eval longer than one container lifetime must:

1. **Checkpoint to disk** at fine granularity, and resume from the checkpoint
   rather than restarting — otherwise every recycle throws the work away.
2. **Be relaunched** after each recycle. The session itself is the only
   supervisor: each recycle re-invokes it ("Continue from where you left
   off"), which is the relaunch trigger — tighter than any timer.

This skill ships both halves so you don't rebuild them:

| File | Role |
|------|------|
| `durable_runner.py` | The engine — grades one cell at a time, checkpoints after **every sample**, resumes at the next unbanked sample. Import it or run via the CLI. |
| `run_eval.py` | CLI supervisor — `run`, `status`, and `ensure-alive` (the guard-relaunch primitive). |

`${CLAUDE_PLUGIN_ROOT}` below is the plugin root; from this repo it is
`plugins/dev-team`.

## The eval module contract

An **eval module** is a plain Python file supplying only the eval-specific
bits. Everything durable is handled for you.

```python
SAMPLES = 5           # optional: trials per cell (majority vote)
WORKERS = 10          # optional: moderate on purpose — see note below

def cells():          # -> list of (key, payload)
    ...               # key = a STABLE string, identical every launch
def sample(payload):  # -> json-serializable; ONE independent trial
    ...
def reduce(samples, key, payload):  # optional -> the cell's record dict
    ...
def finalize(done, out_dir):        # optional -> summary (once all cells bank)
    ...
def flag(record):                   # optional -> bool: force a progress line
    ...
```

`key` is the checkpoint identity — it must be byte-identical across relaunches
(e.g. `f"{fixture}||{variant}"`). `payload` is passed straight to `sample` and
is **never persisted**, so `cells()` reconstructs it each launch.

> **Keep `WORKERS` moderate.** When `sample` collapses a result to a bool, a
> transport error (rate-limit → retries exhausted → False) is indistinguishable
> from a real negative and gets checkpointed as one. Fewer concurrent dispatches
> means fewer such errors. Durability comes from the checkpoint, not the pool
> size — there is no reason to max it out.

## Steps

1. **Write the eval module** against the contract above. Choose an `--out`
   directory under `.claude/evals/<slug>/` (checkpoints live there and
   survive recycles).

2. **Launch it durably** (backgrounded, from the repo root):

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/long-eval/run_eval.py ensure-alive \
     --module <path-to-your-module.py> \
     --out .claude/evals/<slug>
   ```

   `ensure-alive` starts the run **detached** only if no live driver already
   owns that `--out` and it is not already `DONE`. It is safe to call any number
   of times — it never double-launches. This one command is the whole
   guard-relaunch.

3. **On every session wake, re-run the same `ensure-alive`.** A recycle killed
   the driver; this relaunches it, resuming from the checkpoint. Then report
   progress with `status` (add `--json` for a machine-readable line):

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/long-eval/run_eval.py status \
     --out .claude/evals/<slug>
   ```

4. **Arm a backstop timer** as insurance against a missed wake. Schedule a
   self-re-arming check-in (the session's scheduling tool — e.g. `send_later` /
   `ScheduleWakeup` / a Routine, ~20 min out) whose body runs the same
   `ensure-alive` + `status` and re-arms itself, **unless** the run is `DONE`
   or the user said stop. The backstop only matters if a wake is ever missed;
   the recycle-wake is the primary trigger.

   Follow the calling contract in
   [`knowledge/long-run-waiting.md`](../../knowledge/long-run-waiting.md):
   every arm/re-arm call carries the instruction to replay (`prompt`) and a
   `reason` — a call with only a delay fails the "prompt is required when stop
   is not true" validation and **arms nothing**, which silently costs you the
   backstop you thought you had.

5. **Report and stop when `DONE`.** When `status` shows `DONE=True`, read
   `summary.json` from the out-dir, report the final result, and **stop
   re-arming the backstop** — for a wake-up scheduler that means one
   `stop: true`-only call, not a call that merely explains why you are
   stopping. A `flap`-flagged cell (mixed pass/fail across
   samples) is low-confidence — surface it for quarantine/rewrite rather than
   trusting its verdict.

## Guarantees & limits

- **At most one in-flight dispatch is ever lost** on a recycle — samples are
  checkpointed individually, not per-cell.
- Checkpoint writes are **atomic** (`os.replace`), so a recycle mid-write can
  never truncate `cells.json`/`samples.json`.
- A cell whose `sample` **deterministically raises** never banks and blocks
  completion across relaunches by design — the run surfaces it and the operator
  fixes the module. `ensure-alive` will not paper over a broken eval.
- This supervises **one** eval per `--out` directory; run independent evals in
  separate out-dirs.
