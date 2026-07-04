"""docs/model-routing.md documents the effort-band + ladder model: the core
sections, links to the ADRs, and the env-var classification (test-only
seams vs. user-facing knobs). The retired probe/overrides knobs must be
gone.

Ported from tests/docs/model_routing_doc_test.bats (issue #675:
bats -> pytest).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DOC = REPO_ROOT / "plugins" / "dev-team" / "docs" / "model-routing.md"


@pytest.fixture(scope="module")
def text() -> str:
    return DOC.read_text(encoding="utf-8")


def test_doc_file_exists() -> None:
    assert DOC.is_file()


def test_section_contract_present(text: str) -> None:
    assert re.search(r"^## Contract", text, re.MULTILINE)


def test_documents_resolution_precedence(text: str) -> None:
    assert re.search(r"^###? Resolution precedence", text, re.MULTILINE | re.IGNORECASE)


def test_documents_exit_code_taxonomy(text: str) -> None:
    assert re.search(r"exit.code", text, re.IGNORECASE)


def test_documents_legacy_tier_acceptance(text: str) -> None:
    assert re.search(r"^## Legacy tier acceptance", text, re.MULTILINE | re.IGNORECASE)


def test_documents_bump_log(text: str) -> None:
    assert re.search(r"^## The bump log", text, re.MULTILINE | re.IGNORECASE)


def test_documents_authoring_ladder_for_restricted_endpoints(text: str) -> None:
    assert re.search(r"^## Authoring a ladder", text, re.MULTILINE | re.IGNORECASE)
    assert re.search(r"bedrock|vertex|proxy", text, re.IGNORECASE)


def test_links_to_adr_0008_and_adr_0004(text: str) -> None:
    assert "0008-use-effort-bands" in text
    assert "0004-pre-dispatch-model-resolution" in text


def test_links_to_override_authoring_guide(text: str) -> None:
    assert "model-routing-overrides.md" in text


def test_documents_user_facing_env_vars(text: str) -> None:
    assert "ANTHROPIC_BASE_URL" in text
    assert "MODEL_BUMP_TAIL" in text


def test_marks_routing_seams_as_test_only(text: str) -> None:
    assert "MODEL_ROUTING_JSON" in text
    assert "MODEL_LADDER_JSON" in text
    assert "SESSION_MODEL_FILE" in text
    assert "MODEL_BUMP_LOG" in text
    assert "test-only" in text.lower()


def test_no_retired_probe_overrides_env_vars_remain(text: str) -> None:
    assert not re.search(
        r"MODEL_PROBE_TIMEOUT|MODEL_PROBE_FORCE|MODEL_OVERRIDES_JSON", text
    )
