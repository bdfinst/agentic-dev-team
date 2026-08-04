"""Tests for xunit_v3_feature_detector.py — detects and classifies the
xunit.v3-only constructs that break the v2 mutation-shim compile (#1160,
part of #1156)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = (
    Path(__file__).resolve().parents[2]
    / "plugins"
    / "dev-team"
    / "skills"
    / "mutation-testing"
    / "scripts"
)
sys.path.insert(0, str(SCRIPTS_DIR))

import xunit_v3_feature_detector as det

FIXTURE = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "xunit-v3"
    / "V3FeaturesTests.cs"
)


def _by_construct(findings):
    out = {}
    for f in findings:
        out.setdefault(f.construct, []).append(f)
    return out


def test_detects_every_construct_in_fixture():
    names = {f.construct for f in det.scan_file(FIXTURE)}
    assert names == {
        "fact-explicit",
        "assert-skip",
        "test-context",
        "async-lifetime-valuetask",
        "theory-data-row",
        "autofixture-auto-data",
        "assert-multiple",
        "assert-equivalent",
    }


def test_fact_explicit_is_neutral_and_no_equivalent():
    findings = _by_construct(det.scan_file(FIXTURE))["fact-explicit"]
    # [Fact(Explicit=true)], [Theory(Explicit=true)], and the form whose
    # Explicit sits after a string-valued property.
    assert len(findings) == 3
    for f in findings:
        assert f.compile_ability == det.NO_V2_EQUIVALENT
        assert f.coverage_impact == det.COVERAGE_NEUTRAL


def test_assert_skip_matches_all_three_alternations():
    fs = _by_construct(det.scan_file(FIXTURE))["assert-skip"]
    # Assert.SkipWhen, Assert.Skip, Assert.SkipUnless.
    assert len(fs) == 3
    for f in fs:
        assert f.compile_ability == det.NO_V2_EQUIVALENT
        assert f.coverage_impact == det.COVERAGE_BEARING


def test_test_context_is_bearing_and_no_equivalent():
    f = _by_construct(det.scan_file(FIXTURE))["test-context"][0]
    assert f.compile_ability == det.NO_V2_EQUIVALENT
    assert f.coverage_impact == det.COVERAGE_BEARING


def test_async_lifetime_valuetask_is_translatable_and_bearing():
    fs = _by_construct(det.scan_file(FIXTURE))["async-lifetime-valuetask"]
    assert len(fs) == 2  # InitializeAsync + DisposeAsync
    for f in fs:
        assert f.compile_ability == det.CLEAN_TRANSLATABLE
        assert f.coverage_impact == det.COVERAGE_BEARING


def test_theory_data_row_detected():
    text = "public static TheoryDataRow<int> Cases() => new(1);"
    findings = det.scan_text("Cases.cs", text)
    assert len(findings) == 1
    assert findings[0].construct == "theory-data-row"
    assert findings[0].compile_ability == det.CLEAN_TRANSLATABLE
    assert findings[0].coverage_impact == det.COVERAGE_BEARING


# --- AutoFixture / v3-only assertion constructs (#1791) --------------------
#
# The operator-facing gate quotes the detector's classification verbatim
# ("N test files use [AutoData]/AutoFixture.Xunit3, which the v2 shim can't
# compile" — #1791). That sentence is only true if the detector actually
# classifies those constructs, so they are pinned here.


@pytest.mark.parametrize(
    "source",
    [
        "    [Theory, AutoData]",
        "    [AutoData]",
        "    [InlineAutoData(1, 2)]",
        "    [AutoMoqData]",
        "    [MemberAutoData(nameof(Cases))]",
        "using AutoFixture.Xunit3;",
    ],
)
def test_autofixture_constructs_are_classified(source):
    findings = det.scan_text("A.cs", source)
    assert len(findings) == 1, f"expected exactly one finding for {source!r}"
    assert findings[0].construct == "autofixture-auto-data"
    assert findings[0].compile_ability == det.NO_V2_EQUIVALENT
    assert findings[0].coverage_impact == det.COVERAGE_BEARING


def test_autofixture_xunit2_package_not_flagged():
    # AutoFixture.Xunit2 is the v2-compatible package — flagging it would tell
    # the operator to port something that already compiles under the shim.
    assert det.scan_text("A.cs", "using AutoFixture.Xunit2;") == []


def test_autofixture_xunit2_usage_not_flagged():
    # The attribute NAMES are identical between AutoFixture.Xunit2 and .Xunit3,
    # so the name alone cannot decide. A file that declares the v2 package
    # compiles fine in the shim; flagging it would block the gate on nothing and,
    # if the operator picks `exclude`, drop v2-compatible tests from measurement.
    text = "using AutoFixture.Xunit2;\n[Theory, AutoData]\npublic void X(int a) {}\n"
    assert det.scan_text("A.cs", text) == []


def test_autofixture_xunit3_wins_when_a_file_names_both():
    text = (
        "using AutoFixture.Xunit2;\nusing AutoFixture.Xunit3;\n[Theory, AutoData]\n"
    )
    constructs = {f.construct for f in det.scan_text("A.cs", text)}
    assert "autofixture-auto-data" in constructs


def test_auto_data_with_no_package_hint_is_still_flagged():
    # Unknown package (global using, or the reference lives in the .csproj) ->
    # flag and let the operator decide. Blocking-and-asking is the safe default;
    # silently proceeding into an uncompilable shim is not.
    findings = det.scan_text("A.cs", "[Theory, AutoData]")
    assert [f.construct for f in findings] == ["autofixture-auto-data"]


def test_member_auto_data_counted_once_not_twice():
    # `\bAutoData\b` must not also fire inside `MemberAutoData`/`InlineAutoData`,
    # or the operator sees an inflated blocker count.
    findings = det.scan_text("A.cs", "[MemberAutoData(nameof(Cases))]")
    assert len(findings) == 1


def test_assert_multiple_is_classified():
    findings = det.scan_text("A.cs", "Assert.Multiple(() => Assert.True(true));")
    assert len(findings) == 1
    assert findings[0].construct == "assert-multiple"
    assert findings[0].compile_ability == det.NO_V2_EQUIVALENT
    assert findings[0].coverage_impact == det.COVERAGE_BEARING


def test_assert_equivalent_is_classified():
    findings = det.scan_text("A.cs", "Assert.Equivalent(expected, actual);")
    assert len(findings) == 1
    assert findings[0].construct == "assert-equivalent"
    assert findings[0].compile_ability == det.NO_V2_EQUIVALENT


def test_autofixture_summary_names_the_construct_and_file_count():
    findings = det.scan_text("A.cs", "[AutoData]") + det.scan_text("B.cs", "[AutoData]")
    s = det.summarize(findings)
    assert s.files == 2
    assert s.bearing == 2


# --- near-miss negatives: none of these may be flagged ---------------------


def test_explicit_false_not_flagged():
    findings = det.scan_text("N.cs", "[Fact(Explicit = false)]")
    assert findings == []


def test_commented_out_attribute_not_flagged():
    findings = det.scan_text("N.cs", "    // [Fact(Explicit = true)]")
    assert findings == []


def test_linq_skip_not_flagged():
    findings = det.scan_text("N.cs", "var tail = items.Skip(1).ToArray();")
    assert findings == []


def test_display_name_containing_explicit_not_flagged():
    # A quoted argument's CONTENTS must never satisfy the property match.
    findings = det.scan_text("N.cs", '[Fact(DisplayName="Explicit = true story")]')
    assert findings == []


@pytest.mark.parametrize(
    "source",
    [
        '[Fact(DisplayName = "weekly sweep", Explicit = true)]',
        '[Theory(Skip = "flaky", Explicit = true)]',
        '[Trait("area", "slow"), Fact(Explicit = true)]',
        '[Fact(Explicit = true, DisplayName = "x")]',
    ],
)
def test_explicit_found_regardless_of_argument_order_or_bracket_owner(source):
    # The old pattern could not cross a COMPLETED quoted argument, only refuse to
    # enter one, so any string-valued property before Explicit hid the construct
    # entirely — and the guard has no Explicit token to fall back on, so it would
    # auto-scaffold a shim whose linked sources then fail to compile.
    findings = det.scan_text("N.cs", source)
    assert [f.construct for f in findings] == ["fact-explicit"], source


def test_fixture_negatives_not_flagged():
    findings = det.scan_file(FIXTURE)
    snippets = [f.snippet for f in findings]
    # LINQ .Skip and the Explicit=false / commented-out lines never appear.
    assert not any(".Skip(1)" in s for s in snippets)
    assert not any("Explicit = false" in s for s in snippets)
    assert not any(s.lstrip().startswith("//") for s in snippets)


def test_findings_carry_line_numbers():
    findings = det.scan_text("F.cs", "line1\n[Fact(Explicit = true)]\nline3")
    assert len(findings) == 1
    assert findings[0].line == 2


def test_missing_file_yields_no_findings(tmp_path):
    assert det.scan_file(tmp_path / "nope.cs") == []


def test_files_with_findings_dedups_stable():
    findings = det.scan_file(FIXTURE)
    files = det.files_with_findings(findings)
    assert files == [str(FIXTURE)]


def test_files_with_findings_multi_file_first_seen_order():
    # Interleave two files; expect first-seen order, deduped.
    findings = (
        det.scan_text("b.cs", "[Fact(Explicit = true)]")
        + det.scan_text("a.cs", "TestContext.Current.Test")
        + det.scan_text("b.cs", "Assert.Skip(\"x\")")
    )
    assert det.files_with_findings(findings) == ["b.cs", "a.cs"]


# --- summarize / sizing recommendation --------------------------------------


def test_summary_no_findings_says_viable():
    s = det.summarize([])
    assert s.total == 0
    assert "viable" in s.recommendation.lower()


def test_summary_neutral_only_recommends_safe_exclude():
    findings = det.scan_text(
        "N.cs", "[Fact(Explicit = true)]\n[Theory(Explicit=true)]"
    )
    s = det.summarize(findings)
    assert s.bearing == 0
    assert s.neutral == 2
    assert "safe" in s.recommendation.lower()


def test_summary_bearing_warns_about_hidden_coverage():
    findings = det.scan_file(FIXTURE)
    s = det.summarize(findings)
    assert s.bearing > 0
    assert "coverage-analysis off" in s.recommendation.lower()


def test_cli_json_output(capsys):
    rc = det._cli([str(FIXTURE), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    import json

    payload = json.loads(out)
    assert "findings" in payload and "summary" in payload
    assert payload["summary"]["total"] == len(payload["findings"])
    assert payload["summary"]["total"] > 0  # FIXTURE is non-empty
    # The finding record shape the #1159 gate/exclusion wiring consumes.
    assert set(payload["findings"][0]) == {
        "file",
        "line",
        "construct",
        "compile_ability",
        "coverage_impact",
        "snippet",
    }


def test_cli_table_output(capsys):
    rc = det._cli([str(FIXTURE)])
    out = capsys.readouterr().out
    assert rc == 0
    # The per-finding table line shape plus the recommendation footer.
    assert "fact-explicit" in out
    assert "coverage-" in out
    assert "/" in out  # the "[compile / coverage-...]" bracket
    # summarize() recommendation footer is present (bearing hits in fixture).
    assert "coverage-analysis off" in out.lower()
