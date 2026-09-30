"""ADR 0043 records the autocompact decision and its harness constraints (#2177, AC 8)."""

from __future__ import annotations

import re
from pathlib import Path

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
    assert status.lstrip().startswith("Superseded"), "status must lead with Superseded"


def test_relative_links_in_adr_0043_resolve():
    targets = re.findall(r"\]\((?!https?://|#)([^)#\s]+)", _text(NEW))
    assert targets, "ADR 0043 links to nothing"
    for target in targets:
        assert (ADR_DIR / target).resolve().exists(), target


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
        bullet = next((line for line in text.splitlines() if claim in line), None)
        assert bullet is not None, f"ADR 0043 has no line containing {claim!r}"
        assert "(reported)" in bullet, claim


_WINDOW_VAR = "CLAUDE_CODE_AUTO_COMPACT" + "_WINDOW"
# Setting shapes: NAME=, NAME" (JSON key), NAME: (YAML/JSON), NAME then a number.
_WINDOW_SET_RE = re.compile(_WINDOW_VAR + r"(?:=|\"|:|\s+\d)")
_SHIPPED = REPO_ROOT / "plugins" / "dev-team"
_WINDOW_ALLOWED = {
    ADR_DIR / NEW,
    REPO_ROOT / "tests" / "docs" / "test_adr_0043_autocompact.py",
    REPO_ROOT / "tests" / "skills" / "test_setup_autocompact_step.py",
}


def _shipped_files():
    for name in ("hooks", "scripts", "skills"):
        root = _SHIPPED / name
        assert root.is_dir(), root
        yield from (p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    yield _SHIPPED / "settings.json"
    yield _SHIPPED / "hooks" / "hooks.json"


def _window_var_setters(paths) -> list[Path]:
    hits = []
    for path in paths:
        if path in _WINDOW_ALLOWED:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if _WINDOW_SET_RE.search(text):
            hits.append(path)
    return hits


def test_window_env_var_is_never_set_by_the_adr_or_shipped_code():
    files = list(_shipped_files())
    assert len(files) > 100, "shipped-file scan visited suspiciously few files"
    assert "deliberately not used anywhere" in _text(NEW)
    assert _window_var_setters(files) == []
    assert _WINDOW_SET_RE.search(_text(NEW)) is None


@pytest.mark.parametrize(
    "sample",
    [
        _WINDOW_VAR + "=400000",
        '"' + _WINDOW_VAR + '": "400000"',
        _WINDOW_VAR + ": 400000",
        _WINDOW_VAR + " 400000",
    ],
)
def test_window_setter_detector_flags_each_shape(tmp_path, sample):
    assert _WINDOW_SET_RE.search(sample), sample
    probe = tmp_path / "probe.txt"
    probe.write_text(sample + "\n", encoding="utf-8")
    assert _window_var_setters([probe]) == [probe]


def test_window_setter_detector_ignores_a_bare_mention(tmp_path):
    probe = tmp_path / "probe.txt"
    probe.write_text("we never use " + _WINDOW_VAR + " here\n", encoding="utf-8")
    assert _window_var_setters([probe]) == []
