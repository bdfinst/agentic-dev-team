"""Unit tests for scripts/gherkin_stub_gate.py (issue #1391).

Covers the bdd-runner completion gate: per-language pending-marker detection,
directory scanning, and the main() CLI's exit-code contract.
"""

from __future__ import annotations

import json
import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "scripts"))

import gherkin_stub_gate

# ---------------------------------------------------------------------------
# find_step_definition_files
# ---------------------------------------------------------------------------


def test_finds_files_by_known_extension(tmp_path):
    steps = tmp_path / "step_definitions"
    steps.mkdir()
    (steps / "a_steps.js").write_text("")
    (steps / "b_steps.go").write_text("")
    (steps / "README.md").write_text("")  # unrecognized extension — skipped
    found = gherkin_stub_gate.find_step_definition_files([steps])
    assert {p.name for p in found} == {"a_steps.js", "b_steps.go"}


def test_scans_recursively(tmp_path):
    nested = tmp_path / "features" / "step_definitions" / "sub"
    nested.mkdir(parents=True)
    (nested / "deep_steps.java").write_text("")
    found = gherkin_stub_gate.find_step_definition_files([tmp_path])
    assert len(found) == 1
    assert found[0].name == "deep_steps.java"


def test_missing_directory_yields_nothing(tmp_path):
    assert gherkin_stub_gate.find_step_definition_files([tmp_path / "nope"]) == []


def test_multiple_directories_are_all_scanned(tmp_path):
    d1, d2 = tmp_path / "d1", tmp_path / "d2"
    d1.mkdir()
    d2.mkdir()
    (d1 / "a_steps.cs").write_text("")
    (d2 / "b_steps.go").write_text("")
    found = gherkin_stub_gate.find_step_definition_files([d1, d2])
    assert {p.name for p in found} == {"a_steps.cs", "b_steps.go"}


# ---------------------------------------------------------------------------
# find_pending_stubs — per-language marker detection
# ---------------------------------------------------------------------------


def test_detects_js_pending_marker(tmp_path):
    f = tmp_path / "a_steps.js"
    f.write_text("Given('a thing', function () {\n  return this.pending();\n});\n")
    pending = gherkin_stub_gate.find_pending_stubs([f])
    assert len(pending) == 1
    assert pending[0]["language"] == "JS/TS"
    assert pending[0]["line"] == 2


def test_detects_java_pending_marker(tmp_path):
    f = tmp_path / "ASteps.java"
    f.write_text(
        "public class ASteps {\n"
        "  @Given(\"a thing\")\n"
        "  public void aThing() {\n"
        "    throw new io.cucumber.java.PendingException();\n"
        "  }\n"
        "}\n"
    )
    pending = gherkin_stub_gate.find_pending_stubs([f])
    assert len(pending) == 1
    assert pending[0]["language"] == "Java"
    assert pending[0]["line"] == 4


def test_detects_csharp_current_pending_marker(tmp_path):
    f = tmp_path / "ASteps.cs"
    f.write_text(
        "[Given(@\"a thing\")]\n"
        "public void GivenAThing()\n"
        "{\n"
        "    throw new PendingStepException();\n"
        "}\n"
    )
    pending = gherkin_stub_gate.find_pending_stubs([f])
    assert len(pending) == 1
    assert pending[0]["language"] == "C#"
    assert pending[0]["line"] == 4


def test_detects_csharp_deprecated_pending_marker(tmp_path):
    # StepIsPending() is deprecated since Reqnroll 3.3.4 (bdd-frameworks.md)
    # but still recognized — an older or not-yet-regenerated stub must not
    # be a false negative.
    f = tmp_path / "ASteps.cs"
    f.write_text(
        "[Given(@\"a thing\")]\n"
        "public void GivenAThing()\n"
        "{\n"
        "    _scenarioContext.StepIsPending();\n"
        "}\n"
    )
    pending = gherkin_stub_gate.find_pending_stubs([f])
    assert len(pending) == 1
    assert pending[0]["language"] == "C#"
    assert pending[0]["line"] == 4


