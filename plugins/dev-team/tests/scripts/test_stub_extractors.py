"""Unit tests for scripts/lib/stub_extractors/ (issue #1421, plan Step 3.1).

Covers each per-language extractor's normal binding parse, its nested
marker-like-call handling, its lexical string/comment awareness, and its
unbalanced/dangling structural-error case — one behavior group per language,
built and tested in that order (JS/TS, Java, C#, Go) per the Code-First
Small Batches cadence.
"""

from __future__ import annotations

import sys

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "scripts" / "lib"))
sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "scripts"))

import gherkin_stub_merge as gsm
import stub_extractors as se

# ---------------------------------------------------------------------------
# JS/TS
# ---------------------------------------------------------------------------


def test_jsts_normal_binding_is_parsed_with_pattern_and_pending_flag():
    text = (
        "Given('a thing', function () {\n"
        "  return this.pending();\n"
        "});\n"
    )
    result = se.parse_existing_steps(text, ".js")
    assert result.error is None
    assert len(result.bindings) == 1
    binding = result.bindings[0]
    assert binding.pattern == "a thing"
    assert binding.is_pending is True
    assert binding.text == text


def test_jsts_implemented_binding_is_not_pending():
    text = "Given('a thing', function () {\n  assert.equal(1, 1);\n});\n"
    result = se.parse_existing_steps(text, ".js")
    assert result.error is None
    assert result.bindings[0].is_pending is False


def test_jsts_nested_step_invocation_is_not_mistaken_for_a_new_boundary():
    """A step body that itself calls another step programmatically (a
    documented Cucumber pattern) must not fragment the outer binding — the
    nested `Given(`/`When(`/`Then(`-looking text is inside the outer call's
    already-bounded body, so it is data, not a new boundary."""
    text = (
        "Given('an outer thing', function () {\n"
        "  return this.Given('a nested thing');\n"
        "});\n"
        "When('a new thing', function () {\n"
        "  return this.pending();\n"
        "});\n"
    )
    result = se.parse_existing_steps(text, ".js")
    assert result.error is None
    assert [b.pattern for b in result.bindings] == ["an outer thing", "a new thing"]
    assert "this.Given('a nested thing')" in result.bindings[0].text


def test_jsts_brace_inside_a_string_does_not_affect_the_balance_count():
    """A `}` embedded in a string literal inside the callback body must not
    be counted as closing the body early — the exact silent-corruption
    failure mode lexical awareness exists to rule out."""
    text = (
        "Given('a thing', function () {\n"
        "  const s = \"}\";\n"
        "  return this.pending();\n"
        "});\n"
        "When('a second thing', function () {\n"
        "  return this.pending();\n"
        "});\n"
    )
    result = se.parse_existing_steps(text, ".js")
    assert result.error is None
    assert [b.pattern for b in result.bindings] == ["a thing", "a second thing"]
    assert 'const s = "}";' in result.bindings[0].text


def test_jsts_unbalanced_braces_refuses_with_structural_error():
    text = "Given('a thing', function () {\n  return this.pending();\n"  # never closes
    result = se.parse_existing_steps(text, ".js")
    assert result.bindings is None
    assert result.error == se.ERROR_UNBALANCED_BRACES


def test_jsts_destructured_parameter_arrow_callback_span_covers_the_real_body():
    """Regression test (bug 3, CRITICAL): a destructured-parameter arrow
    callback (`async ({ page }) => { ... }`) must not have its span bound
    to the destructure's own `{ page }` brace pair -- the previous "first
    '{' after the pattern" logic landed the binding's end mid-callback,
    misreporting an implemented step as pending and risking a subsequent
    merge splicing a new stub into the middle of this body."""
    text = (
        "Given('a thing', async ({ page }) => {\n"
        "  await page.goto('/');\n"
        "});\n"
    )
    result = se.parse_existing_steps(text, ".js")
    assert result.error is None
    assert len(result.bindings) == 1
    binding = result.bindings[0]
    assert binding.pattern == "a thing"
    # The real callback body -- not the destructure fragment -- was scanned.
    assert "await page.goto('/');" in binding.text
    assert binding.is_pending is False
    # The whole statement, through its closing '});', is captured -- the
    # span does not end mid-callback (e.g. right after "{ page }").
    assert binding.text == text

    # A subsequent merge appends after this binding, not into its middle.
    new_candidate = gsm.StepCandidate(
        pattern="a new thing",
        text="Then('a new thing', function () {\n  return this.pending();\n});\n",
    )
    merge_result = gsm.merge_steps(text, ".js", [new_candidate])
    assert merge_result.error is None
    assert merge_result.text.startswith(text)
    assert "await page.goto('/');" in merge_result.text
    assert merge_result.text.count("await page.goto") == 1


