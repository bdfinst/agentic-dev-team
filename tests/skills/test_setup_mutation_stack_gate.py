"""#1152 — /setup Step 6 mutation-tool install is strictly stack-gated.

Two layers of contract:

1. Behavioral — the `mutation_stack_sections.py` helper maps a repo's
   `stacks` array to the sections /setup runs. A JS-only signal selects only
   `js` (never a `dotnet` probe); a Python signal selects `python` (mutmut);
   an unrecognized signal (e.g. Ruby) selects nothing and is NOT ambiguous
   (installs/probes nothing); a C#/.NET signal selects `csharp`; polyglot
   selects each matching section; and only an empty/missing signal is
   `ambiguous` (the sole path to the interactive fallback).

2. Doc-shape — the SKILL.md prose calls the helper, each language subsection
   re-asserts its own gate as its literal first step, the interactive
   fallback fires only when `ambiguous`, and the Step 12 summary reports only
   in-scope tools.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from skill_doc_helpers import PLUGIN_ROOT, grep, section

# --- import the helper under test -------------------------------------------

_SCRIPT_DIR = PLUGIN_ROOT / "scripts"
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import mutation_stack_sections as mss  # type: ignore[import-not-found]

_SCRIPT_PY = _SCRIPT_DIR / "mutation_stack_sections.py"
SKILL = PLUGIN_ROOT / "skills" / "setup" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text()


# ---------------------------------------------------------------------------
# select_sections() — the deterministic stack -> section mapping
# ---------------------------------------------------------------------------


def test_js_only_signal_runs_only_js_section() -> None:
    """A JS-only stack selects the JS/TS section and emits no C#/.NET probe."""
    result = mss.select_sections(["typescript", "node"])
    assert result["sections"] == ["js"]
    assert result["ambiguous"] is False
    assert result["note"] is None
    # The dotnet probe belongs to the csharp section — it must not be selected.
    assert "csharp" not in result["sections"]
    assert "java" not in result["sections"]


def test_python_signal_runs_mutmut_section() -> None:
    """A Python stack selects the `python` (mutmut) section and carries no
    unsupported-stack note."""
    result = mss.select_sections(["python"])
    assert result["sections"] == ["python"]
    assert result["ambiguous"] is False
    assert result["note"] is None


def test_unrecognized_signal_installs_nothing_not_ambiguous() -> None:
    """An unrecognized-but-present stack (e.g. Ruby, Elixir) selects nothing,
    is not ambiguous, and carries the one-line note — no fallback, no probes
    (it is a definite signal, just unsupported here)."""
    result = mss.select_sections(["ruby", "elixir"])
    assert result["sections"] == []
    assert result["ambiguous"] is False
    assert result["note"] == "no mutation tooling for detected stack (ruby, elixir)"


def test_csharp_signal_runs_stryker_net_section() -> None:
    result = mss.select_sections(["csharp"])
    assert result["sections"] == ["csharp"]
    assert result["ambiguous"] is False
    assert mss.select_sections(["dotnet"])["sections"] == ["csharp"]


def test_polyglot_signal_runs_each_matching_section() -> None:
    """Polyglot repo runs every matching section, in canonical order."""
    result = mss.select_sections(["csharp", "typescript", "java"])
    assert result["sections"] == ["js", "java", "csharp"]
    assert result["ambiguous"] is False
    assert result["note"] is None


def test_polyglot_signal_including_python_runs_all_sections() -> None:
    """A polyglot repo with Python alongside another supported stack runs
    both sections, in canonical order (`python` last)."""
    result = mss.select_sections(["python", "typescript"])
    assert result["sections"] == ["js", "python"]
    assert result["ambiguous"] is False
    assert result["note"] is None


def test_empty_signal_is_the_only_ambiguous_path() -> None:
    """Empty / missing stacks is the ONLY outcome that authorizes the
    interactive fallback."""
    for signal in ([], None):
        result = mss.select_sections(signal)
        assert result["sections"] == []
        assert result["ambiguous"] is True
        assert result["note"] is None


