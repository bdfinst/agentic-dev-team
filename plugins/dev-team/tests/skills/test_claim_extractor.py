"""Tests for skills/source-verification/scripts/claim_extractor.py (#2189).

Covers: heuristic extraction of candidate claims (version numbers, citation
phrases, code-identifier tokens, path references), code/external/ambiguous
classification with pinned fixture assertions, the "no claim extracted"
negative case, and the Claim dataclass's JSON round-trip.
"""

from __future__ import annotations

import dataclasses
import json
import sys

from _repo_root import REPO_ROOT

sys.path.insert(
    0,
    str(
        REPO_ROOT
        / "plugins"
        / "dev-team"
        / "skills"
        / "source-verification"
        / "scripts"
    ),
)

from claim_extractor import Claim, claim_from_dict, claim_to_dict, extract_claims


def test_version_attached_to_named_tool_is_classified_as_code() -> None:
    claims = extract_claims("stryker-net 5.0.0")
    assert len(claims) == 1
    assert claims[0].kind == "code"
    assert claims[0].text == "stryker-net 5.0.0"


def test_external_citation_phrase_with_no_local_identifier_is_external() -> None:
    claims = extract_claims("per RFC 7231")
    assert len(claims) == 1
    assert claims[0].kind == "external"
    assert claims[0].text == "per RFC 7231"


def test_plain_narrative_sentence_extracts_no_claims() -> None:
    claims = extract_claims(
        "The service restarts automatically when it detects a failure."
    )
    assert claims == []


def test_code_identifier_token_is_classified_as_code() -> None:
    claims = extract_claims("resolve_window() controls the context ceiling.")
    assert len(claims) == 1
    assert claims[0].kind == "code"


def test_citation_phrase_plus_local_identifier_is_ambiguous() -> None:
    claims = extract_claims(
        "Per the documentation, resolve_window() returns the ceiling."
    )
    assert len(claims) == 1
    assert claims[0].kind == "ambiguous"


def test_claim_schema_round_trips_through_json() -> None:
    original = Claim(text="stryker-net 5.0.0", kind="code")
    serialized = json.dumps(claim_to_dict(original))
    restored = claim_from_dict(json.loads(serialized))
    assert restored == original
    assert dataclasses.asdict(restored) == dataclasses.asdict(original)


def test_claim_verdict_and_source_consulted_default_to_none() -> None:
    claim = Claim(text="per RFC 7231", kind="external")
    assert claim.verdict is None
    assert claim.source_consulted is None
