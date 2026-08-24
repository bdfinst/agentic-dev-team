"""Unit tests for skills/code-review/scripts/change_shape.py (#1254).

Covers the deterministic change-shape gate: when a changeset has no runtime
surface (docs/config only), the low-yield lenses (performance, correctness) are
skipped; any runtime surface (source, unknown extension, functional Claude
config) keeps them. Fail-safe: unknown = runtime surface.
"""

from __future__ import annotations

import json
import sys
from typing import ClassVar

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_PLUGIN_ROOT = _REPO_ROOT / "plugins" / "dev-team"

sys.path.insert(
    0,
    str(_REPO_ROOT / "plugins" / "dev-team" / "skills" / "code-review" / "scripts"),
)

import change_shape


class TestHasRuntimeSurface:
    def test_source_file_has_runtime_surface(self):
        assert change_shape.has_runtime_surface(["src/app.py"]) is True
        assert change_shape.has_runtime_surface(["src/app.ts", "README.md"]) is True

    def test_docs_only_has_no_runtime_surface(self):
        assert change_shape.has_runtime_surface(["README.md", "docs/guide.rst"]) is False

    def test_config_only_has_no_runtime_surface(self):
        assert change_shape.has_runtime_surface(
            ["config.json", "app.yaml", ".gitignore", "settings.toml"]
        ) is False

    def test_docs_and_config_mixed_has_no_runtime_surface(self):
        assert change_shape.has_runtime_surface(["CHANGELOG.md", "ci.yml"]) is False

    def test_unknown_extension_is_runtime_surface_failsafe(self):
        # A file we cannot prove is doc/config must count as runtime surface,
        # so the code lenses still run (fail-safe).
        assert change_shape.has_runtime_surface(["Makefile"]) is True
        assert change_shape.has_runtime_surface(["thing.rb"]) is True

    def test_functional_claude_config_is_runtime_surface(self):
        # Markdown under agents/skills/etc. drives behavior — never "just docs".
        for f in [
            "agents/security-review.md",
            "skills/plan/SKILL.md",
            "knowledge/agent-registry.md",
            ".claude/settings.json",
            "CLAUDE.md",
            "AGENTS.md",
            "templates/agents/python.md",
        ]:
            assert change_shape.has_runtime_surface([f]) is True, f

    def test_empty_changeset_has_no_runtime_surface(self):
        assert change_shape.has_runtime_surface([]) is False
        assert change_shape.has_runtime_surface(["", "  "]) is False


class TestLensesToSkip:
    def test_docs_only_skips_low_yield_lenses(self):
        skip = change_shape.lenses_to_skip(["README.md", "config.json"])
        assert skip == ["performance-review", "correctness-review"]

    def test_runtime_surface_skips_nothing(self):
        assert change_shape.lenses_to_skip(["src/app.py", "README.md"]) == []

    def test_empty_changeset_skips_nothing(self):
        assert change_shape.lenses_to_skip([]) == []


