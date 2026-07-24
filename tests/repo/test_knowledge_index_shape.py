"""The shipped knowledge/index.json exists, parses as JSON, and contains
exactly the in-scope corpus.

Ported from tests/repo/knowledge_index_shape.bats (issue #671).
"""

from __future__ import annotations

import json
import re

from _repo_root import REPO_ROOT

INDEX = REPO_ROOT / "plugins" / "dev-team" / "knowledge" / "index.json"

_CORPUS_KEY_RE = re.compile(
    r"^plugins/dev-team/(knowledge/[^/]+\.md|skills/[^/]+/SKILL\.md)$"
)


def _load_index() -> dict:
    return json.loads(INDEX.read_text())


def test_index_file_exists_and_parses_as_json() -> None:
    assert INDEX.is_file()
    _load_index()  # raises if not valid JSON


def test_every_knowledge_md_excluding_schemas_appears_as_top_level_key() -> None:
    data = _load_index()
    knowledge_dir = REPO_ROOT / "plugins" / "dev-team" / "knowledge"
    missing = []
    for f in knowledge_dir.glob("*.md"):
        key = str(f.relative_to(REPO_ROOT))
        if key not in data:
            missing.append(key)
    assert not missing, f"missing key(s): {missing}"


def test_every_skill_md_appears_as_top_level_key() -> None:
    data = _load_index()
    skills_dir = REPO_ROOT / "plugins" / "dev-team" / "skills"
    missing = []
    for f in skills_dir.glob("*/SKILL.md"):
        key = str(f.relative_to(REPO_ROOT))
        if key not in data:
            missing.append(key)
    assert not missing, f"missing key(s): {missing}"


def test_no_file_outside_the_corpus_appears_as_a_top_level_key() -> None:
    data = _load_index()
    bad = [k for k in data if not _CORPUS_KEY_RE.match(k)]
    assert not bad, f"out-of-corpus keys found: {bad}"


def test_knowledge_schemas_subdirectory_is_excluded() -> None:
    data = _load_index()
    assert not any("knowledge/schemas" in k for k in data)


def test_no_docs_agents_or_commands_paths_appear() -> None:
    data = _load_index()
    keys = list(data.keys())
    assert not any("/docs/" in k for k in keys)
    assert not any("/agents/" in k for k in keys)
    assert not any("/commands/" in k for k in keys)
