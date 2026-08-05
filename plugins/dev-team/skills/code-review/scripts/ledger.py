#!/usr/bin/env python3
"""Progress ledger and per-slice section artifacts for sliced /code-review.

The persist-and-drop design lives here: as each slice is reviewed, its findings
are written to ``.dev-team-reports/code-review/raw/section-<id>.json`` and the
ledger's status for that slice flips to ``done``. The orchestrator keeps only a
one-line tally per slice in context; the durable record is these files. A later
``consolidate.py`` reads the section artifacts back.

Pure-ish library (``init_ledger``, ``write_section``, ``read_ledger``,
``mark_done``) plus a thin ``main()`` CLI so the orchestrator can drive it from
a shell step. All paths resolve under the target repo's working directory
(``root``), never a sandbox or session root.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_LIB_DIR = _SCRIPTS_DIR.parent.parent.parent / "hooks" / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

from atomic_state import locked_state

LEDGER_SCHEMA = "code-review-ledger/v1"
SECTION_SCHEMA = "code-review-section/v1"

STATUS_PENDING = "pending"
STATUS_DONE = "done"


# --- path resolution (single home) --------------------------------------------


def _cr_dir(root: str) -> Path:
    return Path(root) / ".dev-team-reports" / "code-review"


def ledger_path(root: str) -> Path:
    return _cr_dir(root) / "ledger.json"


def raw_dir(root: str) -> Path:
    return _cr_dir(root) / "raw"


def section_path(root: str, slice_id: str) -> Path:
    return raw_dir(root) / f"section-{slice_id}.json"


def _atomic_write_json(path: Path, obj) -> None:
    """Write ``obj`` as pretty JSON to ``path`` atomically (temp + replace).

    The temp name carries a unique pid+uuid suffix so two writers to the same
    final path can never share a temp file (which would corrupt one write or
    make the second ``os.replace`` raise). ``os.replace`` stays atomic.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True))
    os.replace(tmp, path)


# --- ledger + section operations ----------------------------------------------


def init_ledger(slices: list[dict], cap: int, root: str) -> dict:
    """Write a fresh ledger recording every slice as ``pending``; return it.

    Idempotent for a given ``(slices, cap)`` — the same inputs always produce
    the same file. Records each slice's id, files, and declarative flag plus the
    partition cap (so ``--resume`` can detect a cap mismatch — Slice 4).
    """
    ledger = {
        "schema": LEDGER_SCHEMA,
        "cap": cap,
        "slices": [
            {
                "id": s["id"],
                "files": list(s["files"]),
                "is_declarative": bool(s.get("is_declarative", False)),
                "status": STATUS_PENDING,
            }
            for s in slices
        ],
    }
    _atomic_write_json(ledger_path(root), ledger)
    return ledger


def read_ledger(root: str) -> dict | None:
    """Return the ledger dict, or ``None`` if no ledger exists yet."""
    path = ledger_path(root)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def mark_done(root: str, slice_id: str) -> None:
    """Flip ``slice_id``'s ledger status to ``done`` (no-op if no ledger).

    The orchestrator's sequential persist step is still the intended single
    writer (the 2-3-slice parallelism in ``sliced-mode.md`` is in the *review*
    agents, not the persist calls) — but the read-modify-write is now also
    lock-guarded via ``atomic_state.locked_state``, so a violation of that
    contract (a second writer, or a future caller that doesn't honor it) loses
    no update instead of silently dropping another slice's ``done`` flag.
    """
    with locked_state(ledger_path(root)):
        ledger = read_ledger(root)
        if ledger is None:
            return
        for entry in ledger.get("slices", []):
            if entry.get("id") == slice_id:
                entry["status"] = STATUS_DONE
                break
        _atomic_write_json(ledger_path(root), ledger)


def pending_slices(slices: list[dict], root: str) -> list[dict]:
    """Return the slices still needing review.

    **Disk is the source of truth**, not the ledger's ``status`` field. A slice
    whose ``raw/section-<id>.json`` exists is treated as done (skipped) even if
    the ledger still says ``pending``; a slice whose artifact is missing is
    pending even if the ledger says ``done``. This makes ``--resume`` robust to a
    ledger that was never updated before an interruption.

    A slice whose artifact *exists* but carries a non-empty ``dispatchFailures``
    list is still pending — this is the one exception to "artifact exists ->
    done", so ``--resume`` naturally re-dispatches only the previously-failed
    slice(s) instead of reusing a recorded failure as-is.

    A malformed artifact (unreadable, undecodable, or valid JSON of the wrong
    shape) is also treated as pending, never as a crash — matching
    ``consolidate.py``'s ``_read_sections``' own tolerance for exactly this
    corruption on the same file set; a reader of ``raw/section-*.json`` that
    raised here would abort the whole ``--resume`` run instead of just
    re-reviewing the one bad slice.
    """
    pending = []
    for s in slices:
        path = section_path(root, s["id"])
        if not path.exists():
            pending.append(s)
            continue
        try:
            artifact = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            pending.append(s)
            continue
        if not isinstance(artifact, dict):
            pending.append(s)
            continue
        if artifact.get("dispatchFailures"):
            pending.append(s)
    return pending


