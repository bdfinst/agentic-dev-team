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

It does NOT scaffold blindly: it runs the scope probe first and refuses when the
sources use v3-only constructs that need manual porting, and it never regenerates
over a shim that already exists. A run launched from a `*.Mutation` xunit.v2 shim
directory passes untouched.

When those constructs are present the block body is the **operator decision
gate** (#1791), not just a file list: `xunit_v3_feature_detector.py` classifies
each construct, `hooks/lib/xunit_v3_operator_gate.py` renders what is blocking
plus the four remediation options (port / exclude / skip / degrade) with their
tradeoffs, and the guard **stays blocked until the operator's choice is
recorded**. That recording is what makes the gate a guarantee rather than hook
stdout an agent may paraphrase or skip: before #1791 the shim could be silently
built, silently declined, or silently degraded, and the operator found out from
a report — if at all. Once recorded, the choice drives the outcome: `exclude`
scaffolds with `--compile-exclude` on the flagged files, `port`/`skip` block
until the sources are clean, `degrade` hands back the no-shim floor command.

Contract (docs/python-hook-contract.md):
    Input : PreToolUse JSON on stdin
    Output: exit 2 + `[BLOCK]`-prefixed body on stdout to BLOCK
            exit 0 + no stdout for SILENT-PASS
    Env   : DEV_TEAM_STRYKER_XUNIT3_GATE_SKIP=1 -> silent bypass
            DEV_TEAM_XUNIT3_SHIM_DECISION_FILE  -> decision-store override

Stdlib-only.
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
_PY_SH = _HOOK_DIR / "py.sh"
_OPERATOR_GATE_MODULE = _LIB_DIR / "xunit_v3_operator_gate.py"

# The detector lives with the mutation-testing skill; the guard reuses it rather
# than keeping a second, drifting classification of the same constructs.
_DETECTOR_DIR = _PLUGIN_DIR / "skills" / "mutation-testing" / "scripts"
if str(_DETECTOR_DIR) not in sys.path:
    sys.path.insert(0, str(_DETECTOR_DIR))

try:
    import xunit_v3_feature_detector as _detector  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - degraded fallback, skill tree unreachable
    _detector = None

try:
    import xunit_v3_operator_gate as _operator_gate  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - degraded fallback, hooks/lib unreachable
    _operator_gate = None

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


def _classify(project_dir: Path) -> tuple[list[str], list[dict]]:
    """Scan the project's test sources for shim-breaking v3-only usage.

    Returns ``(flagged_files, classified_findings)``, both keyed on paths
    relative to ``project_dir`` so the operator-facing list and the
    ``--compile-exclude`` globs derived from it are stable regardless of where
    the run was launched.

    Two scans, deliberately: the detector supplies the *classification* the
    operator gate needs (which construct, translatable or not, coverage-bearing
    or neutral), while the older token list is broader — it catches v3-only
    usage the detector has no construct for. Dropping a token-flagged file for
    lacking a classification would silently narrow what the guard blocks on, so
    those files stay in ``flagged_files`` and reach the operator labelled as
    needing manual triage.
    """
    flagged: list[str] = []
    findings: list[dict] = []
    for dirpath, dirnames, filenames in os.walk(project_dir):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for name in sorted(filenames):
            if not name.endswith(".cs"):
                continue
            path = Path(dirpath) / name
            rel = str(path.relative_to(project_dir))
            text = _read(path)
            classified = []
            if _detector is not None:
                classified = [
                    {
                        "file": rel,
                        "line": f.line,
                        "construct": f.construct,
                        "compile_ability": f.compile_ability,
                        "coverage_impact": f.coverage_impact,
                        "snippet": f.snippet,
                    }
                    for f in _detector.scan_text(rel, text)
                ]
            findings.extend(classified)
            if classified or any(tok in text for tok in _V3_ONLY):
                flagged.append(rel)
    return flagged, findings


def _shim_dir_for(real_csproj: Path) -> Path:
    real_dir = real_csproj.parent
    return real_dir.parent / (real_csproj.stem + ".Mutation")


def _run_generator(
    real_csproj: Path, cwd: Path, extra_args: list[str] | None = None
) -> tuple[int, str]:
    if not _GENERATOR.is_file():
        return 127, f"generator not found at {_GENERATOR}"
    try:
        proc = subprocess.run(
            [sys.executable, str(_GENERATOR), str(real_csproj), *(extra_args or [])],
            cwd=str(cwd), capture_output=True, text=True, check=False, timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        return 1, str(exc)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _compile_exclude_globs(name: str, flagged: list[str]) -> list[str]:
    """`--compile-exclude` values for the flagged files.

    `generate_shim.py` links `..\\<Name>\\**\\*.cs`, so an exclusion has to be
    expressed in that same MSBuild-relative, backslashed form — a POSIX path
    here silently excludes nothing.
    """
    return [f"..\\{name}\\" + rel.replace("/", "\\").replace(os.sep, "\\")
            for rel in flagged]


def _record_command(name: str, fingerprint: str) -> str:
    """The command that satisfies the gate once the operator has answered.

    Routed through `hooks/py.sh` rather than a bare `python3` so it works where
    `python3` is absent (Windows, #1078), and with absolute paths so it does not
    depend on the cwd the agent happens to be in.
    """
    return (
        f'sh "{_PY_SH}" "{_OPERATOR_GATE_MODULE}" record '
        f'--project {name} --choice <port|exclude|skip|degrade> '
        f"--fingerprint {fingerprint}"
    )


def _floor_command(real_csproj: Path, cwd: Path) -> list[str]:
    """The sanctioned no-shim floor, spelled out.

    `coverage-analysis` is config-file-only in Stryker.NET (no CLI flag), so the
    instruction says to set it in the config — handing over a `--coverage-analysis`
    flag would just produce a failed command and a retry (#1777).
    """
    rel_project = os.path.relpath(real_csproj.parent, cwd)
    # A `cd .` is noise the operator has to read past to find the real command.
    lines = [] if rel_project == "." else [f"  cd {rel_project}"]
    return lines + [
        (
            '  # set "coverage-analysis": "off" in stryker-config.json '
            "(config-file-only — there is no CLI flag)"
        ),
        "  dotnet-stryker -t mtp",
    ]


def _operator_gate_block(
    header: str, real_csproj: Path, cwd: Path, flagged: list[str], findings: list[dict]
) -> list[str]:
    """The #1791 decision gate for one blocked project.

    Returns the block body: the operator question when no decision covers the
    current blocker set, otherwise the consequence of the recorded choice.
    """
    name = real_csproj.stem
    shim_dir = _shim_dir_for(real_csproj)
    rel_shim = os.path.relpath(shim_dir, cwd)
    unclassified = [f for f in flagged if all(d["file"] != f for d in findings)]

    question = _operator_gate.build_question(name, findings, unclassified)
    decision = _operator_gate.decision_for(question, cwd=cwd)

    if decision is None:
        return [
            header + ", and the operator has to choose how to handle it:",
            "",
        ] + _operator_gate.render_question(
            question, record_command=_record_command(name, question.fingerprint)
        )

    choice = decision.get("choice")
    if choice == "exclude":
        code, out = _run_generator(
            real_csproj,
            cwd,
            [arg for glob in _compile_exclude_globs(name, flagged)
             for arg in ("--compile-exclude", glob)],
        )
        if code != 0:
            return [
                header + ", and scaffolding with the operator's exclusions failed:",
                f"  {out.strip()[:400]}",
            ]
        return [
            header + " — scaffolded a xunit.v2 shim with the operator's exclusions",
            (
                f"({len(flagged)} file(s) dropped from the shim's compile set, so "
                "they stay UNMEASURED by mutation):"
            ),
        ] + ["  " + ln for ln in out.strip().splitlines()] + [
            "Run mutation FROM the shim dir:",
            f"  cd {rel_shim} && dotnet-stryker",
        ]

    if choice == "degrade":
        return [
            (
                header + " — the operator chose 'degrade': skip the shim and run "
                "the no-shim floor instead."
            ),
            (
                "It drives the real xunit.v3 suite, so the score is real but "
                "whole-suite-per-mutant (slow, single advisory pass, no kill loop):"
            ),
        ] + _floor_command(real_csproj, cwd)

    # port / skip: the sources have to change before a shim can compile.
    verb = (
        "Port these to v2-compatible forms"
        if choice == "port"
        else "Deactivate/skip these tests for the duration of the measurement"
    )
    return [
        header + f" — the operator chose '{choice}', which is not done yet.",
        (
            f"{verb} in the REAL test project (the shim links the same sources, so "
            "one edit serves both), then re-run — the guard scaffolds automatically "
            "once the sources are clean:"
        ),
    ] + [
        f"  - {d['file']}:{d['line']}  {d['construct']}  {d['snippet']}"
        for d in findings[:20]
    ] + [f"  - {f}  (unclassified — manual triage)" for f in unclassified[:20]] + [
        "See the stryker-xunit-v2-shim skill, Step 3 for the v3->v2 replacements.",
    ]


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

    # Shim-breaking sources: this is the operator's decision, not the agent's
    # (#1791). Never scaffold, decline, or degrade on their behalf.
    flagged, findings = _classify(real_csproj.parent)
    if flagged and _operator_gate is not None:
        return _operator_gate_block(header, real_csproj, cwd, flagged, findings)
    if flagged:  # pragma: no cover - degraded fallback, hooks/lib unreachable
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
        (
            "Nothing in these sources blocked the shim, so no operator decision "
            "was needed. If you would rather not shim at all, the no-shim floor is:"
        ),
    ] + _floor_command(real_csproj, cwd)
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
    # Resolve: every path in the block body is computed relative to this, and
    # `run_dir` (and so the shim dir derived from it) is already resolved. Mixing
    # a raw cwd with resolved targets turns a sibling directory into a
    # ../../../.. crawl back through the symlink's parent chain the moment the
    # cwd traverses a link — macOS /var -> /private/var is the everyday case.
    base = Path(cwd).resolve()

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
