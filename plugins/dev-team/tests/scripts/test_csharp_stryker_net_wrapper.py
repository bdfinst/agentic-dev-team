"""Unit tests for skills/mutation-testing/scripts/csharp_stryker_net_wrapper.py.

Covers a regression fix: the wrapper's ``--stryker-bin`` default (and the
shipped slice runner's matching default) previously assumed a **global**
Stryker.NET install — a bare ``dotnet-stryker`` executable reachable
directly on ``PATH``. The skill's own docs recommend a **local** tool-
manifest install instead (SKILL.md's "Prefer a local install"), but a local
tool's command name is never placed on ``PATH`` — it is only reachable
through ``dotnet``'s own verb-resolution convention (``dotnet stryker``
finds the local ``dotnet-stryker`` tool). Invoking the previous default
literally as a subprocess therefore failed outright for the documented,
preferred install path. ``build_stryker_argv`` fixes this by auto-detecting
from ``stryker_bin`` whether to insert the ``stryker`` verb.
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

from csharp_stryker_net_wrapper import build_stryker_argv


def test_dotnet_stryker_bin_inserts_the_stryker_verb():
    argv = build_stryker_argv("dotnet", ["--config-file", "stryker-config.json"])

    assert argv == ["dotnet", "stryker", "--config-file", "stryker-config.json"]


def test_explicit_global_install_binary_is_used_unchanged():
    argv = build_stryker_argv("dotnet-stryker", ["--config-file", "stryker-config.json"])

    assert argv == ["dotnet-stryker", "--config-file", "stryker-config.json"]


def test_an_arbitrary_custom_binary_name_is_also_used_unchanged():
    argv = build_stryker_argv("/opt/tools/my-stryker-shim", ["-O", "StrykerOutput"])

    assert argv == ["/opt/tools/my-stryker-shim", "-O", "StrykerOutput"]


def test_empty_stryker_args_still_produces_a_valid_argv():
    assert build_stryker_argv("dotnet", []) == ["dotnet", "stryker"]