def test_jsts_regex_literal_pattern_is_recorded_not_an_empty_string():
    """Regression test (bug 4): a regex-literal step pattern (a real,
    common cucumber-js convention) must be recorded as its de-slashed text,
    not an empty string -- an empty pattern can never dedup-match on a
    re-run (merge_steps dedups by exact pattern text), so an
    already-implemented regex-pattern step would get a duplicate pending
    stub appended every time (the exact clobber-equivalent bug this module
    exists to prevent, for one pattern syntax)."""
    text = (
        r"Given(/^I have (\d+) cukes$/, function () {"
        "\n  assert.equal(1, 1);\n});\n"
    )
    result = se.parse_existing_steps(text, ".js")
    assert result.error is None
    assert len(result.bindings) == 1
    binding = result.bindings[0]
    assert binding.pattern == r"^I have (\d+) cukes$"
    assert binding.pattern != ""
    assert binding.is_pending is False

    # A re-run with the same regex-literal candidate must be deduped, not
    # appended as a duplicate pending stub.
    candidate = gsm.StepCandidate(
        pattern=r"^I have (\d+) cukes$",
        text=r"Given(/^I have (\d+) cukes$/, function () {" + "\n  return this.pending();\n});\n",
    )
    merge_result = gsm.merge_steps(text, ".js", [candidate])
    assert merge_result.error is None
    assert merge_result.added_patterns == []
    assert merge_result.skipped_duplicate_patterns == [r"^I have (\d+) cukes$"]
    assert merge_result.text == text


def test_jsts_named_function_reference_is_dangling_annotation_not_unbalanced_braces():
    """Regression test (bug 2, CRITICAL): a step bound to a named function
    reference (no inline callback braces) is a syntactically valid file —
    its braces balance fine, there's simply no attached body to bound. This
    must report dangling-annotation (a marker with no attached, boundable
    body), matching go.py's and _common.parse_annotation_style's equivalent
    case — not unbalanced-braces, which wrongly implies the file itself
    needs hand-repair."""
    text = "function stepImpl() {\n  assert.equal(1, 1);\n}\nGiven('x', stepImpl);\n"
    result = se.parse_existing_steps(text, ".js")
    assert result.bindings is None
    assert result.error == se.ERROR_DANGLING_ANNOTATION
    assert result.error != se.ERROR_UNBALANCED_BRACES


# ---------------------------------------------------------------------------
# Java
# ---------------------------------------------------------------------------


def test_java_normal_binding_is_parsed_with_pattern_and_pending_flag():
    text = (
        "public class ASteps {\n"
        '  @Given("a thing")\n'
        "  public void aThing() {\n"
        "    throw new io.cucumber.java.PendingException();\n"
        "  }\n"
        "}\n"
    )
    result = se.parse_existing_steps(text, ".java")
    assert result.error is None
    assert len(result.bindings) == 1
    assert result.bindings[0].pattern == "a thing"
    assert result.bindings[0].is_pending is True


def test_java_nested_annotation_like_text_in_body_is_not_mistaken_for_a_boundary():
    text = (
        "public class ASteps {\n"
        '  @Given("an outer thing")\n'
        "  public void outerThing() {\n"
        '    log.info("@Given(\\"looks like an annotation\\") in a log message");\n'
        "    throw new io.cucumber.java.PendingException();\n"
        "  }\n"
        '  @When("a new thing")\n'
        "  public void aNewThing() {\n"
        "    throw new io.cucumber.java.PendingException();\n"
        "  }\n"
        "}\n"
    )
    result = se.parse_existing_steps(text, ".java")
    assert result.error is None
    assert [b.pattern for b in result.bindings] == ["an outer thing", "a new thing"]


