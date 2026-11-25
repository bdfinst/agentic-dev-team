"""Contributors must be told to install Node and run `npm ci`, and be set up for it.

`chk_eslint_templates` needs Node, the repo-root ESLint 10 install, and the
pinned ESLint 9 install under `templates/eslint/dev`. CLAUDE.md names the
prerequisite and `scripts/dev-setup.sh` provisions it, so a fresh checkout is
ready to run the gate. These tests pin the two files against each other and
against `.nvmrc` / `package.json`.
"""

from __future__ import annotations

import json
import re

from _repo_root import REPO_ROOT

CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
DEV_SETUP = REPO_ROOT / "scripts" / "dev-setup.sh"
NVMRC = REPO_ROOT / ".nvmrc"
PACKAGE_JSON = REPO_ROOT / "package.json"
DEV_TREE = "plugins/dev-team/templates/eslint/dev"
NPM_DIR_LOOP = re.compile(r"for\s+npm_dir\s+in\s+([^;]+);\s*do")
NODE_FLOOR = re.compile(r"Node \(>= (\d+)")


def _claude_node_line() -> str:
    lines = [
        line
        for line in CLAUDE_MD.read_text(encoding="utf-8").splitlines()
        if line.startswith("- Node (")
    ]
    assert len(lines) == 1, (
        "CLAUDE.md must have exactly one '- Node (' prerequisite line"
    )
    return lines[0]


def test_claude_md_node_line_names_npm_ci():
    assert "`npm ci`" in _claude_node_line(), (
        "the CLAUDE.md Node prerequisite line must tell contributors to run `npm ci`"
    )


def test_claude_md_line_names_both_install_locations():
    line = _claude_node_line()
    assert "repo root" in line, (
        "the CLAUDE.md Node line must name the repo root install"
    )
    assert "templates/eslint/dev" in line, (
        f"the CLAUDE.md Node line must name {DEV_TREE}, the ESLint 9 install"
    )


def test_dev_setup_installs_in_the_repo_root_and_the_dev_tree():
    match = NPM_DIR_LOOP.search(DEV_SETUP.read_text(encoding="utf-8"))
    assert match is not None, "dev-setup.sh must loop `for npm_dir in ...; do`"
    assert match.group(1).split() == [".", DEV_TREE], (
        "dev-setup.sh must run npm ci at the repo root and in the template dev tree"
    )


def test_claude_md_node_floor_matches_package_json_engines():
    floor = NODE_FLOOR.search(_claude_node_line())
    assert floor is not None, "the CLAUDE.md Node line must state '(>= N'"
    engines = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))["engines"]["node"]
    assert engines == f">={floor.group(1)}", (
        f"CLAUDE.md says Node >= {floor.group(1)} but package.json engines says {engines}"
    )


def test_nvmrc_major_satisfies_the_floor_claude_md_states():
    floor = int(NODE_FLOOR.search(_claude_node_line()).group(1))
    pinned = int(NVMRC.read_text(encoding="utf-8").strip().lstrip("v").split(".")[0])
    assert pinned >= floor, (
        f".nvmrc pins Node {pinned}, below the documented floor {floor}"
    )
