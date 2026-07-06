"""Stale `.sh` filename references left behind by ADR 0015 (bash removal).

ADR 0014/0015 ported every shipped `plugins/dev-team/` script from bash to
Python (epic #572). A handful of docs and skills still name the old `.sh`
filename in prose even though the implementing file on disk is now `.py`
(issue #732). This is a doc-drift sensor, not a functional guard: it asserts
(1) the stale `.sh` name no longer appears in the specific file/line the
audit found, and (2) the real `.py` file the prose *should* point at
actually exists on disk, so a future rename can't silently go stale again.

Ported as a new content-guard test for issue #732 (no bats predecessor).
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

REPO_ROOT = Path(__file__).resolve().parents[2]


class StaleRef(NamedTuple):
    doc: str  # file expected to be free of the stale .sh name
    stale_name: str  # the old .sh filename that should no longer appear
    real_file: str  # the actual .py file on disk that replaced it


STALE_REFS = [
    StaleRef(
        "plugins/dev-team/hooks/lib/build_skills_index.py",
        "build-skills-index.sh",
        "plugins/dev-team/hooks/lib/build_skills_index.py",
    ),
    StaleRef(
        "plugins/dev-team/docs/skills.md",
        "build-skills-index.sh",
        "plugins/dev-team/hooks/lib/build_skills_index.py",
    ),
    StaleRef(
        "plugins/dev-team/skills/mutation-testing/references/languages/"
        "csharp-stryker-net.md",
        "stryker-net.sh",
        "plugins/dev-team/hooks/mutation_adapters/stryker_net.py",
    ),
    StaleRef(
        "plugins/dev-team/docs/agent-architecture.md",
        "plan-waves.sh",
        "plugins/dev-team/scripts/plan_waves.py",
    ),
    StaleRef(
        "plugins/dev-team/docs/agent-architecture.md",
        "pre-tool-guard.sh",
        "plugins/dev-team/hooks/pre_tool_guard.py",
    ),
    StaleRef(
        "plugins/dev-team/docs/codegraph-nudge.md",
        "destructive-guard.sh",
        "plugins/dev-team/hooks/destructive_guard.py",
    ),
    StaleRef(
        "plugins/dev-team/docs/codegraph-nudge.md",
        "codegraph-turn-mark.sh",
        "plugins/dev-team/hooks/codegraph_turn_mark.py",
    ),
    StaleRef(
        "plugins/dev-team/skills/freeze/SKILL.md",
        "pre-tool-guard.sh",
        "plugins/dev-team/hooks/pre_tool_guard.py",
    ),
    StaleRef(
        "plugins/dev-team/skills/careful/SKILL.md",
        "destructive-guard.sh",
        "plugins/dev-team/hooks/destructive_guard.py",
    ),
    StaleRef(
        "plugins/dev-team/skills/plan/SKILL.md",
        "plan-waves.sh",
        "plugins/dev-team/scripts/plan_waves.py",
    ),
    StaleRef(
        "plugins/dev-team/skills/issues-from-plan/SKILL.md",
        "issue-deps.sh",
        "plugins/dev-team/scripts/issue_deps.py",
    ),
    StaleRef(
        "setup-prereqs-linux.sh",
        "codegraph-bootstrap.sh",
        "plugins/dev-team/hooks/codegraph_bootstrap.py",
    ),
]


def test_real_py_replacement_files_exist_on_disk() -> None:
    missing = sorted(
        {
            ref.real_file
            for ref in STALE_REFS
            if not (REPO_ROOT / ref.real_file).is_file()
        }
    )
    assert not missing, "Replacement .py file(s) not found on disk:\n" + "\n".join(
        missing
    )


def test_no_stale_sh_filename_remains_in_the_flagged_doc() -> None:
    failures = []
    for ref in STALE_REFS:
        path = REPO_ROOT / ref.doc
        if not path.is_file():
            failures.append(f"{ref.doc}: file not found")
            continue
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            if ref.stale_name in line:
                failures.append(
                    f"{ref.doc}:{lineno}: still references {ref.stale_name!r}: {line.strip()}"
                )
    assert not failures, "Stale .sh reference(s) found:\n" + "\n".join(failures)