def test_java_brace_inside_a_string_does_not_affect_the_balance_count():
    text = (
        "public class ASteps {\n"
        '  @Given("a thing")\n'
        "  public void aThing() {\n"
        '    String s = "}";\n'
        "    throw new io.cucumber.java.PendingException();\n"
        "  }\n"
        '  @When("a second thing")\n'
        "  public void aSecondThing() {\n"
        "    throw new io.cucumber.java.PendingException();\n"
        "  }\n"
        "}\n"
    )
    result = se.parse_existing_steps(text, ".java")
    assert result.error is None
    assert [b.pattern for b in result.bindings] == ["a thing", "a second thing"]


def test_java_dangling_annotation_with_no_method_refuses_with_structural_error():
    text = 'public class ASteps {\n  @Given("a thing")\n}\n'
    result = se.parse_existing_steps(text, ".java")
    assert result.bindings is None
    assert result.error == se.ERROR_DANGLING_ANNOTATION


# ---------------------------------------------------------------------------
# C#
# ---------------------------------------------------------------------------


def test_csharp_normal_binding_is_parsed_with_pattern_and_pending_flag():
    text = '[Given(@"a thing")]\npublic void GivenAThing()\n{\n    throw new PendingStepException();\n}\n'
    result = se.parse_existing_steps(text, ".cs")
    assert result.error is None
    assert len(result.bindings) == 1
    assert result.bindings[0].pattern == "a thing"
    assert result.bindings[0].is_pending is True


def test_csharp_nested_attribute_like_text_in_body_is_not_mistaken_for_a_boundary():
    text = (
        '[Given(@"an outer thing")]\n'
        "public void OuterThing()\n"
        "{\n"
        '    _logger.Log("[Given(\\"looks like an attribute\\")] in a log message");\n'
        "    throw new PendingStepException();\n"
        "}\n"
        '[When(@"a new thing")]\n'
        "public void ANewThing()\n"
        "{\n"
        "    throw new PendingStepException();\n"
        "}\n"
    )
    result = se.parse_existing_steps(text, ".cs")
    assert result.error is None
    assert [b.pattern for b in result.bindings] == ["an outer thing", "a new thing"]


def test_csharp_brace_inside_a_verbatim_string_does_not_affect_the_balance_count():
    text = (
        '[Given(@"a thing")]\n'
        "public void AThing()\n"
        "{\n"
        '    string s = "}";\n'
        "    throw new PendingStepException();\n"
        "}\n"
        '[When(@"a second thing")]\n'
        "public void ASecondThing()\n"
        "{\n"
        "    throw new PendingStepException();\n"
        "}\n"
    )
    result = se.parse_existing_steps(text, ".cs")
    assert result.error is None
    assert [b.pattern for b in result.bindings] == ["a thing", "a second thing"]


def test_csharp_brace_and_doubled_quote_inside_a_real_verbatim_string_does_not_affect_the_balance_count():
    """Regression test (bug 8): the previous
    test_csharp_brace_inside_a_verbatim_string_does_not_affect_the_balance_count
    doesn't actually exercise skip_verbatim_string -- its only `@"..."` is in
    the attribute pattern, and its brace-in-a-string case uses an ordinary
    quoted string (`"}"`), which goes through the language-agnostic
    skip_quoted path, not the C#-specific verbatim-string lexer with its
    doubled-`""`-is-an-escape rule. This test's body contains a genuine
    verbatim string with both a `}` and a doubled `""` inside it -- the one
    C#-specific branch in _common.py, previously at zero coverage."""
    text = (
        '[Given(@"a thing")]\n'
        "public void AThing()\n"
        "{\n"
        '    string s = @"a}b";\n'
        '    string t = @"say ""hi""";\n'
        "    throw new PendingStepException();\n"
        "}\n"
        '[When(@"a second thing")]\n'
        "public void ASecondThing()\n"
        "{\n"
        "    throw new PendingStepException();\n"
        "}\n"
    )
    result = se.parse_existing_steps(text, ".cs")
    assert result.error is None
    assert [b.pattern for b in result.bindings] == ["a thing", "a second thing"]
    assert 'string s = @"a}b";' in result.bindings[0].text
    assert 'string t = @"say ""hi""";' in result.bindings[0].text


def test_csharp_unbalanced_braces_refuses_with_structural_error():
    text = '[Given(@"a thing")]\npublic void GivenAThing()\n{\n    throw new PendingStepException();\n'
    result = se.parse_existing_steps(text, ".cs")
    assert result.bindings is None
    assert result.error == se.ERROR_UNBALANCED_BRACES


# ---------------------------------------------------------------------------
# Go
# ---------------------------------------------------------------------------


