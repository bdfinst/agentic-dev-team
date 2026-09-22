"""Tests for scripts/test_review_mechanics.py (#2169 Step 2.2).

One fixture per `[MECHANICAL]` check test-review.md documents (#2169 Step
2.1), plus the four cross-cutting scenarios from the plan's Gherkin: a
reflection-only fixture that must NOT set `mechanicalFail`, an
`internal_double_detector.py` translation fixture that MUST set it, a clean
file, an unparseable file, and the tolerated-deviation consolidation
threshold's 3-vs-2 boundary.

Per-step review-fix pass (#2169 Step 2.2 review checkpoint) adds: content-
slice/masking regression fixtures (Fix 1), additional test-declaration-form
recognition fixtures (Fix 2), clock-stub suppression (Fix 3), mock
re-initialization suppression (Fix 4), doubling-detector disclosure
(severity + doublingCheckRan + out-of-scope, Fixes 5/6), deviation-marker
qualifier suppression (Fix 8), and a drift guard tying test-review.md's
gating language to `_GATING_CATEGORIES` (Fix 9).

Every fixture below places its test file under a `tests/` subdirectory of
`tmp_path` (in-scope for `internal_double_detector.py`'s own `test`/`tests`
path-segment scoping) and passes a no-op `double_detector_runner` stub
unless the fixture is specifically exercising the real subprocess call or
the out-of-scope/failure paths (Fix 13 — avoids paying real subprocess-spawn
cost for checks unrelated to doubling detection).
"""

from __future__ import annotations

import json
import sys
from typing import ClassVar

from _repo_root import REPO_ROOT as _REPO_ROOT

_SCRIPTS_DIR = _REPO_ROOT / "plugins" / "dev-team" / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

import test_review_mechanics as trm

AGENT_MD = _REPO_ROOT / "plugins" / "dev-team" / "agents" / "test-review.md"


def _findings_by_category(result: dict, category: str) -> list[dict]:
    return [f for f in result["findings"] if f["category"] == category]


class _StubCompleted:
    """Stand-in for `subprocess.CompletedProcess` — only `.stdout` /
    `.stderr` / `.returncode` are read by `_translate_double_detector_findings`."""

    def __init__(self, stdout: str, returncode: int = 0, stderr: str = "") -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _no_op_runner(*_args, **_kwargs) -> _StubCompleted:
    return _StubCompleted(json.dumps({"findings": []}))


def _tests_dir(tmp_path):
    d = tmp_path / "tests"
    d.mkdir()
    return d


class TestNoAssertion:
    def test_test_with_no_assertion_is_error_and_gates(self, tmp_path):
        test_file = _tests_dir(tmp_path) / "widget.test.js"
        test_file.write_text(
            "it('renders without crashing', () => {\n"
            "  render(Component);\n"
            "});\n",
            encoding="utf-8",
        )

        result = trm.analyze_file(tmp_path, test_file, double_detector_runner=_no_op_runner)

        hits = _findings_by_category(result, "no-assertion")
        assert len(hits) == 1
        assert hits[0]["severity"] == "error"
        assert result["mechanicalFail"] is True
        assert result["skippedQualitative"] is True
        assert result["doublingCheckRan"] is True

    def test_csharp_no_assertion_branch_is_detected(self, tmp_path):
        """Fix 13 — the C# no-assertion branch had no dedicated fixture."""
        test_file = _tests_dir(tmp_path) / "WidgetTests.cs"
        test_file.write_text(
            "public class WidgetTests {\n"
            "    [Test]\n"
            "    public void RendersWithoutCrashing() {\n"
            "        var widget = new Widget();\n"
            "        widget.Render();\n"
            "    }\n"
            "}\n",
            encoding="utf-8",
        )

        result = trm.analyze_file(tmp_path, test_file, double_detector_runner=_no_op_runner)

        hits = _findings_by_category(result, "no-assertion")
        assert len(hits) == 1
        assert result["mechanicalFail"] is True

    def test_java_no_assertion_branch_is_detected(self, tmp_path):
        """Fix 13 — the Java no-assertion branch had no dedicated fixture."""
        test_file = _tests_dir(tmp_path) / "WidgetTest.java"
        test_file.write_text(
            "public class WidgetTest {\n"
            "    @Test\n"
            "    public void rendersWithoutCrashing() {\n"
            "        Widget widget = new Widget();\n"
            "        widget.render();\n"
            "    }\n"
            "}\n",
            encoding="utf-8",
        )

        result = trm.analyze_file(tmp_path, test_file, double_detector_runner=_no_op_runner)

        hits = _findings_by_category(result, "no-assertion")
        assert len(hits) == 1
        assert result["mechanicalFail"] is True

    def test_python_no_assertion_branch_is_detected(self, tmp_path):
        """Fix 13 — the Python no-assertion branch had no dedicated fixture."""
        test_file = _tests_dir(tmp_path) / "test_widget.py"
        test_file.write_text(
            "def test_renders_without_crashing():\n"
            "    widget = Widget()\n"
            "    widget.render()\n",
            encoding="utf-8",
        )

        result = trm.analyze_file(tmp_path, test_file, double_detector_runner=_no_op_runner)

        hits = _findings_by_category(result, "no-assertion")
        assert len(hits) == 1
        assert result["mechanicalFail"] is True


