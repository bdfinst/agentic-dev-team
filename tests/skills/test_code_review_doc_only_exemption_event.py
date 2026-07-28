"""Issue #1461 — the doc-only short-circuit's `.review-passed` write must be
paired with an explicit, auditable boundary event (`"doc-only-review-exempt"`)
rather than a silent code-path skip, so the dispatch-ledger corroboration
gate can recognize the exemption instead of only seeing an uncorroborated
hash-matching write.

The CLI is purpose-locked to a fixed `--event <name>` selector (not a
free-form `--hook/--tool/--decision/--matched-rule` pass-through) since an
earlier draft's unrestricted CLI let anyone forge arbitrary boundary events,
including a fake "record" row for an unregistered agent — see
`hooks/lib/boundary_events.py`'s `_CLI_EVENTS` mapping and its own docstring
for the full account. This test checks the SKILL.md invocation shape *and*
that `_CLI_EVENTS`'s `"doc-only"` entry actually maps to the
`bypass`/`doc-only-review-exempt` tuple this gate relies on — so a change to
either side alone would be caught here.
"""

from __future__ import annotations

import sys

from skill_doc_helpers import PLUGIN_ROOT

CODE_REVIEW = (
    PLUGIN_ROOT / "skills" / "code-review" / "SKILL.md"
).read_text(encoding="utf-8")

_LIB_DIR = PLUGIN_ROOT / "hooks" / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import boundary_events  # type: ignore[import-not-found]


def test_doc_only_short_circuit_emits_the_exemption_boundary_event():
    # The exact matched_rule string ("doc-only-review-exempt") intentionally
    # no longer needs to appear in the skill prose — the CLI's purpose-locked
    # `--event doc-only` selector abstracts it (verified against
    # boundary_events.py's own mapping below). The prose still names the
    # concept and the concrete invocation.
    assert "doc-only exemption" in CODE_REVIEW
    assert "--event doc-only" in CODE_REVIEW


def test_doc_only_exemption_invokes_the_purpose_locked_cli_event():
    assert "hooks/lib/boundary_events.py" in CODE_REVIEW
    assert "--event doc-only" in CODE_REVIEW
    assert "--subject-hash" in CODE_REVIEW
    # Never the free-form flags a forgery vector would need.
    assert "--hook code-review --tool Skill --decision bypass" not in CODE_REVIEW


def test_doc_only_cli_event_maps_to_bypass_doc_only_review_exempt():
    hook, tool, decision, matched_rule = boundary_events._CLI_EVENTS["doc-only"]
    assert (hook, tool, decision, matched_rule) == (
        "code-review",
        "Skill",
        "bypass",
        "doc-only-review-exempt",
    )


def test_single_agent_short_circuit_emits_its_exemption_boundary_event():
    # Same abstraction as the doc-only case: the exact matched_rule string
    # lives in boundary_events.py's _CLI_EVENTS mapping (verified below), not
    # spelled out in the skill prose.
    assert "--agent <name>" in CODE_REVIEW and "single-agent" in CODE_REVIEW, (
        "the --agent <name> single-agent review path must record an "
        "explicit exemption event, since it can never clear the "
        "dispatch-ledger gate's >= 2 distinct-dispatch floor on its own"
    )
    assert "--event single-agent" in CODE_REVIEW


def test_single_agent_cli_event_maps_to_bypass_single_agent_review_exempt():
    hook, tool, decision, matched_rule = boundary_events._CLI_EVENTS["single-agent"]
    assert (hook, tool, decision, matched_rule) == (
        "code-review",
        "Skill",
        "bypass",
        "single-agent-review-exempt",
    )