def test_detects_go_pending_marker(tmp_path):
    f = tmp_path / "a_steps.go"
    f.write_text(
        "func aThing() error {\n"
        "\treturn godog.ErrPending\n"
        "}\n"
    )
    pending = gherkin_stub_gate.find_pending_stubs([f])
    assert len(pending) == 1
    assert pending[0]["language"] == "Go"
    assert pending[0]["line"] == 2


def test_filled_in_step_definition_has_no_pending_marker(tmp_path):
    f = tmp_path / "a_steps.js"
    f.write_text("Given('a thing', function () {\n  assert.equal(1, 1);\n});\n")
    assert gherkin_stub_gate.find_pending_stubs([f]) == []


def test_multiple_pending_markers_in_one_file_all_reported(tmp_path):
    f = tmp_path / "a_steps.go"
    f.write_text(
        "func stepOne() error { return godog.ErrPending }\n"
        "func stepTwo() error { return godog.ErrPending }\n"
    )
    pending = gherkin_stub_gate.find_pending_stubs([f])
    assert len(pending) == 2
    assert [p["line"] for p in pending] == [1, 2]


# ---------------------------------------------------------------------------
# main() CLI contract
# ---------------------------------------------------------------------------


def test_main_exits_zero_when_clean(tmp_path):
    steps = tmp_path / "steps"
    steps.mkdir()
    (steps / "a_steps.js").write_text("Given('x', function () { assert.ok(true); });\n")
    assert gherkin_stub_gate.main(["--dir", str(steps)]) == 0


