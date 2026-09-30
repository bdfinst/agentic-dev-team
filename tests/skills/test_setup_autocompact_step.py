"""Content test: /setup documents the autocompact step (#2177 slice 2)."""

from __future__ import annotations

import re

from _repo_root import REPO_ROOT

_SKILL = REPO_ROOT / "plugins" / "dev-team" / "skills" / "setup" / "SKILL.md"
_SCRIPT = REPO_ROOT / "plugins" / "dev-team" / "scripts" / "set_autocompact_env.py"


def _text() -> str:
    return _SKILL.read_text(encoding="utf-8")


def _step() -> str:
    match = re.search(r"^### 9b\..*?(?=^### 10\.)", _text(), re.DOTALL | re.MULTILINE)
    assert match, "setup/SKILL.md has no Step 9b before Step 10"
    return match.group(0)


def test_step_invokes_the_writer_script_and_it_exists():
    step = _step()
    assert "scripts/set_autocompact_env.py" in step
    assert _SCRIPT.is_file()


def test_step_forwards_yes_and_documents_flags():
    step = _step()
    assert "--yes" in step
    assert "--autocompact-pct" in step
    assert "--no-autocompact" in step
    assert "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE" in step
    assert "`40`" in step


def test_step_says_merge_not_overwrite_and_lower_only():
    step = _step()
    assert "never overwrite" in step
    assert "can only **lower** its threshold" in " ".join(step.split())


def test_flags_are_in_argument_hint_and_arguments_section():
    text = _text()
    hint = re.search(r"^argument-hint:\s*(.+)$", text, re.MULTILINE)
    assert hint and "--autocompact-pct N" in hint.group(1)
    assert "- `--autocompact-pct N`:" in text
    assert "- `--no-autocompact`:" in text


def test_window_env_var_is_not_used():
    assert "CLAUDE_CODE_AUTO_COMPACT_WINDOW" not in _text()
    assert "CLAUDE_CODE_AUTO_COMPACT_WINDOW" not in _SCRIPT.read_text(encoding="utf-8")
