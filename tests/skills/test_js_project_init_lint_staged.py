"""#250 — js-project-init must scaffold lint-staged with a pre-commit
auto-fix hook and simplify the pre-push hook to the test suite only.
Documentation gate over the skill prose and its config templates.

Ported from tests/skills/js_project_init_lint_staged_tests.bats (issue #674).
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, grep, section

SKILL = PLUGIN_ROOT / "skills" / "js-project-init" / "SKILL.md"
CFG = PLUGIN_ROOT / "skills" / "js-project-init" / "references" / "configs.md"


def test_package_json_template_declares_a_lint_staged_block_with_per_extension_fix_commands():
    text = SKILL.read_text()
    assert '"lint-staged"' in text
    assert '"*.{js,mjs,cjs}": ["prettier --write", "oxlint --fix"]' in text
    assert '"*.{json,md,yaml,yml}": ["prettier --write"]' in text


def test_lint_staged_is_added_to_the_dev_dependency_install():
    assert grep(r"npm install -D .*lint-staged", SKILL.read_text())


def test_pre_commit_hook_runs_lint_staged():
    assert "echo 'npx lint-staged' > .husky/pre-commit" in SKILL.read_text()


def test_pre_push_hook_runs_npm_test():
    assert "echo 'npm test' > .husky/pre-push" in SKILL.read_text()


def test_frontend_pre_push_retains_the_e2e_suite():
    assert "npm run test:e2e" in SKILL.read_text()


def test_step_8_summary_lists_both_git_hooks():
    text = SKILL.read_text()
    assert grep(r"pre-commit.*lint-staged", text, ignore_case=True)
    assert grep(r"pre-push.*test", text, ignore_case=True)


def test_configs_md_pre_commit_template_contains_npx_lint_staged():
    assert "npx lint-staged" in CFG.read_text()


def test_configs_md_pre_push_template_contains_npm_test_and_no_lint_format_check():
    # Extract the '## .husky/pre-push' section up to the next level-2
    # heading.
    s = section(
        CFG.read_text(),
        r"^## \.husky/pre-push",
        boundary_pattern=r"^## ",
        include_start_line=False,
    )
    assert "npm test" in s
    assert "format:check" not in s
    assert not grep(r"\bnpm run lint\b", s)