def test_main_exits_one_and_names_offenders(tmp_path, capsys):
    steps = tmp_path / "steps"
    steps.mkdir()
    (steps / "a_steps.js").write_text("Given('x', function () { return this.pending(); });\n")
    rc = gherkin_stub_gate.main(["--dir", str(steps)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "a_steps.js" in out
    assert "1" in out


def test_main_does_not_silently_pass_on_missing_dir_no_files_to_scan(tmp_path, capsys):
    """Regression test (correctness-review, arch-review): a nonexistent
    --dir used to report exit 0 — an affirmative "clean" for zero evidence.
    Mirrors the identical fix in gherkin_failure_path_gate.py: --dir is
    composed by gherkin-derive from a probe of the target repo, not always
    typed by a human, so a gate that scanned nothing must say so distinctly
    rather than silently pass."""
    rc = gherkin_stub_gate.main(["--dir", str(tmp_path / "nope")])
    assert rc == 2
    out = capsys.readouterr().out
    assert "OK" not in out
    assert "no step-definition files found" in out


def test_main_json_warns_on_missing_dir(tmp_path, capsys):
    rc = gherkin_stub_gate.main(["--dir", str(tmp_path / "nope"), "--json"])
    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["scanned"] == []
    assert payload["pending"] == []
    assert "no step-definition files found" in payload["warning"]


def test_main_json_output_is_parseable(tmp_path, capsys):
    steps = tmp_path / "steps"
    steps.mkdir()
    (steps / "a_steps.cs").write_text("public void X() { _ctx.StepIsPending(); }\n")
    rc = gherkin_stub_gate.main(["--dir", str(steps), "--json"])
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert rc == 1
    assert len(parsed["pending"]) == 1
    assert parsed["pending"][0]["language"] == "C#"


def test_main_accepts_multiple_dir_flags(tmp_path):
    d1, d2 = tmp_path / "d1", tmp_path / "d2"
    d1.mkdir()
    d2.mkdir()
    (d1 / "a_steps.js").write_text("assert.ok(true);\n")
    (d2 / "b_steps.js").write_text("return this.pending();\n")
    rc = gherkin_stub_gate.main(["--dir", str(d1), "--dir", str(d2)])
    assert rc == 1


@pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason="NTFS rejects raw control-byte filenames; POSIX-only fixture",
)
def test_main_strips_control_characters_from_file_path_in_text_output(tmp_path, capsys):
    """Security regression (issue #1526 review, extended to this gate): the
    scanned step-definition file's path is drawn from the same untrusted
    repository as its pending-marker text, and must get the same CWE-150
    terminal-escape guard — a crafted filename must not bypass it."""
    hostile_name = "orders\x1b[31m_steps.js"
    (tmp_path / hostile_name).write_text("return this.pending();\n")
    exit_code = gherkin_stub_gate.main(["--dir", str(tmp_path)])
    assert exit_code == 1
    out = capsys.readouterr().out
    assert "\x1b" not in out


def test_main_strips_control_characters_from_pending_marker_text_in_text_output(tmp_path, capsys):
    """Security regression (issue #1526 review round 3): the pending-marker
    line itself (`entry['text']`) is a separate `_safe_for_terminal` call
    site from the file-path guard above — untrusted step-definition source
    content, the same threat class. Reverting just this wrap would leave the
    suite green even though the file-path test still passes."""
    steps = tmp_path / "steps"
    steps.mkdir()
    (steps / "a_steps.js").write_text("return this.pending(); \x1b[31m\n")
    exit_code = gherkin_stub_gate.main(["--dir", str(steps)])
    assert exit_code == 1
    out = capsys.readouterr().out
    assert "\x1b" not in out
    assert "this.pending()" in out


def test_main_strips_control_characters_from_dirs_display_when_dir_is_missing(tmp_path, capsys):
    """--dir is composed by gherkin-derive from a probe of the target repo,
    not always typed by a human — the WARN branch's dirs_display needs the
    same guard as a scanned file's path, since it's the same untrusted-path
    class."""
    hostile_dir = tmp_path / "nope\x1b[31m"
    exit_code = gherkin_stub_gate.main(["--dir", str(hostile_dir)])
    assert exit_code == 2
    out = capsys.readouterr().out
    assert "\x1b" not in out
    assert "no step-definition files found" in out


def test_unrecognized_extension_is_never_scanned_for_markers(tmp_path):
    f = tmp_path / "notes.txt"
    f.write_text("this.pending() mentioned in prose, not code\n")
    assert gherkin_stub_gate.find_step_definition_files([tmp_path]) == []


# ---------------------------------------------------------------------------
# Case-insensitive extension matching (regression: uppercase extensions were
# previously invisible to the scan, silently reporting a false "0 pending")
# ---------------------------------------------------------------------------


def test_uppercase_extension_is_still_discovered(tmp_path):
    f = tmp_path / "Steps.JS"
    f.write_text("return this.pending();\n")
    found = gherkin_stub_gate.find_step_definition_files([tmp_path])
    assert found == [f]


def test_uppercase_extension_pending_marker_is_detected(tmp_path):
    f = tmp_path / "ASteps.CS"
    f.write_text("throw new PendingStepException();\n")
    pending = gherkin_stub_gate.find_pending_stubs(
        gherkin_stub_gate.find_step_definition_files([f.parent])
    )
    assert len(pending) == 1
    assert pending[0]["language"] == "C#"


def test_mixed_case_extension_via_main_reports_pending(tmp_path):
    steps = tmp_path / "steps"
    steps.mkdir()
    (steps / "a_steps.Go").write_text("return godog.ErrPending\n")
    assert gherkin_stub_gate.main(["--dir", str(steps)]) == 1


# ---------------------------------------------------------------------------
# Vendored-directory pruning
# ---------------------------------------------------------------------------


def test_node_modules_subtree_is_not_scanned(tmp_path):
    vendored = tmp_path / "node_modules" / "some-dep"
    vendored.mkdir(parents=True)
    (vendored / "steps.js").write_text("return this.pending();\n")
    (tmp_path / "a_steps.js").write_text("assert.ok(true);\n")
    found = gherkin_stub_gate.find_step_definition_files([tmp_path])
    assert found == [tmp_path / "a_steps.js"]


def test_git_directory_is_not_scanned(tmp_path):
    git_dir = tmp_path / ".git" / "objects"
    git_dir.mkdir(parents=True)
    (git_dir / "fake_steps.go").write_text("return godog.ErrPending\n")
    found = gherkin_stub_gate.find_step_definition_files([tmp_path])
    assert found == []


def test_vendored_pruning_means_main_reports_clean(tmp_path):
    steps = tmp_path / "steps"
    vendored = steps / "vendor" / "dep"
    vendored.mkdir(parents=True)
    (vendored / "steps.go").write_text("return godog.ErrPending\n")
    (steps / "a_steps.go").write_text("func x() error { return nil }\n")
    assert gherkin_stub_gate.main(["--dir", str(steps)]) == 0
