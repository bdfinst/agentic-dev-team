"""Unit tests for skills/mutation-testing/scripts/csharp_stryker_net_slice_runner.py.

Covers a regression fix: without an explicit ``"project"`` key, Stryker.NET
auto-discovers every source project transitively referenced by the
configured ``test-projects`` and re-runs its build + initial-test-run +
coverage-capture cycle for each one on every slice invocation, regardless of
that slice's ``mutate`` glob — multiplying fixed per-slice overhead by the
number of source projects in the solution. ``build_slice_stryker_config``
now passes through any slice key beyond ``mutate`` (most usefully
``"project"``) into the generated per-slice config.
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

from csharp_stryker_net_slice_runner import build_slice_stryker_config, parse_args


def test_stryker_bin_defaults_to_the_local_tool_manifest_shape():
    args = parse_args(["--slice", "all"])

    assert args.stryker_bin == "dotnet"


def test_project_key_is_merged_into_the_generated_config():
    cfg = build_slice_stryker_config(
        {"test-projects": ["Foo.Tests.csproj"]},
        {"name": "widgets", "mutate": "**/Widgets/**/*.cs", "project": "Widgets.csproj"},
    )

    assert cfg["project"] == "Widgets.csproj"


def test_slice_without_a_project_key_omits_it_entirely():
    cfg = build_slice_stryker_config(
        {"test-projects": ["Foo.Tests.csproj"]},
        {"name": "widgets", "mutate": "**/Widgets/**/*.cs"},
    )

    assert "project" not in cfg


def test_name_is_never_merged_into_the_generated_config():
    cfg = build_slice_stryker_config({}, {"name": "widgets", "mutate": "**/*.cs"})

    assert "name" not in cfg


def test_reserved_but_unimplemented_slice_fields_stay_out_of_the_config():
    # kind / mutation-level / exclude-converged are accepted at the slice
    # level (reserved for #667) but not yet acted on by this runner — they
    # must not leak into the generated Stryker config as unknown keys.
    cfg = build_slice_stryker_config(
        {},
        {
            "name": "widgets",
            "mutate": "**/*.cs",
            "kind": "logic",
            "mutation-level": "Standard",
            "exclude-converged": True,
        },
    )

    assert "kind" not in cfg
    assert "mutation-level" not in cfg
    assert "exclude-converged" not in cfg


def test_base_config_values_still_flow_through_unchanged():
    cfg = build_slice_stryker_config(
        {"test-projects": ["Foo.Tests.csproj"], "reporters": ["dots", "json"]},
        {"name": "widgets", "mutate": "**/*.cs", "project": "Widgets.csproj"},
    )

    assert cfg["test-projects"] == ["Foo.Tests.csproj"]
    assert cfg["reporters"] == ["dots", "json"]


def test_mutate_is_still_wrapped_in_a_list_when_given_as_a_bare_string():
    cfg = build_slice_stryker_config({}, {"name": "widgets", "mutate": "**/*.cs"})

    assert cfg["mutate"] == ["**/*.cs"]