class TestContentSliceRegression:
    """Fix 1 — the highest-priority finding: `_check_no_assertion`/
    `_check_missing_await` must scan the CALLBACK only, never the
    description-string title, and boundary extraction must be
    string/comment-aware so a stray `)`/`{` inside a title/comment/string
    can't early-close or overrun a region."""

    def test_title_containing_should_does_not_mask_a_real_no_assertion_test(self, tmp_path):
        """The core regression: `it('should render', ...)` matches
        `should` in the TITLE under the pre-fix bug, silently suppressing
        the no-assertion finding for a test with zero real assertions."""
        test_file = _tests_dir(tmp_path) / "widget.test.js"
        test_file.write_text(
            "it('should render', () => { render(C); });\n",
            encoding="utf-8",
        )

        result = trm.analyze_file(tmp_path, test_file, double_detector_runner=_no_op_runner)

        hits = _findings_by_category(result, "no-assertion")
        assert len(hits) == 1
        assert result["mechanicalFail"] is True

    def test_title_containing_await_does_not_mask_a_real_missing_await(self, tmp_path):
        test_file = _tests_dir(tmp_path) / "fetcher.test.js"
        test_file.write_text(
            "it('awaits the response', async () => { fetchData(); });\n",
            encoding="utf-8",
        )

        result = trm.analyze_file(tmp_path, test_file, double_detector_runner=_no_op_runner)

        hits = _findings_by_category(result, "missing-await")
        assert len(hits) == 1

    def test_stray_close_paren_in_title_does_not_cause_spurious_no_assertion(self, tmp_path):
        test_file = _tests_dir(tmp_path) / "widget.test.js"
        test_file.write_text(
            "it('handles a lone ) gracefully', () => { expect(x).toBe(1); });\n",
            encoding="utf-8",
        )

        result = trm.analyze_file(tmp_path, test_file, double_detector_runner=_no_op_runner)

        assert _findings_by_category(result, "no-assertion") == []
        assert _findings_by_category(result, "parse-failure") == []

    def test_stray_brace_in_csharp_string_literal_does_not_cause_parse_failure(self, tmp_path):
        test_file = _tests_dir(tmp_path) / "WidgetTests.cs"
        test_file.write_text(
            "public class WidgetTests {\n"
            "    [Test]\n"
            "    public void HandlesBraceInString() {\n"
            "        var s = \"{\";\n"
            "        Assert.AreEqual(\"{\", s);\n"
            "    }\n"
            "}\n",
            encoding="utf-8",
        )

        result = trm.analyze_file(tmp_path, test_file, double_detector_runner=_no_op_runner)

        assert _findings_by_category(result, "parse-failure") == []
        assert _findings_by_category(result, "no-assertion") == []


class TestMissingAwait:
    def test_async_test_body_with_no_await_is_warning_and_does_not_gate(self, tmp_path):
        test_file = _tests_dir(tmp_path) / "fetcher.test.js"
        test_file.write_text(
            "it('fetches data', async () => {\n"
            "  const result = fetchData();\n"
            "  expect(result).toBeDefined();\n"
            "});\n",
            encoding="utf-8",
        )

        result = trm.analyze_file(tmp_path, test_file, double_detector_runner=_no_op_runner)

        hits = _findings_by_category(result, "missing-await")
        assert len(hits) == 1
        assert hits[0]["severity"] == "warning"
        assert result["mechanicalFail"] is False


