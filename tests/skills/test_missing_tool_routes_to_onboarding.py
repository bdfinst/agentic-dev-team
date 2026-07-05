"""#838 — a missing REQUIRED tool must route users to the onboarding
command (`/project-init`, or `/setup`) as the consistent first stop,
before/alongside any raw install hint.

Content-guard sensor over shipped SKILL.md prose — a pure text grep, no
state-mutating operations. Modeled on
tests/skills/test_build_project_init_gate.py and using the shared
skill_doc_helpers (`PLUGIN_ROOT`, `grep`).

#838 does NOT expand what `/project-init` installs. For tools it does not
install (semgrep, hadolint/trivy/grype, `adr`, `gh`) the pointer surfaces
onboarding as the discoverable entry point while the tool-specific install
command stays as the direct fallback — so the remediation is honest, not a
false claim that onboarding installs that exact tool.

The enforced list is explicit (not auto-discovered from the tree) so it
reads as a reviewable contract: a new tool-dependent skill is added here on
purpose, and the machine-only `--programmatic` output of semgrep-analyze is
deliberately excluded from prose changes.
"""

from __future__ import annotations

import pytest

from skill_doc_helpers import PLUGIN_ROOT, grep

SKILLS = PLUGIN_ROOT / "skills"

# Generic onboarding pointer accepted at most sites.
ONBOARDING = r"/project-init|/setup"

# file (relative to skills/) -> onboarding pattern its missing-tool
# remediation must reference. `setup/SKILL.md` already names `/setup` as
# its own invocation, so its remediation must point at `/project-init`
# specifically (the tooling installer) to count.
ENFORCED = {
    "semgrep-analyze/SKILL.md": ONBOARDING,
    "benchmark/SKILL.md": ONBOARDING,
    "browse/SKILL.md": ONBOARDING,
    "docker-image-audit/SKILL.md": ONBOARDING,
    "performance-benchmark/SKILL.md": ONBOARDING,
    "browser-testing/SKILL.md": ONBOARDING,
    "adr-tools/SKILL.md": ONBOARDING,
    "setup/SKILL.md": r"/project-init",
    "issues-from-assessment/SKILL.md": ONBOARDING,
}


@pytest.mark.parametrize("rel, pattern", sorted(ENFORCED.items()))
def test_missing_tool_remediation_routes_to_onboarding(rel, pattern):
    text = (SKILLS / rel).read_text()
    assert grep(pattern, text), (
        f"{rel}: missing-required-tool remediation does not reference an "
        f"onboarding command (expected /{pattern.replace('/', '')})"
    )


def test_semgrep_programmatic_branch_stays_prose_free():
    """The `--programmatic` path must return only the machine JSON — the
    onboarding pointer lives in the human-facing branch, never in the
    programmatic output contract."""
    text = (SKILLS / "semgrep-analyze" / "SKILL.md").read_text()
    # The JSON skip envelope must not itself carry a slash-command pointer.
    assert not grep(r'"summary":.*(/project-init|/setup)', text), (
        "semgrep-analyze --programmatic JSON summary must stay prose-free"
    )
