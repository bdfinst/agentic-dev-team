"""Shared merge helper and `.sln`/`.csproj`/`package.json` fixture writers
for the coverage-baseline/coverage-delta flow simulation test helpers (issue
#1759, issue #1852).

`_merge_included_reports` was byte-for-byte duplicated between
`coverage_baseline_flow_helpers.py` and `coverage_delta_flow_helpers.py` —
extracted here so both import a single implementation instead of maintaining
two copies in sync by hand.

`write`/`sln`/`pkg` were redefined verbatim across 12 test files (issue
#1852). Two behaviorally-equivalent `write` variants existed: a str-only
form, and a form that also JSON-encodes dict/list content for
`package.json` fixtures. The JSON-aware form is a strict superset — for str
content it behaves identically to the str-only form — so it is the one
kept here; every prior caller only ever passed str content.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from skill_doc_helpers import PLUGIN_ROOT

SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from coverage_config import weighted_merge


def write(path: Path, content) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, (dict, list)):
        path.write_text(json.dumps(content, indent=2), encoding="utf-8")
    else:
        path.write_text(content, encoding="utf-8")


def sln(repo_root: Path, name: str = "App.sln") -> None:
    write(repo_root / name, "Microsoft Visual Studio Solution File\n")


def pkg(root: Path, data: dict) -> None:
    write(root / "package.json", data)


def merge_included_reports(
    included: list, discovered: list, project_reports_by_path: dict
) -> dict:
    """Merge per-project reports for every path in `included`, distinguishing
    two reasons a path can be missing from `project_reports_by_path`:

    - **Legitimately stale** — the path is no longer in `discovered` at all
      (it was removed/renamed since `included` was written). `drift_check`
      doesn't check `included` entries for staleness (only `excluded`), so
      this is the one place that class of gap is tolerated — skip silently,
      matching the existing "stale exclusions are a warning, not a failure"
      precedent.
    - **Wired wrong** — the path is in BOTH `included` and `discovered` but
      still has no matching report. That combination can't be legitimate
      drift; it means the calling test's fixture forgot to supply a report
      for a project the flow expects one for. Fail loudly rather than
      silently under-counting it into the merge — this is test-helper code,
      not production code, so a loud failure here is correct.
    """
    discovered_paths = {entry["path"] for entry in discovered}
    included_reports = []
    for path in included:
        if path in project_reports_by_path:
            included_reports.append(project_reports_by_path[path])
        elif path not in discovered_paths:
            continue  # legitimately stale; not this helper's job to flag
        else:
            raise AssertionError(
                f"{path!r} is in both config['included'] and the discovered "
                "projects, but has no matching entry in "
                "project_reports_by_path — the test fixture is wired wrong, "
                "not exercising a legitimate runtime gap."
            )
    return weighted_merge(included_reports)
