"""Tests for skills/test-design/scripts/internal_double_detector.py (#2127).

Covers: first-party type resolution and its test/vendor/build-output
exclusions, doubling-construct extraction across all four stacks, waiver
syntax validation, hand-rolled and DI-override detection across all four
ecosystems each, the B2 ambient-API evidence check (the one mechanical
blocker-truth check this detector performs), and the CLI (--strict exit
code, error paths, and finding-message format).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(
    0,
    str(
        _REPO_ROOT
        / "plugins"
        / "dev-team"
        / "skills"
        / "test-design"
        / "scripts"
    ),
)

_TESTS_LIB = _REPO_ROOT / "plugins" / "dev-team" / "tests" / "lib"
if str(_TESTS_LIB) not in sys.path:
    sys.path.insert(0, str(_TESTS_LIB))

import internal_double_detector as detector
from hermetic import hermetic_git_env  # type: ignore[import-not-found]

# --- First-party type resolution ---------------------------------------------


class TestResolveFirstPartyTypes:
    def test_indexes_a_class_from_non_test_source(self, tmp_path):
        src = tmp_path / "src" / "billing"
        src.mkdir(parents=True)
        (src / "gateway.py").write_text("class SmtpGateway:\n    pass\n", encoding="utf-8")

        index = detector.resolve_first_party_types(tmp_path)

        assert "SmtpGateway" in index

    def test_excludes_a_type_declared_under_a_test_directory(self, tmp_path):
        tests_dir = tmp_path / "tests" / "fixtures"
        tests_dir.mkdir(parents=True)
        (tests_dir / "fake_gateway.py").write_text("class FakeGateway:\n    pass\n", encoding="utf-8")

        index = detector.resolve_first_party_types(tmp_path)

        assert "FakeGateway" not in index

    def test_excludes_vendored_and_build_output(self, tmp_path):
        for dirname in ("node_modules", "dist", "vendor"):
            d = tmp_path / dirname
            d.mkdir(parents=True)
            (d / "thing.py").write_text("class VendoredType:\n    pass\n", encoding="utf-8")

        index = detector.resolve_first_party_types(tmp_path)

        assert "VendoredType" not in index

    def test_indexes_js_ts_declaration_forms(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.ts").write_text("export class ClassA {}\n", encoding="utf-8")
        (src / "b.ts").write_text("export interface InterfaceB {}\n", encoding="utf-8")
        (src / "c.ts").write_text("export type TypeC = { x: number };\n", encoding="utf-8")

        index = detector.resolve_first_party_types(tmp_path)

        assert {"ClassA", "InterfaceB", "TypeC"} <= index.keys()


# --- Doubling-construct extraction (all four stacks) -------------------------


class TestFindDoubles:
    def test_csharp_mock_generic(self):
        assert detector.find_doubles("var m = new Mock<ISmtpGateway>();") == [
            (1, "csharp", "ISmtpGateway")
        ]

    def test_csharp_substitute_for(self):
        result = detector.find_doubles("var m = Substitute.For<ISmtpGateway>();")
        assert result[0][1:] == ("csharp", "ISmtpGateway")

    def test_java_mock_of_class(self):
        result = detector.find_doubles("SmtpGateway g = mock(SmtpGateway.class);")
        assert result[0][1:] == ("java", "SmtpGateway")

    def test_js_ts_vi_mock(self):
        # Module path normalized to a plausible type-name form (last path
        # segment, extension stripped) so it can resolve against the
        # name-keyed first-party index (correctness-review fix).
        result = detector.find_doubles("vi.mock('./smtp-gateway')")
        assert result[0][1:] == ("js_ts", "smtp-gateway")

    def test_js_ts_vi_mock_normalizes_deeper_path_and_extension(self):
        result = detector.find_doubles("vi.mock('../services/SmtpGateway.ts')")
        assert result[0][1:] == ("js_ts", "SmtpGateway")

    def test_js_ts_vi_spy_on(self):
        result = detector.find_doubles("vi.spyOn(SmtpGateway, 'send')")
        assert result[0][1:] == ("js_ts", "SmtpGateway")

    def test_python_patch(self):
        result = detector.find_doubles('with patch("billing.gateway.SmtpGateway") as m:')
        assert result[0][1:] == ("python", "SmtpGateway")

    def test_python_magicmock_spec(self):
        result = detector.find_doubles("m = MagicMock(spec=SmtpGateway)")
        assert result[0][1:] == ("python", "SmtpGateway")


# --- Slice 1 verdict: advisory when unresolvable -----------------------------


class TestAnalyzeUnresolvable:
    def test_double_of_unresolvable_type_is_advisory(self, tmp_path):
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_thing.py").write_text(
            "m = MagicMock(spec=SomeThirdPartyThing)\n", encoding="utf-8"
        )

        findings = detector.analyze(tmp_path)

        assert len(findings) == 1
        assert findings[0]["verdict"] == "advisory"

    def test_two_doubles_on_one_line_yield_two_findings(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "gateway.py").write_text(
            "class SmtpGateway:\n    pass\n\n\nclass SmsGateway:\n    pass\n",
            encoding="utf-8",
        )
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_thing.py").write_text(
            "a = MagicMock(spec=SmtpGateway); b = MagicMock(spec=SmsGateway)\n",
            encoding="utf-8",
        )

        findings = detector.analyze(tmp_path)

        assert len(findings) == 2
        assert {f["target"] for f in findings} == {"SmtpGateway", "SmsGateway"}
        assert {f["line"] for f in findings} == {1}

    def test_production_declaration_wins_over_same_named_test_tree_file(self, tmp_path):
        """A production first-party declaration must resolve even when a
        same-named type exists under an excluded test directory -- proves
        the exclusion, not merely a lucky setdefault ordering."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "gateway.py").write_text("class SmtpGateway:\n    pass\n", encoding="utf-8")
        fixtures = tmp_path / "tests" / "fixtures"
        fixtures.mkdir(parents=True)
        (fixtures / "aaa_fake.py").write_text(
            "class SmtpGateway:\n    pass\n", encoding="utf-8"
        )

        index = detector.resolve_first_party_types(tmp_path)

        assert index["SmtpGateway"] == src / "gateway.py"


