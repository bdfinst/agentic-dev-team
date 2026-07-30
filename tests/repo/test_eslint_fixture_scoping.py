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

from _repo_root import REPO_ROOT

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

# All five tests below spawn their own `npx eslint` subprocess. Measured
# directly (issue #1557): one invocation takes ~18-20s wall-clock alone on
# this machine, but climbs to ~42s when 5 run concurrently — `npx` resolves
# the local binary and node_modules on every call, and that resolution
# contends across concurrently-spawned processes. Under `pytest -n auto`,
# each parametrized case lands on a different xdist worker by default, so
# all 5 were racing for that same resolution work simultaneously, on top of
# whatever else the wider `-n auto` run was doing — enough to occasionally
# exceed the 60s subprocess timeout (observed: 3-5 of 5 timing out). This
# mirrors the file-level xdist_group fix already used in this repo for
# careful-state.json contention (see test_code_intelligence_nudge.py) — force
# all 5 subprocess-spawning tests here onto the SAME worker so they run
# sequentially instead of concurrently, removing the intra-file contention
# that was the dominant multiplier. Requires --dist loadgroup (set in
# scripts/ci-local.sh). The per-call timeout below is doubled to 120s (from
# 60s) as CI-variance margin on top of that fix, not a substitute for it:
# once xdist_group removes the concurrent-resolution multiplier, no single
# invocation should exceed the ~18-20s measured above, so 120s leaves ~6x
# headroom for a slower CI box rather than tolerating the prior contention.
pytestmark = pytest.mark.xdist_group(name="eslint-fixture-scoping-subprocess")


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
        timeout=120,
        check=False,
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
            timeout=120,
            check=False,
        )
        assert result.returncode != 0, (
            "first-party JS outside evals/fixtures/** must still be linted"
        )
        assert "no-unused-vars" in result.stdout
    finally:
        bad_file.unlink()
