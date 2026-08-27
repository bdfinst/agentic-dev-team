"""Deterministic cause-data classification for correction turns (issue
#2013, part of epic #2008).

The corpus carries thousands of user corrections and no cause data: a
correction is the most direct signal the harness did the wrong thing, and
until now it was recorded as a bare count. This module attaches three
closed-vocabulary labels to each correction turn `signals.
detect_correction_turn` already detects:

  what       what kind of output was corrected -- `WHAT_VALUES` below.
  component  which component produced it -- `"main-loop"` or a specific
             agent/skill name.
  shape      what kind of correction it was -- `SHAPE_VALUES` below.

Deterministic-first (CLAUDE.md's "deterministic tools over inference"
rule, and this issue's own "must be cheap" constraint): every label comes
from pattern-matching over tool-call shape and correction-turn keywords,
the same style `classify.CORRECTION_RE` already uses to DETECT a
correction turn in the first place. No model call is ever made here. When
`shape` can't be resolved confidently, it's reported as `"ambiguous"`
with `confidence: "low"` rather than guessed -- the inference share is a
queryable statistic (`accuracy.correction_causes.ambiguous_share` in
`session_report.py`), never hidden.

Privacy: only the four labels below are ever emitted to a digest. The
correction TEXT (`classify_shape`'s `text` argument) is read in memory
only, exactly like `classify.CORRECTION_RE`'s own detection pass -- never
written to output. See `redact.py`'s module docstring for the choke-point
this stays inside; this module composes on top of it, it does not open a
new privacy surface.
"""

from __future__ import annotations

import re

from . import classify
from .signals import EDIT_TOOLS

#: what-was-corrected vocabulary (issue #2013).
WHAT_VALUES = (
    "code-edit",
    "plan",
    "review-finding",
    "tool-choice",
    "factual-claim",
    "other",
)

#: correction-shape vocabulary (issue #2013). "ambiguous" is the honest
#: fallback when no shape pattern below matches -- see module docstring.
SHAPE_VALUES = (
    "reverted",
    "redirected",
    "narrowed-scope",
    "flagged-wrong",
    "not-what-asked",
    "ambiguous",
)

#: `component` value when no skill/agent is the currently-active dispatch
#: (`signals.accumulate_skill_agent_signals`'s `active["last"]`, `None`).
MAIN_LOOP_LABEL = "main-loop"


def is_review_agent_name(name: str | None) -> bool:
    """Whether a (already namespace-stripped) agent name follows this
    repo's own review-agent naming convention: `<domain>-review`,
    `<domain>-reviewer` (`quality-reviewer`, `spec-reviewer`), or
    `plan-review-<facet>` (`plan-review-acceptance`, ...). Checked against
    every review agent under `plugins/dev-team/agents/` at the time this
    was written -- a naming-convention check, not a registry lookup, so it
    needs no registry threaded through the classifier."""
    if not name:
        return False
    return name.endswith(("-review", "-reviewer")) or name.startswith("plan-review-")


def new_context() -> dict:
    """Per-thread rolling "what" state. `what` is `None` until the first
    assistant turn is observed (`classify_correction` falls back to
    `"other"` for a correction with no preceding assistant turn at all --
    a real, if unusual, transcript shape, not a guess). Reset once per
    transcript file, same lifecycle as `signals.new_thread()`."""
    return {"what": None}