# --- Waiver parsing -----------------------------------------------------------


class TestFindWaiver:
    def test_waiver_on_preceding_line(self):
        lines = [
            "# double-waiver: B1 — holds a socket",
            "m = MagicMock(spec=SmtpGateway)",
        ]
        assert detector.find_waiver(lines, 2) == ("B1", "holds a socket")

    def test_waiver_on_same_line(self):
        lines = ["m = MagicMock(spec=SmtpGateway)  # double-waiver: B2 — reads the clock"]
        assert detector.find_waiver(lines, 1) == ("B2", "reads the clock")

    def test_no_waiver_returns_none(self):
        lines = ["m = MagicMock(spec=SmtpGateway)"]
        assert detector.find_waiver(lines, 1) is None

    def test_waiver_two_lines_before_is_rejected(self):
        """test-review boundary case: only the double's own line and the
        one immediately before it count -- a waiver written further back
        must not be picked up."""
        lines = [
            "# double-waiver: B1 — holds a socket",
            "",
            "m = MagicMock(spec=SmtpGateway)",
        ]
        assert detector.find_waiver(lines, 3) is None

    def test_malformed_code_still_parses_as_waiver_tuple(self):
        lines = ["m = MagicMock(spec=SmtpGateway)  # double-waiver: B9 — nonsense"]
        assert detector.find_waiver(lines, 1) == ("B9", "nonsense")

    def test_valid_blocker(self):
        assert detector.valid_blocker("B1")
        assert detector.valid_blocker("B2")
        assert detector.valid_blocker("B3")
        assert not detector.valid_blocker("B9")
        assert not detector.valid_blocker("B")


# --- Full-pipeline verdicts (Slice 2) ----------------------------------------


