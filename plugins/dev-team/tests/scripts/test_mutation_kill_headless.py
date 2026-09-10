"""Unit tests for skills/mutation-testing/scripts/mutation_kill_headless.py.

Pins the ``--stryker-bin`` default to ``"dotnet"`` — the local-tool-manifest
invocation shape (``dotnet stryker ...``), which is the skill's own
recommended install path. The previous default (a bare ``dotnet-stryker``)
assumed a global install and failed outright against a local one.
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

from mutation_kill_headless import parse_args


def test_stryker_bin_defaults_to_the_local_tool_manifest_shape(monkeypatch):
    # Isolate from an ambient STRYKER_BIN in the invoking environment now
    # that the default reads it (#2145) -- this test pins the *fallback*.
    monkeypatch.delenv("STRYKER_BIN", raising=False)

    args = parse_args([])

    assert args.stryker_bin == "dotnet"


def test_stryker_bin_default_honors_the_stryker_bin_env_var(monkeypatch):
    """#2145 item 4: this script's --stryker-bin default previously ignored
    STRYKER_BIN, inconsistent with the skill's other scripts (wrapper.py,
    slice_runner.py), whose docs claim every flag has an env-var equivalent."""
    monkeypatch.setenv("STRYKER_BIN", "dotnet-stryker")

    args = parse_args([])

    assert args.stryker_bin == "dotnet-stryker"


def test_explicit_stryker_bin_flag_overrides_the_env_var(monkeypatch):
    monkeypatch.setenv("STRYKER_BIN", "dotnet-stryker")

    args = parse_args(["--stryker-bin", "dotnet"])

    assert args.stryker_bin == "dotnet"
