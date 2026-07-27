"""Tests for plugins/dev-team/scripts/detect_bdd_convention.py (issue #537).

Slice 1 of plans/plan-gherkin-feature-persistence.md: deterministic detection
of a target project's BDD convention. Precedence is existing .feature files >
BDD dependency in a manifest > none, always preferring a false negative (no
signal, which prompts the operator) over a false positive (writing derived
.feature files into the wrong directory).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Ensure the script's dir is on the path so we can import it as a module.
_SCRIPT_DIR = Path(__file__).resolve().parents[2] / "plugins" / "dev-team" / "scripts"
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import detect_bdd_convention  # type: ignore[import-not-found]

from _repo_root import REPO_ROOT as _REPO_ROOT

_BDD_FRAMEWORKS_DOC = (
    _REPO_ROOT
    / "plugins"
    / "dev-team"
    / "knowledge"
    / "test-stack-profiles"
    / "bdd-frameworks.md"
)

_CUCUMBER_JS_PACKAGE_JSON = (
    '{"devDependencies": {"@cucumber/cucumber": "^11.0.0"}}\n'
)
_REQNROLL_CSPROJ = (
    "<Project>\n"
    "  <ItemGroup>\n"
    '    <PackageReference Include="Reqnroll.xUnit" Version="2.0.0" />\n'
    "  </ItemGroup>\n"
    "</Project>\n"
)
_CUCUMBER_JVM_POM = (
    "<project>\n"
    "  <dependencies>\n"
    "    <dependency>\n"
    "      <groupId>io.cucumber</groupId>\n"
    "      <artifactId>cucumber-java</artifactId>\n"
    "    </dependency>\n"
    "  </dependencies>\n"
    "</project>\n"
)
_CUCUMBER_JVM_GRADLE = (
    "dependencies {\n"
    "  testImplementation 'io.cucumber:cucumber-java:7.18.1'\n"
    "}\n"
)
_GODOG_GO_MOD = (
    "module example.com/svc\n\ngo 1.22\n\nrequire github.com/cucumber/godog v0.14.0\n"
)


def _touch(root: Path, relpath: str, content: str = "") -> Path:
    """Create (and return) a fixture file at root/relpath, making parents."""
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def _no_signal() -> dict:
    return {"signal": "none", "framework": None, "dir": None}


# ---------------------------------------------------------------------------
# Feature-file scan — signal "feature-files"
# ---------------------------------------------------------------------------


class TestFeatureFileScan:
    def test_single_root_of_feature_files_is_detected_without_a_manifest(
        self, tmp_path: Path
    ) -> None:
        _touch(tmp_path, "specs/features/login.feature", "Feature: login\n")
        _touch(tmp_path, "specs/features/logout.feature", "Feature: logout\n")

        assert detect_bdd_convention.detect(tmp_path) == {
            "signal": "feature-files",
            "framework": None,
            "dir": "specs/features",
        }

    def test_nested_feature_files_report_their_common_directory(
        self, tmp_path: Path
    ) -> None:
        _touch(tmp_path, "specs/features/auth/login.feature", "Feature: login\n")
        _touch(tmp_path, "specs/features/billing/invoice.feature", "Feature: invoice\n")

        result = detect_bdd_convention.detect(tmp_path)
        assert result["signal"] == "feature-files"
        assert result["dir"] == "specs/features"

    @pytest.mark.parametrize(
        "vendored_root",
        [
            "node_modules/some-dep",
            "vendor/some-dep",
            "dist",
            "build",
            ".git/info",
        ],
    )
    def test_feature_files_only_under_vendored_trees_yield_none(
        self, tmp_path: Path, vendored_root: str
    ) -> None:
        _touch(tmp_path, vendored_root + "/features/x.feature", "Feature: x\n")

        assert detect_bdd_convention.detect(tmp_path) == _no_signal()

    def test_feature_files_only_inside_a_virtualenv_yield_none(
        self, tmp_path: Path
    ) -> None:
        _touch(tmp_path, ".venv/pyvenv.cfg", "home = /usr/bin\n")
        _touch(
            tmp_path,
            ".venv/lib/site-packages/some-dep/features/x.feature",
            "Feature: x\n",
        )

        assert detect_bdd_convention.detect(tmp_path) == _no_signal()

    def test_vendored_feature_files_do_not_count_as_a_second_root(
        self, tmp_path: Path
    ) -> None:
        _touch(tmp_path, "specs/features/login.feature", "Feature: login\n")
        _touch(tmp_path, "node_modules/some-dep/features/x.feature", "Feature: x\n")

        result = detect_bdd_convention.detect(tmp_path)
        assert result["signal"] == "feature-files"
        assert result["dir"] == "specs/features"

    def test_feature_files_under_multiple_unrelated_roots_yield_none(
        self, tmp_path: Path
    ) -> None:
        _touch(tmp_path, "svc-a/features/a.feature", "Feature: a\n")
        _touch(tmp_path, "svc-b/specs/b.feature", "Feature: b\n")

        assert detect_bdd_convention.detect(tmp_path) == _no_signal()

    def test_feature_files_at_the_project_root_are_too_ambiguous_to_claim(
        self, tmp_path: Path
    ) -> None:
        """A root-level .feature file would make the repo root the destination
        — conservative rule: no signal, prompt instead."""
        _touch(tmp_path, "orphan.feature", "Feature: orphan\n")

        assert detect_bdd_convention.detect(tmp_path) == _no_signal()

    def test_project_with_no_bdd_markers_yields_none_and_null_dir(
        self, tmp_path: Path
    ) -> None:
        _touch(tmp_path, "src/app.py", "print('hello')\n")

        assert detect_bdd_convention.detect(tmp_path) == _no_signal()

    def test_feature_files_under_an_unconventional_dir_name_yield_none(
        self, tmp_path: Path
    ) -> None:
        """Regression for issue #1462: a repo whose only `.feature` root is a
        narrowly-scoped directory (e.g. this repo's own evals/skills/, which
        has a documented, non-Gherkin-convention purpose) must not be
        misreported as "the" BDD convention just because it's the only
        `.feature` root that exists."""
        _touch(
            tmp_path,
            "evals/skills/some-workflow/thing.feature",
            "Feature: thing\n",
        )

        assert detect_bdd_convention.detect(tmp_path) == _no_signal()

    @pytest.mark.parametrize(
        "dir_name",
        sorted(detect_bdd_convention._CONVENTIONAL_FEATURE_DIR_NAMES)
        + ["Features", "SPECS"],
    )
    def test_every_conventional_dir_name_signals_case_insensitively(
        self, tmp_path: Path, dir_name: str
    ) -> None:
        """Regression for issue #1462: all six allowlisted names — not just
        "features" — must signal, and matching must be case-insensitive
        (detect_bdd_convention.py:88's `.lower()`), covering a gap the
        original single "specs/features" example left untested."""
        _touch(tmp_path, f"specs/{dir_name}/login.feature", "Feature: login\n")

        result = detect_bdd_convention.detect(tmp_path)
        assert result["signal"] == "feature-files"
        assert result["dir"] == f"specs/{dir_name}"

    def test_single_nested_leaf_under_a_conventional_root_still_signals(
        self, tmp_path: Path
    ) -> None:
        """Regression for issue #1462 (correctness-review finding): when
        every `.feature` file sits under one nested leaf of an otherwise-
        conventional root (no sibling directly under `features/` itself),
        the common ancestor's *final* component ("checkout") is not
        conventional, but "features" — a real ancestor two levels up — is.
        The allowlist check must walk every path component, not just the
        last one, and return the ancestor path up to the first match."""
        _touch(tmp_path, "features/checkout/pay.feature", "Feature: pay\n")

        assert detect_bdd_convention.detect(tmp_path) == {
            "signal": "feature-files",
            "framework": None,
            "dir": "features",
        }

    def test_conventional_and_unconventional_roots_together_are_still_ambiguous(
        self, tmp_path: Path
    ) -> None:
        """A conventional dir and an unconventional dir with no common
        ancestor other than root fall back to the existing "common == '.'"
        None case, independent of the new allowlist check."""
        _touch(tmp_path, "specs/features/login.feature", "Feature: login\n")
        _touch(
            tmp_path,
            "evals/skills/some-workflow/thing.feature",
            "Feature: thing\n",
        )

        assert detect_bdd_convention.detect(tmp_path) == _no_signal()


# ---------------------------------------------------------------------------
# Manifest signals — signal "manifest", canonical destination per stack
# ---------------------------------------------------------------------------


class TestManifestMapping:
    @pytest.mark.parametrize(
        "manifest_relpath, manifest_content, framework, destination",
        [
            (
                "package.json",
                _CUCUMBER_JS_PACKAGE_JSON,
                "cucumber-js",
                "features",
            ),
            (
                "pyproject.toml",
                '[project]\ndependencies = ["pytest-bdd>=7"]\n',
                "pytest-bdd",
                "features",
            ),
            (
                "requirements.txt",
                "behave==1.2.6\n",
                "behave",
                "features",
            ),
            (
                "requirements-dev.txt",
                "pytest-bdd>=7\n",
                "pytest-bdd",
                "features",
            ),
            (
                "tests/Acceptance/Acceptance.csproj",
                _REQNROLL_CSPROJ,
                "reqnroll",
                "tests/Acceptance/Features",
            ),
            (
                "pom.xml",
                _CUCUMBER_JVM_POM,
                "cucumber-jvm",
                "src/test/resources/features",
            ),
            (
                "build.gradle",
                _CUCUMBER_JVM_GRADLE,
                "cucumber-jvm",
                "src/test/resources/features",
            ),
            (
                "build.gradle.kts",
                'dependencies { testImplementation("io.cucumber:cucumber-java:7.18.1") }\n',
                "cucumber-jvm",
                "src/test/resources/features",
            ),
            (
                "go.mod",
                _GODOG_GO_MOD,
                "godog",
                "features",
            ),
        ],
    )
    def test_bdd_runner_dependency_maps_to_its_canonical_directory(
        self,
        tmp_path: Path,
        manifest_relpath: str,
        manifest_content: str,
        framework: str,
        destination: str,
    ) -> None:
        _touch(tmp_path, manifest_relpath, manifest_content)

        assert detect_bdd_convention.detect(tmp_path) == {
            "signal": "manifest",
            "framework": framework,
            "dir": destination,
        }

    def test_dependencies_key_counts_like_dev_dependencies(
        self, tmp_path: Path
    ) -> None:
        _touch(
            tmp_path,
            "package.json",
            '{"dependencies": {"@cucumber/cucumber": "^11.0.0"}}\n',
        )

        result = detect_bdd_convention.detect(tmp_path)
        assert result["signal"] == "manifest"
        assert result["framework"] == "cucumber-js"

    def test_reqnroll_csproj_at_the_repo_root_targets_root_features(
        self, tmp_path: Path
    ) -> None:
        _touch(tmp_path, "Acceptance.csproj", _REQNROLL_CSPROJ)

        result = detect_bdd_convention.detect(tmp_path)
        assert result["signal"] == "manifest"
        assert result["dir"] == "Features"

    def test_specflow_counts_as_a_bdd_signal_like_reqnroll(
        self, tmp_path: Path
    ) -> None:
        _touch(
            tmp_path,
            "tests/Acceptance/Acceptance.csproj",
            '<Project><ItemGroup><PackageReference Include="SpecFlow.xUnit" /></ItemGroup></Project>\n',
        )

        result = detect_bdd_convention.detect(tmp_path)
        assert result["signal"] == "manifest"
        assert result["dir"] == "tests/Acceptance/Features"

    def test_package_json_without_a_cucumber_dependency_is_no_signal(
        self, tmp_path: Path
    ) -> None:
        _touch(tmp_path, "package.json", '{"devDependencies": {"vitest": "^2.0.0"}}\n')

        assert detect_bdd_convention.detect(tmp_path) == _no_signal()

    def test_a_vendored_manifest_is_not_a_signal(self, tmp_path: Path) -> None:
        _touch(
            tmp_path,
            "node_modules/some-dep/package.json",
            _CUCUMBER_JS_PACKAGE_JSON,
        )

        assert detect_bdd_convention.detect(tmp_path) == _no_signal()

    def test_unparseable_package_json_is_no_signal_not_a_crash(
        self, tmp_path: Path
    ) -> None:
        _touch(tmp_path, "package.json", "not json {\n")

        assert detect_bdd_convention.detect(tmp_path) == _no_signal()


# ---------------------------------------------------------------------------
# Precedence and conflict rules
# ---------------------------------------------------------------------------


class TestPrecedenceAndConflicts:
    def test_existing_feature_files_beat_a_manifest_dependency(
        self, tmp_path: Path
    ) -> None:
        _touch(tmp_path, "e2e/features/login.feature", "Feature: login\n")
        _touch(tmp_path, "package.json", _CUCUMBER_JS_PACKAGE_JSON)

        assert detect_bdd_convention.detect(tmp_path) == {
            "signal": "feature-files",
            "framework": None,
            "dir": "e2e/features",
        }

    def test_manifests_with_conflicting_destinations_yield_none(
        self, tmp_path: Path
    ) -> None:
        _touch(tmp_path, "pom.xml", _CUCUMBER_JVM_POM)
        _touch(tmp_path, "package.json", _CUCUMBER_JS_PACKAGE_JSON)

        assert detect_bdd_convention.detect(tmp_path) == _no_signal()

    def test_manifests_sharing_one_destination_are_not_a_conflict(
        self, tmp_path: Path
    ) -> None:
        _touch(
            tmp_path,
            "pyproject.toml",
            '[project]\ndependencies = ["pytest-bdd>=7"]\n',
        )
        _touch(tmp_path, "requirements.txt", "behave==1.2.6\n")

        result = detect_bdd_convention.detect(tmp_path)
        assert result["signal"] == "manifest"
        assert result["dir"] == "features"
        # Tie-break is deterministic: alphabetically first framework wins.
        assert result["framework"] == "behave"

    def test_unrelated_dependencies_are_not_a_signal(self, tmp_path: Path) -> None:
        _touch(tmp_path, "requirements.txt", "requests==2.32.0\nflask>=3\n")
        _touch(
            tmp_path,
            "pyproject.toml",
            '[project]\ndependencies = ["rich>=13"]\n',
        )

        assert detect_bdd_convention.detect(tmp_path) == _no_signal()

    def test_hyphenated_superstring_tokens_are_not_a_signal(
        self, tmp_path: Path
    ) -> None:
        """`behave-django` / `pytest-bdd-ng` must not read as behave/pytest-bdd."""
        _touch(tmp_path, "requirements.txt", "behave-django==1.5\npytest-bdd-ng\n")

        assert detect_bdd_convention.detect(tmp_path) == _no_signal()

    def test_symlinked_feature_dirs_are_ignored(self, tmp_path: Path) -> None:
        """Symlinks are skipped wholesale — conservative: no signal."""
        real = tmp_path / ".git" / "real-features"  # only reachable via symlink
        real.mkdir(parents=True)
        (real / "login.feature").write_text("Feature: x\n", encoding="utf-8")
        (tmp_path / "features").symlink_to(real, target_is_directory=True)

        assert detect_bdd_convention.detect(tmp_path) == _no_signal()

    def test_feature_files_beat_even_conflicting_manifests(
        self, tmp_path: Path
    ) -> None:
        """Precedence pins the evaluation order: an unambiguous .feature root
        wins before the manifest conflict rule is ever consulted."""
        _touch(tmp_path, "e2e/features/login.feature", "Feature: login\n")
        _touch(tmp_path, "pom.xml", _CUCUMBER_JVM_POM)
        _touch(tmp_path, "package.json", _CUCUMBER_JS_PACKAGE_JSON)

        result = detect_bdd_convention.detect(tmp_path)
        assert result["signal"] == "feature-files"
        assert result["dir"] == "e2e/features"

    def test_two_reqnroll_csprojs_in_different_directories_yield_none(
        self, tmp_path: Path
    ) -> None:
        """Same framework, multiple candidate destinations — the conflict rule
        applies."""
        _touch(tmp_path, "svc-a/Acceptance.csproj", _REQNROLL_CSPROJ)
        _touch(tmp_path, "svc-b/Acceptance.csproj", _REQNROLL_CSPROJ)

        assert detect_bdd_convention.detect(tmp_path) == _no_signal()


# ---------------------------------------------------------------------------
# Sync-guard — the script's mapping must stay aligned with the knowledge doc
# ---------------------------------------------------------------------------


class TestMappingDocSync:
    def test_every_mapping_destination_is_documented(self) -> None:
        doc = _BDD_FRAMEWORKS_DOC.read_text()
        for rule in detect_bdd_convention.MANIFEST_RULES:
            destination = (
                rule.destination or detect_bdd_convention.CSPROJ_FEATURES_SUBDIR
            )
            assert f"`{destination}/`" in doc, (
                f"{rule.framework}: canonical destination `{destination}/` is not documented in {_BDD_FRAMEWORKS_DOC.name} — "
                "update the doc or the mapping"
            )

    def test_every_documented_framework_token_appears_in_the_doc(self) -> None:
        doc = _BDD_FRAMEWORKS_DOC.read_text()
        for rule in detect_bdd_convention.MANIFEST_RULES:
            assert any(token in doc for token in rule.tokens), (
                f"{rule.framework}: none of its dependency tokens {rule.tokens} appear in {_BDD_FRAMEWORKS_DOC.name} — "
                "update the doc or the mapping"
            )


class TestConventionalNameAllowlistSync:
    """Issue #1462/#1467-adjacent (arch-review finding): `MANIFEST_RULES`
    destinations and `_CONVENTIONAL_FEATURE_DIR_NAMES` are two independent
    tables that decide overlapping things — a manifest-driven canonical
    destination, and a feature-file-scan signal — and nothing previously
    caught them drifting apart. If a future manifest destination's final
    path component isn't in the allowlist, `scan_feature_dir` would silently
    fail to recognize that destination as a signal on a re-scan."""

    def test_every_manifest_destination_final_component_is_conventional(self) -> None:
        for rule in detect_bdd_convention.MANIFEST_RULES:
            destination = (
                rule.destination or detect_bdd_convention.CSPROJ_FEATURES_SUBDIR
            )
            final_component = destination.rstrip("/").rsplit("/", 1)[-1].lower()
            assert (
                final_component in detect_bdd_convention._CONVENTIONAL_FEATURE_DIR_NAMES
            ), (
                f"{rule.framework}: destination `{destination}` ends in "
                f"`{final_component}`, which is not in "
                "_CONVENTIONAL_FEATURE_DIR_NAMES — scan_feature_dir would not "
                "recognize this destination as a signal; update the allowlist "
                "or the mapping"
            )


# ---------------------------------------------------------------------------
# CLI contract — JSON on stdout, exit codes, bad-path handling
# ---------------------------------------------------------------------------

_SCRIPT_PY = _SCRIPT_DIR / "detect_bdd_convention.py"


def _run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_SCRIPT_PY), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd is not None else None,
        check=False,
    )


class TestCliContract:
    def test_detection_emits_json_with_exactly_the_contract_keys(
        self, tmp_path: Path
    ) -> None:
        _touch(tmp_path, "features/login.feature", "Feature: login\n")

        completed = _run_cli(str(tmp_path))

        assert completed.returncode == 0
        payload = json.loads(completed.stdout)
        assert set(payload) == {"signal", "framework", "dir"}
        assert payload == {
            "signal": "feature-files",
            "framework": None,
            "dir": "features",
        }

    def test_a_manifest_signal_round_trips_through_the_cli(
        self, tmp_path: Path
    ) -> None:
        _touch(tmp_path, "go.mod", _GODOG_GO_MOD)

        completed = _run_cli(str(tmp_path))

        assert completed.returncode == 0
        assert json.loads(completed.stdout) == {
            "signal": "manifest",
            "framework": "godog",
            "dir": "features",
        }

    def test_no_signal_is_a_successful_result_not_an_error(
        self, tmp_path: Path
    ) -> None:
        completed = _run_cli(str(tmp_path))

        assert completed.returncode == 0
        assert json.loads(completed.stdout) == {
            "signal": "none",
            "framework": None,
            "dir": None,
        }

    def test_target_defaults_to_the_working_directory(self, tmp_path: Path) -> None:
        _touch(tmp_path, "specs/features/login.feature", "Feature: login\n")

        completed = _run_cli(cwd=tmp_path)

        assert completed.returncode == 0
        assert json.loads(completed.stdout)["dir"] == "specs/features"

    def test_nonexistent_target_exits_nonzero_naming_the_path(
        self, tmp_path: Path
    ) -> None:
        missing = tmp_path / "no-such-project"

        completed = _run_cli(str(missing))

        assert completed.returncode != 0
        assert str(missing) in completed.stderr

    def test_a_file_target_is_rejected_like_a_missing_one(
        self, tmp_path: Path
    ) -> None:
        not_a_dir = _touch(tmp_path, "a-file.txt", "hello\n")

        completed = _run_cli(str(not_a_dir))

        assert completed.returncode != 0
        assert str(not_a_dir) in completed.stderr
