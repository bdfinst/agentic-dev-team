"""Regression test for issue #930: eslint.config.mjs's first-party JS/CJS/MJS
block must not lint dirty `evals/fixtures/**` files.

Those fixtures are intentionally-flawed review-agent eval inputs (the same
role `.ts` dirty fixtures play, already excluded by construction since no
config block matches unlisted `.ts` files) — linting them fails by design, so
the pre-push hook's `chk_eslint` gate was red on `main` itself. The fix scopes
the first-party block's `files: ["**/*.{js,cjs,mjs}"]` with a matching
`ignores: ["evals/fixtures/**"]`, deferring to the "clean fixtures" block for
whichever fixtures actually belong on an allow-list.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# The exact files issue #930 reported as failing on main.
DIRTY_JS_FIXTURES = [
    "evals/fixtures/cr-boundary-omission.js",
    "evals/fixtures/cr-literal-vs-interpolation.js",
    "evals/fixtures/cr-missing-assignment.js",
    "evals/fixtures/cr-missing-guard.js",
]

npx_available = shutil.which("npx") is not None
node_modules_present = (REPO_ROOT / "node_modules").is_dir()
requires_npx = pytest.mark.skipif(
    not (npx_available and node_modules_present),
    reason="npx/node_modules not available — run `npm ci` first",
)


@requires_npx
@pytest.mark.parametrize("fixture", DIRTY_JS_FIXTURES)
def test_dirty_js_fixture_is_not_linted(fixture: str) -> None:
    """A dirty eval fixture must produce zero eslint findings — it should be
    excluded from linting entirely, not merely tolerated."""
    result = subprocess.run(
        ["npx", "--no-install", "eslint", fixture],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"eslint should skip {fixture} entirely (dirty eval fixture), "
        f"but it produced findings:\n{result.stdout}\n{result.stderr}"
    )


@requires_npx
def test_first_party_js_is_still_linted(tmp_path: Path) -> None:
    """The fixture-scoping fix must not blanket-disable first-party linting —
    only evals/fixtures/** is exempted."""
    bad_file = REPO_ROOT / "unused_var_probe.js"
    assert not bad_file.exists(), "probe file collides with a tracked file"
    bad_file.write_text("const unused = 1;\n")
    try:
        result = subprocess.run(
            ["npx", "--no-install", "eslint", bad_file.name],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode != 0, (
            "first-party JS outside evals/fixtures/** must still be linted"
        )
        assert "no-unused-vars" in result.stdout
    finally:
        bad_file.unlink()
