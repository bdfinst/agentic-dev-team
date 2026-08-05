"""Tests for scripts/coverage_discovery_js.py (issue #1759, Slice 3).

Pure filesystem glob resolution and JSON/minimal-YAML parsing — no npm/yarn/
pnpm/lerna CLI is invoked, so these tests need no package manager installed.
"""

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import coverage_discovery_js as cdj
from coverage_config import DISCOVERY_NOT_APPLICABLE, TestClassification

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def write(path: Path, content) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, (dict, list)):
        path.write_text(json.dumps(content, indent=2), encoding="utf-8")
    else:
        path.write_text(content, encoding="utf-8")


def pkg(root: Path, data: dict) -> None:
    write(root / "package.json", data)


TEST_PKG = {
    "name": "test-pkg",
    "scripts": {"test": "jest"},
    "devDependencies": {"jest": "^29"},
}
NOT_TEST_PKG = {
    "name": "helper-pkg",
    "scripts": {"build": "tsc"},
}


# ---------------------------------------------------------------------------
# Step 3.1 — discover + classify happy path, across all three config shapes
# ---------------------------------------------------------------------------


def test_npm_workspaces_array_discovers_and_classifies(tmp_path):
    pkg(tmp_path, {"name": "root", "private": True, "workspaces": ["packages/*"]})
    pkg(tmp_path / "packages" / "a", TEST_PKG)
    pkg(tmp_path / "packages" / "b", NOT_TEST_PKG)

    result = cdj.discover_js_packages(tmp_path)

    assert result == [
        {"path": "packages/a", "classification": TestClassification.TEST},
        {"path": "packages/b", "classification": TestClassification.NOT_TEST},
    ]


def test_yarn_workspaces_packages_dict_form_discovers(tmp_path):
    pkg(
        tmp_path,
        {"name": "root", "private": True, "workspaces": {"packages": ["packages/*"]}},
    )
    pkg(tmp_path / "packages" / "a", TEST_PKG)

    result = cdj.discover_js_packages(tmp_path)

    assert result == [{"path": "packages/a", "classification": TestClassification.TEST}]


def test_pnpm_workspace_yaml_block_style_discovers_and_classifies(tmp_path):
    write(
        tmp_path / "pnpm-workspace.yaml",
        "packages:\n  - 'packages/*'\n  - 'apps/*'\n",
    )
    pkg(tmp_path / "packages" / "a", TEST_PKG)
    pkg(tmp_path / "apps" / "b", NOT_TEST_PKG)

    result = cdj.discover_js_packages(tmp_path)

    assert result == [
        {"path": "apps/b", "classification": TestClassification.NOT_TEST},
        {"path": "packages/a", "classification": TestClassification.TEST},
    ]


def test_lerna_json_discovers_and_classifies(tmp_path):
    write(tmp_path / "lerna.json", {"packages": ["packages/*"]})
    pkg(tmp_path / "packages" / "a", TEST_PKG)
    pkg(tmp_path / "packages" / "b", NOT_TEST_PKG)

    result = cdj.discover_js_packages(tmp_path)

    assert result == [
        {"path": "packages/a", "classification": TestClassification.TEST},
        {"path": "packages/b", "classification": TestClassification.NOT_TEST},
    ]


def test_test_script_without_coverage_capable_runner_is_not_test(tmp_path):
    pkg(tmp_path, {"name": "root", "private": True, "workspaces": ["packages/*"]})
    pkg(
        tmp_path / "packages" / "a",
        {"name": "a", "scripts": {"test": "tap test.js"}, "devDependencies": {"tap": "^18"}},
    )

    result = cdj.discover_js_packages(tmp_path)

    assert result == [{"path": "packages/a", "classification": TestClassification.NOT_TEST}]


def test_mocha_paired_with_nyc_is_test(tmp_path):
    pkg(tmp_path, {"name": "root", "private": True, "workspaces": ["packages/*"]})
    pkg(
        tmp_path / "packages" / "a",
        {
            "name": "a",
            "scripts": {"test": "mocha"},
            "devDependencies": {"mocha": "^10", "nyc": "^15"},
        },
    )

    result = cdj.discover_js_packages(tmp_path)

    assert result == [{"path": "packages/a", "classification": TestClassification.TEST}]


