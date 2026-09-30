"""Contract test: /build's documented build-phase.json schema == the shared reader (#2177)."""

from __future__ import annotations

import json
import re
import sys

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"))

from build_state import RECORD_KEYS, read_active_build_state

_BUILD_SKILL = _REPO_ROOT / "plugins" / "dev-team" / "skills" / "build" / "SKILL.md"


def _documented_record_keys() -> list[str]:
    text = _BUILD_SKILL.read_text(encoding="utf-8")
    match = re.search(r"write `(\{\"phase\":.*?\})` at \*\*each\*\* phase transition", text)
    assert match, "build/SKILL.md no longer documents the build-phase.json schema line"
    return re.findall(r'"([a-z_]+)":', match.group(1))


def test_reader_keys_equal_the_documented_schema():
    assert _documented_record_keys() == list(RECORD_KEYS)


def test_reader_round_trips_a_record_built_from_the_documented_schema(tmp_path):
    (tmp_path / "plans").mkdir()
    (tmp_path / "plans" / "p.md").write_text("x", encoding="utf-8")
    record = {key: "" for key in _documented_record_keys()}
    record.update(
        phase="refactor",
        step="3.2",
        test_files_staged=[],
        plan_path="plans/p.md",
        written_at="2026-09-30T00:00:00Z",
    )
    state_file = tmp_path / ".claude" / "memory" / "build-phase.json"
    state_file.parent.mkdir(parents=True)
    state_file.write_text(json.dumps(record), encoding="utf-8")
    state = read_active_build_state(tmp_path)
    assert (state.phase, state.step, state.plan_path) == ("refactor", "3.2", "plans/p.md")