class TestMockNotReset:
    def test_mock_construct_with_no_reset_call_is_warning(self, tmp_path):
        test_file = _tests_dir(tmp_path) / "callback.test.js"
        test_file.write_text(
            "const mockFn = jest.fn();\n\n"
            "it('calls the callback', () => {\n"
            "  mockFn();\n"
            "  expect(mockFn).toHaveBeenCalled();\n"
            "});\n",
            encoding="utf-8",
        )

        result = trm.analyze_file(tmp_path, test_file, double_detector_runner=_no_op_runner)

        hits = _findings_by_category(result, "mock-not-reset")
        assert len(hits) == 1
        assert hits[0]["severity"] == "warning"
        assert result["mechanicalFail"] is False

    def test_csharp_setup_reinstantiation_suppresses_mock_not_reset(self, tmp_path):
        test_file = _tests_dir(tmp_path) / "WidgetTests.cs"
        test_file.write_text(
            "public class WidgetTests {\n"
            "    private Mock<IGateway> _gateway;\n\n"
            "    [SetUp]\n"
            "    public void Setup() {\n"
            "        _gateway = new Mock<IGateway>();\n"
            "    }\n\n"
            "    [Test]\n"
            "    public void CallsGateway() {\n"
            "        _gateway.Object.Send();\n"
            "        Assert.IsTrue(true);\n"
            "    }\n"
            "}\n",
            encoding="utf-8",
        )

        result = trm.analyze_file(tmp_path, test_file, double_detector_runner=_no_op_runner)

        assert _findings_by_category(result, "mock-not-reset") == []

    def test_java_beforeeach_reinitialization_suppresses_mock_not_reset(self, tmp_path):
        test_file = _tests_dir(tmp_path) / "WidgetTest.java"
        test_file.write_text(
            "public class WidgetTest {\n"
            "    private Gateway gateway;\n\n"
            "    @BeforeEach\n"
            "    public void setup() {\n"
            "        gateway = Mockito.mock(Gateway.class);\n"
            "    }\n\n"
            "    @Test\n"
            "    public void callsGateway() {\n"
            "        gateway.send();\n"
            "        assertTrue(true);\n"
            "    }\n"
            "}\n",
            encoding="utf-8",
        )

        result = trm.analyze_file(tmp_path, test_file, double_detector_runner=_no_op_runner)

        assert _findings_by_category(result, "mock-not-reset") == []

    def test_java_tightened_marker_does_not_accept_unqualified_reset(self, tmp_path):
        """Fix 4's tightened Java marker (`Mockito.reset(` only) — a
        production `reset()` method of the same name must NOT suppress
        the finding."""
        test_file = _tests_dir(tmp_path) / "WidgetTest.java"
        test_file.write_text(
            "public class WidgetTest {\n"
            "    private Gateway gateway = Mockito.mock(Gateway.class);\n\n"
            "    @Test\n"
            "    public void callsGateway() {\n"
            "        state.reset();\n"
            "        gateway.send();\n"
            "        assertTrue(true);\n"
            "    }\n"
            "}\n",
            encoding="utf-8",
        )

        result = trm.analyze_file(tmp_path, test_file, double_detector_runner=_no_op_runner)

        assert len(_findings_by_category(result, "mock-not-reset")) == 1


class TestUnstubbedClockRngTimer:
    def test_unstubbed_new_date_is_warning(self, tmp_path):
        test_file = _tests_dir(tmp_path) / "timestamp.test.js"
        test_file.write_text(
            "it('creates a timestamp', () => {\n"
            "  const now = new Date();\n"
            "  expect(now).toBeTruthy();\n"
            "});\n",
            encoding="utf-8",
        )

        result = trm.analyze_file(tmp_path, test_file, double_detector_runner=_no_op_runner)

        hits = _findings_by_category(result, "unstubbed-clock-rng-timer")
        assert len(hits) == 1
        assert hits[0]["severity"] == "warning"
        assert result["mechanicalFail"] is False

    def test_fake_timers_marker_suppresses_unstubbed_clock_finding(self, tmp_path):
        test_file = _tests_dir(tmp_path) / "timestamp.test.js"
        test_file.write_text(
            "beforeEach(() => { jest.useFakeTimers(); });\n\n"
            "it('creates a timestamp', () => {\n"
            "  const now = Date.now();\n"
            "  expect(now).toBeTruthy();\n"
            "});\n",
            encoding="utf-8",
        )

        result = trm.analyze_file(tmp_path, test_file, double_detector_runner=_no_op_runner)

        assert _findings_by_category(result, "unstubbed-clock-rng-timer") == []


