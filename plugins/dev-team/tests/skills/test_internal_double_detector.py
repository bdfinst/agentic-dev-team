"""Tests for skills/test-design/scripts/internal_double_detector.py (#2127).

Covers: first-party type resolution and its test/vendor/build-output
exclusions, doubling-construct extraction across all four stacks, waiver
syntax validation, hand-rolled and DI-override detection across all four
ecosystems each, the B2 ambient-API evidence check (the one mechanical
blocker-truth check this detector performs), and the CLI (--strict exit
code, error paths, and finding-message format).
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
        / "test-design"
        / "scripts"
    ),
)

import internal_double_detector as detector

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