def test_mocha_without_nyc_or_c8_is_not_test(tmp_path):
    pkg(tmp_path, {"name": "root", "private": True, "workspaces": ["packages/*"]})
    pkg(
        tmp_path / "packages" / "a",
        {"name": "a", "scripts": {"test": "mocha"}, "devDependencies": {"mocha": "^10"}},
    )

    result = cdj.discover_js_packages(tmp_path)

    assert result == [{"path": "packages/a", "classification": TestClassification.NOT_TEST}]


def test_vitest_devdependency_is_test(tmp_path):
    pkg(tmp_path, {"name": "root", "private": True, "workspaces": ["packages/*"]})
    pkg(
        tmp_path / "packages" / "a",
        {"name": "a", "scripts": {"test": "vitest run"}, "devDependencies": {"vitest": "^2"}},
    )

    result = cdj.discover_js_packages(tmp_path)

    assert result == [{"path": "packages/a", "classification": TestClassification.TEST}]


# ---------------------------------------------------------------------------
# Step 3.2 — no-workspace-config and malformed/unsupported-input edge cases
# ---------------------------------------------------------------------------


def test_no_workspace_config_reports_not_applicable(tmp_path):
    pkg(tmp_path, {"name": "root"})

    result = cdj.discover_js_packages(tmp_path)

    assert result is DISCOVERY_NOT_APPLICABLE


def test_no_package_json_and_no_other_config_reports_not_applicable(tmp_path):
    result = cdj.discover_js_packages(tmp_path)

    assert result is DISCOVERY_NOT_APPLICABLE


def test_pnpm_workspace_yaml_flow_style_array_is_discovery_error(tmp_path):
    write(tmp_path / "pnpm-workspace.yaml", "packages: ['packages/a', 'packages/b']\n")

    result = cdj.discover_js_packages(tmp_path)

    assert result["signal"] == "error"
    assert result != DISCOVERY_NOT_APPLICABLE
    assert result != []
    assert "unsupported shape" in result["message"]


def test_pnpm_workspace_yaml_malformed_is_discovery_error(tmp_path):
    write(tmp_path / "pnpm-workspace.yaml", "this is not yaml with a packages key\n")

    result = cdj.discover_js_packages(tmp_path)

    assert result["signal"] == "error"
    assert "no top-level 'packages:' key" in result["message"]


def test_pnpm_workspace_yaml_error_messages_are_distinguishable(tmp_path):
    """The flow-style-array and outright-malformed-YAML error paths must
    produce genuinely different, shape-naming text — not collapse into one
    indistinguishable message."""
    flow_root = tmp_path / "flow"
    flow_root.mkdir()
    write(flow_root / "pnpm-workspace.yaml", "packages: ['packages/a']\n")

    malformed_root = tmp_path / "malformed"
    malformed_root.mkdir()
    write(malformed_root / "pnpm-workspace.yaml", "this is not yaml with a packages key\n")

    flow_result = cdj.discover_js_packages(flow_root)
    malformed_result = cdj.discover_js_packages(malformed_root)

    assert flow_result["message"] != malformed_result["message"]


def test_lerna_json_malformed_is_discovery_error(tmp_path):
    write(tmp_path / "lerna.json", "{not valid json")

    result = cdj.discover_js_packages(tmp_path)

    assert result["signal"] == "error"


def test_lerna_json_with_no_packages_key_resolves_to_empty_list(tmp_path):
    """A syntactically-valid lerna.json with no `packages` list is a
    recognized, present config declaring zero packages — not an error."""
    write(tmp_path / "lerna.json", {"version": "independent"})

    result = cdj.discover_js_packages(tmp_path)

    assert result == []


