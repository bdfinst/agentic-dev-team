"""Unit tests for scripts/gherkin_stub_gate.py (issue #1391).

Covers the bdd-runner completion gate: per-language pending-marker detection,
directory scanning, and the main() CLI's exit-code contract.
"""

from __future__ import annotations

import json
import sys

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


def test_detects_csharp_pending_marker(tmp_path):
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


def test_main_exits_zero_on_missing_dir_no_files_to_scan(tmp_path):
    # An absent directory has nothing pending — the caller decides whether
    # "no step-definitions directory" is itself an error condition.
    assert gherkin_stub_gate.main(["--dir", str(tmp_path / "nope")]) == 0


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


def test_unrecognized_extension_is_never_scanned_for_markers(tmp_path):
    f = tmp_path / "notes.txt"
    f.write_text("this.pending() mentioned in prose, not code\n")
    assert gherkin_stub_gate.find_step_definition_files([tmp_path]) == []