class TestAnalyzeVerdicts:
    def _make_tree(self, tmp_path, collaborator_body="class SmtpGateway:\n    pass\n"):
        src = tmp_path / "src"
        src.mkdir()
        (src / "gateway.py").write_text(collaborator_body, encoding="utf-8")
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        return tests_dir

    def test_unwaived_internal_double_is_high(self, tmp_path):
        tests_dir = self._make_tree(tmp_path)
        (tests_dir / "test_thing.py").write_text(
            "m = MagicMock(spec=SmtpGateway)\n", encoding="utf-8"
        )

        findings = detector.analyze(tmp_path)

        assert findings[0]["verdict"] == "high"

    def test_valid_blocker_waiver_is_informational(self, tmp_path):
        tests_dir = self._make_tree(tmp_path)
        (tests_dir / "test_thing.py").write_text(
            "# double-waiver: B1 — holds the socket\n"
            "m = MagicMock(spec=SmtpGateway)\n",
            encoding="utf-8",
        )

        findings = detector.analyze(tmp_path)

        assert findings[0]["verdict"] == "informational"

    def test_invalid_blocker_code_is_high(self, tmp_path):
        tests_dir = self._make_tree(tmp_path)
        (tests_dir / "test_thing.py").write_text(
            "# double-waiver: B9 — reason\n"
            "m = MagicMock(spec=SmtpGateway)\n",
            encoding="utf-8",
        )

        findings = detector.analyze(tmp_path)

        assert findings[0]["verdict"] == "high"


# --- Hand-rolled doubles and DI-overrides (all four ecosystems each) --------


class TestHandRolledDoubles:
    def _resolvable_tree(self, tmp_path, declaration):
        src = tmp_path / "src"
        src.mkdir()
        (src / "gateway.py").write_text("class SmtpGateway:\n    pass\n", encoding="utf-8")
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        return tests_dir, declaration

    def test_python_subclass(self, tmp_path):
        tests_dir, decl = self._resolvable_tree(
            tmp_path, "class FakeGateway(SmtpGateway):\n    pass\n"
        )
        (tests_dir / "fake.py").write_text(decl, encoding="utf-8")

        findings = detector.analyze(tmp_path)

        assert any(f["vector"] == "hand_rolled" and f["target"] == "SmtpGateway" for f in findings)

    def test_java_implements(self, tmp_path):
        tests_dir, decl = self._resolvable_tree(
            tmp_path, "class FakeGateway implements SmtpGateway {}\n"
        )
        (tests_dir / "Fake.java").write_text(decl, encoding="utf-8")

        findings = detector.analyze(tmp_path)

        assert any(f["vector"] == "hand_rolled" and f["target"] == "SmtpGateway" for f in findings)

    def test_ts_implements(self, tmp_path):
        tests_dir, decl = self._resolvable_tree(
            tmp_path, "class FakeGateway implements SmtpGateway {}\n"
        )
        (tests_dir / "fake.ts").write_text(decl, encoding="utf-8")

        findings = detector.analyze(tmp_path)

        assert any(f["vector"] == "hand_rolled" and f["target"] == "SmtpGateway" for f in findings)

    def test_csharp_colon_inheritance(self, tmp_path):
        tests_dir, decl = self._resolvable_tree(
            tmp_path, "class FakeGateway : SmtpGateway {}\n"
        )
        (tests_dir / "Fake.cs").write_text(decl, encoding="utf-8")

        findings = detector.analyze(tmp_path)

        assert any(f["vector"] == "hand_rolled" and f["target"] == "SmtpGateway" for f in findings)


