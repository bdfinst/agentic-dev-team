"""I/O half of the acceptance-examination record (#2270): identity, binding, persistence."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import artifact_paths
import atomic_state
from examination_verdict import RECORD_SCHEMA, TAINTED, VERDICTS
from review_gate_hash import EMPTY_DIGEST, branch_diff_gate_hash, default_base_ref

BASE_UNRESOLVABLE = "base-unresolvable"
EMPTY_DIFF = "empty-diff"
RECORD_FILENAME_PREFIX = "acceptance-examination-"
RECORD_FILENAME_SUFFIX = ".json"
_PATH_SEPARATOR_ESCAPE = "__"
_GIT_TIMEOUT_SECONDS = 30
_BINDING_HASH = re.compile(r"[0-9a-f]{64}")
_REQUIRED_KEYS = ("plan", "overall", "criteria", "binding_hash", "inputs_digest")
_OVERALL_VALUES = (*VERDICTS, TAINTED)


class NotARepository(Exception):
    """The path is not inside a git working tree, or git could not be run."""


class RecordUnreadable(Exception):
    """A record file exists but fails validation; `.problem` names why."""

    def __init__(self, problem: str) -> None:
        super().__init__(problem)
        self.problem = problem


def repo_root(path: Path | str) -> Path:
    """Return the git toplevel of the directory holding `path`.

    Raises `NotARepository` outside a working tree, when git is missing, or
    when git does not answer within the timeout.
    """
    start = Path(path)
    directory = start if start.is_dir() else start.parent
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(directory),
            capture_output=True,
            check=False,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise NotARepository(f"cannot run git in {directory}: {exc}") from exc
    toplevel = completed.stdout.strip()
    if completed.returncode != 0 or not toplevel:
        raise NotARepository(f"not a git repository: {directory}")
    return Path(toplevel).resolve()


def canonical_plan_id(plan_path: Path | str, root: Path | str) -> str:
    """Repo-root-relative POSIX path of the resolved plan.

    Raises `ValueError` when the plan lies outside `root`.
    """
    resolved_root = Path(root).resolve()
    resolved_plan = Path(plan_path).resolve()
    try:
        relative = resolved_plan.relative_to(resolved_root)
    except ValueError:
        raise ValueError(f"plan {resolved_plan} is outside {resolved_root}") from None
    return relative.as_posix()


def record_path(root: Path | str, plan_id: str) -> Path:
    """Where the record for `plan_id` lives, one file per plan."""
    escaped = plan_id.replace("/", _PATH_SEPARATOR_ESCAPE)
    filename = f"{RECORD_FILENAME_PREFIX}{escaped}{RECORD_FILENAME_SUFFIX}"
    return artifact_paths.memory_dir(root) / filename


def current_binding(root: Path | str, plan_id: str) -> str:
    """sha256 of the branch diff against its base, leaving out the plan file.

    Returns `BASE_UNRESOLVABLE` when no base ref resolves and `EMPTY_DIFF` when
    the diff is empty (or git failed), so a caller can never match either
    against a stored hash.
    """
    base_ref = default_base_ref(Path(root))
    if base_ref is None:
        return BASE_UNRESOLVABLE
    digest = branch_diff_gate_hash(base_ref, Path(root), exclude=(plan_id,))
    return EMPTY_DIFF if digest == EMPTY_DIGEST else digest


def is_binding_hash(value: object) -> bool:
    """True for a real binding hash: 64 lowercase hex characters, and not the
    empty-input digest, which is never a valid subject-hash match."""
    if not isinstance(value, str) or value == EMPTY_DIGEST:
        return False
    return _BINDING_HASH.fullmatch(value) is not None


def _parse_object(text: str) -> dict:
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise RecordUnreadable("invalid JSON") from exc
    if not isinstance(data, dict):
        raise RecordUnreadable("not an object")
    return data


def _check_record(data: dict) -> None:
    schema = data.get("schema")
    if isinstance(schema, bool) or schema != RECORD_SCHEMA:
        raise RecordUnreadable("unsupported schema")
    for key in _REQUIRED_KEYS:
        if key not in data:
            raise RecordUnreadable(f"missing key {key}")
    if not isinstance(data["criteria"], list):
        raise RecordUnreadable("invalid criteria")
    if not isinstance(data["plan"], str):
        raise RecordUnreadable("invalid plan")
    if data["overall"] not in _OVERALL_VALUES:
        raise RecordUnreadable("invalid overall")


def read_record(path: Path | str) -> dict:
    """Load and validate the record at `path`.

    Raises `RecordUnreadable` (with `.problem`) for a malformed record; a
    missing file raises `FileNotFoundError`, which callers treat as "absent".
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise RecordUnreadable("invalid JSON") from exc
    data = _parse_object(text)
    _check_record(data)
    return data


def write_record(path: Path | str, record: dict) -> None:
    """Persist `record` atomically under an exclusive lock.

    Raises (never silently skips) when the lock or the write fails.
    """
    target = Path(path)
    text = json.dumps(record, indent=2) + "\n"
    with atomic_state.locked_state(target, strict=True):
        atomic_state.atomic_write(target, text, fail_open=False)


__all__ = (
    "BASE_UNRESOLVABLE",
    "EMPTY_DIFF",
    "NotARepository",
    "RecordUnreadable",
    "canonical_plan_id",
    "current_binding",
    "is_binding_hash",
    "read_record",
    "record_path",
    "repo_root",
    "write_record",
)
