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


def test_stryker_bin_defaults_to_the_local_tool_manifest_shape():
    args = parse_args([])

    assert args.stryker_bin == "dotnet"
