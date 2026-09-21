"""Tests for skills/property-based-testing/scripts/hypothesis_scaffold.py (#2190).

Covers: the round-trip heuristic (encode/decode pair), the invariant
heuristic (docstring postcondition near a type hint), and the negative case
(neither heuristic matches -> exact message, no file written). The
round-trip and invariant generated test files are additionally run via a
real `pytest` subprocess to confirm they pass against `hypothesis`-generated
inputs, not just that the source text looks right.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

SKILL_DIR = REPO_ROOT / "plugins" / "dev-team" / "skills" / "property-based-testing"
SCRIPTS_DIR = SKILL_DIR / "scripts"
FIXTURES_DIR = SKILL_DIR / "fixtures"

sys.path.insert(0, str(SCRIPTS_DIR))

from hypothesis_scaffold import NO_PROPERTY_MESSAGE, scaffold


def _run_generated_test(test_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "pytest", str(test_path), "-q"],
        capture_output=True,
        text=True,
        check=False,
    )


def test_roundtrip_fixture_generates_passing_decode_encode_property(tmp_path) -> None:
    module_path = FIXTURES_DIR / "roundtrip_fixture.py"

    out_path = scaffold(str(module_path), "encode", str(tmp_path))

    assert out_path is not None
    generated = Path(out_path)
    assert generated.exists()
    content = generated.read_text(encoding="utf-8")
    assert "encoded = encode(x)" in content
    assert "assert decode(encoded) == x" in content

    result = _run_generated_test(generated)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout


def test_invariant_fixture_generates_passing_sorted_property(tmp_path) -> None:
    module_path = FIXTURES_DIR / "invariant_fixture.py"

    out_path = scaffold(str(module_path), "sort_values", str(tmp_path))

    assert out_path is not None
    generated = Path(out_path)
    assert generated.exists()
    content = generated.read_text(encoding="utf-8")
    assert "assert result == sorted(result)" in content

    result = _run_generated_test(generated)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout


def test_no_derivable_property_prints_exact_message_and_writes_nothing(
    tmp_path, capsys
) -> None:
    module_path = FIXTURES_DIR / "no_property_fixture.py"

    out_path = scaffold(str(module_path), "add_one", str(tmp_path))

    assert out_path is None
    captured = capsys.readouterr()
    assert captured.out.strip() == NO_PROPERTY_MESSAGE.format(function="add_one")
    assert list(tmp_path.iterdir()) == []


def test_non_identifier_module_filename_is_rejected_before_rendering(tmp_path) -> None:
    """A module basename that isn't a valid Python identifier must never
    reach the generated test's `from {module} import ...` line — that value
    is interpolated unescaped, so a filename crafted with e.g. a newline
    could otherwise inject arbitrary statements into a file pytest later
    collects and executes (security-review finding). A basename containing
    a space is enough to demonstrate the rejection; the underlying check
    (`str.isidentifier()`) rejects any such shape, newlines included."""
    module_path = tmp_path / "not an identifier.py"
    module_path.write_text(
        "def encode(x):\n    return x\n\n\ndef decode(x):\n    return x\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="not an identifier"):
        scaffold(str(module_path), "encode", str(tmp_path / "out"))
    assert not (tmp_path / "out").exists()


def test_class_method_invariant_is_not_derived_as_module_level(
    tmp_path, capsys
) -> None:
    """A method with an invariant-shaped docstring must not be scaffolded as
    a module-level function — the invariant render path assumes `from
    {module} import {function_name}` works, which is false for a method
    (regression: previously produced an unimportable generated test file,
    since ast.walk() matched the method the same way it would a module-level
    function)."""
    module_path = tmp_path / "class_invariant_module.py"
    module_path.write_text(
        "class Sorter:\n"
        "    def sort_values(self, values: list[int]) -> list[int]:\n"
        '        """Returns sorted output."""\n'
        "        return sorted(values)\n",
        encoding="utf-8",
    )

    out_dir = tmp_path / "out"
    out_path = scaffold(str(module_path), "sort_values", str(out_dir))

    assert out_path is None
    captured = capsys.readouterr()
    assert captured.out.strip() == NO_PROPERTY_MESSAGE.format(function="sort_values")
    assert not out_dir.exists() or list(out_dir.iterdir()) == []
