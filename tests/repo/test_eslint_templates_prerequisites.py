"""Contributors must be told to install Node and run `npm ci`.

`chk_eslint_templates` needs Node, the repo-root ESLint 10 install, and the
pinned ESLint 9 install under `templates/eslint/dev`. CLAUDE.md names the
prerequisite and `scripts/dev-setup.sh` provisions it, so a fresh checkout is
ready to run the gate.
"""

from __future__ import annotations

import pytest

from _repo_root import REPO_ROOT

DOCS = [REPO_ROOT / "CLAUDE.md", REPO_ROOT / "scripts" / "dev-setup.sh"]


@pytest.mark.parametrize("path", DOCS, ids=lambda p: p.name)
def test_mentions_node_and_npm_ci(path):
    text = path.read_text(encoding="utf-8")
    assert "Node" in text, f"{path.name} must mention Node"
    assert "npm ci" in text, f"{path.name} must mention `npm ci`"


@pytest.mark.parametrize("path", DOCS, ids=lambda p: p.name)
def test_names_both_install_locations(path):
    text = path.read_text(encoding="utf-8")
    assert "templates/eslint/dev" in text, (
        f"{path.name} must name plugins/dev-team/templates/eslint/dev, the "
        "ESLint 9 install the gate runs against"
    )
