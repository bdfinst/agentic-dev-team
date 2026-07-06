"""Guard: the /v1/models model probe is fully removed. Availability now comes
from the effort ladder, not a network probe. This fails loudly if the probe
script, its tests, the curl shim, or any reference to them returns.

Ported from tests/hooks/no_probe_refs_tests.bats (issue #676).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Step 4.1 — the probe files are gone
# ---------------------------------------------------------------------------


def test_model_probe_sh_no_longer_exists() -> None:
    assert not (
        REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib" / "model-probe.sh"
    ).exists()


def test_model_probe_tests_bats_no_longer_exists() -> None:
    assert not (REPO_ROOT / "tests" / "hooks" / "model_probe_tests.bats").exists()


def test_init_dev_team_probe_tests_bats_no_longer_exists() -> None:
    assert not (
        REPO_ROOT / "tests" / "commands" / "init_dev_team_probe_tests.bats"
    ).exists()


def test_the_fake_curl_shim_no_longer_exists() -> None:
    assert not (REPO_ROOT / "tests" / "hooks" / "fake-bin" / "curl").exists()


# ---------------------------------------------------------------------------
# Step 4.2 — init flows no longer reference the probe
# ---------------------------------------------------------------------------


def test_setup_skill_md_does_not_reference_the_model_probe() -> None:
    skill = REPO_ROOT / "plugins" / "dev-team" / "skills" / "setup" / "SKILL.md"
    text = skill.read_text()
    assert not re.search(r"model-probe|/v1/models", text)


def test_setup_prereqs_linux_sh_does_not_reference_the_model_probe() -> None:
    script = REPO_ROOT / "setup-prereqs-linux.sh"
    text = script.read_text()
    assert not re.search(r"model-probe|/v1/models|SKIP_PROBE", text)
