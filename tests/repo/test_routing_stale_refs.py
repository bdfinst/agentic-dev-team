"""Stale-reference guard for the effort-band routing migration.

The canonical routing docs must describe the effort/ladder model and must
NOT:
  - use `complexity:` as the frontmatter band key (the spec's old wording),
  - mention any file removed by this migration (the probe, the overrides
    cache, the retired SessionStart banner, the /v1/models endpoint).

ADR 0004 and the CHANGELOG are intentionally NOT scanned: they are immutable
historical records (ADR 0004 carries an "Amended by 0008" banner).

ADR 0026 supersedes ADR 0008 and restores `model: <tier>` as the native,
correct frontmatter contract (epic #1284) — the check that used to forbid it
here is gone; `docs/model-routing.md`/`model-routing-overrides.md` and the
rest of this file's assertions are retired along with the infrastructure
they describe in #1288, not here.

Ported from tests/repo/routing_stale_refs_tests.bats (#673).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parents[2]

# Canonical, current-facing routing docs.
FILES = [
    "CLAUDE.md",
    "plugins/dev-team/CLAUDE.md",
    "plugins/dev-team/docs/model-routing.md",
    "plugins/dev-team/docs/model-routing-overrides.md",
    "plugins/dev-team/docs/agent-architecture.md",
    "plugins/dev-team/docs/concurrent-use.md",
    "plugins/dev-team/docs/session-review.md",
    "plugins/dev-team/agents/orchestrator.md",
    "plugins/dev-team/skills/model-routing-check/SKILL.md",
    "plugins/dev-team/skills/session-review/SKILL.md",
    "docs/adr/0008-use-effort-bands-instead-of-model-names-in-agent-frontmatter.md",
]


def _matches(pattern: str) -> List[str]:
    regex = re.compile(pattern)
    fails = []
    for rel in FILES:
        path = REPO_ROOT / rel
        if not path.is_file():
            continue
        hit_lines = []
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            if regex.search(line):
                hit_lines.append(f"{lineno}:{line}")
        if hit_lines:
            fails.append(f"{rel}:\n" + "\n".join(hit_lines))
    return fails


def test_no_canonical_routing_doc_mentions_a_removed_file() -> None:
    fails = _matches(r"model-probe|overrides-banner\.sh|model-overrides|/v1/models")
    assert not fails, "Removed-file references found:\n" + "\n".join(fails)


def test_no_canonical_routing_doc_uses_complexity_as_the_band_key() -> None:
    fails = _matches(r"complexity:\s*(low|medium|high)")
    assert not fails, "Stale complexity: band key found:\n" + "\n".join(fails)


def test_routing_contract_doc_and_override_guide_describe_effort_ladder_model() -> None:
    text = (REPO_ROOT / "plugins/dev-team/docs/model-routing.md").read_text().lower()
    assert "effort" in text
    assert "ladder" in text


def test_model_routing_override_guide_exists() -> None:
    assert (REPO_ROOT / "plugins/dev-team/docs/model-routing-overrides.md").is_file()


def test_override_guide_documents_ladder_schema_and_resolution_precedence() -> None:
    text = (REPO_ROOT / "plugins/dev-team/docs/model-routing-overrides.md").read_text()
    assert ".claude/model-ladder.json" in text
    assert "precedence" in text.lower()
    assert "default map" in text.lower()
    assert "session" in text.lower()


def test_override_guide_shows_worked_ladders() -> None:
    text = (
        (REPO_ROOT / "plugins/dev-team/docs/model-routing-overrides.md")
        .read_text()
        .lower()
    )
    assert "single-model" in text
    assert re.search(r"bedrock|vertex", text)


def test_override_guide_states_the_migration_guarantee() -> None:
    text = (
        (REPO_ROOT / "plugins/dev-team/docs/model-routing-overrides.md")
        .read_text()
        .lower()
    )
    assert re.search(
        r"migrat|no ladder.*default|default map.*identical|identical.*default", text
    )


def test_readme_links_the_override_guide_in_the_docs_toc() -> None:
    assert "docs/model-routing-overrides.md" in (REPO_ROOT / "README.md").read_text()