class TestReflectionPrimaryStrategy:
    def test_reflection_alone_is_warning_and_never_gates(self, tmp_path):
        test_file = _tests_dir(tmp_path) / "internals.test.js"
        test_file.write_text(
            "it('accesses private state', () => {\n"
            "  const value = component['_internalState'];\n"
            "  expect(value).toBeDefined();\n"
            "});\n",
            encoding="utf-8",
        )

        result = trm.analyze_file(tmp_path, test_file, double_detector_runner=_no_op_runner)

        hits = _findings_by_category(result, "reflection-primary-strategy")
        assert len(hits) == 1
        assert hits[0]["severity"] == "warning"
        assert result["mechanicalFail"] is False
        assert result["skippedQualitative"] is False


class TestAdditionalTestDeclarationForms:
    """Fix 2 — forms this repo (and common frameworks) use that the
    original regexes silently skipped, leaving the no-assertion gating
    check failing open for tests written this way."""

    def test_js_each_parameterized_form_is_recognized(self, tmp_path):
        test_file = _tests_dir(tmp_path) / "math.test.js"
        test_file.write_text(
            "it.each([[1, 2], [3, 4]])('adds %i and %i', (a, b) => {\n"
            "  addNumbers(a, b);\n"
            "});\n",
            encoding="utf-8",
        )

        result = trm.analyze_file(tmp_path, test_file, double_detector_runner=_no_op_runner)

        assert len(_findings_by_category(result, "no-assertion")) == 1

    def test_csharp_theory_attribute_is_recognized(self, tmp_path):
        test_file = _tests_dir(tmp_path) / "MathTests.cs"
        test_file.write_text(
            "public class MathTests {\n"
            "    [Theory]\n"
            "    public void AddsNumbers(int a, int b) {\n"
            "        AddNumbers(a, b);\n"
            "    }\n"
            "}\n",
            encoding="utf-8",
        )

        result = trm.analyze_file(tmp_path, test_file, double_detector_runner=_no_op_runner)

        assert len(_findings_by_category(result, "no-assertion")) == 1

    def test_csharp_testcase_attribute_is_recognized(self, tmp_path):
        test_file = _tests_dir(tmp_path) / "MathTests.cs"
        test_file.write_text(
            "public class MathTests {\n"
            "    [TestCase(1, 2)]\n"
            "    public void AddsNumbers(int a, int b) {\n"
            "        AddNumbers(a, b);\n"
            "    }\n"
            "}\n",
            encoding="utf-8",
        )

        result = trm.analyze_file(tmp_path, test_file, double_detector_runner=_no_op_runner)

        assert len(_findings_by_category(result, "no-assertion")) == 1

    def test_java_parameterized_test_annotation_is_recognized(self, tmp_path):
        test_file = _tests_dir(tmp_path) / "MathTest.java"
        test_file.write_text(
            "public class MathTest {\n"
            "    @ParameterizedTest\n"
            "    public void addsNumbers(int a, int b) {\n"
            "        addNumbers(a, b);\n"
            "    }\n"
            "}\n",
            encoding="utf-8",
        )

        result = trm.analyze_file(tmp_path, test_file, double_detector_runner=_no_op_runner)

        assert len(_findings_by_category(result, "no-assertion")) == 1

    def test_python_async_def_test_is_recognized(self, tmp_path):
        test_file = _tests_dir(tmp_path) / "test_math.py"
        test_file.write_text(
            "async def test_adds_numbers():\n"
            "    await add_numbers(1, 2)\n",
            encoding="utf-8",
        )

        result = trm.analyze_file(tmp_path, test_file, double_detector_runner=_no_op_runner)

        assert len(_findings_by_category(result, "no-assertion")) == 1