def check_resume_cap(root: str, requested_cap: int | None) -> None:
    """Raise if ``--resume`` is given a cap differing from the recorded one.

    Repartitioning with a different cap would desync the new slice ids from the
    ``section-<id>.json`` files already on disk, silently re-reviewing or
    orphaning slices. Refuse instead. No-op when there is no prior ledger or no
    explicit cap was requested.
    """
    ledger = read_ledger(root)
    if ledger is None or requested_cap is None:
        return
    recorded = ledger.get("cap")
    if recorded is not None and recorded != requested_cap:
        raise ValueError(
            f"--resume cap {requested_cap} does not match the cap {recorded} "
            f"recorded by the interrupted run. Rerun with --slice {recorded} "
            f"(or without --slice), or start a fresh run to repartition."
        )


def write_section(
    slice_record: dict,
    findings: list,
    panel: list[str],
    root: str,
    dispatch_failures: list | None = None,
) -> Path:
    """Persist a reviewed slice's findings and mark it done in the ledger.

    ``slice_record`` is a partition record (``id``/``files``/``is_declarative``).
    ``panel`` is the list of agent names that ran (so a reader can tell a
    reduced-panel slice from a full one). ``dispatch_failures`` is an optional
    list of unrecovered per-slice dispatch failures (empty when omitted) —
    ``pending_slices`` treats a non-empty list as still-pending on
    ``--resume``. Returns the artifact path.
    """
    artifact = {
        "schema": SECTION_SCHEMA,
        "id": slice_record["id"],
        "files": list(slice_record["files"]),
        "is_declarative": bool(slice_record.get("is_declarative", False)),
        "panel": list(panel),
        "findings": list(findings),
        "dispatchFailures": list(dispatch_failures or []),
    }
    path = section_path(root, slice_record["id"])
    _atomic_write_json(path, artifact)
    mark_done(root, slice_record["id"])
    return path


# --- thin CLI -----------------------------------------------------------------


def _load_json_arg(value: str):
    """Load JSON from a file path, or parse it inline if not a path."""
    p = Path(value)
    return json.loads(p.read_text() if p.exists() else value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="write a fresh ledger from slices")
    p_init.add_argument("--root", default=".")
    p_init.add_argument("--slices", required=True, help="slices JSON (file or inline)")
    p_init.add_argument("--cap", type=int, required=True)

    p_ws = sub.add_parser("write-section", help="persist a slice's findings")
    p_ws.add_argument("--root", default=".")
    p_ws.add_argument("--slice", required=True, help="slice record JSON (file or inline)")
    p_ws.add_argument("--findings", required=True, help="findings JSON (file or inline)")
    p_ws.add_argument("--panel", required=True, help="comma-separated agent names")
    p_ws.add_argument(
        "--dispatch-failures",
        default=None,
        help="dispatch failures JSON list (file or inline); omit for none",
    )

    p_pending = sub.add_parser("pending", help="list slices still needing review")
    p_pending.add_argument("--root", default=".")
    p_pending.add_argument("--slices", required=True, help="slices JSON (file or inline)")
    p_pending.add_argument("--cap", type=int, default=None, help="resume cap to validate")

    args = parser.parse_args(argv)

    if args.cmd == "init":
        ledger = init_ledger(_load_json_arg(args.slices), args.cap, args.root)
        print(f"Ledger initialized: {len(ledger['slices'])} slices at {ledger_path(args.root)}")
        return 0

    if args.cmd == "write-section":
        path = write_section(
            _load_json_arg(args.slice),
            _load_json_arg(args.findings),
            [a.strip() for a in args.panel.split(",") if a.strip()],
            args.root,
            dispatch_failures=(
                _load_json_arg(args.dispatch_failures) if args.dispatch_failures else None
            ),
        )
        print(f"Section written: {path}")
        return 0

    if args.cmd == "pending":
        slices = _load_json_arg(args.slices)
        check_resume_cap(args.root, args.cap)  # raises on cap mismatch
        pending = pending_slices(slices, args.root)
        print(json.dumps([s["id"] for s in pending]))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
