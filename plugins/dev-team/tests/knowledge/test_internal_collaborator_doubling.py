"""Content contract for knowledge/internal-collaborator-doubling.md (#2124),
the single normative source for epic #2123's internal-collaborator doubling
rule.

Assertions verify structural presence and non-duplication only — that the
required content exists, and exists in exactly one place. They cannot close
AC16's full negative-space claim (no *contradicting* exemption language
anywhere in the file); that is a human `/code-review` judgment, not a grep.
"""

from __future__ import annotations

import re

import pytest

from _repo_root import REPO_ROOT

DOC = REPO_ROOT / "plugins" / "dev-team" / "knowledge" / "internal-collaborator-doubling.md"

TREE_ROOTS = ("knowledge", "agents", "skills")


@pytest.fixture(scope="module")
def text() -> str:
    return DOC.read_text(encoding="utf-8")


def test_doc_exists() -> None:
    assert DOC.is_file()


# --- Required sections ---


def test_states_the_rule_heading(text: str) -> None:
    assert "## The rule" in text


def test_states_the_rule_content(text: str) -> None:
    assert "stays real" in text
    assert "admissible only when that collaborator matches a blocker" in text


def test_blocker_table_heading(text: str) -> None:
    assert "## The three blockers" in text


def test_blocker_table_has_three_rows_with_remedy(text: str) -> None:
    for blocker, keyword in (
        ("B1", "Out-of-process handle"),
        ("B2", "Ambient state"),
        ("B3", "Prohibitive real cost"),
    ):
        assert blocker in text
        assert keyword in text
    # Each row has a "Preferred remedy" — verify the column header exists
    # once, and three data rows follow it (one per blocker).
    assert "Preferred remedy before doubling" in text
    row_count = len(re.findall(r"\|\s*\*\*B[123]\*\*\s*\|", text))
    assert row_count == 3


def test_non_reasons_heading(text: str) -> None:
    assert "## Non-reasons" in text


def test_non_reasons_lists_required_items(text: str) -> None:
    assert "Setup is easier" in text
    assert "It's an injected interface" in text


def test_patching_never_admissible_heading(text: str) -> None:
    assert "## Patching internal functions" in text


def test_patching_never_admissible_content(text: str) -> None:
    assert "never" in text and "admissible" in text
    for term in ("patch", "spyOn", "monkeypatch"):
        assert term.lower() in text.lower()


def test_waiver_contract_heading(text: str) -> None:
    assert "## The waiver" in text


def test_waiver_marker_present(text: str) -> None:
    assert "double-waiver: B" in text


def test_declaration_never_exempts_heading(text: str) -> None:
    assert "## A declaration never exempts" in text


def test_declaration_never_exempts_content(text: str) -> None:
    assert "solitary" in text.lower()
    assert "sociable" in text.lower()
    assert "never exempts" in text.lower() or "neither exempts" in text.lower()


def test_cross_reference_present(text: str) -> None:
    assert "test-doubles.md" in text
    assert "component-test-patterns.md" in text


# --- Non-duplication (tree-wide) ---


def _iter_other_md_files():
    plugin_root = REPO_ROOT / "plugins" / "dev-team"
    for root_name in TREE_ROOTS:
        root = plugin_root / root_name
        if not root.is_dir():
            continue
        for path in root.rglob("*.md"):
            if path.resolve() == DOC.resolve():
                continue
            yield path


@pytest.mark.parametrize(
    "needle",
    [
        "Out-of-process handle",
        "Prohibitive real cost",
        "double-waiver: B",
        "It's an injected interface",
        "stays real",
    ],
)
def test_blocker_content_not_duplicated_elsewhere(needle: str) -> None:
    offenders = []
    for path in _iter_other_md_files():
        content = path.read_text(encoding="utf-8", errors="ignore")
        if needle in content:
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, (
        f"'{needle}' from internal-collaborator-doubling.md duplicated in: {offenders}"
    )
