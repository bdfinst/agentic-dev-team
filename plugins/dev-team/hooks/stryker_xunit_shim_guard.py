#!/usr/bin/env python3
"""Stryker xunit.v3 shim gate — PreToolUse hook (#1083).

Stryker.NET (through >=4.15/4.16) cannot observe mutant kills through xunit.v3:
xunit.v3 runs on the Microsoft Testing Platform (MTP) and Stryker's per-test
coverage/kill mapping does not work across it (stryker-net issues 3237/3629/3094).
A run against a real xunit.v3 test project completes but reports a false near-zero
score with almost everything "Survived" — silently, since the initial test run
passes. The fix is a xunit.v2 shim project (see the stryker-xunit-v2-shim skill).

On a `dotnet stryker` run that would produce the false score, this gate
**auto-scaffolds the shim and reports what it wrote** (it is not silent), then
blocks the current invocation — a PreToolUse hook cannot change the directory the
in-flight command runs in, so the shim must be run from its own directory as the
next step. It guards the two invocations that produce the false score:

  * `dotnet stryker` in a directory whose test project references xunit.v3
    (project mode bound to v3);
  * `dotnet stryker` at a solution root whose solution contains a xunit.v3 test
    project (solution mode binds to it).

It does NOT scaffold blindly: it runs the scope probe first and refuses (blocks
with the file list) when the sources use v3-only constructs that need manual
porting, and it never regenerates over a shim that already exists. A run launched
from a `*.Mutation` xunit.v2 shim directory passes untouched.

Contract (docs/python-hook-contract.md):
    Input : PreToolUse JSON on stdin
    Output: exit 2 + `[BLOCK]`-prefixed body on stdout to BLOCK
            exit 0 + no stdout for SILENT-PASS
    Env   : DEV_TEAM_STRYKER_XUNIT3_GATE_SKIP=1 -> silent bypass

Stdlib-only. Python 3.8+.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

_HOOK_DIR = Path(__file__).resolve().parent
_PLUGIN_DIR = _HOOK_DIR.parent
_LIB_DIR = _HOOK_DIR / "lib"

sys.path.insert(0, str(_LIB_DIR))
try:
    from stdin_json import read_stdin_json  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - fallback keeps the hook self-contained

    def read_stdin_json() -> dict | None:  # type: ignore[misc]
        import json

        try:
            return json.loads(sys.stdin.read() or "{}")
        except (ValueError, OSError):
            return None


# `dotnet stryker`, `dotnet-stryker`, or the plugin's wrapper — mirror the
# smoke-gate trigger so both gates recognise the same invocations.
_STRYKER_TRIGGER = re.compile(
    r"(?:^|[^a-zA-Z0-9])dotnet[ \t-]+stryker(?:\b|$)|csharp[_-]stryker[_-]net[_-]wrapper"
)

_GENERATOR = _PLUGIN_DIR / "skills" / "stryker-xunit-v2-shim" / "scripts" / "generate_shim.py"

# Directories never worth walking when scanning for test projects/sources.
_SKIP_DIRS = {"bin", "obj", ".git", "node_modules", ".vs", "StrykerOutput"}

# v3-only constructs that must be ported to v2-compatible forms before a shim
# can compile the linked sources (see the skill's Step 1 scope probe).
_V3_ONLY = (
    "AutoFixture.Xunit3", "[AutoData", "InlineAutoData", "AutoMoqData",
    "MemberAutoData", "TestContext", "Assert.Skip", "Assert.Multiple",
    "IAsyncLifetime", "Assert.Equivalent",
)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _is_v2_shim(csproj: Path) -> bool:
    if not csproj.name.endswith(".Mutation.csproj"):
        return False
    return bool(re.search(r'Include="xunit"\s+Version="2', _read(csproj)))


def _is_v3(csproj: Path) -> bool:
    return "xunit.v3" in _read(csproj)


_MTP_RUNNER_RE = re.compile(r"""(?:^|\s)(?:-t|--test-runner)[ =]+["']?mtp\b""")


def _uses_mtp_runner(command: str) -> bool:
    """True when the command explicitly selects Stryker's Microsoft Testing
    Platform runner (`-t mtp` / `--test-runner mtp`) — the sanctioned no-shim
    floor (#1156/#1159): it drives the real xunit.v3 suite and yields a real
    (if slow, whole-suite-per-mutant) score, so the false-~0% premise this gate
    guards against does not apply."""
    return bool(_MTP_RUNNER_RE.search(command))


def _resolve_run_dir(command: str, cwd: str) -> Path:
    """Honour a leading `cd <dir> && ...` so the gate reasons about where Stryker
    actually runs, not where the shell started."""
    match = re.search(r"\bcd\s+([^\s&;|]+)", command)
    if match:
        target = match.group(1).strip("'\"")
        return (Path(cwd) / target).resolve()
    return Path(cwd).resolve()


def _find_v3_test_projects(root: Path, limit: int = 400) -> list[Path]:
    """Bounded walk for xunit.v3 test .csproj under a solution root."""
    found: list[Path] = []
    seen = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for name in filenames:
            if name.endswith(".csproj"):
                seen += 1
                if seen > limit:
                    return found
                path = Path(dirpath) / name
                if not path.name.endswith(".Mutation.csproj") and _is_v3(path):
                    found.append(path)
    return found


