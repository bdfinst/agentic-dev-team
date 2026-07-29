"""Unit tests for scripts/gherkin_stub_merge.py (issue #1421).

Step 3.1 covers `merge_steps`'s append-only merge core (empty file, all-new,
mixed pending/implemented/new, duplicate-pattern skip). Step 3.2 adds the
CLI, atomic write, and malformed-input error contract.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "scripts"))

import gherkin_stub_merge as gsm

SCRIPT = _REPO_ROOT / "plugins" / "dev-team" / "scripts" / "gherkin_stub_merge.py"

# ---------------------------------------------------------------------------
# merge_steps (Step 3.1)
# ---------------------------------------------------------------------------

_IMPLEMENTED_JS = "Given('a thing', function () {\n  assert.equal(1, 1);\n});\n"
_PENDING_JS = "When('a pending thing', function () {\n  return this.pending();\n});\n"


def _js_candidate(pattern: str) -> gsm.StepCandidate:
    text = f"Then('{pattern}', function () {{\n  return this.pending();\n}});\n"
    return gsm.StepCandidate(pattern=pattern, text=text)


def test_empty_file_all_candidates_become_the_new_file():
    candidates = [_js_candidate("first new thing"), _js_candidate("second new thing")]
    result = gsm.merge_steps("", ".js", candidates)
    assert result.error is None
    assert result.added_patterns == ["first new thing", "second new thing"]
    assert result.skipped_duplicate_patterns == []
    assert "first new thing" in result.text
    assert "second new thing" in result.text


def test_mixed_pending_implemented_and_new_only_appends_the_new_one():
    existing_text = _IMPLEMENTED_JS + _PENDING_JS
    candidates = [
        gsm.StepCandidate(pattern="a thing", text=_js_candidate("a thing").text),
        gsm.StepCandidate(pattern="a pending thing", text=_js_candidate("a pending thing").text),
        _js_candidate("a genuinely new thing"),
    ]
    result = gsm.merge_steps(existing_text, ".js", candidates)
    assert result.error is None
    assert result.added_patterns == ["a genuinely new thing"]
    assert result.skipped_duplicate_patterns == ["a thing", "a pending thing"]
    # The implemented and pending bindings are preserved byte-for-byte.
    assert result.text.startswith(existing_text)
    assert "a genuinely new thing" in result.text


def test_duplicate_pattern_against_existing_is_skipped_not_appended():
    candidates = [gsm.StepCandidate(pattern="a thing", text=_js_candidate("a thing").text)]
    result = gsm.merge_steps(_IMPLEMENTED_JS, ".js", candidates)
    assert result.error is None
    assert result.added_patterns == []
    assert result.skipped_duplicate_patterns == ["a thing"]
    assert result.text == _IMPLEMENTED_JS


def test_two_candidates_sharing_a_pattern_the_second_is_skipped_not_both_appended():
    candidates = [_js_candidate("Duplicate pattern"), _js_candidate("Duplicate pattern")]
    result = gsm.merge_steps("", ".js", candidates)
    assert result.error is None
    assert result.added_patterns == ["Duplicate pattern"]
    assert result.skipped_duplicate_patterns == ["Duplicate pattern"]
    assert result.text.count("Duplicate pattern") == 1


def test_malformed_existing_file_relays_the_structural_error_unchanged():
    malformed = "Given('a thing', function () {\n  return this.pending();\n"  # never closes
    candidates = [_js_candidate("a new thing")]
    result = gsm.merge_steps(malformed, ".js", candidates)
    assert result.error == gsm.ERROR_UNBALANCED_BRACES
    assert result.text == malformed
    assert result.added_patterns == []


def test_new_candidate_is_appended_after_the_last_existing_binding():
    existing_text = _IMPLEMENTED_JS
    candidates = [_js_candidate("a new thing")]
    result = gsm.merge_steps(existing_text, ".js", candidates)
    assert result.error is None
    idx_existing = result.text.index("assert.equal")
    idx_new = result.text.index("a new thing")
    assert idx_existing < idx_new


# ---------------------------------------------------------------------------
# Go's two-part splice (regression test — found via this module's own
# mandated runtime CLI verification, not by pytest: a Go step is split
# across a top-level `func` declaration and a separate `sc.Step(...)`
# registration call; reusing a binding's `text` field as-is silently
# dropped the function declaration, producing a merged file that referenced
# an undeclared function).
# ---------------------------------------------------------------------------

_EXISTING_GO = (
    "func anOrderExists() error { return nil }\n\n"
    "func theOrderIsCancelled() error { return godog.ErrPending }\n\n"
    "func InitializeScenario(sc *godog.ScenarioContext) {\n"
    "\tsc.Step(`^an order exists$`, anOrderExists)\n"
    "\tsc.Step(`^the order is cancelled$`, theOrderIsCancelled)\n"
    "}\n"
)


def _go_candidate_text(func_name: str, pattern: str) -> str:
    return (
        f"func {func_name}() error {{ return godog.ErrPending }}\n"
        "func InitializeScenario(sc *godog.ScenarioContext) {\n"
        f"\tsc.Step(`{pattern}`, {func_name})\n"
        "}\n"
    )


def test_go_appending_a_new_step_to_an_existing_file_keeps_the_function_declaration():
    """The specific regression: appending one genuinely new Go step to a
    file that already registers two steps must not lose the new step's
    `func` declaration — dropping it produces a file that references an
    undeclared function name and fails to compile."""
    candidates_text = (
        _go_candidate_text("anOrderExists", "^an order exists$")
        + _go_candidate_text("theOrderIsCancelled", "^the order is cancelled$")
        + _go_candidate_text("aRefundIsIssued", "^a refund is issued$")
    )
    candidates, error = gsm.parse_candidate_steps(candidates_text, ".go")
    assert error is None

    result = gsm.merge_steps(_EXISTING_GO, ".go", candidates)
    assert result.error is None
    assert result.added_patterns == ["^a refund is issued$"]
    assert result.skipped_duplicate_patterns == [
        "^an order exists$",
        "^the order is cancelled$",
    ]
    # The new step's function declaration must be present, not just its
    # registration call.
    assert "func aRefundIsIssued() error { return godog.ErrPending }" in result.text
    assert "sc.Step(`^a refund is issued$`, aRefundIsIssued)" in result.text
    # The two existing functions and their registrations are untouched.
    assert "func anOrderExists() error { return nil }" in result.text
    assert "func theOrderIsCancelled() error { return godog.ErrPending }" in result.text
    # The new registration lands inside InitializeScenario, before its
    # closing brace — not after it (which would be invalid Go).
    init_start = result.text.index("func InitializeScenario")
    init_close = result.text.index("\n}", init_start)
    new_call_idx = result.text.index("sc.Step(`^a refund is issued$`")
    assert init_start < new_call_idx < init_close
    # The new declaration lands at the top level, alongside the other step
    # functions — not nested inside InitializeScenario's body.
    new_decl_idx = result.text.index("func aRefundIsIssued()")
    assert new_decl_idx < init_start


_EXISTING_GO_ZERO_BINDINGS = "func InitializeScenario(sc *godog.ScenarioContext) {\n}\n"


def test_go_merge_into_existing_file_with_zero_bindings_keeps_the_function_declaration():
    """Regression test (bug 1, CRITICAL): an existing non-empty .go file
    whose InitializeScenario has no sc.Step(...) calls yet used to route
    through _splice_single_point (gated on `bool(result.bindings)`, which is
    False here), which only ever concatenates a candidate's registration
    call text — silently dropping the new candidate's func declaration and
    producing a file that references an undeclared function."""
    candidates_text = _go_candidate_text("aRefundIsIssued", "^a refund is issued$")
    candidates, error = gsm.parse_candidate_steps(candidates_text, ".go")
    assert error is None

    result = gsm.merge_steps(_EXISTING_GO_ZERO_BINDINGS, ".go", candidates)
    assert result.error is None
    assert result.added_patterns == ["^a refund is issued$"]
    # Both the new step's function declaration and its registration call
    # must be present — not just the registration.
    assert "func aRefundIsIssued() error { return godog.ErrPending }" in result.text
    assert "sc.Step(`^a refund is issued$`, aRefundIsIssued)" in result.text
    # The registration call lands inside InitializeScenario's body, not
    # outside it as an invalid top-level statement.
    init_start = result.text.index("func InitializeScenario")
    init_close = result.text.index("\n}", init_start)
    new_call_idx = result.text.index("sc.Step(`^a refund is issued$`")
    assert init_start < new_call_idx < init_close
    # The new declaration lands at the top level, not nested inside
    # InitializeScenario's body.
    new_decl_idx = result.text.index("func aRefundIsIssued()")
    assert new_decl_idx < init_start


def test_go_appending_a_new_step_does_not_duplicate_or_corrupt_existing_registrations():
    candidates_text = _go_candidate_text("aRefundIsIssued", "^a refund is issued$")
    candidates, error = gsm.parse_candidate_steps(candidates_text, ".go")
    assert error is None

    result = gsm.merge_steps(_EXISTING_GO, ".go", candidates)
    assert result.error is None
    assert result.text.count("sc.Step(`^an order exists$`, anOrderExists)") == 1
    assert result.text.count("sc.Step(`^the order is cancelled$`, theOrderIsCancelled)") == 1
    assert result.text.count("sc.Step(`^a refund is issued$`, aRefundIsIssued)") == 1


# ---------------------------------------------------------------------------
# parse_candidate_steps (Step 3.1 helper, exercised standalone)
# ---------------------------------------------------------------------------


def test_parse_candidate_steps_well_formed_text_reports_no_error():
    candidates, error = gsm.parse_candidate_steps(_js_candidate("New one").text, ".js")
    assert error is None
    assert [c.pattern for c in candidates] == ["New one"]


def test_parse_candidate_steps_malformed_text_reports_error_not_silent_empty():
    """Regression test (mirrors gherkin_feature_merge's identical fix): a
    malformed --candidates fragment must report the same structural error
    parse_existing_steps would, not silently collapse to an empty list."""
    malformed = "Given('a thing', function () {\n  return this.pending();\n"
    candidates, error = gsm.parse_candidate_steps(malformed, ".js")
    assert candidates == []
    assert error == gsm.ERROR_UNBALANCED_BRACES


# ---------------------------------------------------------------------------
# CLI (Step 3.2)
# ---------------------------------------------------------------------------


def _run_cli(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, check=False
    )


def test_cli_merge_creates_a_brand_new_file_with_all_pending_stubs(tmp_path):
    """Slice 3's headline scenario: no existing file, 3 newly-derived steps
    become 3 pending stubs in a freshly-created file."""
    target = tmp_path / "steps" / "a_steps.js"
    candidates = tmp_path / "candidates.txt"
    candidates.write_text(
        _js_candidate("first thing").text
        + _js_candidate("second thing").text
        + _js_candidate("third thing").text,
        encoding="utf-8",
    )

    proc = _run_cli(
        "merge", "--existing", str(target), "--candidates", str(candidates), "--ext", ".js", "--json"
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["written"] is True
    assert payload["added_patterns"] == ["first thing", "second thing", "third thing"]
    written = target.read_text(encoding="utf-8")
    assert written.count("this.pending()") == 3


def test_cli_merge_writes_file_and_reports_added_patterns(tmp_path):
    existing = tmp_path / "a_steps.js"
    existing.write_text(_IMPLEMENTED_JS, encoding="utf-8")
    candidates = tmp_path / "candidates.txt"
    candidates.write_text(_js_candidate("a new thing").text, encoding="utf-8")

    proc = _run_cli(
        "merge",
        "--existing",
        str(existing),
        "--candidates",
        str(candidates),
        "--ext",
        ".js",
        "--json",
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["added_patterns"] == ["a new thing"]
    assert "a new thing" in existing.read_text(encoding="utf-8")
    assert "assert.equal" in existing.read_text(encoding="utf-8")


def test_cli_merge_dry_run_never_touches_filesystem(tmp_path):
    existing = tmp_path / "a_steps.js"
    existing.write_text(_IMPLEMENTED_JS, encoding="utf-8")
    before_mtime = existing.stat().st_mtime
    candidates = tmp_path / "candidates.txt"
    candidates.write_text(_js_candidate("a new thing").text, encoding="utf-8")

    proc = _run_cli(
        "merge",
        "--existing",
        str(existing),
        "--candidates",
        str(candidates),
        "--ext",
        ".js",
        "--dry-run",
    )
    assert proc.returncode == 0
    assert existing.stat().st_mtime == before_mtime
    assert existing.read_text(encoding="utf-8") == _IMPLEMENTED_JS


def test_cli_merge_malformed_candidates_exits_2_and_leaves_file_unchanged(tmp_path):
    existing = tmp_path / "a_steps.js"
    existing.write_text(_IMPLEMENTED_JS, encoding="utf-8")
    before = existing.read_text(encoding="utf-8")
    candidates = tmp_path / "candidates.txt"
    candidates.write_text("Given('unterminated', function () {\n  return this.pending();\n", encoding="utf-8")

    proc = _run_cli(
        "merge", "--existing", str(existing), "--candidates", str(candidates), "--ext", ".js"
    )
    assert proc.returncode == 2
    assert existing.read_text(encoding="utf-8") == before
    assert "malformed" in proc.stderr.lower()


@pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason="NTFS rejects raw control-byte filenames; POSIX-only fixture",
)
def test_cli_merge_malformed_candidates_strips_control_characters_from_candidates_path(tmp_path):
    """Security regression (issue #1529): --candidates is composed by
    gherkin-derive from a probe of the target repository, the same
    untrusted-path class as --existing in the sibling gherkin_feature_merge.py
    — a crafted path must not bypass the CWE-150 terminal-escape guard
    applied there."""
    existing = tmp_path / "a_steps.js"
    existing.write_text(_IMPLEMENTED_JS, encoding="utf-8")
    hostile_dir = tmp_path / "cand\x1b[31m"
    hostile_dir.mkdir()
    candidates = hostile_dir / "candidates.txt"
    candidates.write_text("Given('unterminated', function () {\n  return this.pending();\n", encoding="utf-8")

    proc = _run_cli(
        "merge", "--existing", str(existing), "--candidates", str(candidates), "--ext", ".js"
    )
    assert proc.returncode == 2
    assert "\x1b" not in proc.stderr
    assert "malformed" in proc.stderr.lower()


@pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason="NTFS rejects raw control-byte filenames; POSIX-only fixture",
)
def test_cli_merge_missing_candidates_file_strips_control_characters_from_candidates_path(
    tmp_path,
):
    """Security regression (issue #1529): the unreadable-candidates error
    branch (a distinct _safe_for_terminal call site from the malformed-
    candidates branch above) must sanitize --candidates the same way."""
    existing = tmp_path / "a_steps.js"
    existing.write_text(_IMPLEMENTED_JS, encoding="utf-8")
    hostile_dir = tmp_path / "cand\x1b[31m"
    hostile_dir.mkdir()

    proc = _run_cli(
        "merge",
        "--existing",
        str(existing),
        "--candidates",
        str(hostile_dir / "does_not_exist.txt"),
        "--ext",
        ".js",
    )
    assert proc.returncode == 2
    assert "\x1b" not in proc.stderr
    assert "could not be read" in proc.stderr


def test_cli_merge_malformed_candidates_json_error_is_distinct_from_existing_structural_error(
    tmp_path,
):
    existing = tmp_path / "a_steps.js"
    existing.write_text(_IMPLEMENTED_JS, encoding="utf-8")
    candidates = tmp_path / "candidates.txt"
    candidates.write_text("Given('unterminated', function () {\n  return this.pending();\n", encoding="utf-8")

    proc = _run_cli(
        "merge",
        "--existing",
        str(existing),
        "--candidates",
        str(candidates),
        "--ext",
        ".js",
        "--json",
    )
    assert proc.returncode == 2
    payload = json.loads(proc.stdout)
    assert payload["error"] == gsm.ERROR_MALFORMED_CANDIDATES
    assert payload["error"] != gsm.ERROR_UNBALANCED_BRACES


def test_cli_merge_missing_candidates_file_exits_2_with_json_sentinel_not_a_traceback(tmp_path):
    """Regression test (bug 6): a --candidates path that doesn't exist must
    report the unreadable-candidates sentinel through the same --json exit-2
    contract every other structural problem uses, not escape as a raw
    Python traceback."""
    existing = tmp_path / "a_steps.js"
    existing.write_text(_IMPLEMENTED_JS, encoding="utf-8")

    proc = _run_cli(
        "merge",
        "--existing",
        str(existing),
        "--candidates",
        str(tmp_path / "does_not_exist.txt"),
        "--ext",
        ".js",
        "--json",
    )
    assert proc.returncode == 2
    assert "Traceback" not in proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["written"] is False
    assert payload["error"] == gsm.ERROR_UNREADABLE_CANDIDATES
    assert existing.read_text(encoding="utf-8") == _IMPLEMENTED_JS


def test_cli_merge_missing_candidates_file_non_json_reports_error_not_a_traceback(tmp_path):
    existing = tmp_path / "a_steps.js"
    existing.write_text(_IMPLEMENTED_JS, encoding="utf-8")

    proc = _run_cli(
        "merge",
        "--existing",
        str(existing),
        "--candidates",
        str(tmp_path / "does_not_exist.txt"),
        "--ext",
        ".js",
    )
    assert proc.returncode == 2
    assert "Traceback" not in proc.stderr
    assert "could not be read" in proc.stderr
    assert existing.read_text(encoding="utf-8") == _IMPLEMENTED_JS


def test_cli_merge_unsupported_extension_exits_2_with_json_sentinel_not_a_traceback(tmp_path):
    """Regression test (bug 6): an --ext naming no known step-definition
    language (argparse has no choices= for it) must report the
    unsupported-extension sentinel, not escape parse_existing_steps's
    ValueError as a raw traceback."""
    existing = tmp_path / "a_steps.rb"
    existing.write_text("Given('a thing') { assert true }\n", encoding="utf-8")
    candidates = tmp_path / "candidates.txt"
    candidates.write_text("Given('a new thing') { assert true }\n", encoding="utf-8")

    proc = _run_cli(
        "merge",
        "--existing",
        str(existing),
        "--candidates",
        str(candidates),
        "--ext",
        ".rb",
        "--json",
    )
    assert proc.returncode == 2
    assert "Traceback" not in proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["written"] is False
    assert payload["error"] == gsm.ERROR_UNSUPPORTED_EXTENSION


def test_cli_merge_unsupported_extension_non_json_reports_error_not_a_traceback(tmp_path):
    existing = tmp_path / "a_steps.rb"
    existing.write_text("Given('a thing') { assert true }\n", encoding="utf-8")
    candidates = tmp_path / "candidates.txt"
    candidates.write_text("Given('a new thing') { assert true }\n", encoding="utf-8")

    proc = _run_cli(
        "merge", "--existing", str(existing), "--candidates", str(candidates), "--ext", ".rb"
    )
    assert proc.returncode == 2
    assert "Traceback" not in proc.stderr
    assert "not a supported" in proc.stderr


def test_cli_merge_malformed_existing_file_exits_2_and_leaves_file_unchanged(tmp_path):
    existing = tmp_path / "a_steps.js"
    malformed = "Given('a thing', function () {\n  return this.pending();\n"  # never closes
    existing.write_text(malformed, encoding="utf-8")
    candidates = tmp_path / "candidates.txt"
    candidates.write_text(_js_candidate("a new thing").text, encoding="utf-8")

    proc = _run_cli(
        "merge", "--existing", str(existing), "--candidates", str(candidates), "--ext", ".js"
    )
    assert proc.returncode == 2
    assert existing.read_text(encoding="utf-8") == malformed
    assert "structure could not be parsed" in proc.stderr
    assert f"error={gsm.ERROR_UNBALANCED_BRACES}" in proc.stderr


@pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason="NTFS rejects raw control-byte filenames; POSIX-only fixture",
)
def test_cli_merge_malformed_existing_file_strips_control_characters_from_existing_path(
    tmp_path,
):
    """Security regression (issue #1529): --existing is composed by
    gherkin-derive from a probe of the target repository — the structural-
    error branch's _safe_for_terminal call must sanitize it the same way
    the sibling gherkin_feature_merge.py does."""
    hostile_dir = tmp_path / "exist\x1b[31m"
    hostile_dir.mkdir()
    existing = hostile_dir / "a_steps.js"
    malformed = "Given('a thing', function () {\n  return this.pending();\n"  # never closes
    existing.write_text(malformed, encoding="utf-8")
    candidates = tmp_path / "candidates.txt"
    candidates.write_text(_js_candidate("a new thing").text, encoding="utf-8")

    proc = _run_cli(
        "merge", "--existing", str(existing), "--candidates", str(candidates), "--ext", ".js"
    )
    assert proc.returncode == 2
    assert "\x1b" not in proc.stderr
    assert "structure could not be parsed" in proc.stderr


@pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason="NTFS rejects raw control-byte filenames; POSIX-only fixture",
)
def test_cli_merge_writes_file_strips_control_characters_from_existing_path_in_text_output(
    tmp_path,
):
    """Security regression (issue #1529): the merge-success branch's
    _safe_for_terminal call is a separate call site from the structural-
    error branch above — each needs its own hostile-input coverage."""
    hostile_dir = tmp_path / "exist\x1b[31m"
    hostile_dir.mkdir()
    existing = hostile_dir / "a_steps.js"
    existing.write_text(_IMPLEMENTED_JS, encoding="utf-8")
    candidates = tmp_path / "candidates.txt"
    candidates.write_text(_js_candidate("a new thing").text, encoding="utf-8")

    proc = _run_cli(
        "merge", "--existing", str(existing), "--candidates", str(candidates), "--ext", ".js"
    )
    assert proc.returncode == 0, proc.stderr
    assert "\x1b" not in proc.stdout
    assert "OK: merged" in proc.stdout


def test_cli_merge_dangling_annotation_java_exits_2_and_leaves_file_unchanged(tmp_path):
    """The Slice 3 headline structural-error scenario: a dangling @Given
    annotation with no matching method body refuses the write."""
    existing = tmp_path / "ASteps.java"
    malformed = 'public class ASteps {\n  @Given("a thing")\n}\n'
    existing.write_text(malformed, encoding="utf-8")
    candidates = tmp_path / "candidates.txt"
    candidates.write_text(
        'public class ASteps {\n  @When("a new thing")\n  public void aNewThing() {\n'
        "    throw new io.cucumber.java.PendingException();\n  }\n}\n",
        encoding="utf-8",
    )

    proc = _run_cli(
        "merge", "--existing", str(existing), "--candidates", str(candidates), "--ext", ".java", "--json"
    )
    assert proc.returncode == 2
    payload = json.loads(proc.stdout)
    assert payload["error"] == gsm.ERROR_DANGLING_ANNOTATION
    assert existing.read_text(encoding="utf-8") == malformed


def test_cli_merge_rejects_existing_path_containing_dotdot(tmp_path):
    """Regression test (security-review, mirrors gherkin_feature_merge's
    identical guard): --existing is composed from untrusted, target-repo-
    derived content per gherkin-derive/SKILL.md Step 4, so a '..' path
    component must be rejected rather than followed."""
    candidates = tmp_path / "candidates.txt"
    candidates.write_text(_js_candidate("New one").text, encoding="utf-8")

    proc = _run_cli(
        "merge",
        "--existing",
        str(tmp_path / ".." / "escaped_steps.js"),
        "--candidates",
        str(candidates),
        "--ext",
        ".js",
    )
    assert proc.returncode == 2
    assert "'..'" in proc.stderr
    assert not (tmp_path.parent / "escaped_steps.js").exists()


def test_cli_merge_rejects_existing_path_containing_dotdot_json(tmp_path):
    candidates = tmp_path / "candidates.txt"
    candidates.write_text(_js_candidate("New one").text, encoding="utf-8")

    proc = _run_cli(
        "merge",
        "--existing",
        str(tmp_path / ".." / "escaped_steps.js"),
        "--candidates",
        str(candidates),
        "--ext",
        ".js",
        "--json",
    )
    assert proc.returncode == 2
    payload = json.loads(proc.stdout)
    assert payload["written"] is False
    assert payload["error"] == gsm.ERROR_UNSAFE_PATH
    assert not (tmp_path.parent / "escaped_steps.js").exists()


# ---------------------------------------------------------------------------
# _write_atomic — crash-safety (mirrors gherkin_feature_merge's identical tests)
# ---------------------------------------------------------------------------


def test_write_atomic_leaves_no_temp_file_on_success(tmp_path):
    target = tmp_path / "a_steps.js"
    gsm._write_atomic(target, "written content")
    assert target.read_text(encoding="utf-8") == "written content"
    assert list(tmp_path.iterdir()) == [target]


def test_write_atomic_leaves_original_untouched_on_replace_failure(tmp_path, monkeypatch):
    target = tmp_path / "a_steps.js"
    target.write_text("original content", encoding="utf-8")

    def _boom(*_args, **_kwargs):
        raise OSError("simulated crash mid-write")

    monkeypatch.setattr(gsm.os, "replace", _boom)

    with pytest.raises(OSError):
        gsm._write_atomic(target, "new content")

    assert target.read_text(encoding="utf-8") == "original content"
    assert list(tmp_path.iterdir()) == [target]
