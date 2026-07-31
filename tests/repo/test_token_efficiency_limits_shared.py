"""The 5000-char / 500-line token-efficiency thresholds were hardcoded
independently in both plugins/dev-team/hooks/token_efficiency_review.py (the
shipped hook) and plugins/dev-team/scripts/token_efficiency_review.py (the
review-agent CI runner). Both must now source the thresholds from one
shared constants module so a future policy change can't update one copy
and miss the other.
"""

from __future__ import annotations

from _repo_root import REPO_ROOT

LIMITS_MODULE = (
    REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib" / "token_efficiency_limits.py"
)
HOOK = REPO_ROOT / "plugins" / "dev-team" / "hooks" / "token_efficiency_review.py"
CI_SCRIPT = REPO_ROOT / "plugins" / "dev-team" / "scripts" / "token_efficiency_review.py"


def test_shared_limits_module_exists_with_expected_values() -> None:
    assert LIMITS_MODULE.is_file(), "expected hooks/lib/token_efficiency_limits.py"
    ns: dict = {}
    exec(  # noqa: S102 - executing the repo's own constants module to read its values
        compile(LIMITS_MODULE.read_text(encoding="utf-8"), str(LIMITS_MODULE), "exec"),
        ns,
    )
    assert ns["CLAUDE_MD_CHAR_LIMIT"] == 5000
    assert ns["FILE_LINE_LIMIT"] == 500


def test_hook_imports_shared_limits_instead_of_hardcoding() -> None:
    src = HOOK.read_text(encoding="utf-8")
    assert "token_efficiency_limits" in src
    assert "> 5000" not in src, "hook still hardcodes the char limit inline"
    assert "> 500" not in src, "hook still hardcodes the line limit inline"


def test_ci_script_imports_shared_limits_instead_of_hardcoding() -> None:
    src = CI_SCRIPT.read_text(encoding="utf-8")
    assert "token_efficiency_limits" in src
    assert "CLAUDE_MD_CHAR_LIMIT: int = 5000" not in src, (
        "plugins/dev-team/scripts/token_efficiency_review.py still hardcodes its own copy of "
        "CLAUDE_MD_CHAR_LIMIT"
    )
    assert "FILE_LINE_LIMIT: int = 500" not in src, (
        "plugins/dev-team/scripts/token_efficiency_review.py still hardcodes its own copy of "
        "FILE_LINE_LIMIT"
    )
