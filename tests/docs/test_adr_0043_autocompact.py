"""ADR 0043 records the autocompact decision and its harness constraints (#2177, AC 8)."""

from __future__ import annotations

import re

import pytest

from _repo_root import REPO_ROOT

ADR_DIR = REPO_ROOT / "docs" / "adr"
NEW = "0043-replace-the-context-ceiling-guard-with-harness-autocompact.md"
SUPERSEDED = {
    "0011": "0011-enforce-context-ceiling-with-transcript-measured-pretooluse-hook.md",
    "0016": "0016-rely-on-harness-native-compaction-the-plugin-performs-structured-summarization-only.md",
    "0037": "0037-block-by-default-at-the-context-ceiling-2000.md",
    "0038": "0038-raise-the-absolute-context-ceiling-to-350k.md",
    "0039": "0039-only-skill-loads-are-worth-blocking-at-the-context-ceiling.md",
}


def _text(name: str) -> str:
    return (ADR_DIR / name).read_text(encoding="utf-8")


def _status(name: str) -> str:
    match = re.search(r"^## Status\n\n(.*?)(?=^## )", _text(name), re.DOTALL | re.MULTILINE)
    assert match, f"{name}: no Status section"
    return match.group(1)


def test_adr_0043_is_accepted_and_supersedes_each_old_adr_with_a_link():
    status = _status(NEW)
    assert status.lstrip().startswith("Accepted")
    for num, filename in SUPERSEDED.items():
        assert re.search(rf"Supersedes \[{int(num)}\. [^\]]+\]\({re.escape(filename)}\)", status), num


@pytest.mark.parametrize("num", sorted(SUPERSEDED))
def test_each_superseded_adr_points_back_to_0043(num):
    status = _status(SUPERSEDED[num])
    assert re.search(rf"Superseded by \[43\. [^\]]+\]\({re.escape(NEW)}\)", status)
    assert not status.lstrip().startswith("Accepted"), "status must lead with Superseded"


def test_links_resolve_to_existing_files():
    for filename in (NEW, *SUPERSEDED.values()):
        assert (ADR_DIR / filename).is_file()


def test_readme_lists_adr_43():
    assert f"]({NEW})" in _text("README.md")


@pytest.mark.parametrize(
    "phrase",
    [
        "Hooks cannot start a compaction",  # no plugin-triggered compaction
        "can only block",  # PreCompact
        "values above the harness default are ignored",  # lower-only
        "Fires between turns, not per tool call",
        "Coverage is per repo",
        "deliberately dropped",  # 350K cap
        "40% of a 1M window is 400K",
        "deliberately not used anywhere",  # CLAUDE_CODE_AUTO_COMPACT_WINDOW
        "10,000 characters",
    ],
)
def test_required_constraints_are_recorded(phrase):
    assert phrase in _text(NEW)


def test_unconfirmed_claims_are_tagged_reported_and_point_at_2233():
    text = _text(NEW)
    assert text.count("(reported)") >= 3
    assert "#2233" in text
    for claim in ("Fires between turns", "A `compact` SessionStart hook firing"):
        bullet = next(line for line in text.splitlines() if claim in line)
        assert "(reported)" in bullet, claim


def test_window_env_var_is_never_set_by_the_adr_or_shipped_code():
    assert "CLAUDE_CODE_AUTO_COMPACT_WINDOW=" not in _text(NEW)
    for path in (
        REPO_ROOT / "plugins" / "dev-team" / "scripts" / "set_autocompact_env.py",
        REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib" / "autocompact_config.py",
    ):
        assert "AUTO_COMPACT_WINDOW" not in path.read_text(encoding="utf-8")
