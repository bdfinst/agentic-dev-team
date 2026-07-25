"""Content-guard: artifact-usage.json readers are home-scoped (AC20, Finding
1; Slice 5 Step 5.10, plan opt-in-metrics-and-claude-scoped-artifacts.md).

`telemetry.py` (Slice 1) writes artifact-usage.json exclusively under
`~/.claude/metrics/` — the bare project-scoped `metrics/artifact-usage.json`
path will never again be populated. The five reader surfaces below still
described the stale project-scoped path (a correctness bug, not staleness);
every occurrence must now read `~/.claude/metrics/artifact-usage.json`.
"""

from __future__ import annotations

import re

from skill_doc_helpers import PLUGIN_ROOT

_FILES = {
    "artifact-lifecycle/SKILL.md": PLUGIN_ROOT / "skills" / "artifact-lifecycle" / "SKILL.md",
    "harness-audit/SKILL.md": PLUGIN_ROOT / "skills" / "harness-audit" / "SKILL.md",
    "knowledge/artifact-lifecycle.md": PLUGIN_ROOT / "knowledge" / "artifact-lifecycle.md",
    "docs/workflows.md": PLUGIN_ROOT / "docs" / "workflows.md",
    "docs/skills.md": PLUGIN_ROOT / "docs" / "skills.md",
}

# A bare or .claude/-nested (but not home-scoped) artifact-usage.json path —
# i.e. anything other than the `~/.claude/metrics/` prefix.
_STALE_PATH_RE = re.compile(r"(?<!~/\.claude/metrics/)artifact-usage\.json")


def test_all_five_files_exist():
    for label, path in _FILES.items():
        assert path.is_file(), f"expected file missing: {label}"


def test_no_stale_project_scoped_references_remain():
    offenders = []
    for label, path in _FILES.items():
        text = path.read_text(encoding="utf-8")
        for m in _STALE_PATH_RE.finditer(text):
            window = text[max(0, m.start() - 20) : m.end()]
            offenders.append(f"{label}: ...{window}...")
    assert not offenders, f"stale artifact-usage.json references found: {offenders}"


def test_every_file_references_the_home_scoped_path():
    for label, path in _FILES.items():
        text = path.read_text(encoding="utf-8")
        assert "~/.claude/metrics/artifact-usage.json" in text, (
            f"{label} does not reference the home-scoped artifact-usage.json path"
        )
