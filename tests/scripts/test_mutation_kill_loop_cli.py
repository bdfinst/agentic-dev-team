"""Pytest tests for mutation_kill_loop.py's CLI dispatch and the cross-module
no-repo-specific-literal sweep (#1564 split of ``test_mutation_kill_loop.py``).

The bulk of headless generation / CLI behavior already lives in
``test_mutation_kill_headless.py`` (#1562) — this file covers only the two
tests that remained directly in ``test_mutation_kill_loop.py``: the script's
own ``__main__`` dispatch to ``mutation_kill_headless.main()``, and the
whole-module literal sweep across all three split script files.
"""

from __future__ import annotations

import subprocess
import sys

from _mutation_test_helpers import FORBIDDEN_LITERALS, SCRIPTS_DIR

import _mutation_kill_loop_test_helpers  # noqa: F401 (sys.path side effect)
import mutation_kill_headless  # module-split literal check below
import mutation_kill_insert  # module-split literal check below
import mutation_kill_loop as loop  # noqa: E402


# =============================================================================
# Scenario: `python mutation_kill_loop.py --headless ...` — the real
# subprocess entry point stryker_shard_pipeline.py invokes by filename —
# dispatches to mutation_kill_headless.main() without double-loading this
# module (the sys.modules aliasing in the __main__ guard).
# =============================================================================
def test_script_invocation_dispatches_to_headless_main():
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "mutation_kill_loop.py"), "--file", "Foo.cs"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 1
    assert mutation_kill_headless.NO_GENERATOR_MESSAGE in result.stderr


# =============================================================================
# Scenario: No module in the mutation_kill_loop split carries a repo-specific
# literal (#1562 split into three files — every one is checked).
# =============================================================================
def test_module_source_carries_no_repo_specific_literal():
    for mod, filename in (
        (loop, "mutation_kill_loop.py"),
        (mutation_kill_insert, "mutation_kill_insert.py"),
        (mutation_kill_headless, "mutation_kill_headless.py"),
    ):
        source = (SCRIPTS_DIR / filename).read_text(encoding="utf-8")
        present = [lit for lit in FORBIDDEN_LITERALS if lit in source]
        assert present == [], f"repo-specific literals leaked into {mod.__name__}: {present}"
