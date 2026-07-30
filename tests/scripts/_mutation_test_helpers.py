"""Shared constants for tests/scripts/test_mutation_*.py.

Named with a leading underscore (not ``conftest``) to avoid ambiguity with
pytest's own conftest.py fixture-collection mechanism — this is a plain
importable module, not a pytest plugin. Follows this repo's existing
convention for cross-directory test helpers (``tests/agents/_plugin_dirs.py``,
``tests/bats/_stack_aware_helpers.py``, ``tests/repo/_repo_root.py``).

``SCRIPTS_DIR`` resolves the mutation-testing skill's scripts directory so
each test module can put it on ``sys.path`` before importing the module
under test. ``FORBIDDEN_LITERALS`` is the shared list of repo-specific
literals (ACI project/tooling names) those modules must never leak into
their source — mirrors the list originally defined in
``test_mutation_kill_loop.py`` (issue #1554).
"""

from __future__ import annotations

from pathlib import Path

SCRIPTS_DIR = (
    Path(__file__).resolve().parents[2]
    / "plugins"
    / "dev-team"
    / "skills"
    / "mutation-testing"
    / "scripts"
)

FORBIDDEN_LITERALS = ["Aci.Speedpay", "Controllers", "AwesomeAssertions", "Moq", "AutoFixture"]
