"""Tests for coverage_discovery_js.py — JS/TS workspace discovery (#1782).

Workspace globs are resolved against the filesystem directly, so no
package-manager CLI is invoked and no `node_modules` install is needed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

import coverage_config as cc
import coverage_discovery_js as jsd

_TEST = cc.TestClassification.TEST
_NOT_TEST = cc.TestClassification.NOT_TEST


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _package(
    root: Path,
    rel_dir: str,
    *,
    name: str | None = None,
    scripts: dict | None = None,
    dev_dependencies: dict | None = None,
    dependencies: dict | None = None,
) -> Path:
    manifest: dict = {"name": name or rel_dir.replace("/", "-")}
    if scripts is not None:
        manifest["scripts"] = scripts
    if dev_dependencies is not None:
        manifest["devDependencies"] = dev_dependencies
    if dependencies is not None:
        manifest["dependencies"] = dependencies
    return _write(root / rel_dir / "package.json", json.dumps(manifest))


def _jest_package(root: Path, rel_dir: str) -> Path:
    return _package(
        root,
        rel_dir,
        scripts={"test": "jest"},
        dev_dependencies={"jest": "^29.0.0"},
    )


def _root_manifest(root: Path, workspaces: object) -> Path:
    return _write(
        root / "package.json", json.dumps({"name": "monorepo", "workspaces": workspaces})
    )


def _classification_of(projects: list[cc.DiscoveredProject], path: str):
    return next(project.classification for project in projects if project.path == path)


# ---------------------------------------------------------------------------
# Not-applicable signal
# ---------------------------------------------------------------------------


def test_a_single_package_with_no_workspace_config_is_not_applicable(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "package.json",
        json.dumps({"name": "solo", "scripts": {"test": "jest"}}),
    )

    result = jsd.discover(tmp_path)

    assert result is cc.DISCOVERY_NOT_APPLICABLE


def test_no_manifest_at_all_is_not_applicable(tmp_path: Path) -> None:
    assert jsd.discover(tmp_path) is cc.DISCOVERY_NOT_APPLICABLE


# ---------------------------------------------------------------------------
# The three workspace-config shapes
# ---------------------------------------------------------------------------


def test_npm_yarn_workspaces_array_is_discovered(tmp_path: Path) -> None:
    _root_manifest(tmp_path, ["packages/*"])
    _jest_package(tmp_path, "packages/alpha")
    _package(tmp_path, "packages/beta", scripts={"build": "tsc"})

    result = jsd.discover(tmp_path)

    assert [project.path for project in result] == [
        "packages/alpha",
        "packages/beta",
    ]
    assert _classification_of(result, "packages/alpha") is _TEST
    assert _classification_of(result, "packages/beta") is _NOT_TEST


def test_yarn_object_workspaces_form_is_discovered(tmp_path: Path) -> None:
    _root_manifest(tmp_path, {"packages": ["libs/*"], "nohoist": ["**/react-native"]})
    _jest_package(tmp_path, "libs/one")

    result = jsd.discover(tmp_path)

    assert [project.path for project in result] == ["libs/one"]


def test_pnpm_workspace_yaml_is_discovered(tmp_path: Path) -> None:
    _write(
        tmp_path / "pnpm-workspace.yaml",
        "packages:\n  - 'packages/*'\n  - \"apps/*\"\n  - tools/cli\n",
    )
    _jest_package(tmp_path, "packages/alpha")
    _jest_package(tmp_path, "apps/web")
    _jest_package(tmp_path, "tools/cli")

    result = jsd.discover(tmp_path)

    assert [project.path for project in result] == [
        "apps/web",
        "packages/alpha",
        "tools/cli",
    ]


def test_pnpm_workspace_yml_extension_is_also_recognized(tmp_path: Path) -> None:
    _write(tmp_path / "pnpm-workspace.yml", "packages:\n  - 'packages/*'\n")
    _jest_package(tmp_path, "packages/alpha")

    result = jsd.discover(tmp_path)

    assert [project.path for project in result] == ["packages/alpha"]


def test_lerna_json_packages_is_discovered(tmp_path: Path) -> None:
    _write(tmp_path / "lerna.json", json.dumps({"packages": ["modules/*"]}))
    _jest_package(tmp_path, "modules/one")

    result = jsd.discover(tmp_path)

    assert [project.path for project in result] == ["modules/one"]


def test_all_three_shapes_classify_consistently(tmp_path: Path) -> None:
    # The same package, reachable through each config shape, must classify the
    # same way regardless of which shape declared it.
    classifications = set()
    for index, writer in enumerate(
        (
            lambda root: _root_manifest(root, ["packages/*"]),
            lambda root: _write(
                root / "pnpm-workspace.yaml", "packages:\n  - 'packages/*'\n"
            ),
            lambda root: _write(
                root / "lerna.json", json.dumps({"packages": ["packages/*"]})
            ),
        )
    ):
        root = tmp_path / f"repo{index}"
        root.mkdir()
        writer(root)
        _jest_package(root, "packages/alpha")
        result = jsd.discover(root)
        assert [project.path for project in result] == ["packages/alpha"]
        classifications.add(_classification_of(result, "packages/alpha"))

    assert classifications == {_TEST}


def test_config_shapes_are_unioned_not_first_match_wins(tmp_path: Path) -> None:
    _root_manifest(tmp_path, ["packages/*"])
    _write(tmp_path / "lerna.json", json.dumps({"packages": ["legacy/*"]}))
    _jest_package(tmp_path, "packages/alpha")
    _jest_package(tmp_path, "legacy/old")

    result = jsd.discover(tmp_path)

    assert [project.path for project in result] == ["legacy/old", "packages/alpha"]


# ---------------------------------------------------------------------------
# Glob resolution
# ---------------------------------------------------------------------------


def test_a_recursive_glob_resolves(tmp_path: Path) -> None:
    _root_manifest(tmp_path, ["packages/**"])
    _jest_package(tmp_path, "packages/group/nested")

    result = jsd.discover(tmp_path)

    assert [project.path for project in result] == ["packages/group/nested"]


def test_a_negated_pattern_excludes_a_matched_package(tmp_path: Path) -> None:
    _root_manifest(tmp_path, ["packages/*", "!packages/fixtures"])
    _jest_package(tmp_path, "packages/alpha")
    _jest_package(tmp_path, "packages/fixtures")

    result = jsd.discover(tmp_path)

    assert [project.path for project in result] == ["packages/alpha"]


def test_a_glob_matching_a_directory_without_a_manifest_is_skipped(
    tmp_path: Path,
) -> None:
    _root_manifest(tmp_path, ["packages/*"])
    _jest_package(tmp_path, "packages/alpha")
    (tmp_path / "packages" / "not-a-package").mkdir(parents=True)

    result = jsd.discover(tmp_path)

    assert [project.path for project in result] == ["packages/alpha"]


def test_node_modules_is_never_discovered(tmp_path: Path) -> None:
    _root_manifest(tmp_path, ["packages/**"])
    _jest_package(tmp_path, "packages/alpha")
    _jest_package(tmp_path, "packages/alpha/node_modules/hoisted-dep")

    result = jsd.discover(tmp_path)

    assert [project.path for project in result] == ["packages/alpha"]


def test_the_root_package_is_not_discovered_as_its_own_workspace(
    tmp_path: Path,
) -> None:
    _root_manifest(tmp_path, ["."])
    _jest_package(tmp_path, "packages/alpha")

    result = jsd.discover(tmp_path)

    assert [project.path for project in result] == []


def test_discovered_paths_are_repo_relative_forward_slash(tmp_path: Path) -> None:
    _root_manifest(tmp_path, ["packages/*"])
    _jest_package(tmp_path, "packages/deep/alpha")
    _root_manifest(tmp_path, ["packages/deep/*"])

    result = jsd.discover(tmp_path)

    assert [project.path for project in result] == ["packages/deep/alpha"]


@pytest.mark.parametrize(
    "unsafe", ["/etc", "../outside/*", "packages/$(whoami)", "packages/a;rm -rf b"]
)
def test_an_unsafe_glob_pattern_is_a_discovery_error(
    tmp_path: Path, unsafe: str
) -> None:
    _root_manifest(tmp_path, [unsafe])

    with pytest.raises(cc.DiscoveryError, match="unsafe"):
        jsd.discover(tmp_path)


def test_a_brace_alternation_pattern_resolves(tmp_path: Path) -> None:
    # All three managers accept braces; `pathlib.Path.glob` does not, so without
    # expansion these two real test packages would vanish with no diagnostic.
    _root_manifest(tmp_path, ["apps/{web,api}"])
    _jest_package(tmp_path, "apps/web")
    _jest_package(tmp_path, "apps/api")
    _jest_package(tmp_path, "apps/admin")

    result = jsd.discover(tmp_path)

    assert [project.path for project in result] == ["apps/api", "apps/web"]


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ("apps/*", ["apps/*"]),
        ("apps/{web,api}", ["apps/web", "apps/api"]),
        ("{a,b}/{x,y}", ["a/x", "a/y", "b/x", "b/y"]),
        ("apps/{ web , api }", ["apps/web", "apps/api"]),
    ],
)
def test_brace_expansion_enumerates_every_combination(
    pattern: str, expected: list[str]
) -> None:
    assert sorted(jsd.expand_braces(pattern)) == sorted(expected)


def test_an_unbalanced_brace_is_a_discovery_error_not_a_silent_zero_match(
    tmp_path: Path,
) -> None:
    _root_manifest(tmp_path, ["apps/{web"])
    _jest_package(tmp_path, "apps/web")

    with pytest.raises(cc.DiscoveryError, match="unbalanced brace"):
        jsd.discover(tmp_path)


def test_a_wildcard_never_matches_a_dot_directory(tmp_path: Path) -> None:
    # minimatch and fast-glob exclude leading-dot names from `*`; Path.glob does not.
    _root_manifest(tmp_path, ["packages/*"])
    _jest_package(tmp_path, "packages/alpha")
    _jest_package(tmp_path, "packages/.cache")

    result = jsd.discover(tmp_path)

    assert [project.path for project in result] == ["packages/alpha"]


def test_an_explicitly_declared_dot_path_is_still_discovered(tmp_path: Path) -> None:
    # Dropping these would be the under-report direction: the operator named it.
    _root_manifest(tmp_path, [".internal/*"])
    _jest_package(tmp_path, ".internal/tools")

    result = jsd.discover(tmp_path)

    assert [project.path for project in result] == [".internal/tools"]


def test_a_repo_path_that_is_not_a_directory_is_an_error_not_not_applicable(
    tmp_path: Path,
) -> None:
    # A typo'd repo path must not read as "this stack does not apply".
    with pytest.raises(cc.DiscoveryError, match="not a directory"):
        jsd.discover(tmp_path / "does-not-exist")


def test_a_symlinked_workspace_keeps_its_declared_identity(tmp_path: Path) -> None:
    # Resolving the candidate would rewrite the identity `coverage_config`
    # matches as an exact string, collapsing two entries into one.
    _root_manifest(tmp_path, ["packages/*", "apps/*"])
    _jest_package(tmp_path, "packages/web")
    (tmp_path / "apps").mkdir()
    (tmp_path / "apps" / "web").symlink_to(
        tmp_path / "packages" / "web", target_is_directory=True
    )

    result = jsd.discover(tmp_path)

    assert [project.path for project in result] == ["apps/web", "packages/web"]


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "dev_dependencies",
    [
        {"jest": "^29.0.0"},
        {"vitest": "^2.0.0"},
        {"mocha": "^10.0.0", "nyc": "^17.0.0"},
        {"mocha": "^10.0.0", "c8": "^10.0.0"},
        {"ava": "^6.0.0", "c8": "^10.0.0"},
        {"ava": "^6.0.0", "nyc": "^17.0.0"},
    ],
)
def test_a_test_script_plus_a_coverage_capable_runner_classifies_test(
    tmp_path: Path, dev_dependencies: dict
) -> None:
    _root_manifest(tmp_path, ["packages/*"])
    _package(
        tmp_path,
        "packages/alpha",
        scripts={"test": "run tests"},
        dev_dependencies=dev_dependencies,
    )

    result = jsd.discover(tmp_path)

    assert _classification_of(result, "packages/alpha") is _TEST


@pytest.mark.parametrize(
    ("scripts", "dev_dependencies"),
    [
        # Test script but no coverage-capable runner at all.
        ({"test": "node --test"}, {"typescript": "^5.0.0"}),
        # mocha/ava without a coverage tool alongside it.
        ({"test": "mocha"}, {"mocha": "^10.0.0"}),
        ({"test": "ava"}, {"ava": "^6.0.0"}),
        # A coverage-capable runner but no test script to invoke it.
        ({"build": "tsc"}, {"jest": "^29.0.0"}),
        # No scripts block at all.
        (None, {"jest": "^29.0.0"}),
        # An empty test script is not a test script.
        ({"test": "   "}, {"jest": "^29.0.0"}),
        # The npm-init placeholder that exits non-zero is not a real test script.
        (
            {"test": 'echo "Error: no test specified" && exit 1'},
            {"jest": "^29.0.0"},
        ),
    ],
)
def test_an_incomplete_marker_classifies_not_test(
    tmp_path: Path, scripts: dict | None, dev_dependencies: dict
) -> None:
    _root_manifest(tmp_path, ["packages/*"])
    _package(
        tmp_path,
        "packages/alpha",
        scripts=scripts,
        dev_dependencies=dev_dependencies,
    )

    result = jsd.discover(tmp_path)

    assert _classification_of(result, "packages/alpha") is _NOT_TEST


def test_a_runner_in_dependencies_rather_than_dev_dependencies_still_counts(
    tmp_path: Path,
) -> None:
    # Misplacing a runner in `dependencies` is common and never a reason to leave
    # a real test package out of coverage — the #1759 failure direction.
    _root_manifest(tmp_path, ["packages/*"])
    _package(
        tmp_path,
        "packages/alpha",
        scripts={"test": "vitest run"},
        dependencies={"vitest": "^2.0.0"},
    )

    result = jsd.discover(tmp_path)

    assert _classification_of(result, "packages/alpha") is _TEST


def test_a_scoped_runner_package_is_not_mistaken_for_the_runner(
    tmp_path: Path,
) -> None:
    _root_manifest(tmp_path, ["packages/*"])
    _package(
        tmp_path,
        "packages/alpha",
        scripts={"test": "echo hi"},
        dev_dependencies={"@types/jest": "^29.0.0", "eslint-plugin-jest": "^28.0.0"},
    )

    result = jsd.discover(tmp_path)

    assert _classification_of(result, "packages/alpha") is _NOT_TEST


# ---------------------------------------------------------------------------
# pnpm YAML parser — supported and unsupported shapes
# ---------------------------------------------------------------------------


def test_pnpm_yaml_ignores_unrelated_top_level_keys(tmp_path: Path) -> None:
    _write(
        tmp_path / "pnpm-workspace.yaml",
        "onlyBuiltDependencies:\n  - esbuild\npackages:\n  - 'packages/*'\n"
        "catalog:\n  react: ^19.0.0\n",
    )
    _jest_package(tmp_path, "packages/alpha")

    result = jsd.discover(tmp_path)

    assert [project.path for project in result] == ["packages/alpha"]


def test_pnpm_yaml_tolerates_comments_and_blank_lines(tmp_path: Path) -> None:
    _write(
        tmp_path / "pnpm-workspace.yaml",
        "# our workspaces\npackages:\n\n  - 'packages/*'  # the libs\n",
    )
    _jest_package(tmp_path, "packages/alpha")

    result = jsd.discover(tmp_path)

    assert [project.path for project in result] == ["packages/alpha"]


def test_pnpm_yaml_accepts_a_zero_indented_block_sequence(tmp_path: Path) -> None:
    # YAML allows a block sequence at the same indentation as its mapping key.
    _write(
        tmp_path / "pnpm-workspace.yaml",
        "packages:\n- 'packages/*'\n- 'apps/*'\n",
    )
    _jest_package(tmp_path, "packages/alpha")
    _jest_package(tmp_path, "apps/web")

    result = jsd.discover(tmp_path)

    assert [project.path for project in result] == ["apps/web", "packages/alpha"]


def test_a_zero_indented_sequence_still_terminates_at_the_next_key(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "pnpm-workspace.yaml",
        "packages:\n- 'packages/*'\ncatalog:\n  react: ^19.0.0\n",
    )
    _jest_package(tmp_path, "packages/alpha")

    result = jsd.discover(tmp_path)

    assert [project.path for project in result] == ["packages/alpha"]


def test_a_quoted_packages_key_is_recognized(tmp_path: Path) -> None:
    # Reading it as an absent key would silently yield zero patterns.
    _write(tmp_path / "pnpm-workspace.yaml", "\"packages\":\n  - 'packages/*'\n")
    _jest_package(tmp_path, "packages/alpha")

    result = jsd.discover(tmp_path)

    assert [project.path for project in result] == ["packages/alpha"]


def test_a_duplicate_packages_key_is_a_discovery_error(tmp_path: Path) -> None:
    # A tolerant YAML loader is last-wins, so silently taking the first block
    # would resolve patterns pnpm itself would not use.
    _write(
        tmp_path / "pnpm-workspace.yaml",
        "packages:\n  - 'packages/*'\npackages:\n  - 'apps/*'\n",
    )

    with pytest.raises(cc.DiscoveryError, match="appears 2 times"):
        jsd.discover(tmp_path)


def test_a_bom_prefixed_manifest_is_not_reported_as_malformed(tmp_path: Path) -> None:
    # npm strips the BOM; calling such a file "malformed" would mislead.
    _root_manifest(tmp_path, ["packages/*"])
    (tmp_path / "packages" / "alpha").mkdir(parents=True)
    (tmp_path / "packages" / "alpha" / "package.json").write_text(
        json.dumps({"name": "a", "scripts": {"test": "jest"}, "devDependencies": {"jest": "^29"}}),
        encoding="utf-8-sig",
    )

    result = jsd.discover(tmp_path)

    assert _classification_of(result, "packages/alpha") is _TEST


def test_an_undecodable_manifest_is_a_discovery_error_naming_it(tmp_path: Path) -> None:
    # UnicodeDecodeError is a ValueError, not an OSError.
    _root_manifest(tmp_path, ["packages/*"])
    (tmp_path / "packages" / "alpha").mkdir(parents=True)
    (tmp_path / "packages" / "alpha" / "package.json").write_bytes(
        b"\xff\xfe{\x00\"\x00n\x00\"\x00:\x001\x00}\x00"
    )

    with pytest.raises(cc.DiscoveryError) as excinfo:
        jsd.discover(tmp_path)

    assert "packages/alpha" in str(excinfo.value)
    assert "undecodable" in str(excinfo.value)


def test_a_real_test_script_wrapped_around_echo_is_not_a_placeholder(
    tmp_path: Path,
) -> None:
    # An unanchored placeholder regex would drop this genuine test package.
    _root_manifest(tmp_path, ["packages/*"])
    _package(
        tmp_path,
        "packages/alpha",
        scripts={"test": "echo linting && jest --coverage || exit 1"},
        dev_dependencies={"jest": "^29.0.0"},
    )

    result = jsd.discover(tmp_path)

    assert _classification_of(result, "packages/alpha") is _TEST


def test_the_cli_never_emits_a_traceback_for_an_unexpected_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _boom(*_args: object, **_kwargs: object):
        raise RuntimeError("something nobody anticipated")

    monkeypatch.setattr(jsd, "discover", _boom)

    exit_code = jsd.main([str(tmp_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err.startswith("error: unexpected failure:")
    assert "Traceback" not in captured.err


def test_pnpm_yaml_with_no_packages_key_contributes_no_patterns(
    tmp_path: Path,
) -> None:
    # Still a workspace signal (so not NOT_APPLICABLE) — just no declared globs.
    _write(tmp_path / "pnpm-workspace.yaml", "onlyBuiltDependencies:\n  - esbuild\n")

    result = jsd.discover(tmp_path)

    assert result is not cc.DISCOVERY_NOT_APPLICABLE
    assert list(result) == []


@pytest.mark.parametrize(
    "yaml_text",
    [
        # Flow-style array — syntactically valid YAML, not supported here.
        "packages: ['packages/*', 'apps/*']\n",
        "packages: []\n",
        # A nested mapping rather than a sequence of scalars.
        "packages:\n  first: 'packages/*'\n",
        # A block scalar.
        "packages: |\n  packages/*\n",
        # An anchor/alias.
        "base: &b\n  - 'packages/*'\npackages: *b\n",
        # A sequence of mappings.
        "packages:\n  - path: 'packages/*'\n",
    ],
)
def test_an_unsupported_pnpm_yaml_shape_is_a_discovery_error(
    tmp_path: Path, yaml_text: str
) -> None:
    _write(tmp_path / "pnpm-workspace.yaml", yaml_text)

    with pytest.raises(cc.DiscoveryError) as excinfo:
        jsd.discover(tmp_path)

    message = str(excinfo.value)
    # Explicitly not a silent fallthrough and not NOT_APPLICABLE.
    assert "pnpm-workspace" in message
    assert "block-style" in message


def test_the_unsupported_pnpm_shape_error_is_not_the_not_applicable_sentinel(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "pnpm-workspace.yaml", "packages: ['packages/*']\n")
    _jest_package(tmp_path, "packages/alpha")

    with pytest.raises(cc.DiscoveryError):
        jsd.discover(tmp_path)


# ---------------------------------------------------------------------------
# Malformed-manifest error paths
# ---------------------------------------------------------------------------


def test_malformed_lerna_json_is_a_discovery_error(tmp_path: Path) -> None:
    _write(tmp_path / "lerna.json", "{ not json")

    with pytest.raises(cc.DiscoveryError) as excinfo:
        jsd.discover(tmp_path)

    assert "lerna.json" in str(excinfo.value)


def test_malformed_root_package_json_is_a_discovery_error(tmp_path: Path) -> None:
    _write(tmp_path / "package.json", "{ not json")
    _write(tmp_path / "lerna.json", json.dumps({"packages": ["packages/*"]}))

    with pytest.raises(cc.DiscoveryError, match="package.json"):
        jsd.discover(tmp_path)


def test_malformed_workspace_package_json_is_a_discovery_error_naming_it(
    tmp_path: Path,
) -> None:
    _root_manifest(tmp_path, ["packages/*"])
    _write(tmp_path / "packages" / "broken" / "package.json", "{ not json")

    with pytest.raises(cc.DiscoveryError) as excinfo:
        jsd.discover(tmp_path)

    assert "packages/broken" in str(excinfo.value)


@pytest.mark.parametrize(
    "workspaces", ['"packages/*"', "42", '{"packages": "not-a-list"}', "[1, 2]"]
)
def test_a_wrong_typed_workspaces_field_is_a_discovery_error(
    tmp_path: Path, workspaces: str
) -> None:
    _write(
        tmp_path / "package.json",
        '{"name": "monorepo", "workspaces": ' + workspaces + "}",
    )

    with pytest.raises(cc.DiscoveryError, match="workspaces"):
        jsd.discover(tmp_path)


def test_a_wrong_typed_lerna_packages_field_is_a_discovery_error(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "lerna.json", json.dumps({"packages": "modules/*"}))

    with pytest.raises(cc.DiscoveryError, match="lerna.json"):
        jsd.discover(tmp_path)


def test_a_lerna_json_with_no_packages_key_contributes_no_patterns(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "lerna.json", json.dumps({"version": "independent"}))

    result = jsd.discover(tmp_path)

    assert result is not cc.DISCOVERY_NOT_APPLICABLE
    assert list(result) == []


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_emits_json_classifications(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _root_manifest(tmp_path, ["packages/*"])
    _jest_package(tmp_path, "packages/alpha")
    _package(tmp_path, "packages/beta", scripts={"build": "tsc"})

    exit_code = jsd.main([str(tmp_path)])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {
        "applicable": True,
        "projects": [
            {"path": "packages/alpha", "classification": "test"},
            {"path": "packages/beta", "classification": "not_test"},
        ],
    }


def test_cli_reports_not_applicable_without_failing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = jsd.main([str(tmp_path)])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {"applicable": False, "projects": []}


def test_cli_reports_a_discovery_error_without_a_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path / "lerna.json", "{ not json")

    exit_code = jsd.main([str(tmp_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err.startswith("error: ")
    assert "Traceback" not in captured.err
