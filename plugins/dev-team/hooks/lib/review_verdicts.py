"""review_verdicts.py — per-lens review verdict store (#2166).

Records, per genuine review-agent dispatch, an outcome (`pass` | `findings`)
bound to `(lens, file_path, file_content_hash)` — NOT per-diff (Decision 3,
plans/2164-verdict-ledger-writer.md): a verdict row answers "did this lens
pass this exact file content", so it can be looked up again the next time the
same file content recurs, regardless of which diff produced it.

A deliberate sibling of `hooks/lib/boundary_events.py`, not an extension of
it (Decision 1): `boundary_events.py`'s own docstring forbids ever writing a
real `file_path` into that stream ("Never write free text ... file paths ...
must never appear"), so a per-file verdict needs its own store,
`.claude/metrics/review-verdicts.jsonl`, written via the same
`atomic_state.append_line_locked` primitive `boundary_events.py` uses.

ALWAYS-ON (Decision 2): unlike `telemetry.py`, this stream is not gated by
`DEV_TEAM_TELEMETRY`/`~/.claude/telemetry.json` consent — same posture as
`boundary-events.jsonl` itself, for the same reason (local-only, mechanical
accountability data: lens/path/hash/outcome, no prose).

Fail-open: every exception in `emit_review_verdict()` is swallowed. A full
disk, read-only `.claude/metrics/`, or malformed state must never change the
calling hook's stdout, stderr, or exit code. `load_verdicts()` never raises
either — an absent file, a corrupted line, or a stale `plugin_version` row
all degrade to "no usable rows" rather than an exception.

`hooks/review_verdict_recorder.py` is a writer only — it never calls
`load_verdicts()`. `scripts/verdict_scope.py` (#2167) is `load_verdicts()`'s
sanctioned reader: before scoping a review dispatch, it consults these rows
to decide which `(lens, file)` pairs an exact current-content `pass` match
already clears. See this module's own test
`test_load_verdicts_has_no_other_consumers` for the mechanical check that
enforces that boundary.

## Trust boundary: the ledger must never travel through version control
(#2167 security review)

Once a `pass` row can suppress a real dispatch, the ledger stops being pure
telemetry and becomes something a contributor benefits from forging: commit
a `.claude/metrics/review-verdicts.jsonl` (this repo's `.gitignore` excludes
`**/metrics/*`, but `git add -f` still works) claiming `security-review`
already passed a file whose content-hash the contributor can trivially
compute themselves (they wrote it), and a reviewer who checks out that
branch and runs `/code-review` never dispatches `security-review` against
it at all. `load_verdicts()` therefore refuses the file outright — treats it
exactly like "no ledger" — whenever it is tracked by git in `cwd`'s
repository (`_ledger_is_git_tracked`). This is the same self-certification
concern the epic (#2164) names for the PR gate ("a `pass` row must never
become a self-certification shortcut"), applied here to the ledger's OWN
provenance rather than to `pre_pr_review.py`'s corroboration. Any git error
(no `git` on `PATH`, `cwd` isn't a repository, a subprocess failure)
resolves toward TRUSTING the file, matching every other environment
assumption this plugin already makes about git being present — this check
adds a targeted distrust signal, it is not a general "can we run git"
capability probe.

Stdlib only, except for one deliberate `git` subprocess call in
`_ledger_is_git_tracked` — the read-side analogue of `hooks/lib/
review_gate_hash.py`'s own git subprocess use elsewhere in this plugin's
`hooks/lib/`. See ADR 0014 / ADR 0015.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import artifact_paths
import atomic_state
import plugin_version

_LOG_NAME = "review-verdicts.jsonl"

# 50 MiB cap: bounds a content-hash read against a FIFO/device path or a
# multi-GB file hanging past a fail-open caller's exception wrapper — a hang
# is not an exception that wrapper can catch. Originally
# `review_verdict_recorder.py`'s own module-private constant (#2166 Fix #4,
# security review); promoted here (#2167) so `verdict_scope.py`'s read-side
# consult hashes files with the exact same algorithm and cap the writer used
# — two independently-maintained hash implementations could silently drift,
# making every lookup a guaranteed miss (correct, but wastefully so, and
# undetectable except by noticing the ledger never skips anything).
MAX_HASH_FILE_BYTES = 50 * 1024 * 1024
HASH_CHUNK_BYTES = 1 << 20  # 1 MiB incremental read

# The literal text prefix `skills/code-review/SKILL.md` step 4 renders into
# each per-agent dispatch prompt (`Files in scope for this review: <path>,
# ...`) and that Step 2.3's SubagentStop verdict recorder parses back out of
# the transcript. Sharing one constant between the renderer's test (Step 2.1)
# and the future parser (Step 2.3) keeps the marker format and its parser
# from silently drifting apart.
SCOPE_MARKER_PREFIX = "Files in scope for this review: "


def canonical_path(file_path: str, root) -> str | None:
    """Resolve `file_path` against `root` to a `root`-relative, symlink-
    resolved POSIX path, or `None` when it can't be resolved or escapes
    `root` (an absolute path elsewhere on disk, a `..` traversal, or a
    broken symlink chain raising `OSError`).

    The single canonicalization both the writer
    (`hooks/review_verdict_recorder.py`, which stamps each verdict row's
    `file_path`) and the reader (`scripts/verdict_scope.py`, #2167) key the
    ledger on — reported independently by three review lenses (correctness,
    security, arch) as a real drift risk before this was shared: a caller
    passing `./a.py`, an absolute path, or a path relative to a different
    root than the writer used would silently never match a genuine row.
    Failing toward `None` (never dispatch a hash for it) rather than a
    best-effort guess keeps this on the module's existing fail-toward-
    more-work side."""
    try:
        root_resolved = Path(root).resolve()
        target = Path(file_path)
        if not target.is_absolute():
            target = root_resolved / target
        resolved = target.resolve()
    except OSError:
        return None
    if not resolved.is_relative_to(root_resolved):
        return None
    try:
        return resolved.relative_to(root_resolved).as_posix()
    except ValueError:
        return None


def hash_file(path: Path) -> str | None:
    """Current-content sha256 hex digest of `path`, or `None` on any read
    failure (deleted, unreadable, not a regular file — a directory, FIFO, or
    device — or over `MAX_HASH_FILE_BYTES`).

    Shared by `hooks/review_verdict_recorder.py` (the writer) and
    `scripts/verdict_scope.py` (the #2167 reader): the writer stamps each
    verdict row's `file_content_hash` with this function, and the reader
    must recompute the SAME hash for the SAME bytes to ever find a match —
    a second, independently-drifting implementation would make every lookup
    silently miss."""
    try:
        if not path.is_file():
            return None
        if path.stat().st_size > MAX_HASH_FILE_BYTES:
            return None
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            while chunk := fh.read(HASH_CHUNK_BYTES):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _isoformat_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def emit_review_verdict(
    cwd,
    lens: str,
    file_path: str,
    file_content_hash: str,
    outcome: str,
    session_id: str | None = None,
) -> None:
    """Append one compact JSON line to
    `<cwd>/.claude/metrics/review-verdicts.jsonl`.

    Unconditional (Decision 2) — no consent check. Fail-open: any error (bad
    `cwd`, unwritable `.claude/metrics/`, disk full, etc.) is swallowed
    silently, matching `emit_boundary_event`'s own contract.

    Args:
        cwd: Directory whose `.claude/metrics/` subdirectory receives the
            row. Accepts `str` or `Path`.
        lens: The review agent's name (e.g. "security-review").
        file_path: The in-scope file this verdict is about.
        file_content_hash: Content hash of `file_path` at review time.
        outcome: `"pass"` or `"findings"`.
        session_id: Optional opaque session ID from the hook payload.
    """
    try:
        base = Path(cwd) if cwd else Path.cwd()
        log = artifact_paths.resolve_file("metrics", _LOG_NAME, base)
        log.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "ts": _isoformat_utc(),
            "lens": lens,
            "file_path": file_path,
            "file_content_hash": file_content_hash,
            "outcome": outcome,
            "plugin_version": plugin_version.shipped_version(),
        }
        if session_id:
            payload["session_id"] = session_id

        line = json.dumps(payload, separators=(",", ":")) + "\n"
        atomic_state.append_line_locked(log, line)
    except Exception:  # noqa: BLE001, S110 — fail-open by design, see module docstring
        pass


def _ledger_is_git_tracked(log: Path, base: Path) -> bool:
    """True only when `log` is CONFIRMED tracked by git in `base`'s
    repository — the one signal a forged, PR-committed ledger row would
    need (see module docstring's "Trust boundary" section). Any inability
    to confirm this either way — no `git` on `PATH`, `base` is not a git
    repository, or any other subprocess failure — returns `False`: an
    environment this check can't reason about is treated as "nothing
    travelled through version control to distrust", not as a reason to
    distrust every local, gitignored ledger that already exists in every
    supported environment today. `--error-unmatch` is git's own "is this
    path tracked" primitive; exit 0 means tracked, any non-zero exit means
    untracked or not-a-repository, and both of those are indistinguishable
    here on purpose — this check only ever needs the positive "yes, tracked"
    signal, never the reason for a negative one."""
    try:
        result = subprocess.run(
            ["git", "-C", str(base), "ls-files", "--error-unmatch", "--", str(log)],
            capture_output=True,
            check=False,
        )
    except OSError:
        return False
    return result.returncode == 0


def _version_tuple(version: object) -> tuple[int, ...] | None:
    """Parse a dotted numeric version string into a comparable tuple, or
    `None` when it isn't one (e.g. the `"unknown"` fallback
    `plugin_version.shipped_version()` can return)."""
    if not isinstance(version, str) or not version:
        return None
    parts: list[int] = []
    for segment in version.split("."):
        if not segment.isdigit():
            return None
        parts.append(int(segment))
    return tuple(parts) if parts else None


def _is_usable_version(row_version: object, current_version: str) -> bool:
    """A row is usable when its `plugin_version` is the current one, or a
    numerically parseable version no older than it. Anything else — a
    strictly older version, or a value that fails to parse and isn't an
    exact string match — is treated as stale/unusable (fail toward
    excluding, never toward raising)."""
    if row_version == current_version:
        return True
    row_tuple = _version_tuple(row_version)
    current_tuple = _version_tuple(current_version)
    if row_tuple is None or current_tuple is None:
        return False
    return row_tuple >= current_tuple


def load_verdicts(cwd) -> list[dict]:
    """Read `<cwd>/.claude/metrics/review-verdicts.jsonl` and return its
    usable rows.

    "Usable" excludes: an absent file, a git-tracked ledger (see module
    docstring's "Trust boundary" section — treated identically to "no
    ledger"), a line that isn't valid JSON, a line that isn't a JSON object,
    and a row whose `plugin_version` is older than
    `plugin_version.shipped_version()`. Never raises — every failure mode
    degrades to an empty (or partial) list.
    """
    try:
        base = Path(cwd) if cwd else Path.cwd()
        log = artifact_paths.resolve_file("metrics", _LOG_NAME, base, migrate=False)
        if not log.is_file():
            return []
        if _ledger_is_git_tracked(log, base):
            return []
        text = log.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001 — fail-open by design, see module docstring
        return []

    current_version = plugin_version.shipped_version()
    rows: list[dict] = []
    for raw_line in text.splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            row = json.loads(raw_line)
        except ValueError:
            continue
        if not isinstance(row, dict):
            continue
        if not _is_usable_version(row.get("plugin_version"), current_version):
            continue
        rows.append(row)
    return rows
