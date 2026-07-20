"""#1236 — /setup only installs missing tools; it checks presence first.

The setup SKILL already guards jq/python3 (Step 3) and the Stryker core
binary (Step 6) with `command -v`/`test -f`. This suite pins the one Step 6
gap that #1236 closed: the JS/TS Stryker *runner plugin* install must be
guarded by its own presence check, independent of the core check, so an
already-installed runner plugin is never reinstalled.
"""

from __future__ import annotations

import re

from skill_doc_helpers import PLUGIN_ROOT, collapsed

SETUP = (PLUGIN_ROOT / "skills" / "setup" / "SKILL.md").read_text(encoding="utf-8")


def test_runner_plugin_install_has_presence_check():
    body = collapsed(SETUP)
    # The probe must target a runner-specific directory (…/<runner>-runner),
    # NOT the core package dir (…/core) that the Step 6 core check already
    # probes — a check that silently degraded to the core dir would defeat the
    # #1236 fix, yet still contain the `@stryker-mutator/` prefix. Require the
    # `-runner` suffix so that regression fails.
    assert re.search(r"test -d node_modules/@stryker-mutator/\w+-runner", body)
    # And the install is explicitly conditioned on that probe reporting missing.
    assert "only if the check above reported `missing`" in body


def test_runner_plugin_check_is_independent_of_core_check():
    body = collapsed(SETUP)
    assert "independently of the core check" in body