class TestDiOverrides:
    def _resolvable_tree(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "gateway.py").write_text("class SmtpGateway:\n    pass\n", encoding="utf-8")
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        return tests_dir

    def test_dotnet_add_singleton(self, tmp_path):
        tests_dir = self._resolvable_tree(tmp_path)
        (tests_dir / "Setup.cs").write_text(
            "services.AddSingleton<SmtpGateway>(fake);\n", encoding="utf-8"
        )
        findings = detector.analyze(tmp_path)
        assert any(f["vector"] == "di_override" for f in findings)

    def test_spring_bean(self, tmp_path):
        tests_dir = self._resolvable_tree(tmp_path)
        (tests_dir / "TestConfig.java").write_text(
            "@Bean\npublic SmtpGateway fakeGateway() { return new FakeGateway(); }\n",
            encoding="utf-8",
        )
        findings = detector.analyze(tmp_path)
        assert any(f["vector"] == "di_override" for f in findings)

    def test_fastapi_dependency_overrides(self, tmp_path):
        tests_dir = self._resolvable_tree(tmp_path)
        (tests_dir / "conftest.py").write_text(
            "app.dependency_overrides[SmtpGateway] = fake_gateway\n", encoding="utf-8"
        )
        findings = detector.analyze(tmp_path)
        assert any(f["vector"] == "di_override" for f in findings)

    def test_nestjs_override_provider(self, tmp_path):
        tests_dir = self._resolvable_tree(tmp_path)
        (tests_dir / "app.spec.ts").write_text(
            "overrideProvider(SmtpGateway).useValue(fake);\n", encoding="utf-8"
        )
        findings = detector.analyze(tmp_path)
        assert any(f["vector"] == "di_override" for f in findings)


# --- B2 ambient-API evidence check -------------------------------------------


class TestReferencesAmbientApiAllStacks:
    """test-review gap: the B2 ambient-API markers were only exercised for
    Python via full analyze() fixtures. Direct unit tests against
    references_ambient_api() cover the other three stacks cheaply."""

    def test_csharp_datetime_now(self):
        assert detector.references_ambient_api("var t = DateTime.Now;", "csharp")

    def test_java_system_current_time_millis(self):
        assert detector.references_ambient_api(
            "long t = System.currentTimeMillis();", "java"
        )

    def test_js_ts_date_now(self):
        assert detector.references_ambient_api("const t = Date.now();", "js_ts")

    def test_no_marker_present_for_any_stack(self):
        for stack in ("python", "csharp", "java", "js_ts"):
            assert not detector.references_ambient_api("class Plain {}", stack)


class TestAmbientApiEvidence:
    def test_b2_waiver_contradicted_by_no_ambient_evidence_is_high(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "gateway.py").write_text("class SmtpGateway:\n    pass\n", encoding="utf-8")
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_thing.py").write_text(
            "# double-waiver: B2 — reads the clock\n"
            "m = MagicMock(spec=SmtpGateway)\n",
            encoding="utf-8",
        )

        findings = detector.analyze(tmp_path)

        assert findings[0]["verdict"] == "high"

    def test_b2_waiver_with_ambient_evidence_is_informational(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "gateway.py").write_text(
            "import time\nclass SmtpGateway:\n    def now(self):\n        return time.time()\n",
            encoding="utf-8",
        )
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_thing.py").write_text(
            "# double-waiver: B2 — reads the clock\n"
            "m = MagicMock(spec=SmtpGateway)\n",
            encoding="utf-8",
        )

        findings = detector.analyze(tmp_path)

        assert findings[0]["verdict"] == "informational"

    def test_b1_stays_informational_regardless_of_ambient_evidence(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "gateway.py").write_text("class SmtpGateway:\n    pass\n", encoding="utf-8")
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_thing.py").write_text(
            "# double-waiver: B1 — holds a socket\n"
            "m = MagicMock(spec=SmtpGateway)\n",
            encoding="utf-8",
        )

        findings = detector.analyze(tmp_path)

        assert findings[0]["verdict"] == "informational"

    def test_b3_stays_informational_regardless_of_ambient_evidence(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "gateway.py").write_text("class SmtpGateway:\n    pass\n", encoding="utf-8")
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_thing.py").write_text(
            "# double-waiver: B3 — prod work factor\n"
            "m = MagicMock(spec=SmtpGateway)\n",
            encoding="utf-8",
        )

        findings = detector.analyze(tmp_path)

        assert findings[0]["verdict"] == "informational"


# --- Docstring / help-text semantic-bound statement --------------------------


class TestSemanticBoundDocumented:
    def test_module_docstring_states_syntax_vs_truth_bound(self):
        doc = detector.__doc__
        assert "waiver syntax" in doc.lower() or "waiver truth" in doc.lower()
        assert "test-smell-review" in doc

    def test_module_docstring_states_b2_asymmetry(self):
        doc = detector.__doc__
        assert "B2" in doc
        assert "ambient" in doc.lower()


