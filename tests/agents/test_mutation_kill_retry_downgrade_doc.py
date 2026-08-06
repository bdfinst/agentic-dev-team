"""Doc-content contract for the retry-then-downgrade behavior on repeated
headless-generation failures (#1908, Slice 3, Step 3.3 of
plans/mutation-kill-batch-hardening-1906-1910.md).

Mirrors the grep-on-section pattern already used in
``test_mutation_kill_skip_static_doc.py`` — pure text assertions over shipped
agent prose, no state-mutating filesystem/git operations. Reuses
``skill_doc_helpers.collapsed()`` for whitespace-reflow-proof flattening
rather than a hand-rolled ``.replace("\\n", " ")``.

The actual retry/downgrade mechanism is implemented and behaviorally tested
in ``tests/scripts/test_mutation_kill_shared.py`` (Steps 3.1/3.2/3.2b) —
this file only guards that ``mutation-kill.md``'s "Generation modes" section
still names the same five facts an operator needs to recognize and configure
the behavior: the 3-consecutive-failure threshold, the single same-model
retry, the at-most-once-per-file downgrade rule, that exhaustion at the
fallback tier surfaces to the operator rather than cascading, and the
``DEV_TEAM_MUTATION_FALLBACK_MODEL`` override name. ``mutation-kill.md`` has
a hard, enforced 620-line ceiling with zero headroom (see
``test_mutation_kill_agent.py::test_agent_body_stays_under_500_line_limit``),
so the doc text this guards is a single terse bullet, not a full section.
"""

from __future__ import annotations

import re

import pytest
from skill_doc_helpers import collapsed, section

from _repo_root import REPO_ROOT

AGENT = REPO_ROOT / "plugins" / "dev-team" / "agents" / "mutation-kill.md"


@pytest.fixture(scope="module")
def text() -> str:
    return AGENT.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def generation_modes_flat(text: str) -> str:
    result = section(
        text,
        r"^## Generation modes",
        boundary_pattern=r"^## ",
        include_start_line=False,
    )
    assert result, "Generation modes section not found"
    return collapsed(result)


def test_documents_three_consecutive_failure_threshold(generation_modes_flat: str) -> None:
    assert re.search(r"3(rd| consecutive)", generation_modes_flat)
    assert "502/gateway-class" in generation_modes_flat


def test_documents_exactly_one_same_model_retry(generation_modes_flat: str) -> None:
    assert re.search(r"exactly 1 same-model retry", generation_modes_flat)


def test_documents_at_most_once_downgrade_per_file(generation_modes_flat: str) -> None:
    assert re.search(r"at most once per file, ever", generation_modes_flat)
    assert re.search(r"opus.{0,5}sonnet.{0,5}haiku", generation_modes_flat)


def test_documents_fallback_exhaustion_surfaces_to_operator(generation_modes_flat: str) -> None:
    assert re.search(
        r"[Ee]xhaustion.{0,60}surfaces.{0,40}operator", generation_modes_flat
    )
    assert re.search(r"instead of a second downgrade", generation_modes_flat)
    assert "--all" in generation_modes_flat


def test_documents_fallback_model_env_var_override(generation_modes_flat: str) -> None:
    assert "DEV_TEAM_MUTATION_FALLBACK_MODEL" in generation_modes_flat
    assert re.search(
        r"invalid value.{0,40}(rejected|ladder default)", generation_modes_flat
    )