def test_go_normal_binding_is_parsed_with_pattern_and_pending_flag():
    text = (
        "func aThing() error { return godog.ErrPending }\n\n"
        "func InitializeScenario(sc *godog.ScenarioContext) {\n"
        "\tsc.Step(`^a thing$`, aThing)\n"
        "}\n"
    )
    result = se.parse_existing_steps(text, ".go")
    assert result.error is None
    assert len(result.bindings) == 1
    assert result.bindings[0].pattern == "^a thing$"
    assert result.bindings[0].is_pending is True


def test_go_nested_step_like_text_in_function_body_is_not_mistaken_for_a_boundary():
    """A step's implementation function containing a string that mentions
    `sc.Step(` (e.g. a log message) must not be mistaken for a second
    registration — it sits inside the already-bounded referenced function
    body, which this extractor never re-scans for registrations."""
    text = (
        'func aThing() error {\n\tlog.Print("sc.Step(`looks like a registration`)")\n\treturn godog.ErrPending\n}\n\n'
        "func aSecondThing() error { return godog.ErrPending }\n\n"
        "func InitializeScenario(sc *godog.ScenarioContext) {\n"
        "\tsc.Step(`^a thing$`, aThing)\n"
        "\tsc.Step(`^a second thing$`, aSecondThing)\n"
        "}\n"
    )
    result = se.parse_existing_steps(text, ".go")
    assert result.error is None
    assert [b.pattern for b in result.bindings] == ["^a thing$", "^a second thing$"]


def test_go_brace_inside_a_raw_string_pattern_does_not_affect_the_balance_count():
    """A Gherkin regex pattern like `^a payload (.+)$` (parens) or a raw
    string containing `}` must not be miscounted while bounding the call."""
    text = (
        "func aThing() error { return godog.ErrPending }\n\n"
        "func InitializeScenario(sc *godog.ScenarioContext) {\n"
        "\tsc.Step(`^a payload (.+) with \\}$`, aThing)\n"
        "}\n"
    )
    result = se.parse_existing_steps(text, ".go")
    assert result.error is None
    assert result.bindings[0].pattern == r"^a payload (.+) with \}$"


def test_go_dangling_registration_with_no_declared_function_refuses_with_structural_error():
    text = "func InitializeScenario(sc *godog.ScenarioContext) {\n\tsc.Step(`^a thing$`, aThing)\n}\n"
    result = se.parse_existing_steps(text, ".go")
    assert result.bindings is None
    assert result.error == se.ERROR_DANGLING_ANNOTATION


def test_go_many_registrations_resolve_functions_declared_in_reverse_and_mixed_order():
    """Regression test (bug 7): go.py used to re-search the whole file from
    offset 0 for every sc.Step(...) registration's referenced function
    (O(bindings * file size)). The fix builds a one-time {name: position}
    index instead -- confirm each registration still resolves the correct
    function body regardless of declaration order (reverse of reference
    order here), not just "whichever the linear scan happens to hit"."""
    text = (
        "func fifthThing() error { return godog.ErrPending }\n\n"
        "func fourthThing() error { return godog.ErrPending }\n\n"
        "func thirdThing() error { assert.True(true); return nil }\n\n"
        "func secondThing() error { return godog.ErrPending }\n\n"
        "func firstThing() error { return godog.ErrPending }\n\n"
        "func InitializeScenario(sc *godog.ScenarioContext) {\n"
        "\tsc.Step(`^first$`, firstThing)\n"
        "\tsc.Step(`^second$`, secondThing)\n"
        "\tsc.Step(`^third$`, thirdThing)\n"
        "\tsc.Step(`^fourth$`, fourthThing)\n"
        "\tsc.Step(`^fifth$`, fifthThing)\n"
        "}\n"
    )
    result = se.parse_existing_steps(text, ".go")
    assert result.error is None
    assert [b.pattern for b in result.bindings] == [
        "^first$",
        "^second$",
        "^third$",
        "^fourth$",
        "^fifth$",
    ]
    pending_by_pattern = {b.pattern: b.is_pending for b in result.bindings}
    assert pending_by_pattern["^third$"] is False  # the only implemented one
    assert pending_by_pattern["^first$"] is True
    assert pending_by_pattern["^second$"] is True
    assert pending_by_pattern["^fourth$"] is True
    assert pending_by_pattern["^fifth$"] is True
