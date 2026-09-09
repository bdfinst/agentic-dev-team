"""Unit tests for skills/mutation-testing/scripts/stryker_shard_pipeline.py.

Pins the ``--stryker-bin`` default to ``"dotnet"`` — the local-tool-manifest
invocation shape (``dotnet stryker ...``), which is the skill's own
recommended install path. The previous default (a bare ``dotnet-stryker``)
assumed a global install and failed outright against a local one. The
argv actually built for the run itself is unaffected here: this module
delegates to ``csharp_stryker_net_wrapper.run_stryker``, which owns
building the real argv (covered by that module's own tests).
"""

from __future__ import annotations

import sys

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(
    0,
    str(
        _REPO_ROOT
        / "plugins"
        / "dev-team"
        / "skills"
        / "mutation-testing"
        / "scripts"
    ),
)

from pathlib import Path

from stryker_shard_pipeline import build_loop_command, build_parser


def test_stryker_bin_defaults_to_the_local_tool_manifest_shape(monkeypatch):
    # Isolate from an ambient STRYKER_BIN in the invoking environment now
    # that the default reads it (#2145) -- this test pins the *fallback*.
    monkeypatch.delenv("STRYKER_BIN", raising=False)

    args = build_parser().parse_args([])

    assert args.stryker_bin == "dotnet"


def test_stryker_bin_default_honors_the_stryker_bin_env_var(monkeypatch):
    """#2145 item 4: this script's --stryker-bin default previously ignored
    STRYKER_BIN, inconsistent with the skill's other scripts (wrapper.py,
    slice_runner.py), whose docs claim every flag has an env-var equivalent."""
    monkeypatch.setenv("STRYKER_BIN", "dotnet-stryker")

    args = build_parser().parse_args([])

    assert args.stryker_bin == "dotnet-stryker"


def test_explicit_stryker_bin_flag_overrides_the_env_var(monkeypatch):
    monkeypatch.setenv("STRYKER_BIN", "dotnet-stryker")

    args = build_parser().parse_args(["--stryker-bin", "dotnet"])

    assert args.stryker_bin == "dotnet"


def test_build_loop_command_forwards_stryker_bin_to_the_survivor_fix_subprocess():
    # An explicit --stryker-bin override (e.g. targeting a global install)
    # on the pipeline must reach the per-file mutation_kill_loop subprocess
    # too, not silently fall back to that subprocess's own independent
    # default.
    cmd = build_loop_command(
        config=Path("stryker-config.json"),
        source_file="Foo.cs",
        source_path="src/Foo.cs",
        test_file=Path("tests/FooTests.cs"),
        report=Path("report.json"),
        model=None,
        max_rounds=5,
        stryker_bin="dotnet-stryker",
    )

    assert "--stryker-bin" in cmd
    assert cmd[cmd.index("--stryker-bin") + 1] == "dotnet-stryker"
