"""Unit tests for scripts/measure_tokens.py (Step 2.1 of
plans/test-improve-context-loading-strategy.md, issue #1797).

Covers only what Step 2.1 builds: tokenizer selection (with the fallback
path forced independent of whatever happens to be pip-installed in the
running environment), byte-vs-char parity of the heuristic fallback,
per-file measurement, explicit-path CLI invocation (including a nonexistent
path reported as an error, not a crash), and zero-args auto-discovery
against a temp directory tree mirroring the real glob shape.

``--verify`` mode does not exist yet (Step 2.2) and is not tested here.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT

_SCRIPT = REPO_ROOT / "scripts" / "measure_tokens.py"


def _load():
    spec = importlib.util.spec_from_file_location("measure_tokens", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mt = _load()


def _run_cli(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# detect_tokenizer
# ---------------------------------------------------------------------------


def test_detect_tokenizer_falls_back_to_heuristic_when_tiktoken_unimportable(monkeypatch):
    # Force ImportError regardless of whether tiktoken happens to be
    # pip-installed in this environment — sys.modules[name] = None makes
    # `import tiktoken` raise ImportError deterministically.
    monkeypatch.setitem(sys.modules, "tiktoken", None)

    tokenizer, note = mt.detect_tokenizer()

    assert tokenizer == "heuristic"
    assert "heuristic" in note.lower()


def test_detect_tokenizer_uses_tiktoken_when_importable(monkeypatch):
    import types

    fake_tiktoken = types.ModuleType("tiktoken")
    monkeypatch.setitem(sys.modules, "tiktoken", fake_tiktoken)

    tokenizer, note = mt.detect_tokenizer()

    assert tokenizer == "tiktoken"
    assert "tiktoken" in note.lower()


# ---------------------------------------------------------------------------
# count_tokens — byte-vs-char parity, known byte count
# ---------------------------------------------------------------------------


def test_count_tokens_heuristic_uses_utf8_byte_length_not_char_length(tmp_path):
    # "café" x 50 has non-ASCII content where byte length != char length
    # (each "é" is 2 bytes in UTF-8, 1 char in Python str).
    text = "café " * 50
    f = tmp_path / "nonascii.md"
    f.write_text(text, encoding="utf-8")

    byte_based = len(text.encode("utf-8")) // 4
    char_based = len(text) // 4
    assert byte_based != char_based, "fixture must actually exercise byte/char divergence"

    tokens = mt.count_tokens(f, "heuristic")

    assert tokens == byte_based
    assert tokens != char_based


def test_count_tokens_heuristic_known_byte_count(tmp_path):
    f = tmp_path / "known.md"
    content = "x" * 400  # 400 ASCII bytes
    f.write_text(content, encoding="utf-8")

    assert mt.count_tokens(f, "heuristic") == 100  # 400 / 4


# ---------------------------------------------------------------------------
# Explicit-path CLI invocation
# ---------------------------------------------------------------------------


def test_bare_mode_measures_multiple_explicit_paths(tmp_path):
    f1 = tmp_path / "a.md"
    f1.write_text("a" * 40, encoding="utf-8")
    f2 = tmp_path / "b.md"
    f2.write_text("b" * 80, encoding="utf-8")

    result = _run_cli([str(f1), str(f2)])

    assert result.returncode == 0
    assert str(f1) in result.stdout
    assert str(f2) in result.stdout
    assert "TOTAL" in result.stdout


def test_bare_mode_explicit_nonexistent_path_reports_error_not_crash(tmp_path):
    missing = tmp_path / "does-not-exist.md"

    result = _run_cli([str(missing)])

    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    assert str(missing) in result.stdout or str(missing) in result.stderr


# ---------------------------------------------------------------------------
# discover_budget_targets — zero-args auto-discovery
# ---------------------------------------------------------------------------


def _build_fixture_repo(tmp_path: Path) -> Path:
    """Build a temp directory tree mirroring the real glob shape:
    agents/*.md, skills/*/SKILL.md, knowledge/*.md, plus the two fixed
    files. No prompts/ dir (matching the real repo today).
    """
    plugin_root = tmp_path / "plugins" / "dev-team"

    agents_dir = plugin_root / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "architect.md").write_text("agent a", encoding="utf-8")
    (agents_dir / "orchestrator.md").write_text("agent b", encoding="utf-8")

    skills_dir = plugin_root / "skills"
    (skills_dir / "code-review").mkdir(parents=True)
    (skills_dir / "code-review" / "SKILL.md").write_text("skill a", encoding="utf-8")
    (skills_dir / "build").mkdir(parents=True)
    (skills_dir / "build" / "SKILL.md").write_text("skill b", encoding="utf-8")
    # A non-SKILL.md file under skills/ must not be picked up.
    (skills_dir / "build" / "references.md").write_text("not a skill entry", encoding="utf-8")

    knowledge_dir = plugin_root / "knowledge"
    knowledge_dir.mkdir(parents=True)
    (knowledge_dir / "agent-registry.md").write_text("registry", encoding="utf-8")
    (knowledge_dir / "other-knowledge.md").write_text("other", encoding="utf-8")

    (plugin_root / "CLAUDE.md").write_text("claude md", encoding="utf-8")

    return tmp_path


def test_discover_budget_targets_matches_real_glob_shape(tmp_path):
    fixture_root = _build_fixture_repo(tmp_path)

    targets = mt.discover_budget_targets(fixture_root)

    expected = sorted(
        {
            "plugins/dev-team/CLAUDE.md",
            "plugins/dev-team/knowledge/agent-registry.md",
            "plugins/dev-team/agents/architect.md",
            "plugins/dev-team/agents/orchestrator.md",
            "plugins/dev-team/skills/code-review/SKILL.md",
            "plugins/dev-team/skills/build/SKILL.md",
            "plugins/dev-team/knowledge/other-knowledge.md",
        }
    )

    assert targets == expected
    # The non-SKILL.md sibling file must never appear.
    assert "plugins/dev-team/skills/build/references.md" not in targets


def test_discover_budget_targets_includes_prompts_dir_when_present(tmp_path):
    fixture_root = _build_fixture_repo(tmp_path)
    prompts_dir = fixture_root / "plugins" / "dev-team" / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "reviewer.md").write_text("prompt", encoding="utf-8")

    targets = mt.discover_budget_targets(fixture_root)

    assert "plugins/dev-team/prompts/reviewer.md" in targets


def test_discover_budget_targets_empty_glob_when_prompts_dir_absent(tmp_path):
    fixture_root = _build_fixture_repo(tmp_path)
    assert not (fixture_root / "plugins" / "dev-team" / "prompts").exists()

    targets = mt.discover_budget_targets(fixture_root)

    assert not any("/prompts/" in t for t in targets)


def test_zero_args_cli_measures_repo_default_file_set():
    # Integration smoke test against the real repo (the script always
    # resolves REPO_ROOT from its own on-disk location, so a temp-fixture
    # tree can't be substituted at the CLI level — see discover_budget_targets
    # unit tests above for the exact-set assertions against a fixture tree).
    result = _run_cli([])

    assert result.returncode == 0
    assert "TOTAL" in result.stdout
    assert "plugins/dev-team/CLAUDE.md" in result.stdout
    assert "plugins/dev-team/knowledge/agent-registry.md" in result.stdout
