"""Tests for scripts/citation_lint.py — the preventive skill-citation drift lint
(issue #312). Phase 1 is advisory (always exit 0); these pin the warning
behaviour on a tiny self-contained plugin tree.

``Cites:`` is a body-level declaration, not frontmatter (issue #1333 — it is
not part of the official Claude Code sub-agent contract).

Ported from tests/repo/citation_lint_tests.bats (issue #572: bash -> Python).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

LINT = REPO_ROOT / "scripts" / "citation_lint.py"


@pytest.fixture
def plugin(tmp_path: Path) -> Path:
    (tmp_path / "agents").mkdir()
    (tmp_path / "skills" / "complexity").mkdir(parents=True)
    (tmp_path / "knowledge").mkdir()
    (tmp_path / "skills" / "complexity" / "SKILL.md").write_text(
        "# Complexity\n"
        "Functions should be under 50 lines and 80% branch coverage is expected.\n"
    )
    (tmp_path / "knowledge" / "object-calisthenics.md").write_text(
        "Object calisthenics: no more than 2 instance variables.\n"
    )
    return tmp_path


def _lint(plugin: Path, target: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(LINT), "--plugin-root", str(plugin), str(target)],
        capture_output=True,
        text=True,
    )


def test_cites_present_and_thresholds_backed_no_warning(plugin: Path) -> None:
    target = plugin / "agents" / "clean.md"
    target.write_text(
        """---
name: clean
---
# Clean
Cites: [complexity, object-calisthenics]
Functions MUST be under 50 lines. Coverage SHOULD reach 80%.
Classes MUST hold no more than 2 instance variables.
"""
    )
    res = _lint(plugin, target)
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert "Citation lint OK" in out


def test_cites_present_but_threshold_uncited_warns(plugin: Path) -> None:
    target = plugin / "agents" / "drift.md"
    target.write_text(
        """---
name: drift
---
# Drift
Cites: [complexity]
Functions MUST be under 40 lines.
"""
    )
    res = _lint(plugin, target)
    out = res.stdout + res.stderr
    assert res.returncode == 0, out  # Phase 1 non-blocking
    assert "'40'" in out  # the drifted token
    assert "drift:6:" in out  # token line number in the file
    assert "possible drift" in out


def test_no_cites_no_normative_tokens_no_warning(plugin: Path) -> None:
    target = plugin / "agents" / "prose.md"
    target.write_text(
        """---
name: prose
---
# Prose
This agent reviews naming clarity and reports issues.
"""
    )
    res = _lint(plugin, target)
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert "Citation lint OK" in out


def test_no_cites_but_normative_tokens_advisory_warning(plugin: Path) -> None:
    target = plugin / "agents" / "advise.md"
    target.write_text(
        """---
name: advise
---
# Advise
Functions MUST be under 50 lines.
"""
    )
    res = _lint(plugin, target)
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert "advisory" in out
    assert "declares no `Cites:`" in out


def test_thresholds_inside_code_fences_not_flagged(plugin: Path) -> None:
    target = plugin / "agents" / "fenced.md"
    target.write_text(
        """---
name: fenced
---
# Fenced
Cites: [complexity]

```
Functions MUST be under 40 lines.
```
"""
    )
    res = _lint(plugin, target)
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert "Citation lint OK" in out  # the 40 in the fence is ignored


def test_thresholds_inside_blockquotes_not_flagged(plugin: Path) -> None:
    target = plugin / "agents" / "quoted.md"
    target.write_text(
        """---
name: quoted
---
# Quoted
Cites: [complexity]
> Functions MUST be under 40 lines.
"""
    )
    res = _lint(plugin, target)
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert "Citation lint OK" in out


def test_cites_unknown_source_yields_warning(plugin: Path) -> None:
    target = plugin / "agents" / "badcite.md"
    target.write_text(
        """---
name: badcite
---
# BadCite
Cites: [does-not-exist]
Functions MUST be under 50 lines.
"""
    )
    res = _lint(plugin, target)
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert "unknown source" in out
    assert "does-not-exist" in out


def test_block_list_cites_syntax_parsed(plugin: Path) -> None:
    target = plugin / "agents" / "block.md"
    target.write_text(
        """---
name: block
---
# Block
Cites:
- complexity
- object-calisthenics

Functions MUST be under 50 lines and hold no more than 2 variables.
"""
    )
    res = _lint(plugin, target)
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert "Citation lint OK" in out


def test_issue_refs_not_treated_as_thresholds(plugin: Path) -> None:
    target = plugin / "agents" / "issueref.md"
    target.write_text(
        """---
name: issueref
---
# IssueRef
Cites: [complexity]
This rule MUST follow the contract from #99 and #312.
"""
    )
    res = _lint(plugin, target)
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert "Citation lint OK" in out  # 99 / 312 are issue refs, not thresholds
