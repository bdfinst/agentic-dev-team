"""#574 — Python hook contract doc exists with required sections. The
settings-toggle mechanism was retired in #618 (epic #572 close), so its
doc + tests are gone; the contract doc itself survives as historical
reference + the still-authoritative statement of exit codes / stdin /
stderr / authoring rules for shipped Python hooks.

Ported from tests/docs/python_hook_contract_tests.bats (issue #675:
bats -> pytest).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT = REPO_ROOT / "docs" / "python-hook-contract.md"


@pytest.fixture(scope="module")
def text() -> str:
    return CONTRACT.read_text(encoding="utf-8")


def test_python_hook_contract_file_exists() -> None:
    assert CONTRACT.is_file()


def test_contract_names_stdin_json_schema(text: str) -> None:
    assert re.search(r"^## stdin", text, re.MULTILINE)


def test_contract_names_stdout_format(text: str) -> None:
    assert re.search(r"^## stdout", text, re.MULTILINE)


def test_contract_names_exit_codes(text: str) -> None:
    assert re.search(r"^## Exit codes", text, re.MULTILINE)
    assert re.search(r"\b0\b", text)
    assert re.search(r"\b1\b", text)
    assert re.search(r"\b2\b", text)


def test_contract_names_environment_variables(text: str) -> None:
    assert re.search(r"^## Environment variables", text, re.MULTILINE)
    assert "CLAUDE_PROJECT_DIR" in text


def test_contract_names_stderr_conventions(text: str) -> None:
    assert re.search(r"^## stderr", text, re.MULTILINE)


def test_contract_names_python_authoring_rules(text: str) -> None:
    assert re.search(r"^## Python authoring rules", text, re.MULTILINE)
    assert "stdlib" in text.lower()
    assert re.search(r"3\.8", text)