# --- CLI ----------------------------------------------------------------------


class TestCli:
    def _resolvable_tree(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "gateway.py").write_text("class SmtpGateway:\n    pass\n", encoding="utf-8")
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        return tests_dir

    def test_flags_and_fails_under_strict_then_passes_once_fixed(self, tmp_path):
        tests_dir = self._resolvable_tree(tmp_path)
        offender = tests_dir / "test_thing.py"
        offender.write_text("m = MagicMock(spec=SmtpGateway)\n", encoding="utf-8")

        exit_code_before = detector.main([str(tmp_path), "--strict"])
        assert exit_code_before == 1

        offender.write_text(
            "# double-waiver: B1 — holds the socket\nm = MagicMock(spec=SmtpGateway)\n",
            encoding="utf-8",
        )
        exit_code_after = detector.main([str(tmp_path), "--strict"])
        assert exit_code_after == 0

    def test_without_strict_always_exits_zero(self, tmp_path):
        tests_dir = self._resolvable_tree(tmp_path)
        (tests_dir / "test_thing.py").write_text(
            "m = MagicMock(spec=SmtpGateway)\n", encoding="utf-8"
        )

        assert detector.main([str(tmp_path)]) == 0

    def test_nonexistent_path_exits_cleanly(self, tmp_path, capsys):
        missing = tmp_path / "does-not-exist"

        exit_code = detector.main([str(missing)])

        assert exit_code == 2
        captured = capsys.readouterr()
        assert "not found" in captured.err

    def test_empty_tree_reports_zero_findings(self, tmp_path, capsys):
        exit_code = detector.main([str(tmp_path)])

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "0 findings" in captured.out

    def test_finding_message_includes_file_line_verdict_and_hint(self, tmp_path, capsys):
        tests_dir = self._resolvable_tree(tmp_path)
        (tests_dir / "test_thing.py").write_text(
            "m = MagicMock(spec=SmtpGateway)\n", encoding="utf-8"
        )

        detector.main([str(tmp_path)])

        out = capsys.readouterr().out
        assert "test_thing.py:1" in out
        assert "high" in out
        assert "SmtpGateway" in out
        assert "double-waiver" in out
        assert "internal-collaborator-doubling.md" in out

    def test_summary_line_counts_by_verdict(self, tmp_path, capsys):
        tests_dir = self._resolvable_tree(tmp_path)
        (tests_dir / "test_thing.py").write_text(
            "m1 = MagicMock(spec=SmtpGateway)\n"
            "# double-waiver: B1 — holds the socket\n"
            "m2 = MagicMock(spec=SmtpGateway)\n",
            encoding="utf-8",
        )

        detector.main([str(tmp_path)])

        out = capsys.readouterr().out
        first_line = out.splitlines()[0]
        assert "high" in first_line
        assert "informational" in first_line

    def test_json_output_shape(self, tmp_path, capsys):
        tests_dir = self._resolvable_tree(tmp_path)
        (tests_dir / "test_thing.py").write_text(
            "m = MagicMock(spec=SmtpGateway)\n", encoding="utf-8"
        )

        detector.main([str(tmp_path), "--json"])

        import json

        payload = json.loads(capsys.readouterr().out)
        assert "findings" in payload
        assert payload["findings"][0]["verdict"] == "high"

    def test_recall_bounds_statement_always_printed(self, tmp_path, capsys):
        detector.main([str(tmp_path)])

        out = capsys.readouterr().out
        assert "Recall bounds" in out


# --- Changed-file scoping (#2128) --------------------------------------------


