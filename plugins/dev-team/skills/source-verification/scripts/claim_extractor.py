"""Claim extraction heuristics for the source-verification skill (#2189).

This is explicitly NOT a general NLP claim extractor. It flags sentences that
*look like* they assert something checkable against a source (this repo's own
code, or an external tool/spec/doc) using four small, documented heuristics:

1. A version number (e.g. ``5.0.0``, ``stryker-net 5.0.0``).
2. A citation-like phrase (``per X``, ``documented at``, ``according to``).
3. A code-identifier-looking token: a ``snake_case()`` function/method call,
   or a ``CamelCase`` class-looking name.
4. A path reference to a file in this repo (e.g. ``hooks/foo.py``).

A plain narrative sentence matching none of these is not extracted at all.

Verification (grepping the codebase, WebFetch for external sources) is a
model-driven procedure documented in SKILL.md, not scripted here — this
module covers extraction and the shared output schema only. ``verdict`` and
``source_consulted`` stay ``None`` until a later verification pass fills
them in.
"""

from __future__ import annotations

import dataclasses
import re
from typing import Literal

Kind = Literal["code", "external", "ambiguous"]
Verdict = Literal["verified", "contradicted", "unverifiable"]


@dataclasses.dataclass
class Claim:
    """A candidate claim extracted from text, pending verification.

    ``source_consulted``/``verdict`` are filled in by a later verification
    pass (SKILL.md), not by this module.
    """

    text: str
    kind: Kind
    source_consulted: str | None = None
    verdict: Verdict | None = None


def claim_to_dict(claim: Claim) -> dict:
    """Convert a ``Claim`` to a plain JSON-serializable dict."""
    return dataclasses.asdict(claim)


def claim_from_dict(data: dict) -> Claim:
    """Reconstruct a ``Claim`` from a dict produced by ``claim_to_dict``."""
    return Claim(**data)


# Heuristic 1: version numbers, e.g. "5.0.0" or "2.1".
_VERSION_RE = re.compile(r"\b\d+\.\d+(?:\.\d+)?\b")

# Heuristic 2: citation-like phrases.
_CITATION_RE = re.compile(r"\b(?:per|documented at|according to)\b", re.IGNORECASE)

# Heuristic 3: code-identifier-looking tokens — a snake_case() call, or a
# CamelCase name (uppercase letter, lowercase run, then another uppercase).
_CODE_IDENTIFIER_RE = re.compile(
    r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\(\)"
    r"|\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)+\b"
)

# Heuristic 4: a path-looking reference to a file in this repo.
_PATH_RE = re.compile(r"\b[\w\-./]+\.(?:py|md|js|ts|json|ya?ml|sh)\b")

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _candidate_sentences(text: str):
    """Split text into candidate sentences, line by line."""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        for sentence in _SENTENCE_SPLIT_RE.split(line):
            sentence = sentence.strip()
            if sentence:
                yield sentence


def _classify(sentence: str) -> Kind | None:
    """Classify a sentence, or return None if it has no extractable claim.

    A repo-internal-looking identifier/path/version (heuristics 1, 3, 4)
    with no external citation phrase -> "code" (about this repo's own
    code/tooling). An external citation phrase (heuristic 2) with no local
    identifier -> "external". Both present -> "ambiguous". Neither -> not a
    claim at all.
    """
    has_citation = bool(_CITATION_RE.search(sentence))
    has_local = bool(
        _CODE_IDENTIFIER_RE.search(sentence)
        or _PATH_RE.search(sentence)
        or _VERSION_RE.search(sentence)
    )
    if has_citation and has_local:
        return "ambiguous"
    if has_citation:
        return "external"
    if has_local:
        return "code"
    return None


def extract_claims(text: str) -> list[Claim]:
    """Extract candidate claims from ``text`` using the heuristics above."""
    claims: list[Claim] = []
    for sentence in _candidate_sentences(text):
        kind = _classify(sentence)
        if kind is None:
            continue
        claims.append(Claim(text=sentence, kind=kind))
    return claims
