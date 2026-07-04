"""Every ADR under docs/adr/ must be discoverable from docs/adr/README.md.

Issue #732: the README's table of contents stopped at ADR 0012 while ADRs
0013 (LLM-driven orchestration), 0014 (Python for cross-OS scripts), and
0015 (bash removal complete) were added to the directory without a
corresponding README entry. This is a deterministic completeness sensor,
not a content sensor: it only asserts every `NNNN-*.md` file in docs/adr/
has a markdown link to itself somewhere in the README, not that the link
text or ordering is any particular shape.

Ported as a new content-guard test for issue #732 (no bats predecessor).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ADR_DIR = REPO_ROOT / "docs" / "adr"
README = ADR_DIR / "README.md"

_ADR_FILENAME_RE = re.compile(r"^\d{4}-.+\.md$")


def _adr_filenames() -> list[str]:
    return sorted(
        p.name
        for p in ADR_DIR.iterdir()
        if p.is_file() and _ADR_FILENAME_RE.match(p.name)
    )


def test_adr_directory_has_at_least_the_expected_records() -> None:
    # Sanity check the fixture assumption itself hasn't rotted.
    names = _adr_filenames()
    assert "0014-python-for-cross-os-scripts.md" in names
    assert "0015-bash-removal-complete.md" in names


def test_every_adr_file_is_linked_from_the_readme_toc() -> None:
    readme_text = README.read_text()
    missing = [name for name in _adr_filenames() if f"]({name})" not in readme_text]
    assert not missing, "ADR(s) not linked from docs/adr/README.md:\n" + "\n".join(
        missing
    )