def _git(cwd, *args):
    # #715 / hermetic_git_env: never let this subprocess inherit an
    # ambient GIT_DIR/GIT_INDEX_FILE/GIT_WORK_TREE (set when THIS suite
    # itself runs from inside a pre-push git hook) — that would redirect
    # `git init`/`git commit` into the real repo's .git instead of tmp_path.
    env = hermetic_git_env(home=cwd)
    result = subprocess.run(
        ["git", *args], cwd=str(cwd), env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def _init_repo_with_base_commit(tmp_path):
    """A first-party class in an unchanged production file, committed as the
    base; returns (tests_dir, base_sha) for the caller to add a second
    commit (the "diff") on top of."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    src = tmp_path / "src"
    src.mkdir()
    (src / "gateway.py").write_text("class SmtpGateway:\n    pass\n", encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_old.py").write_text("# nothing doubled here\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    return tests_dir, _git(tmp_path, "rev-parse", "HEAD").strip()


class TestChangedFilesSince:
    def test_resolves_a_real_ref(self, tmp_path):
        tests_dir, base_sha = _init_repo_with_base_commit(tmp_path)
        new_file = tests_dir / "test_new.py"
        new_file.write_text("m = MagicMock(spec=SmtpGateway)\n", encoding="utf-8")
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-q", "-m", "add double")

        changed = detector.changed_files_since(base_sha, tmp_path)

        assert changed == {new_file.resolve()}

    def test_returns_none_on_git_failure(self, tmp_path):
        # tmp_path is not a git repo at all.
        assert detector.changed_files_since("HEAD", tmp_path) is None

    def test_returns_none_on_a_bad_ref(self, tmp_path):
        _init_repo_with_base_commit(tmp_path)

        assert detector.changed_files_since("not-a-real-ref", tmp_path) is None

    def test_empty_set_on_a_diff_with_no_changes(self, tmp_path):
        _tests_dir, base_sha = _init_repo_with_base_commit(tmp_path)

        assert detector.changed_files_since(base_sha, tmp_path) == set()

    def test_correct_when_root_is_a_repo_subdirectory(self, tmp_path):
        """`git diff --name-only` always emits paths relative to the repo's
        TOP LEVEL, never relative to the cwd it ran from — regression guard
        for the false-negative correctness-review caught: joining the
        output onto `root` itself (rather than the actual git top-level)
        silently produced non-existent, double-prefixed paths whenever
        `root` was a subdirectory of the repo, matching nothing and
        disabling the gate with no ADVISORY and no block."""
        tests_dir, base_sha = _init_repo_with_base_commit(tmp_path)
        sub = tmp_path / "sub"
        sub.mkdir()
        new_file = tests_dir / "test_new.py"
        new_file.write_text("m = MagicMock(spec=SmtpGateway)\n", encoding="utf-8")
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-q", "-m", "add double")

        changed = detector.changed_files_since(base_sha, sub)

        assert changed == {new_file.resolve()}
        for path in changed:
            assert path.exists()


class TestFilterSince:
    def test_retains_findings_inside_the_diff(self, tmp_path):
        target = tmp_path / "tests" / "test_a.py"
        findings = [{"file": str(target), "verdict": "high"}]

        result = detector.filter_since(findings, {target.resolve()}, tmp_path)

        assert result == findings

    def test_excludes_findings_outside_the_diff(self, tmp_path):
        target = tmp_path / "tests" / "test_a.py"
        other = tmp_path / "tests" / "test_b.py"
        findings = [{"file": str(target), "verdict": "high"}]

        result = detector.filter_since(findings, {other.resolve()}, tmp_path)

        assert result == []

    def test_correct_regardless_of_absolute_or_relative_root(self, tmp_path, monkeypatch):
        target = tmp_path / "tests" / "test_a.py"
        findings_abs = [{"file": str(target), "verdict": "high"}]
        changed = {target.resolve()}

        assert detector.filter_since(findings_abs, changed, tmp_path) == findings_abs

        monkeypatch.chdir(tmp_path)
        relative_root = Path(".")
        findings_rel = [{"file": str(target.relative_to(tmp_path)), "verdict": "high"}]

        assert detector.filter_since(findings_rel, changed, relative_root) == findings_rel

    def test_with_empty_changed_set(self, tmp_path):
        target = tmp_path / "tests" / "test_a.py"
        findings = [{"file": str(target), "verdict": "high"}]

        assert detector.filter_since(findings, set(), tmp_path) == []


class TestAnalyzeSince:
    def test_new_high_finding_inside_the_diff_is_retained(self, tmp_path):
        # Proves analyze()'s full-tree first-party resolution is untouched:
        # SmtpGateway is declared in an UNCHANGED file from the base commit,
        # yet the double added in the diff still resolves to `high`.
        tests_dir, base_sha = _init_repo_with_base_commit(tmp_path)
        new_test = tests_dir / "test_new.py"
        new_test.write_text("m = MagicMock(spec=SmtpGateway)\n", encoding="utf-8")
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-q", "-m", "add double")

        findings, reason = detector.analyze_since(tmp_path, base_sha)

        assert reason is None
        assert len(findings) == 1
        assert findings[0]["target"] == "SmtpGateway"
        assert findings[0]["verdict"] == "high"

    def test_this_holds_regardless_of_absolute_or_relative_root(self, tmp_path, monkeypatch):
        tests_dir, base_sha = _init_repo_with_base_commit(tmp_path)
        (tests_dir / "test_new.py").write_text(
            "m = MagicMock(spec=SmtpGateway)\n", encoding="utf-8"
        )
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-q", "-m", "add double")

        monkeypatch.chdir(tmp_path)
        findings, reason = detector.analyze_since(Path("."), base_sha)

        assert reason is None
        assert len(findings) == 1
        assert findings[0]["target"] == "SmtpGateway"
        assert findings[0]["verdict"] == "high"

    def test_a_production_only_diff_can_activate_a_previously_advisory_double(self, tmp_path):
        """Disclosed gap, not a bug (see the hook's "Two enforcement
        points" design): a diff that adds ONLY a new first-party class,
        leaving an already-existing test file untouched, makes that test
        file's existing advisory finding become `high` — but the CHANGED
        SET is keyed on the finding's own file, which isn't in this diff,
        so the scoped result excludes it while the unfiltered analyze()
        correctly still reports it. Both halves are pinned here so a
        future change to what filter_since keys on can't silently break
        this documented, load-bearing behavior with no regression signal."""
        env = hermetic_git_env(home=tmp_path)
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, env=env, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, env=env, check=True)
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        # No first-party SmtpGateway exists yet -> this is only `advisory`.
        (tests_dir / "test_old.py").write_text(
            "m = MagicMock(spec=SmtpGateway)\n", encoding="utf-8"
        )
        subprocess.run(["git", "add", "-A"], cwd=tmp_path, env=env, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=tmp_path, env=env, check=True)
        base_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=tmp_path, env=env, capture_output=True, text=True, check=True
        ).stdout.strip()

        # The diff adds ONLY a new first-party class with that name -
        # test_old.py itself is untouched.
        src = tmp_path / "src"
        src.mkdir()
        (src / "gateway.py").write_text("class SmtpGateway:\n    pass\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=tmp_path, env=env, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "add the first-party class"], cwd=tmp_path, env=env, check=True
        )

        unfiltered = detector.analyze(tmp_path)
        assert len(unfiltered) == 1
        assert unfiltered[0]["verdict"] == "high"

        scoped, reason = detector.analyze_since(tmp_path, base_sha)
        assert reason is None
        assert scoped == []

    def test_excludes_a_pre_existing_finding_outside_the_diff(self, tmp_path):
        tests_dir, _base_sha = _init_repo_with_base_commit(tmp_path)
        # An unwaived double already present at the base commit (outside
        # any future diff).
        (tests_dir / "test_old.py").write_text(
            "m = MagicMock(spec=SmtpGateway)\n", encoding="utf-8"
        )
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-q", "-m", "amend base with a pre-existing double")
        second_base_sha = _git(tmp_path, "rev-parse", "HEAD").strip()
        # A no-op commit so the diff vs second_base_sha is genuinely empty.
        (tests_dir / "unrelated.txt").write_text("noop\n", encoding="utf-8")
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-q", "-m", "unrelated")

        findings, reason = detector.analyze_since(tmp_path, second_base_sha)

        assert reason is None
        assert findings == []

    def test_returns_advisory_reason_on_git_failure_with_unfiltered_findings(self, tmp_path):
        tests_dir = self._resolvable_tree_no_git(tmp_path)
        (tests_dir / "test_thing.py").write_text(
            "m = MagicMock(spec=SmtpGateway)\n", encoding="utf-8"
        )

        findings, reason = detector.analyze_since(tmp_path, "HEAD")

        assert reason is not None
        assert any(f["verdict"] == "high" for f in findings)

    @staticmethod
    def _resolvable_tree_no_git(tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "gateway.py").write_text("class SmtpGateway:\n    pass\n", encoding="utf-8")
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        return tests_dir


class TestMainChangedSince:
    def test_strict_exit_code_on_git_failure_uses_the_unscoped_set(self, tmp_path, capsys):
        # A non-git tree with a real high finding: changed_files_since fails
        # (no git repo at all), so --changed-since --strict falls back to
        # the unscoped set on purpose — the CLI-only exception to AC8.
        src = tmp_path / "src"
        src.mkdir()
        (src / "gateway.py").write_text("class SmtpGateway:\n    pass\n", encoding="utf-8")
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_thing.py").write_text(
            "m = MagicMock(spec=SmtpGateway)\n", encoding="utf-8"
        )

        exit_code = detector.main([str(tmp_path), "--changed-since", "HEAD", "--strict"])

        assert exit_code == 1
        out = capsys.readouterr().out
        assert "ADVISORY" in out

    def test_scopes_to_the_diff_when_git_succeeds(self, tmp_path, capsys):
        tests_dir, _base_sha = _init_repo_with_base_commit(tmp_path)
        (tests_dir / "test_old.py").write_text(
            "m = MagicMock(spec=SmtpGateway)\n", encoding="utf-8"
        )
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-q", "-m", "pre-existing double outside future diff")
        second_base_sha = _git(tmp_path, "rev-parse", "HEAD").strip()
        (tests_dir / "unrelated.txt").write_text("noop\n", encoding="utf-8")
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-q", "-m", "unrelated")

        exit_code = detector.main(
            [str(tmp_path), "--changed-since", second_base_sha, "--strict"]
        )

        assert exit_code == 0
        out = capsys.readouterr().out
        assert "ADVISORY" not in out


# --- CI check: whole-repo scan (#2128) ---------------------------------------
#
# `_assert_no_high_severity_findings` is the ACTUAL production check's own
# code, called by both the real-repo test below and its own fail-on-purpose
# fixture test — not a structurally-similar reimplementation of it.


def _assert_no_high_severity_findings(root):
    findings = detector.analyze(root)
    high = [f for f in findings if f["verdict"] == "high"]
    assert high == [], (
        f"{len(high)} unwaived internal double(s) found:\n"
        + "\n".join(f["message"] for f in high)
        + "\n"
        + detector._RECALL_BOUNDS_STATEMENT
    )


def test_full_repo_scan_has_no_high_severity_findings():
    """The CI check (#2128): runs unfiltered across the whole live repo on
    every PR — the exhaustive backstop the scoped hook is not. See the
    plan's "Two enforcement points" section for why both exist."""
    _assert_no_high_severity_findings(_REPO_ROOT)


def test_the_real_repo_assertion_would_catch_a_high_finding(tmp_path):
    """Fail-on-purpose proof for the CI check specifically (CLAUDE.md: "make
    a new gate fail on purpose once before trusting it") — calls the SAME
    helper the real check uses, against a crafted fixture with one genuine
    unwaived high-severity double."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "gateway.py").write_text("class SmtpGateway:\n    pass\n", encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_thing.py").write_text(
        "m = MagicMock(spec=SmtpGateway)\n", encoding="utf-8"
    )

    try:
        _assert_no_high_severity_findings(tmp_path)
    except AssertionError as exc:
        message = str(exc)
        assert "SmtpGateway" in message
        assert "Recall bounds" in message
    else:
        raise AssertionError(
            "expected _assert_no_high_severity_findings to fail on a real "
            "unwaived high-severity double"
        )