def _scope_flags(project_dir: Path) -> list[str]:
    """Test sources using v3-only constructs, relative to project_dir."""
    flagged: list[str] = []
    for dirpath, dirnames, filenames in os.walk(project_dir):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for name in filenames:
            if name.endswith(".cs"):
                path = Path(dirpath) / name
                if any(tok in _read(path) for tok in _V3_ONLY):
                    flagged.append(str(path.relative_to(project_dir)))
    return flagged


def _shim_dir_for(real_csproj: Path) -> Path:
    real_dir = real_csproj.parent
    return real_dir.parent / (real_csproj.stem + ".Mutation")


def _run_generator(real_csproj: Path, cwd: Path) -> tuple[int, str]:
    if not _GENERATOR.is_file():
        return 127, f"generator not found at {_GENERATOR}"
    try:
        proc = subprocess.run(
            [sys.executable, str(_GENERATOR), str(real_csproj)],
            cwd=str(cwd), capture_output=True, text=True, check=False, timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        return 1, str(exc)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _handle_v3_project(real_csproj: Path, cwd: Path) -> list[str]:
    """Auto-scaffold the shim for one xunit.v3 test project (or explain why not),
    and return the block body reporting exactly what happened."""
    name = real_csproj.stem
    shim_dir = _shim_dir_for(real_csproj)
    rel_shim = os.path.relpath(shim_dir, cwd)
    header = f"[BLOCK] Stryker on the xunit.v3 project '{name}' reports a FALSE ~0% score"

    # Never regenerate over an existing shim.
    if (shim_dir / (name + ".Mutation.csproj")).exists():
        return [
            header + " — a v2 shim already exists.",
            f"Run mutation FROM the shim dir: cd {rel_shim} && dotnet-stryker",
        ]

    # Refuse to scaffold blindly when sources need manual porting.
    flagged = _scope_flags(real_csproj.parent)
    if flagged:
        return [
            header + ", and the shim can't be auto-built:",
            "these sources use v3-only constructs that must be ported to v2-compatible",
            "forms first (see the stryker-xunit-v2-shim skill, Step 3):",
        ] + [f"  - {f}" for f in sorted(set(flagged))[:20]]

    code, out = _run_generator(real_csproj, cwd)
    if code != 0:
        return [
            header + ", and auto-scaffolding failed:",
            f"  {out.strip()[:400]}",
            f"Build the shim by hand: python3 {os.path.relpath(_GENERATOR, cwd)} {os.path.relpath(real_csproj, cwd)}",
        ]
    lines = [
        header + " — auto-scaffolded a xunit.v2 shim (perTest, 30s timeout):",
    ]
    lines += ["  " + ln for ln in out.strip().splitlines()]
    lines += [
        "Review the generated shim, then run mutation FROM it:",
        f"  cd {rel_shim} && dotnet-stryker",
        f'If the product uses InternalsVisibleTo, add [assembly: InternalsVisibleTo("{name}.Mutation")].',
    ]
    return lines


def _block(lines: list[str]) -> int:
    print("\n".join(lines))
    return 2


def main() -> int:
    if os.environ.get("DEV_TEAM_STRYKER_XUNIT3_GATE_SKIP") == "1":
        return 0

    event = read_stdin_json() or {}
    if event.get("tool_name") != "Bash":
        return 0
    command = (event.get("tool_input") or {}).get("command", "") or ""
    if not _STRYKER_TRIGGER.search(command):
        return 0

    # Sanctioned no-shim floor (#1156/#1159): an explicit MTP-runner run drives
    # the real xunit.v3 suite and produces a real score, so it must not be
    # blocked or shimmed. Let it through before any v3-project detection.
    if _uses_mtp_runner(command):
        return 0

    cwd = event.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    run_dir = _resolve_run_dir(command, cwd)
    if not run_dir.is_dir():
        return 0
    base = Path(cwd)

    local = list(run_dir.glob("*.csproj"))

    # Correct invocation: already inside a xunit.v2 shim dir. Let it run.
    if any(_is_v2_shim(p) for p in local):
        return 0

    # Project mode bound directly to a xunit.v3 test project.
    v3_local = [p for p in local if _is_v3(p)]
    if v3_local:
        return _block(_handle_v3_project(v3_local[0], base))

    # Solution mode: a bare run at a solution root binds to the v3 test project(s).
    if list(run_dir.glob("*.sln")):
        v3 = _find_v3_test_projects(run_dir)
        if v3:
            lines = [
                "[BLOCK] `dotnet stryker` at this solution root enters solution mode and binds to",
                "xunit.v3 test project(s), reporting a FALSE ~0% score (Stryker.NET can't observe",
                "kills through xunit.v3 — MTP; stryker-net #3237/#3629/#3094). Handling each:",
                "",
            ]
            for proj in v3[:5]:
                lines += _handle_v3_project(proj, base) + [""]
            lines.append("Run each shim from its own directory (no .sln in scope forces project mode).")
            return _block(lines)

    return 0


if __name__ == "__main__":
    sys.exit(main())