class TestCli:
    def test_cli_docs_only_reports_skip(self, capsys):
        rc = change_shape.main(["--files", "README.md", "config.yaml"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["hasRuntimeSurface"] is False
        assert out["skipLenses"] == ["performance-review", "correctness-review"]

    def test_cli_runtime_surface_reports_no_skip(self, capsys):
        rc = change_shape.main(["--files", "src/main.go"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["hasRuntimeSurface"] is True
        assert out["skipLenses"] == []

    def test_cli_files_from_stdin(self, capsys, monkeypatch):
        import io

        monkeypatch.setattr(sys, "stdin", io.StringIO("docs/a.md\nb.json\n"))
        rc = change_shape.main(["--files-from", "-"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["skipLenses"] == ["performance-review", "correctness-review"]


class TestTestOnlyClassification:
    """#1964: a second, independent question — is EVERY changed file provably
    a test file? Include-biased in the same direction as the runtime-surface
    check: anything unproven answers False, so the full panel runs."""

    @pytest.mark.parametrize(
        "files",
        [
            pytest.param(["tests/a.test.js", "src/b.spec.ts"], id="js-test-and-spec"),
            pytest.param(["tests/test_a.py", "tests/b_test.py"], id="python-both-conventions"),
            pytest.param(["features/login.feature"], id="gherkin-feature"),
            pytest.param(["steps/login.steps.js"], id="step-definitions"),
            pytest.param(["pkg/__tests__/a.js"], id="tests-directory"),
            pytest.param(["src/FooTest.java"], id="java-class-name-convention"),
            pytest.param(
                ["features/x.feature", "tests/test_a.py", "pkg/__tests__/b.js"],
                id="mixed-languages-all-tests",
            ),
        ],
    )
    def test_provably_test_only_changesets(self, files):
        assert change_shape.is_test_only(files) is True

    @pytest.mark.parametrize(
        "files,why",
        [
            pytest.param(["tests/a.test.js", "src/prod.js"], "production file present", id="mixed"),
            pytest.param(["tests/conftest.py"], "fixture module, not a test by name", id="conftest"),
            pytest.param(["tests/helpers.py"], "test helper, not a test by name", id="helper"),
            pytest.param(["tests/FooTests.cs"], "C# test-ness needs file contents", id="csharp"),
            pytest.param(["src/Foo.java"], "no test class-name suffix", id="plain-java"),
            pytest.param(["tests/fixtures/data.json"], "fixture data", id="fixture-data"),
            pytest.param(["weird.xyz"], "unknown extension", id="unknown-ext"),
            pytest.param(["README.md"], "documentation", id="docs"),
            pytest.param([], "nothing to prove", id="empty"),
        ],
    )
    def test_not_test_only_is_the_fail_safe_answer(self, files, why):
        assert change_shape.is_test_only(files) is False, why

    def test_csharp_classification_does_not_touch_the_filesystem(self, tmp_path, monkeypatch):
        """The module's no-I/O contract: a real C# test file on disk still
        classifies as unproven, because the content probe is starved rather
        than allowed to read it."""
        cs = tmp_path / "RealTests.cs"
        cs.write_text("public class RealTests { [Fact] public void T() {} }")
        monkeypatch.chdir(tmp_path)
        assert change_shape.is_test_only(["RealTests.cs"]) is False

    def test_whitespace_entries_are_ignored_not_counted_as_unproven(self):
        assert change_shape.is_test_only(["tests/test_a.py", "   ", ""]) is True


class TestTestOnlySkipsNothingYet:
    """The measure-then-flip contract. `TEST_ONLY_SKIP_LENSES` ships empty:
    which lens is safe to drop on a test-only diff is an empirical question,
    and the `diff_shape` outcome data is still being collected. A PR that
    populates it must cite that measurement — and update these tests."""

    def test_skip_list_is_empty_pending_measurement(self):
        assert change_shape.TEST_ONLY_SKIP_LENSES == []

    def test_test_only_changeset_currently_skips_no_lens(self):
        assert change_shape.lenses_to_skip(["tests/a.test.js"]) == []

    @pytest.mark.parametrize("lens", ["security-review", "correctness-review"])
    def test_the_two_never_on_intuition_lenses_are_absent(self, lens):
        """Tests embed credentials and injection payloads (`security-review`),
        and an inverted assertion is exactly `correctness-review`'s subject."""
        assert lens not in change_shape.TEST_ONLY_SKIP_LENSES

    def test_doc_only_precedence_is_unchanged_by_the_new_branch(self):
        """A doc/config-only changeset still yields the low-yield pair — the
        test-only branch is reached only when runtime surface is present."""
        assert change_shape.lenses_to_skip(["README.md"]) == [
            "performance-review",
            "correctness-review",
        ]


class TestTestOnlyCli:
    def test_cli_reports_is_test_only(self, capsys):
        rc = change_shape.main(["--files", "tests/a.test.js"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["isTestOnly"] is True
        assert out["hasRuntimeSurface"] is True
        assert out["skipLenses"] == []

    def test_cli_reports_not_test_only_for_mixed(self, capsys):
        rc = change_shape.main(["--files", "tests/a.test.js", "src/prod.js"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["isTestOnly"] is False

    def test_cli_always_emits_the_key(self, capsys):
        """Consumers read it unconditionally; it must never be absent."""
        rc = change_shape.main(["--files", "README.md"])
        assert rc == 0
        assert "isTestOnly" in json.loads(capsys.readouterr().out)


class TestDegradedFallbackParity:
    """The `hooks/lib`-unreachable fallback must agree with the shared
    classifier it stands in for (#1964).

    This is not theoretical tidiness. The fallback originally folded all four
    indicator families into one `re.IGNORECASE` pattern, but
    `test_file_classify` compiles its step-definition regex case-SENSITIVELY —
    so `backsteps.py` and `mysteps.js` classified as step definitions. That is
    an ordinary source file passing as a test, which over-claims `test-only`:
    the one direction this module's include-bias must never fail in. Every
    other test in this file exercises the primary path and passed throughout,
    so only a differential test catches it.
    """

    @staticmethod
    def _fallback_module():
        """Load change_shape with `hooks/lib` unimportable, forcing the
        `except ImportError` branch."""
        import importlib.util

        hooks_lib = str((_PLUGIN_ROOT / "hooks" / "lib").resolve())
        saved_path, saved_mods = list(sys.path), {}
        sys.path = [p for p in sys.path if p != hooks_lib]
        for name in ("test_file_classify", "doc_classification"):
            saved_mods[name] = sys.modules.get(name, "__absent__")
            sys.modules[name] = None  # force ImportError on import
        try:
            spec = importlib.util.spec_from_file_location(
                "change_shape_degraded",
                _PLUGIN_ROOT / "skills" / "code-review" / "scripts" / "change_shape.py",
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        finally:
            sys.path = saved_path
            for name, prev in saved_mods.items():
                if prev == "__absent__":
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = prev

    #: Names chosen to straddle every indicator family AND its case variants —
    #: the axis the original defect hid behind.
    _CORPUS: ClassVar[list[str]] = [
        "tests/a.test.js", "tests/A.TEST.JS", "src/b.spec.ts",
        "tests/test_a.py", "tests/b_test.py", "tests/TEST_A.PY",
        "features/x.feature", "features/X.FEATURE",
        "steps/x.steps.js", "steps/x.STEPS.js",
        "a/FooSteps.js", "a/foosteps.js", "a/mysteps.js", "a/backsteps.py",
        "a/FooStepDefinitions.cs", "a/foostepdefinitions.cs",
        "pkg/__tests__/a.js", "pkg/__TESTS__/a.js",
        "src/FooTest.java", "src/FooTests.java", "src/FooSpec.java", "src/Foo.java",
        "tests/FooTests.cs", "tests/conftest.py", "src/prod.js",
        "README.md", "weird.xyz", "no_extension", "",
    ]

    @pytest.mark.parametrize("path", _CORPUS, ids=lambda p: p or "<empty>")
    def test_fallback_matches_shared_classifier(self, path):
        from test_file_classify import is_test_file as shared

        degraded = self._fallback_module()
        expected = bool(shared(path, content="")) if path else False
        assert degraded._is_provably_test_file(path) is expected, (
            f"degraded fallback disagrees with test_file_classify on {path!r}"
        )

    def test_fallback_never_over_claims_a_plain_source_file(self):
        """Direction matters more than agreement: a false positive here turns
        a mixed diff into a `test-only` one."""
        degraded = self._fallback_module()
        for source in ("a/backsteps.py", "a/mysteps.js", "src/prod.js", "a/foosteps.js"):
            assert degraded._is_provably_test_file(source) is False, source
