"""Constants the model/effort A/B harness tests share: models, prices, pinned estimate inputs and run sizes."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path

import ab_harness_path  # noqa: F401  (puts the harness on sys.path first)
from model_effort import (
    estimate,
    invocation,
)

TRANSCRIPT_FIXTURES = (
    Path(__file__).resolve().parent.parent / "fixtures" / "model_effort_ab"
)
HAIKU_MODEL_ID = "claude-haiku-5-5"
SONNET_MODEL_ID = "claude-sonnet-5-5"
NOW = datetime(2026, 10, 8, 12, 30, 45, tzinfo=timezone.utc)
RUN_ID = "20261008T123045Z-scout-haiku-high-0ab3"
SCOUT_TOOLS = "Read, Grep, mcp__x__y, Bash(graphify *)"
PASS_VERDICT = {"status": "pass", "issues": [], "summary": "Nothing to report."}
TRIAL_COST = 0.01
# The scout agent with its candidate arm on haiku, the tail most CLI runs share.
SCOUT_HAIKU_ARGS = ("scout", "--model", "haiku")
CLEAN_FORM_ARGS = (*SCOUT_HAIKU_ARGS, "--fixtures", "clean-form")
# Dollars per million tokens. Aliases mirror the agent files' `sonnet` and the
# candidate `haiku`; `opus` is deliberately absent so it is unpriced.
PRICEY_RATE = {"input": 4.0, "output": 20.0}
CHEAP_RATE = {"input": 1.0, "output": 5.0}
TEST_PRICING = {
    "models": {"test-pricey": PRICEY_RATE, "test-cheap": CHEAP_RATE},
    "aliases": {"sonnet": "test-pricey", "haiku": "test-cheap"},
}
# Pinned so CLI estimates do not move when the shipped calibration is retuned.
PINNED_CHARS_PER_TOKEN = 4
PINNED_TURN_MULTIPLIER = 2
PINNED_OUTPUT_TOKENS = 100
ARM_COUNT = 2
# The `scout` world resolves two fixtures: clean-form and layered-svc.
SCOUT_FIXTURE_COUNT = 2
SCOUT_TRIALS = 3


def _trial_input_chars(system_prompt_chars: int, fixture_chars: int, name: str) -> int:
    """Characters one trial sends: system prompt, fixture contents and the user prompt naming it."""
    return system_prompt_chars + fixture_chars + len(invocation.build_user_prompt(name))


def _arm_estimate_usd(input_chars: int, output_tokens: int, rate: dict) -> float:
    """What the estimator charges one arm for `SCOUT_TRIALS` rounds of the trial described."""
    input_tokens = input_chars / PINNED_CHARS_PER_TOKEN * PINNED_TURN_MULTIPLIER
    per_round_usd = (
        input_tokens * rate["input"] + output_tokens * rate["output"]
    ) / estimate.TOKENS_PER_RATE_UNIT
    return per_round_usd * SCOUT_TRIALS


# The `scout` world run over both fixtures with SCOUT_TRIALS trials per arm. A round
# is one trial on each fixture. The agent file's body keeps its trailing newline.
SCOUT_ROUND_INPUT_CHARS = _trial_input_chars(
    len("You are scout.\n"), len("<form></form>"), "clean-form.html"
) + _trial_input_chars(len("You are scout.\n"), len("app"), "layered-svc")


SCOUT_ROUND_OUTPUT_TOKENS = SCOUT_FIXTURE_COUNT * PINNED_OUTPUT_TOKENS
BASELINE_TWO_ARM_ESTIMATE = _arm_estimate_usd(
    SCOUT_ROUND_INPUT_CHARS, SCOUT_ROUND_OUTPUT_TOKENS, PRICEY_RATE
)
CANDIDATE_TWO_ARM_ESTIMATE = _arm_estimate_usd(
    SCOUT_ROUND_INPUT_CHARS, SCOUT_ROUND_OUTPUT_TOKENS, CHEAP_RATE
)
TWO_ARM_ESTIMATE = BASELINE_TWO_ARM_ESTIMATE + CANDIDATE_TWO_ARM_ESTIMATE
# A `--max-cost` under the estimate, so the startup refusal applies.
MAX_COST_BELOW_ESTIMATE = TWO_ARM_ESTIMATE / 2
# Calls and cost of one arm, and of both, when every planned trial runs.
ARM_RUN_CALLS = SCOUT_FIXTURE_COUNT * SCOUT_TRIALS
FULL_RUN_CALLS = ARM_COUNT * ARM_RUN_CALLS
FULL_RUN_COST = FULL_RUN_CALLS * TRIAL_COST
# A spend limit of two and a half trials' cost: the third trial takes the total past it.
LIMIT_IN_TRIALS = 2.5
MAX_COST_MID_RUN = LIMIT_IN_TRIALS * TRIAL_COST
TRIALS_BEFORE_STOP = math.ceil(LIMIT_IN_TRIALS)
ENABLED = ("Read", "Grep")
# The most characters of a trial's error text (and of its grader messages) that are kept.
CAUSE_LIMIT = 500
# Long enough that a slow interpreter start still reaches the stub before the kill.
TIMEOUT_SECONDS = 3
TRUNCATED_OUTER_OBJECT = '{"status":"fail","issues":[{"severity":"error","message":"x"}'
GRADED_AGENT = "x-review"
GRADED_STEM = "clean-form"
# One planned trial per arm, so an arm's per-trial estimate is its whole estimate.
ARM_ESTIMATE = 0.005
WORLD_KNOWLEDGE_NOTE = "shared reference text"
