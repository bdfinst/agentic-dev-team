"""Shared builders for acceptance-examination tests (#2270).

The pinned temp repository (`make_repo`), `git_env`, and the `row`/`record`
dict builders live in `plugins/dev-team/tests/lib/examination_repo.py`, shared
with the hook tests. Importing this module puts that directory on `sys.path`,
so import it before `examination_repo`.

`write_met_record` writes a record bound to the repository's real branch
binding and the plan's real inputs digest, so it counts as current.
`exempt_from_examination` declares the documented `not-applicable` exemption.

Callers that run git in-process (not through a subprocess given `git_env`)
must pin their own environment.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PLUGIN = Path(__file__).resolve().parents[2] / "plugins" / "dev-team"
for _entry in (
    _PLUGIN / "hooks" / "lib",
    _PLUGIN / "scripts" / "lib",
    _PLUGIN / "tests" / "lib",
):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

import examination_store as store  # type: ignore[import-not-found]
from examination_inputs import (  # type: ignore[import-not-found]
    criteria_ids,
    is_exempt,
    plan_examination_inputs,
)
from examination_repo import (  # type: ignore[import-not-found]
    PLAN_ID,
    RUN_COMMAND,
    row,
)
from examination_verdict import (
    build_record,  # type: ignore[import-not-found]
)

EXEMPT_HEADER = "**Examination**: not-applicable\n\n"


def _met_rows(plan_text: str) -> list[dict]:
    return [
        row(cid, command=RUN_COMMAND, observation=f"{cid} passed")
        for cid in criteria_ids(plan_examination_inputs(plan_text))
    ]


def write_met_record(
    root: Path, plan_id: str = PLAN_ID, overall: str = "met", **overrides: object
) -> Path:
    """Write a record bound to the real binding and inputs digest; return its path.

    `overall` and any keyword override replace the matching record field.
    The binding is whatever `current_binding` reports now, so a repository
    with no base or no diff gets a sentinel `binding_hash`, which the store
    refuses to read back (an unreadable record).
    """
    plan_text = (root / plan_id).read_text(encoding="utf-8")
    record = build_record(
        plan_id,
        _met_rows(plan_text),
        [],
        [],
        store.binding_for_plan(root, plan_id, plan_text),
        "agent-1",
    )
    record["overall"] = overall
    record.update(overrides)
    path = store.record_path(root, plan_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    store.write_record(path, record)
    return path


def exempt_from_examination(plan: Path) -> None:
    """Declare `**Examination**: not-applicable` on `plan`, once.

    The plan then passes the examination gate without a record. A plan that
    already declares the exemption is left as it is.
    """
    text = plan.read_text(encoding="utf-8")
    if not is_exempt(text):
        plan.write_text(EXEMPT_HEADER + text, encoding="utf-8")