class TestInternalDoubleDetectorTranslation:
    def test_high_verdict_double_translates_to_error_and_gates(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "SmtpGateway.js").write_text("export class SmtpGateway {}\n", encoding="utf-8")

        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        test_file = tests_dir / "smtp_gateway.test.js"
        test_file.write_text(
            "import { SmtpGateway } from '../src/SmtpGateway';\n"
            "jest.mock('../src/SmtpGateway');\n\n"
            "it('sends', () => {\n"
            "  expect(SmtpGateway).toBeDefined();\n"
            "});\n",
            encoding="utf-8",
        )

        result = trm.analyze_file(tmp_path, test_file)

        hits = _findings_by_category(result, "internal-collaborator-doubling")
        assert len(hits) == 1
        assert hits[0]["severity"] == "error"
        assert result["mechanicalFail"] is True
        assert result["skippedQualitative"] is True
        assert result["doublingCheckRan"] is True
        # No no-assertion finding here — mechanicalFail must be attributable
        # to the translated doubling finding alone.
        assert _findings_by_category(result, "no-assertion") == []


class TestDoubleDetectorDisclosure:
    """Fixes 5/6 — a run that never happened (spawn/timeout failure,
    invalid JSON, or the detector's own test/tests-path-segment scoping
    miss) must be reported at `warning`, not `suggestion`, and must set
    `doublingCheckRan: False` rather than reading like a clean pass."""

    def test_runner_oserror_is_warning_severity_and_check_did_not_run(self, tmp_path):
        test_file = _tests_dir(tmp_path) / "widget.test.js"
        test_file.write_text(
            "it('adds', () => { expect(1 + 1).toBe(2); });\n",
            encoding="utf-8",
        )

        def _raising_runner(*_args, **_kwargs):
            raise OSError("no such executable")

        result = trm.analyze_file(tmp_path, test_file, double_detector_runner=_raising_runner)

        hits = _findings_by_category(result, "internal-collaborator-doubling-unavailable")
        assert len(hits) == 1
        assert hits[0]["severity"] == "warning"
        assert result["doublingCheckRan"] is False

    def test_runner_invalid_json_is_warning_severity_and_check_did_not_run(self, tmp_path):
        test_file = _tests_dir(tmp_path) / "widget.test.js"
        test_file.write_text(
            "it('adds', () => { expect(1 + 1).toBe(2); });\n",
            encoding="utf-8",
        )

        def _garbage_runner(*_args, **_kwargs):
            return _StubCompleted("not json", returncode=1, stderr="boom")

        result = trm.analyze_file(tmp_path, test_file, double_detector_runner=_garbage_runner)

        hits = _findings_by_category(result, "internal-collaborator-doubling-unavailable")
        assert len(hits) == 1
        assert hits[0]["severity"] == "warning"
        assert result["doublingCheckRan"] is False

    def test_file_outside_test_dir_segment_is_flagged_out_of_scope(self, tmp_path):
        """A co-located `__tests__/widget.test.js` (no `test`/`tests`
        path segment) is a test file by this repo's own conventions
        (test-file-indicators.md) but is invisible to
        internal_double_detector.py's own `analyze()` scoping."""
        tests_dir = tmp_path / "__tests__"
        tests_dir.mkdir()
        test_file = tests_dir / "widget.test.js"
        test_file.write_text(
            "it('renders', () => { render(C); });\n",
            encoding="utf-8",
        )

        result = trm.analyze_file(tmp_path, test_file, double_detector_runner=_no_op_runner)

        assert len(_findings_by_category(result, "internal-collaborator-doubling-out-of-scope")) == 1
        assert result["doublingCheckRan"] is False
        # The out-of-scope doubling gap doesn't touch the no-assertion gate.
        assert len(_findings_by_category(result, "no-assertion")) == 1
        assert result["mechanicalFail"] is True


class TestCleanFile:
    def test_clean_file_produces_no_findings_and_does_not_gate(self, tmp_path):
        test_file = _tests_dir(tmp_path) / "math.test.js"
        test_file.write_text(
            "it('adds numbers', () => {\n"
            "  const result = add(1, 2);\n"
            "  expect(result).toBe(3);\n"
            "});\n",
            encoding="utf-8",
        )

        result = trm.analyze_file(tmp_path, test_file, double_detector_runner=_no_op_runner)

        assert result["findings"] == []
        assert result["mechanicalFail"] is False
        assert result["skippedQualitative"] is False
        assert result["doublingCheckRan"] is True


class TestParseFailure:
    def test_unparseable_file_produces_parse_failure_and_falls_through(self, tmp_path):
        test_file = _tests_dir(tmp_path) / "binary.test.js"
        test_file.write_bytes(b"\xff\xfe\x00\x01\x02binary-not-utf8\x00\xd8")

        result = trm.analyze_file(tmp_path, test_file, double_detector_runner=_no_op_runner)

        hits = _findings_by_category(result, "parse-failure")
        assert len(hits) == 1
        assert result["mechanicalFail"] is False
        assert result["skippedQualitative"] is False
        assert result["doublingCheckRan"] is False


