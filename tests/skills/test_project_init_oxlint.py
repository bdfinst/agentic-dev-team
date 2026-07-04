"""#808 — project-init's greenfield JS scaffold installs oxlint as the
default linter: the
devDependency install includes oxlint, the `lint`/`lint:fix` npm scripts run
oxlint, lint-staged auto-fixes with oxlint, and ESLint stays one script away
behind `lint:deep` for plugin-only rules. Documentation gate over the skill
prose.
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, grep

SKILL = PLUGIN_ROOT / "skills" / "project-init" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text()


def test_dev_dependency_install_includes_oxlint():
    assert grep(r"npm install -D .*oxlint", _text())


def test_lint_script_runs_oxlint():
    assert '"lint": "oxlint' in _text()


def test_lint_fix_script_runs_oxlint_fix():
    assert '"lint:fix": "oxlint --fix' in _text()


def test_lint_deep_script_keeps_eslint_available():
    assert '"lint:deep": "eslint' in _text()


def test_eslint_is_not_the_day_to_day_lint_script():
    text = _text()
    assert '"lint": "eslint' not in text
    assert '"lint:fix": "eslint' not in text


def test_defaults_summary_names_oxlint_fast_and_eslint_deep():
    text = _text()
    assert grep(r"^- \*\*Linter\*\*:.*oxlint", text, ignore_case=True)
    assert grep(r"oxlint.*fast", text, ignore_case=True)
    assert grep(r"eslint.*(deep|lint:deep)", text, ignore_case=True)
