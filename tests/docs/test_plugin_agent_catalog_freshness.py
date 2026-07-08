"""Disk-vs-catalog freshness tests for security-assessment and marketplace-dev agent catalogs.

Each plugin ships an ``agent_info.md`` that documents its agents. These tests compare the
``agents/*.md`` files on disk directly against the ``agent_info.md`` rows, so an added or removed
agent fails loudly rather than silently drifting.

Unlike ``test_agent_info_registry_sync.py`` (which diffs two registered-table sources), these
tests use the filesystem as the ground truth since neither plugin has an ``agent-registry.md``
equivalent.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

_ROW_RE = re.compile(r"^\|\s*([a-z0-9][a-z0-9-]*)\s*\|")


def _catalog_agent_names(agent_info_path: Path) -> set[str]:
    """Parse agent names from a markdown table in agent_info.md.

    Matches the first cell of every table row that begins with a lowercase
    agent-name token (skips header rows and separator rows).
    """
    names: set[str] = set()
    for line in agent_info_path.read_text(encoding="utf-8").splitlines():
        m = _ROW_RE.match(line.strip())
        if m and m.group(1) not in ("agent", "---"):
            names.add(m.group(1))
    return names


def _disk_agent_names(agents_dir: Path) -> set[str]:
    """Return the stems of every ``*.md`` file in ``agents/``."""
    return {p.stem for p in agents_dir.glob("*.md")}


# --------------------------------------------------------------------------- #
# security-assessment
# --------------------------------------------------------------------------- #

SA_PLUGIN = REPO_ROOT / "plugins" / "security-assessment"
SA_AGENT_INFO = SA_PLUGIN / "docs" / "agent_info.md"
SA_AGENTS_DIR = SA_PLUGIN / "agents"


def test_security_assessment_catalog_no_missing_agents() -> None:
    """Every agent .md on disk must appear in agent_info.md."""
    disk = _disk_agent_names(SA_AGENTS_DIR)
    catalog = _catalog_agent_names(SA_AGENT_INFO)
    missing = disk - catalog
    assert not missing, (
        f"security-assessment/docs/agent_info.md is missing rows for agents present on disk: "
        f"{sorted(missing)}"
    )


def test_security_assessment_catalog_no_stale_entries() -> None:
    """Every agent row in agent_info.md must have a corresponding .md file on disk."""
    disk = _disk_agent_names(SA_AGENTS_DIR)
    catalog = _catalog_agent_names(SA_AGENT_INFO)
    stale = catalog - disk
    assert not stale, (
        f"security-assessment/docs/agent_info.md has stale rows for agents no longer on disk: "
        f"{sorted(stale)}"
    )


def test_security_assessment_catalog_all_13_agents_present() -> None:
    """Regression guard: the catalog must list all 13 known agents."""
    catalog = _catalog_agent_names(SA_AGENT_INFO)
    assert len(catalog) == 13, (
        f"Expected 13 security-assessment agents in the catalog, got {len(catalog)}: "
        f"{sorted(catalog)}"
    )


# --------------------------------------------------------------------------- #
# marketplace-dev
# --------------------------------------------------------------------------- #

MD_PLUGIN = REPO_ROOT / "plugins" / "marketplace-dev"
MD_AGENT_INFO = MD_PLUGIN / "docs" / "agent_info.md"
MD_AGENTS_DIR = MD_PLUGIN / "agents"


def test_marketplace_dev_catalog_no_missing_agents() -> None:
    """Every agent .md on disk must appear in agent_info.md."""
    disk = _disk_agent_names(MD_AGENTS_DIR)
    catalog = _catalog_agent_names(MD_AGENT_INFO)
    missing = disk - catalog
    assert not missing, (
        f"marketplace-dev/docs/agent_info.md is missing rows for agents present on disk: "
        f"{sorted(missing)}"
    )


def test_marketplace_dev_catalog_no_stale_entries() -> None:
    """Every agent row in agent_info.md must have a corresponding .md file on disk."""
    disk = _disk_agent_names(MD_AGENTS_DIR)
    catalog = _catalog_agent_names(MD_AGENT_INFO)
    stale = catalog - disk
    assert not stale, (
        f"marketplace-dev/docs/agent_info.md has stale rows for agents no longer on disk: "
        f"{sorted(stale)}"
    )


def test_marketplace_dev_catalog_1_agent_present() -> None:
    """Regression guard: the catalog must list the 1 known agent."""
    catalog = _catalog_agent_names(MD_AGENT_INFO)
    assert len(catalog) == 1, (
        f"Expected 1 marketplace-dev agent in the catalog, got {len(catalog)}: "
        f"{sorted(catalog)}"
    )