def observe_assistant_turn(rec: dict, content) -> dict | None:
    """Recompute the rolling "what" context from ONE assistant record.

    Returns `None` for a non-assistant record -- the caller should keep
    its existing context unchanged, since `detect_correction_turn` only
    ever fires on a `"user"` record and "what" answers "what did the
    IMMEDIATELY PRECEDING assistant turn do" (issue #2013's own framing).
    This is why the result REPLACES the context wholesale rather than
    updating it in place, unlike the sticky `active` skill/agent pointer
    `component` is built from below: a later text-only turn must
    overwrite an earlier tool call's classification, not merely
    supplement it.
    """
    if rec.get("type") != "assistant":
        return None
    if not isinstance(content, list):
        has_text = isinstance(content, str) and bool(content.strip())
        return {"what": "factual-claim" if has_text else "other"}

    candidates: set[str] = set()
    saw_tool_use = False
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        saw_tool_use = True
        name = block.get("name", "?")
        inp = block.get("input", {}) if isinstance(block.get("input"), dict) else {}
        if name in EDIT_TOOLS:
            candidates.add("code-edit")
        elif name == "Skill":
            skill_name = classify.strip_ns(str(inp.get("skill") or inp.get("name") or ""))
            if skill_name == "plan":
                candidates.add("plan")
        elif name in ("Agent", "Task"):
            agent_name = classify.strip_ns(str(inp.get("subagent_type") or ""))
            if is_review_agent_name(agent_name):
                candidates.add("review-finding")
        elif name == "Bash":
            candidates.add("tool-choice")

    if not saw_tool_use:
        return {"what": "factual-claim"}
    for label in ("code-edit", "plan", "review-finding", "tool-choice"):
        if label in candidates:
            return {"what": label}
    return {"what": "other"}


# Priority-ordered, most-specific-first: the FIRST pattern that matches the
# correction turn's own (lowercased) text wins. Every alternative here is a
# refinement of `classify.CORRECTION_RE`'s own keyword set (the same
# keyword-matching approach that already detects a correction turn), not a
# new detection mechanism -- a correction turn that matched CORRECTION_RE
# only via its bare "no" alternative (no "wrong"/"actually"/"revert"/...
# alongside it) matches none of these and correctly falls through to
# "ambiguous": that's a real, non-trivial subset of correction turns whose
# shape genuinely can't be told apart by keyword alone.
_SHAPE_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ("reverted", re.compile(r"\b(revert|undo|roll\s*back|put\s+(it\s+)?back)\b")),
    ("not-what-asked", re.compile(r"not what i (asked|wanted|meant)")),
    ("flagged-wrong", re.compile(r"\b(that'?s wrong|that is wrong|incorrect|wrong)\b")),
    (
        "narrowed-scope",
        re.compile(
            r"\b(just|only|too (much|broad|big)|narrow(er)?|smaller scope|"
            r"don'?t need|no need)\b"
        ),
    ),
    ("redirected", re.compile(r"\b(actually|instead|rather|stop|don'?t|do not)\b")),
)


def classify_shape(text: str) -> tuple[str, str]:
    """Correction SHAPE from the correction turn's own text (read in
    memory only -- see module docstring). Returns `(shape, confidence)`;
    `confidence` is `"low"` exactly when `shape == "ambiguous"` -- shape is
    the one genuinely fuzzy dimension of this classifier (`what` and
    `component` are read off structural facts -- tool names, dispatch
    state -- not inferred from text, so they carry no comparable
    ambiguity)."""
    lowered = text.lower()
    for label, pattern in _SHAPE_PATTERNS:
        if pattern.search(lowered):
            return label, "high"
    return "ambiguous", "low"


def classify_correction(turn_context: dict, dispatch: tuple[str, str] | None, text: str) -> dict:
    """The full cause-data record for one correction turn.

    `turn_context`: the rolling "what" state (`new_context`/
    `observe_assistant_turn`'s last non-`None` result).
    `dispatch`: the currently-active `(kind, name)` skill/agent dispatch
    (`signals.accumulate_skill_agent_signals`'s `active["last"]`), or
    `None` when nothing has been dispatched yet in this thread.
    `text`: the correction turn's own flattened text
    (`classify.text_of(content)`) -- read in memory only, never returned.

    Returns `{"what", "component", "shape", "confidence"}` -- the only
    four values a caller should emit; never the raw text, dispatch name
    provenance details, or tool-call sequence itself beyond what these
    four labels already encode.
    """
    what = (turn_context or {}).get("what") or "other"
    component = dispatch[1] if dispatch else MAIN_LOOP_LABEL
    shape, confidence = classify_shape(text)
    return {"what": what, "component": component, "shape": shape, "confidence": confidence}