def test_workspace_glob_escaping_repo_root_is_discovery_error(tmp_path):
    """A workspace glob containing `..` that resolves outside the
    repository root must be rejected before it is ever read — never
    included, and never used to locate a package.json outside the root."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    pkg(repo_root, {"name": "root", "private": True, "workspaces": ["../outside/*"]})
    pkg(tmp_path / "outside" / "evil", {"name": "evil"})

    result = cdj.discover_js_packages(repo_root)

    assert result["signal"] == "error"
    assert "outside the repository root" in result["message"]


# ---------------------------------------------------------------------------
# Review fixes — Path.glob exception timing (an exception inside `glob`
# fires on first iteration, not on the call itself; the whole generator
# must be materialized inside a try/except, not just the call).
# ---------------------------------------------------------------------------


def test_absolute_path_glob_is_discovery_error(tmp_path):
    """`Path.glob` raises `NotImplementedError` for a non-relative pattern
    only once iterated — the exception must be caught, not left to
    propagate uncaught and crash discovery."""
    pkg(tmp_path, {"name": "root", "private": True, "workspaces": ["/etc/*"]})

    result = cdj.discover_js_packages(tmp_path)

    assert result["signal"] == "error"
    assert "/etc/*" in result["message"]


def test_malformed_double_star_glob_is_discovery_error(tmp_path):
    """`Path.glob` raises `ValueError` for a `**` that isn't its own path
    component — also only once iterated, not on the call."""
    pkg(tmp_path, {"name": "root", "private": True, "workspaces": ["packages/**pkg"]})

    result = cdj.discover_js_packages(tmp_path)

    assert result["signal"] == "error"
    assert "packages/**pkg" in result["message"]


# ---------------------------------------------------------------------------
# Review fixes — unbounded glob expansion guard (more than one `**` segment)
# ---------------------------------------------------------------------------


def test_glob_with_multiple_double_star_segments_is_discovery_error(tmp_path):
    pkg(tmp_path, {"name": "root", "private": True, "workspaces": ["**/a/**/b"]})

    result = cdj.discover_js_packages(tmp_path)

    assert result["signal"] == "error"
    assert "**/a/**/b" in result["message"]


# ---------------------------------------------------------------------------
# Review fixes — pnpm-workspace.yaml "packages: key present, no valid
# block-style items follow it" must error, never resolve to an empty list.
# ---------------------------------------------------------------------------


def test_pnpm_workspace_yaml_unindented_list_is_discovery_error(tmp_path):
    write(tmp_path / "pnpm-workspace.yaml", "packages:\n- 'packages/*'\n")

    result = cdj.discover_js_packages(tmp_path)

    assert result["signal"] == "error"


def test_pnpm_workspace_yaml_mapping_value_is_discovery_error(tmp_path):
    write(tmp_path / "pnpm-workspace.yaml", "packages:\n  foo: bar\n")

    result = cdj.discover_js_packages(tmp_path)

    assert result["signal"] == "error"


def test_pnpm_workspace_yaml_empty_value_is_discovery_error(tmp_path):
    write(tmp_path / "pnpm-workspace.yaml", "packages:\n")

    result = cdj.discover_js_packages(tmp_path)

    assert result["signal"] == "error"


# ---------------------------------------------------------------------------
# Review fixes — a whole-line `#` comment inside the `packages:` block must
# be skipped, not treated as the dedent that ends the list.
# ---------------------------------------------------------------------------


def test_pnpm_workspace_yaml_comment_line_does_not_truncate_list(tmp_path):
    write(
        tmp_path / "pnpm-workspace.yaml",
        "packages:\n  - 'packages/*'\n  # apps ship separately\n  - 'apps/*'\n",
    )
    pkg(tmp_path / "packages" / "a", TEST_PKG)
    pkg(tmp_path / "apps" / "b", NOT_TEST_PKG)

    result = cdj.discover_js_packages(tmp_path)

    assert result == [
        {"path": "apps/b", "classification": TestClassification.NOT_TEST},
        {"path": "packages/a", "classification": TestClassification.TEST},
    ]


# ---------------------------------------------------------------------------
# Review fixes — malformed/unrecognized-shape root package.json must error,
# never silently fall through to DISCOVERY_NOT_APPLICABLE.
# ---------------------------------------------------------------------------


def test_malformed_root_package_json_is_discovery_error(tmp_path):
    write(tmp_path / "package.json", "{not valid json")

    result = cdj.discover_js_packages(tmp_path)

    assert result["signal"] == "error"
    assert result != DISCOVERY_NOT_APPLICABLE


def test_workspaces_bare_string_is_discovery_error(tmp_path):
    pkg(tmp_path, {"name": "root", "private": True, "workspaces": "packages/*"})

    result = cdj.discover_js_packages(tmp_path)

    assert result["signal"] == "error"
    assert "unsupported shape" in result["message"]
    assert result != DISCOVERY_NOT_APPLICABLE


# ---------------------------------------------------------------------------
# Review fixes — a resolved package's package.json that exists but fails to
# parse must propagate a discovery_error naming that package, never
# silently classify NOT_TEST.
# ---------------------------------------------------------------------------


def test_resolved_package_with_malformed_package_json_is_discovery_error(tmp_path):
    pkg(tmp_path, {"name": "root", "private": True, "workspaces": ["packages/*"]})
    write(tmp_path / "packages" / "a" / "package.json", "{not valid json")

    result = cdj.discover_js_packages(tmp_path)

    assert result["signal"] == "error"
    assert "packages/a" in result["message"] or "packages" in result["message"]


# ---------------------------------------------------------------------------
# Review fixes — symlink/manifest-containment: a resolved package
# directory's package.json FILE must itself be re-resolved and checked for
# containment, not just the directory it lives in.
# ---------------------------------------------------------------------------


def test_symlinked_package_json_escaping_repo_root_is_discovery_error(tmp_path):
    """A resolved package directory can be safely inside `repo_root` while
    its `package.json` is a symlink pointing outside it — the directory-
    level containment check alone would miss this."""
    repo_root = tmp_path / "repo"
    pkg_dir = repo_root / "packages" / "a"
    pkg_dir.mkdir(parents=True)
    pkg(repo_root, {"name": "root", "private": True, "workspaces": ["packages/*"]})

    outside_manifest = tmp_path / "outside-package.json"
    write(outside_manifest, {"name": "evil"})
    try:
        (pkg_dir / "package.json").symlink_to(outside_manifest)
    except OSError as exc:
        pytest.skip(f"symlinks not supported on this platform: {exc}")

    result = cdj.discover_js_packages(repo_root)

    assert result["signal"] == "error"
    assert "outside the repository root" in result["message"]


# ---------------------------------------------------------------------------
# Review fixes — additional coverage: precedence order, more runner/tool
# combinations, non-string workspaces entries.
# ---------------------------------------------------------------------------


def test_package_json_workspaces_takes_precedence_over_pnpm_workspace_yaml(tmp_path):
    pkg(tmp_path, {"name": "root", "private": True, "workspaces": ["packages/*"]})
    write(tmp_path / "pnpm-workspace.yaml", "packages:\n  - 'apps/*'\n")
    pkg(tmp_path / "packages" / "a", TEST_PKG)
    pkg(tmp_path / "apps" / "b", NOT_TEST_PKG)

    result = cdj.discover_js_packages(tmp_path)

    assert result == [{"path": "packages/a", "classification": TestClassification.TEST}]


def test_ava_paired_with_nyc_is_test(tmp_path):
    pkg(tmp_path, {"name": "root", "private": True, "workspaces": ["packages/*"]})
    pkg(
        tmp_path / "packages" / "a",
        {
            "name": "a",
            "scripts": {"test": "ava"},
            "devDependencies": {"ava": "^5", "nyc": "^15"},
        },
    )

    result = cdj.discover_js_packages(tmp_path)

    assert result == [{"path": "packages/a", "classification": TestClassification.TEST}]


def test_mocha_paired_with_c8_is_test(tmp_path):
    pkg(tmp_path, {"name": "root", "private": True, "workspaces": ["packages/*"]})
    pkg(
        tmp_path / "packages" / "a",
        {
            "name": "a",
            "scripts": {"test": "mocha"},
            "devDependencies": {"mocha": "^10", "c8": "^9"},
        },
    )

    result = cdj.discover_js_packages(tmp_path)

    assert result == [{"path": "packages/a", "classification": TestClassification.TEST}]


def test_non_string_workspaces_entry_is_skipped(tmp_path):
    pkg(tmp_path, {"name": "root", "private": True, "workspaces": ["packages/*", 42]})
    pkg(tmp_path / "packages" / "a", TEST_PKG)

    result = cdj.discover_js_packages(tmp_path)

    assert result == [{"path": "packages/a", "classification": TestClassification.TEST}]


# ---------------------------------------------------------------------------
# Brace-glob expansion (issue #1827)
#
# npm, yarn and pnpm all accept brace alternations in workspace globs, but
# `pathlib` does not expand them — so before #1827 an affected repo resolved
# to ZERO packages with no error, the silent-under-report shape #1759 exists
# to prevent.
# ---------------------------------------------------------------------------


def test_brace_glob_discovers_every_alternative(tmp_path):
    pkg(tmp_path, {"name": "root", "workspaces": ["apps/{web,api}"]})
    pkg(tmp_path / "apps" / "web", TEST_PKG)
    pkg(tmp_path / "apps" / "api", TEST_PKG)

    result = cdj.discover_js_packages(tmp_path)

    assert [p["path"] for p in result] == ["apps/api", "apps/web"]
    assert all(p["classification"] is TestClassification.TEST for p in result)


def test_brace_glob_matches_plain_star_glob_on_same_tree(tmp_path):
    """The regression guard for #1827: brace and star forms describe the same
    set here, so they must discover the same packages."""
    brace_root = tmp_path / "brace"
    star_root = tmp_path / "star"
    for root, globs in ((brace_root, ["apps/{web,api}"]), (star_root, ["apps/*"])):
        pkg(root, {"name": "root", "workspaces": globs})
        pkg(root / "apps" / "web", TEST_PKG)
        pkg(root / "apps" / "api", TEST_PKG)

    brace = [p["path"] for p in cdj.discover_js_packages(brace_root)]
    star = [p["path"] for p in cdj.discover_js_packages(star_root)]

    assert brace == star == ["apps/api", "apps/web"]


def test_multiple_brace_groups_expand_as_cartesian_product(tmp_path):
    pkg(tmp_path, {"name": "root", "workspaces": ["{apps,libs}/{web,api}"]})
    for top in ("apps", "libs"):
        for leaf in ("web", "api"):
            pkg(tmp_path / top / leaf, TEST_PKG)

    result = [p["path"] for p in cdj.discover_js_packages(tmp_path)]

    assert result == ["apps/api", "apps/web", "libs/api", "libs/web"]


def test_nested_braces_expand(tmp_path):
    pkg(tmp_path, {"name": "root", "workspaces": ["apps/{web,{api,worker}}"]})
    for leaf in ("web", "api", "worker"):
        pkg(tmp_path / "apps" / leaf, TEST_PKG)

    result = [p["path"] for p in cdj.discover_js_packages(tmp_path)]

    assert result == ["apps/api", "apps/web", "apps/worker"]


def test_brace_glob_combines_with_star(tmp_path):
    pkg(tmp_path, {"name": "root", "workspaces": ["{apps,libs}/*"]})
    pkg(tmp_path / "apps" / "web", TEST_PKG)
    pkg(tmp_path / "libs" / "shared", NOT_TEST_PKG)

    result = cdj.discover_js_packages(tmp_path)

    assert [p["path"] for p in result] == ["apps/web", "libs/shared"]


@pytest.mark.parametrize(
    "bad_glob",
    [
        "apps/{web,api",
        "apps/web}",
        "apps/{a,{b}",
        "apps/}web{",
        # Regression guards for the defect both reviewers caught in the first
        # cut of this fix: a stray `}` LEFT of the first `{` was absorbed into
        # the literal prefix, expanding to globs that match nothing — the very
        # silent-zero outcome #1827 exists to prevent. Each of these has a
        # well-formed group after the stray brace, so an implementation that
        # only balance-checks from the first `{` onward accepts them.
        "apps/}x{a,b}",
        "{apps,libs}}/{web,api}",
    ],
)
def test_unbalanced_brace_is_a_discovery_error_not_a_silent_empty(tmp_path, bad_glob):
    pkg(tmp_path, {"name": "root", "workspaces": [bad_glob]})
    pkg(tmp_path / "apps" / "web", TEST_PKG)

    result = cdj.discover_js_packages(tmp_path)

    assert isinstance(result, dict)
    assert result.get("signal") == "error"
    assert "brace" in result["message"].lower()
    assert bad_glob in result["message"]


def test_brace_traversal_guard_still_fires_on_an_expanded_alternative(tmp_path):
    """An escaping path hidden inside one brace alternative must still be
    refused — expansion happens before the containment check, not instead."""
    root = tmp_path / "repo"
    pkg(root, {"name": "root", "workspaces": ["{apps,../outside}/*"]})
    pkg(root / "apps" / "web", TEST_PKG)
    pkg(tmp_path / "outside" / "evil", TEST_PKG)

    result = cdj.discover_js_packages(root)

    assert isinstance(result, dict)
    assert result.get("signal") == "error"
    assert "outside the repository" in result["message"]


def test_empty_brace_alternative_does_not_fail_the_whole_workspace(tmp_path):
    """`{packages/*,}` is legal in npm/minimatch — the empty alternative just
    contributes nothing. It must not reach `Path.glob`, which rejects `''`
    outright and would otherwise fail discovery for the entire workspace even
    though the non-empty alternative resolved fine."""
    pkg(tmp_path, {"name": "root", "workspaces": ["{packages/*,}"]})
    pkg(tmp_path / "packages" / "a", TEST_PKG)

    result = cdj.discover_js_packages(tmp_path)

    assert not isinstance(result, dict), f"expected packages, got error: {result}"
    assert [p["path"] for p in result] == ["packages/a"]


def test_trailing_empty_alternative_keeps_the_named_packages(tmp_path):
    pkg(tmp_path, {"name": "root", "workspaces": ["apps/{web,api,}"]})
    pkg(tmp_path / "apps" / "web", TEST_PKG)
    pkg(tmp_path / "apps" / "api", TEST_PKG)

    result = cdj.discover_js_packages(tmp_path)

    assert [p["path"] for p in result] == ["apps/api", "apps/web"]


def test_brace_multiplication_cannot_smuggle_extra_double_stars(tmp_path):
    """The `>1 '**'` cost guard is enforced on the DECLARED glob, not only per
    expanded alternative — otherwise `{**/x,**/y,**/z}` (three single-`**`
    alternatives) would buy three recursive walks past a guard whose whole
    purpose is to refuse exactly that."""
    pkg(tmp_path, {"name": "root", "workspaces": ["{**/x,**/y,**/z}"]})

    result = cdj.discover_js_packages(tmp_path)

    assert isinstance(result, dict)
    assert result.get("signal") == "error"
    assert "'**'" in result["message"]


def test_brace_group_combined_with_double_star_still_resolves(tmp_path):
    """The declared-pattern budget must not reject a legitimate single-`**`
    glob just because a brace group multiplies it."""
    pkg(tmp_path, {"name": "root", "workspaces": ["{apps,libs}/**"]})
    pkg(tmp_path / "apps" / "web", TEST_PKG)
    pkg(tmp_path / "libs" / "shared" / "nested", NOT_TEST_PKG)

    result = cdj.discover_js_packages(tmp_path)

    assert not isinstance(result, dict), f"expected packages, got error: {result}"
    assert [p["path"] for p in result] == ["apps/web", "libs/shared/nested"]


def test_absolute_path_hidden_in_a_brace_alternative_is_refused(tmp_path):
    pkg(tmp_path, {"name": "root", "workspaces": ["{apps,/etc}/*"]})
    pkg(tmp_path / "apps" / "web", TEST_PKG)

    result = cdj.discover_js_packages(tmp_path)

    assert isinstance(result, dict)
    assert result.get("signal") == "error"


def test_runaway_brace_expansion_is_a_discovery_error_not_a_walk_bomb(tmp_path):
    """Expansion is a cartesian product; 20 two-way groups is 2**20 globs and
    as many filesystem walks. Refuse rather than attempt it."""
    pkg(tmp_path, {"name": "root", "workspaces": ["{a,b}" * 20 + "/*"]})

    result = cdj.discover_js_packages(tmp_path)

    assert isinstance(result, dict)
    assert result.get("signal") == "error"
    assert "alternatives" in result["message"]


def test_deeply_nested_braces_error_rather_than_raising_recursionerror(tmp_path):
    pkg(tmp_path, {"name": "root", "workspaces": ["{" * 400 + "x" + "}" * 400]})

    result = cdj.discover_js_packages(tmp_path)

    assert isinstance(result, dict)
    assert result.get("signal") == "error"


def test_brace_glob_works_via_pnpm_workspace_yaml(tmp_path):
    """Brace expansion lives in the shared resolution path, so it must apply to
    every workspace source — not just `package.json`."""
    pkg(tmp_path, {"name": "root", "private": True})
    write(tmp_path / "pnpm-workspace.yaml", "packages:\n  - 'apps/{web,api}'\n")
    pkg(tmp_path / "apps" / "web", TEST_PKG)
    pkg(tmp_path / "apps" / "api", TEST_PKG)

    result = cdj.discover_js_packages(tmp_path)

    assert not isinstance(result, dict), f"expected packages, got error: {result}"
    assert [p["path"] for p in result] == ["apps/api", "apps/web"]


def test_brace_glob_works_via_lerna_json(tmp_path):
    pkg(tmp_path, {"name": "root", "private": True})
    write(tmp_path / "lerna.json", {"packages": ["{apps,libs}/web"]})
    pkg(tmp_path / "apps" / "web", TEST_PKG)
    pkg(tmp_path / "libs" / "web", TEST_PKG)

    result = cdj.discover_js_packages(tmp_path)

    assert not isinstance(result, dict), f"expected packages, got error: {result}"
    assert [p["path"] for p in result] == ["apps/web", "libs/web"]
