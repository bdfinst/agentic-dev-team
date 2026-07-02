"""Parity harness — the mechanical gate for the bash → Python hook migration (#572).

For each hook slice in Phases 1–3 of `plans/cached-inventing-wave.md`, this
module dispatches identical `(stdin, env, argv, initial-tree)` fixtures at
both the `.sh` and `.py` implementations, snapshots the observable outcome,
and asserts byte-equal parity.

Public surface:

- `Fixture` — the input record for a parity comparison.
- `HookResult` — captured outcome (stdout, stderr, exit code, side-effect tree).
- `dispatch(...)` — run one implementation, return HookResult.
- `assert_parity(...)` — run both, assert byte-equal outcome.
- `record_fixture(...)` — regenerate an `expected.json` snapshot from the .sh
  when running with `--parity-record`.

Sandbox contract (docs/python-hook-contract.md):
    HOME              → tmpdir
    CLAUDE_PROJECT_DIR → tmpdir
    GIT_CONFIG_GLOBAL  → /dev/null
    GIT_CONFIG_SYSTEM  → /dev/null
    Everything else scrubbed to a minimal `PATH` + `LANG`.

stderr normalization strips ONLY:
    - ISO-8601 timestamps
    - PIDs written as `pid=N`
    - the tmpdir path prefix (both impls run in different tmpdirs)

Nothing else. If two implementations diverge on anything past these three
axes, that is a real divergence — fix the hook, don't widen the normalizer.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Fixture:
    """Input tuple for one parity comparison.

    `initial_tree` is a mapping of relative-path → text-content applied to the
    sandbox root before the hook runs. Absent = empty sandbox.
    """

    name: str
    stdin: bytes = b""
    argv: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    initial_tree: Dict[str, str] = field(default_factory=dict)


@dataclass
class HookResult:
    stdout: bytes
    stderr: bytes
    exit_code: int
    tree: Dict[str, str]  # relative-path → sha256:hexdigest (files only)
    sandbox_root: Optional[Path] = None  # tmpdir the hook ran in (post-cleanup)


# ---------------------------------------------------------------------------
# Sandbox helpers
# ---------------------------------------------------------------------------


def _minimal_env(sandbox_root: Path, extra: Mapping[str, str]) -> Dict[str, str]:
    """Build the scrubbed environment for a hook invocation.

    Base includes only what portable hooks need: PATH, LANG, PYTHONIOENCODING,
    plus the sandbox-scoped Claude/git vars from the contract. Callers can add
    hook-specific vars via `extra` (they override the base).
    """
    base: Dict[str, str] = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": "C.UTF-8",
        "PYTHONIOENCODING": "utf-8",
        # Never write .pyc bytecode into $HOME (which we point at the sandbox)
        # — that would flood the side-effect tree with unrelated files on
        # every hook invocation and defeat the parity comparison.
        "PYTHONDONTWRITEBYTECODE": "1",
        "HOME": str(sandbox_root),
        # PWD is the shell's logical cwd; bash preserves it verbatim while
        # Python's os.getcwd() resolves symlinks. On macOS /var → /private/var
        # the two diverge — align both by explicitly setting PWD.
        "PWD": str(sandbox_root),
        "CLAUDE_PROJECT_DIR": str(sandbox_root),
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    }
    base.update(extra)
    return base


def _apply_initial_tree(root: Path, tree: Mapping[str, str]) -> None:
    for rel, content in tree.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)


def _snapshot_tree(root: Path) -> Dict[str, str]:
    """Return {relative_path: sha256-of-normalized-content} for files under `root`.

    Content is normalized before hashing so that timestamps, PIDs, and the
    per-side tmpdir prefix — which the .sh and .py MUST embed at different
    values for the same fixture — do not fail the parity check. This mirrors
    the stderr normalization: if two impls diverge on anything past those
    three axes inside a file they wrote, that is a real divergence.
    """
    snapshot: Dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = str(path.relative_to(root))
        raw = path.read_bytes()
        normalized = _normalize_stderr(raw, root)
        snapshot[rel] = "sha256:" + hashlib.sha256(normalized).hexdigest()
    return snapshot


# ---------------------------------------------------------------------------
# stderr normalization
# ---------------------------------------------------------------------------


_ISO8601_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?"
)
_PID_RE = re.compile(r"\bpid=\d+\b")


def _normalize_stderr(raw: bytes, tmpdir_prefix: Optional[Path] = None) -> bytes:
    text = raw.decode("utf-8", errors="replace")
    text = _ISO8601_RE.sub("<TS>", text)
    text = _PID_RE.sub("pid=<PID>", text)
    if tmpdir_prefix is not None:
        text = text.replace(str(tmpdir_prefix), "<SANDBOX>")
    return text.encode("utf-8")


def _scrub_sandbox_prefix(raw: bytes, tmpdir_prefix: Optional[Path]) -> bytes:
    """Replace each side's own tmpdir prefix in stdout with <SANDBOX>.

    Unlike stderr normalization, this does NOT touch timestamps or PIDs —
    those never legitimately appear on stdout for a hook and any divergence
    on those axes should still fail the parity check.
    """
    if tmpdir_prefix is None:
        return raw
    text = raw.decode("utf-8", errors="replace")
    text = text.replace(str(tmpdir_prefix), "<SANDBOX>")
    return text.encode("utf-8")


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def dispatch(
    argv: List[str],
    *,
    stdin_bytes: bytes = b"",
    env: Optional[Mapping[str, str]] = None,
    cwd: Optional[Path] = None,
    sandbox: bool = True,
    initial_tree: Optional[Mapping[str, str]] = None,
    timeout: float = 30.0,
) -> HookResult:
    """Run one hook implementation and return its captured outcome.

    When `sandbox=True` (default), the process runs in a fresh tmpdir with the
    scrubbed env from the contract and no side effects leak outside. The
    HookResult.tree captures every file the hook wrote into the sandbox.

    Substitute the literal argv token `SANDBOX` with the sandbox root path so
    fixtures can name a working directory without knowing the tmpdir in advance.
    """
    extra_env: Dict[str, str] = dict(env or {})
    with tempfile.TemporaryDirectory(prefix="parity-") as tmpdir_str:
        root = Path(tmpdir_str)
        _apply_initial_tree(root, initial_tree or {})
        proc_env = _minimal_env(root, extra_env) if sandbox else dict(os.environ)
        effective_cwd = cwd if cwd is not None else root
        # Substitute SANDBOX token in argv.
        resolved_argv = [str(root) if a == "SANDBOX" else a for a in argv]
        try:
            completed = subprocess.run(
                resolved_argv,
                input=stdin_bytes,
                env=proc_env,
                cwd=str(effective_cwd),
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return HookResult(
                stdout=exc.stdout or b"",
                stderr=(exc.stderr or b"") + b"\n[parity-harness] TIMEOUT\n",
                exit_code=124,
                tree=_snapshot_tree(root),
                sandbox_root=root,
            )
        return HookResult(
            stdout=completed.stdout,
            stderr=completed.stderr,
            exit_code=completed.returncode,
            tree=_snapshot_tree(root),
            sandbox_root=root,
        )


# ---------------------------------------------------------------------------
# assert_parity
# ---------------------------------------------------------------------------


def _fmt_bytes(b: bytes) -> str:
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return repr(b)


def assert_parity(
    *,
    sh_argv: List[str],
    py_argv: List[str],
    fixture: Fixture,
) -> None:
    """Dispatch both implementations at `fixture` and assert equal outcome."""
    sh_result = dispatch(
        sh_argv,
        stdin_bytes=fixture.stdin,
        env=fixture.env,
        initial_tree=fixture.initial_tree,
    )
    py_result = dispatch(
        py_argv,
        stdin_bytes=fixture.stdin,
        env=fixture.env,
        initial_tree=fixture.initial_tree,
    )

    # Exit code first — the loudest divergence signal.
    assert sh_result.exit_code == py_result.exit_code, (
        f"[{fixture.name}] exit code diverged: sh={sh_result.exit_code} "
        f"py={py_result.exit_code}\n"
        f"sh stdout: {_fmt_bytes(sh_result.stdout)!r}\n"
        f"py stdout: {_fmt_bytes(py_result.stdout)!r}\n"
        f"sh stderr: {_fmt_bytes(sh_result.stderr)!r}\n"
        f"py stderr: {_fmt_bytes(py_result.stderr)!r}"
    )
    # Stdout byte-equal after sandbox-prefix normalization. Each side runs in
    # its own tmpdir, so an identical hook that echoes its cwd still emits
    # different strings — that is a harness artifact, not a hook divergence.
    # Scrub only each side's own sandbox root (no timestamps, no PIDs — stdout
    # is the user-visible channel and we do not want to hide real drift there).
    sh_stdout_norm = _scrub_sandbox_prefix(sh_result.stdout, sh_result.sandbox_root)
    py_stdout_norm = _scrub_sandbox_prefix(py_result.stdout, py_result.sandbox_root)
    assert sh_stdout_norm == py_stdout_norm, (
        f"[{fixture.name}] stdout diverged\n"
        f"sh: {_fmt_bytes(sh_stdout_norm)!r}\n"
        f"py: {_fmt_bytes(py_stdout_norm)!r}"
    )
    # Stderr equal after normalization — each side's own tmpdir is scrubbed.
    sh_stderr_norm = _normalize_stderr(sh_result.stderr, sh_result.sandbox_root)
    py_stderr_norm = _normalize_stderr(py_result.stderr, py_result.sandbox_root)
    assert sh_stderr_norm == py_stderr_norm, (
        f"[{fixture.name}] stderr diverged after normalization\n"
        f"sh: {_fmt_bytes(sh_stderr_norm)!r}\n"
        f"py: {_fmt_bytes(py_stderr_norm)!r}"
    )
    # Side-effect tree equal.
    assert sh_result.tree == py_result.tree, (
        f"[{fixture.name}] side-effect tree diverged\n"
        f"sh: {sh_result.tree}\n"
        f"py: {py_result.tree}"
    )


# ---------------------------------------------------------------------------
# --record mode
# ---------------------------------------------------------------------------


def record_fixture(
    *,
    sh_argv: List[str],
    fixture: Fixture,
    snapshot_path: Path,
) -> Path:
    """Run the .sh implementation and write its outcome as JSON to snapshot_path.

    Used by `--parity-record` when a fixture's expected snapshot is missing or
    the operator wants to regenerate against the current authoritative bash
    behavior. Does NOT run the .py — the .py is validated by assert_parity in
    the non-record run that follows.
    """
    result = dispatch(
        sh_argv,
        stdin_bytes=fixture.stdin,
        env=fixture.env,
        initial_tree=fixture.initial_tree,
    )
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(
        json.dumps(
            {
                "name": fixture.name,
                "stdout": result.stdout.decode("utf-8", errors="replace"),
                "stderr_normalized": _normalize_stderr(result.stderr).decode(
                    "utf-8", errors="replace"
                ),
                "exit_code": result.exit_code,
                "tree": result.tree,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return snapshot_path
