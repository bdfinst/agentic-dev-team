"""plugins/dev-team/scripts/lib/slug.py — shared repo-root slug derivation.

`codebase_recon.py::_derive_slug` and `orchestrator.py::_derive_recon_slug`
hand-duplicated this algorithm until #2068 promoted it to this shared
module (both scripts now `from lib.slug import derive_slug`). This file is
the canonical, module-level test coverage for the algorithm itself; the two
callers keep their own tests for wiring (e.g.
`test_main_reuses_derive_slug_helper_instead_of_duplicating_the_regex` in
tests/scripts/test_codebase_recon.py) rather than re-testing the algorithm.
"""

from __future__ import annotations

import sys
from pathlib import Path

from _repo_root import REPO_ROOT

LIB = REPO_ROOT / "plugins" / "dev-team" / "scripts" / "lib"
sys.path.insert(0, str(LIB))

import slug

derive_slug = slug.derive_slug


def test_derive_slug_lowercases_and_kebab_cases_a_messy_name() -> None:
    assert derive_slug(Path("/tmp/My Repo__Name!!")) == "my-repo__name"


def test_derive_slug_collapses_repeated_dashes() -> None:
    assert derive_slug(Path("/tmp/a---b")) == "a-b"


def test_derive_slug_strips_leading_and_trailing_dashes() -> None:
    # Leading/trailing punctuation maps to "-", which strip("-") then removes.
    assert derive_slug(Path("/tmp/--weird-name--")) == "weird-name"
    assert derive_slug(Path("/tmp/!!!leading")) == "leading"
    assert derive_slug(Path("/tmp/trailing!!!")) == "trailing"


def test_derive_slug_falls_back_to_repo_for_an_empty_result() -> None:
    # An all-punctuation name has nothing left after stripping — the "or
    # repo" fallback must fire rather than returning an empty string.
    assert derive_slug(Path("/tmp/!!!")) == "repo"


def test_derive_slug_preserves_dots_and_underscores() -> None:
    assert derive_slug(Path("/tmp/my.repo_v2")) == "my.repo_v2"
