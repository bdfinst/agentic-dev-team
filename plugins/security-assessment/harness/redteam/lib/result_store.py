"""result_store — inter-script data passing for the red-team harness.

Scripts call `save(name, data)` and `load(name)` — never reading each other's
JSON files directly. Typed helpers provide named access to the common
artefacts so probe scripts don't hardcode JSON key paths.

Progress manifest (owned by this module, per the plan's handoff contract):
    list_completed_phases() -> list[str]
    record_completion(name)
    resume_message(failed_phase) -> str    "Resume with --start <phase>"
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .. import config


def _path_for(name: str) -> Path:
    return config.RESULTS_DIR / f"{name}.json"


def save(name: str, data: Any) -> Path:
    """Persist `data` as JSON at RESULTS_DIR / <name>.json. Atomic via temp + rename."""
    config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    target = _path_for(name)
    tmp = target.with_suffix(target.suffix + ".tmp")
    with tmp.open("w") as f:
        json.dump(data, f, indent=2)
    tmp.rename(target)
    return target


def load(name: str) -> Any:
    """Read JSON by name. Raises FileNotFoundError if absent."""
    p = _path_for(name)
    with p.open() as f:
        return json.load(f)


def exists(name: str) -> bool:
    return _path_for(name).exists()


# ── Typed helpers for common artefacts ────────────────────────────────────────

def get_discovered_features() -> list[str]:
    """Return the feature list produced by probe 02_schema_discovery."""
    data = load("02_schema")
    return list(data.get("features", []))


def get_recon_data() -> dict:
    return load("01_recon")


def get_sensitivity_data() -> dict:
    return load("03_sensitivity")


def get_boundary_data() -> dict:
    return load("04_boundaries")


# ── Progress manifest ────────────────────────────────────────────────────────

def _read_manifest() -> dict:
    if not config.PROGRESS_MANIFEST.exists():
        return {"completed": [], "failed": None}
    try:
        with config.PROGRESS_MANIFEST.open() as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"completed": [], "failed": None}


def _write_manifest(manifest: dict) -> None:
    config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = config.PROGRESS_MANIFEST.with_suffix(config.PROGRESS_MANIFEST.suffix + ".tmp")
    with tmp.open("w") as f:
        json.dump(manifest, f, indent=2)
    tmp.rename(config.PROGRESS_MANIFEST)


def list_completed_phases() -> list[str]:
    return list(_read_manifest().get("completed", []))


def record_completion(name: str) -> None:
    m = _read_manifest()
    if name not in m["completed"]:
        m["completed"].append(name)
    m["failed"] = None
    _write_manifest(m)


def record_failure(name: str, error: str) -> None:
    m = _read_manifest()
    m["failed"] = {"phase": name, "error": error}
    _write_manifest(m)


def resume_message(failed_phase: str) -> str:
    """Canonical resume-hint string printed on mid-run failure."""
    return f"Resume with --start {failed_phase}"


def reset() -> None:
    """Wipe the manifest (used at pipeline start when --start is NOT set)."""
    _write_manifest({"completed": [], "failed": None})