def test_definite_signals_are_never_ambiguous() -> None:
    """No non-empty stack ever flips ambiguous — the fallback never fires when
    a definite stack was detected."""
    for signal in (["typescript"], ["python"], ["csharp"], ["java"], ["ruby"]):
        assert mss.select_sections(signal)["ambiguous"] is False


def test_tokens_are_case_and_whitespace_insensitive() -> None:
    result = mss.select_sections([" TypeScript ", "Node"])
    assert result["sections"] == ["js"]


def test_node_synonym_alone_maps_to_js() -> None:
    """Isolates the `node` synonym entry — a JS-only signal via `typescript`
    doesn't exercise this specific key/value pair."""
    assert mss.select_sections(["node"])["sections"] == ["js"]


def test_javascript_synonym_alone_maps_to_js() -> None:
    assert mss.select_sections(["javascript"])["sections"] == ["js"]


def test_kotlin_synonym_alone_maps_to_java() -> None:
    assert mss.select_sections(["kotlin"])["sections"] == ["java"]


def test_ambiguous_result_echoes_normalized_stacks() -> None:
    """The ambiguous branch's `stacks` key must echo the (normalized) input,
    not just be present with any value."""
    result = mss.select_sections([])
    assert result["stacks"] == []


def test_definite_result_echoes_normalized_stacks() -> None:
    result = mss.select_sections([" TypeScript ", "Node"])
    assert result["stacks"] == ["typescript", "node"]


# ---------------------------------------------------------------------------
# CLI — reads .claude/project-stack.json, prints one JSON object
# ---------------------------------------------------------------------------


def _run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_SCRIPT_PY), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd is not None else None,
        check=False,
    )


def _collapsed(text: str) -> str:
    """Collapse whitespace runs so argparse's line-wrapped --help output can
    still be matched against an unwrapped expected substring."""
    return " ".join(text.split())


def _write_stack(project_dir: Path, stacks) -> None:
    claude = project_dir / ".claude"
    claude.mkdir(parents=True, exist_ok=True)
    (claude / "project-stack.json").write_text(json.dumps({"stacks": stacks}))


def test_cli_reads_stack_file_js_only(tmp_path: Path) -> None:
    _write_stack(tmp_path, ["typescript", "node"])
    r = _run_cli(".", cwd=tmp_path)
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert out["sections"] == ["js"]
    assert out["ambiguous"] is False


def test_cli_missing_stack_file_is_ambiguous(tmp_path: Path) -> None:
    """No project-stack.json at all -> ambiguous (fallback allowed)."""
    r = _run_cli(".", cwd=tmp_path)
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert out["sections"] == []
    assert out["ambiguous"] is True


def test_cli_python_only_runs_mutmut_section(tmp_path: Path) -> None:
    _write_stack(tmp_path, ["python"])
    r = _run_cli(".", cwd=tmp_path)
    out = json.loads(r.stdout)
    assert out["sections"] == ["python"]
    assert out["ambiguous"] is False
    assert out["note"] is None


def test_cli_unrecognized_stack_note(tmp_path: Path) -> None:
    _write_stack(tmp_path, ["ruby"])
    r = _run_cli(".", cwd=tmp_path)
    out = json.loads(r.stdout)
    assert out["sections"] == []
    assert out["ambiguous"] is False
    assert out["note"] == "no mutation tooling for detected stack (ruby)"


def test_cli_invalid_json_is_ambiguous(tmp_path: Path) -> None:
    claude = tmp_path / ".claude"
    claude.mkdir(parents=True)
    (claude / "project-stack.json").write_text("{ not json")
    r = _run_cli(".", cwd=tmp_path)
    out = json.loads(r.stdout)
    assert out["ambiguous"] is True


def test_cli_stacks_flag_bypasses_file() -> None:
    r = _run_cli("--stacks", "csharp")
    out = json.loads(r.stdout)
    assert out["sections"] == ["csharp"]


def test_cli_stacks_flag_splits_multiple_comma_separated_values() -> None:
    r = _run_cli("--stacks", "csharp,typescript,java")
    out = json.loads(r.stdout)
    assert out["sections"] == ["js", "java", "csharp"]


