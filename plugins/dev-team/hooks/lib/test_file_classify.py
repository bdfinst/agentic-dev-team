"""test_file_classify — shared test-file classifier + build-phase reader.

Single encoding of `knowledge/test-file-indicators.md` for hooks that need to
decide "is this a test file?" (the refactor test-freeze guards), plus the
reader for the build-phase state `/build` records at each step-phase
transition (`.claude/memory/build-phase.json`).

Stdlib-only. Python 3.8+. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import artifact_paths

#: memory/build-phase.json older than this is treated as absent — a crashed
#: build must not freeze tests forever.
STALE_AFTER_SECONDS = 4 * 60 * 60

_JS_TS_NAME_RE = re.compile(r"\.(test|spec)\.[^./]+$", re.IGNORECASE)
_STEP_DEF_RE = re.compile(r"(\.steps\.[^./]+$|StepDefinitions\.[^./]+$|Steps\.[^./]+$)")
_CSHARP_MARKER_RE = re.compile(r"\[(Fact|Theory|Test|TestCase|TestMethod|TestClass)\]")
_JAVA_MARKER_RE = re.compile(r"@(Test|ParameterizedTest|TestFactory)\b")
_JAVA_CLASS_SUFFIXES = ("Test", "Tests", "TestCase", "Spec")
_PYTHON_NAME_RE = re.compile(r"^(test_.+|.+_test)\.py$", re.IGNORECASE)

#: How much of a file to read when a content probe is needed.
_CONTENT_PROBE_BYTES = 256 * 1024


def _read_probe(path: Path) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read(_CONTENT_PROBE_BYTES)
    except OSError:
        return ""


def is_test_file(path: str, content: str | None = None) -> bool:
    """True when `path` is a test file per knowledge/test-file-indicators.md.

    `content` overrides the on-disk read for the languages whose indicator is
    content-based (C#, Java) — pass it in tests or when the file is not on
    disk yet (a PreToolUse Write).
    """
    if not path:
        return False
    p = Path(path)
    name = p.name
    posix = p.as_posix()

    # BDD/Gherkin — a .feature file always counts as a test file.
    if name.lower().endswith(".feature"):
        return True
    if _STEP_DEF_RE.search(name):
        return True

    # JS/TS — *.test.*, *.spec.*, or inside __tests__/
    if _JS_TS_NAME_RE.search(name):
        return True
    if "/__tests__/" in posix or posix.startswith("__tests__/"):
        return True

    # Python — test_*.py or *_test.py (pytest/unittest convention).
    if _PYTHON_NAME_RE.match(name):
        return True

    suffix = p.suffix.lower()
    if suffix == ".cs":
        probe = content if content is not None else _read_probe(p)
        return bool(_CSHARP_MARKER_RE.search(probe))

    if suffix == ".java":
        if p.stem.endswith(_JAVA_CLASS_SUFFIXES):
            return True
        probe = content if content is not None else _read_probe(p)
        return bool(_JAVA_MARKER_RE.search(probe))

    return False


def _parse_written_at(value: str) -> float | None:
    """ISO-8601 → epoch seconds, tolerant of a trailing 'Z'. None when unparseable."""
    if not isinstance(value, str) or not value:
        return None
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def build_phase_path(project_dir: Path) -> Path:
    # Read-only: no Python writer of build-phase.json exists anywhere in
    # hooks/ — it is agent-instruction-written (build/SKILL.md). migrate=False
    # so this read never migrates a legacy file or creates .claude/memory/ as
    # a side effect.
    return artifact_paths.resolve_file(
        "memory", "build-phase.json", project_dir, migrate=False
    )


def read_build_phase(
    project_dir: Path, now: float | None = None
) -> tuple[dict | None, str | None]:
    """Read `memory/build-phase.json`. Returns `(state, error)`.

    - `(None, None)`  — no state recorded, or the state is stale
      (> STALE_AFTER_SECONDS old): guards treat both as "no phase".
    - `(None, <why>)` — the file exists but is unreadable or malformed:
      guards fail OPEN and record the reason in the audit log.
    - `(state, None)` — an active, fresh phase record. `state["phase"]` is a
      string; `state["test_files_staged"]` is always a list of strings.

    `now` is the injectable clock (epoch seconds) for staleness tests.
    """
    path = build_phase_path(project_dir)
    if not path.is_file():
        return None, None
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"unreadable build-phase state: {exc}"
    try:
        data = json.loads(raw)
    except ValueError:
        return None, "malformed build-phase state: invalid JSON"
    if not isinstance(data, dict):
        return None, "malformed build-phase state: not an object"
    phase = data.get("phase")
    if not isinstance(phase, str) or not phase:
        return None, "malformed build-phase state: missing phase"
    written_at = _parse_written_at(data.get("written_at", ""))
    if written_at is None:
        return None, "malformed build-phase state: missing/unparseable written_at"
    current = time.time() if now is None else now
    if current - written_at > STALE_AFTER_SECONDS:
        return None, None
    staged = data.get("test_files_staged", [])
    if not isinstance(staged, list):
        return None, "malformed build-phase state: test_files_staged not a list"
    files: list[str] = [f for f in staged if isinstance(f, str) and f]
    state = dict(data)
    state["test_files_staged"] = files
    return state, None