class TestToleratedDeviationConsolidation:
    def test_exactly_three_artifacts_fires_consolidation(self, tmp_path):
        test_file = _tests_dir(tmp_path) / "legacy.test.js"
        test_file.write_text(
            "it('does the thing', () => {\n"
            "  const result = doThing(); // TODO fix rounding\n"
            "  // FIXME handle negative numbers\n"
            "  // HACK workaround for legacy API\n"
            "  expect(result).toBe(3);\n"
            "});\n",
            encoding="utf-8",
        )

        result = trm.analyze_file(tmp_path, test_file, double_detector_runner=_no_op_runner)

        hits = _findings_by_category(result, "tolerated-deviation-consolidation")
        assert len(hits) == 1
        assert hits[0]["count"] == 3

    def test_exactly_two_artifacts_does_not_fire_consolidation(self, tmp_path):
        test_file = _tests_dir(tmp_path) / "legacy.test.js"
        test_file.write_text(
            "it('does the thing', () => {\n"
            "  const result = doThing(); // TODO fix rounding\n"
            "  // FIXME handle negative numbers\n"
            "  expect(result).toBe(3);\n"
            "});\n",
            encoding="utf-8",
        )

        result = trm.analyze_file(tmp_path, test_file, double_detector_runner=_no_op_runner)

        assert _findings_by_category(result, "tolerated-deviation-consolidation") == []

    def test_ticket_qualified_marker_does_not_count_toward_threshold(self, tmp_path):
        """Fix 8 — a disabled-test/aged-marker/suppressed-warning marker
        with a linked ticket reference on its own or an adjacent line does
        not count toward the >=3 consolidation threshold."""
        test_file = _tests_dir(tmp_path) / "legacy.test.js"
        test_file.write_text(
            "it('does the thing', () => {\n"
            "  const result = doThing(); // TODO(#123): tracked, remove after fix ships\n"
            "  // FIXME handle negative numbers\n"
            "  // HACK workaround for legacy API\n"
            "  expect(result).toBe(3);\n"
            "});\n",
            encoding="utf-8",
        )

        result = trm.analyze_file(tmp_path, test_file, double_detector_runner=_no_op_runner)

        # The TODO(#123) is qualified and excluded; only 2 unqualified
        # markers (FIXME, HACK) remain — below the threshold.
        assert _findings_by_category(result, "tolerated-deviation-consolidation") == []


class TestCLI:
    def test_main_prints_valid_json_result(self, tmp_path, capsys):
        test_file = _tests_dir(tmp_path) / "widget.test.js"
        test_file.write_text(
            "it('adds numbers', () => {\n  expect(1 + 1).toBe(2);\n});\n",
            encoding="utf-8",
        )

        exit_code = trm.main([str(tmp_path), str(test_file)])

        assert exit_code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["file"] == str(test_file)
        assert payload["mechanicalFail"] is False


class TestGatingCategoryDriftGuard:
    """Fix 9 — a mechanical check on the invariant test-review.md's own
    gating language and `_GATING_CATEGORIES` must never silently drift
    apart. Maps each machine category name to a phrase test-review.md
    uses to describe it (the doc has no kebab-case category identifiers
    of its own to grep for directly)."""

    _DOC_GATING_PHRASES: ClassVar[dict[str, str]] = {
        "no-assertion": "Tests with no assertion",
        "internal-collaborator-doubling": "Internal-collaborator doubling",
    }

    def test_gating_categories_match_documented_set(self):
        assert trm._GATING_CATEGORIES == frozenset(self._DOC_GATING_PHRASES)

    def test_each_gating_category_is_still_documented_in_test_review_md(self):
        text = AGENT_MD.read_text(encoding="utf-8")
        for category, phrase in self._DOC_GATING_PHRASES.items():
            assert phrase in text, (
                f"test-review.md no longer documents the gating category "
                f"{category!r} (expected phrase {phrase!r} to appear)"
            )

    def test_test_review_md_references_this_script_by_path(self):
        text = AGENT_MD.read_text(encoding="utf-8")
        assert "scripts/test_review_mechanics.py" in text