def test_cli_default_project_dir_is_cwd(tmp_path: Path) -> None:
    """No positional arg -> the `project_dir` default ('.') resolves against
    the current directory, same as passing '.' explicitly."""
    _write_stack(tmp_path, ["typescript"])
    r = _run_cli(cwd=tmp_path)
    out = json.loads(r.stdout)
    assert out["sections"] == ["js"]


def test_cli_help_documents_project_dir_default() -> None:
    """A mutmut string mutation wraps the value in `XX...XX` rather than
    replacing it, so a plain substring check can't distinguish mutated help
    text from real — the original text is still contained inside the
    wrapper. Assert exact equality of the collapsed help text's argument
    line instead."""
    r = _run_cli("--help")
    collapsed = _collapsed(r.stdout)
    assert "Project directory (default: current directory)." in collapsed
    assert "XX" not in collapsed


def test_cli_help_documents_stacks_flag() -> None:
    r = _run_cli("--help")
    collapsed = _collapsed(r.stdout)
    assert (
        "Comma-separated stacks to use directly, bypassing the file (testing)."
        in collapsed
    )
    assert "XX" not in collapsed


# ---------------------------------------------------------------------------
# Doc-shape — SKILL.md wires the helper and gates every section
# ---------------------------------------------------------------------------


def _step6() -> str:
    return section(_text(), r"^### 6\. Install per-language mutation tooling")


def test_step6_calls_the_helper() -> None:
    step6 = _step6()
    assert grep(r"mutation_stack_sections\.py", step6)


def test_step6_fallback_gated_on_ambiguous() -> None:
    """The interactive fallback must be explicitly conditioned on `ambiguous`
    being true — never on a definite stack."""
    step6 = _step6()
    assert grep(r"only when `ambiguous` is `true`", step6, ignore_case=True)


def test_each_section_reasserts_its_gate_first() -> None:
    """Each language subsection's literal first step is a `sections`-membership
    precondition that returns before any probe."""
    js = section(_text(), r"^#### JS/TS", boundary_pattern=r"^#### ")
    java = section(_text(), r"^#### Java / Kotlin", boundary_pattern=r"^#### ")
    csharp = section(_text(), r"^#### C# / .NET", boundary_pattern=r"^#### ")
    python = section(_text(), r"^#### Python", boundary_pattern=r"^#### ")

    for body, key in ((js, "js"), (java, "java"), (csharp, "csharp"), (python, "python")):
        assert grep(r"Stack gate \(first step", body), f"{key} missing gate header"
        assert grep(rf"`{key}` is not in", body), f"{key} gate missing membership check"
        assert grep(r"return immediately", body), f"{key} gate missing early-return"


def test_python_section_installs_mutmut() -> None:
    """The Python subsection installs mutmut via pip, not a global-only tool."""
    python = section(_text(), r"^#### Python", boundary_pattern=r"^#### ")
    assert grep(r"mutmut", python)
    assert grep(r"pip install", python, ignore_case=True)


def test_csharp_gate_precedes_dotnet_probe() -> None:
    """The C#/.NET gate must come before the `command -v dotnet` probe so a
    non-C# repo never probes dotnet."""
    csharp = section(_text(), r"^#### C# / .NET", boundary_pattern=r"^#### ")
    gate_idx = csharp.find("Stack gate")
    probe_idx = csharp.find("command -v dotnet")
    assert gate_idx != -1 and probe_idx != -1
    assert gate_idx < probe_idx


def test_summary_reports_only_in_scope_tools() -> None:
    """The Step 12 summary line must scope the mutation-testing report to the
    sections actually selected, and surface the no-stack note. (The Report
    section embeds a fenced example whose lines break `section()` boundary
    detection, so assert against the full body — these phrases are unique to
    Step 12's guidance.)"""
    body = _text()
    assert grep(r"only for sections actually in scope", body, ignore_case=True)
    assert grep(r"When the helper's `note` was set", body)
