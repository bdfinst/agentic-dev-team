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
