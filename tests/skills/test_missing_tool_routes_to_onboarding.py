"""#838 — a missing REQUIRED tool must route users to the onboarding
command (`/project-init`, or `/setup`) as the consistent first stop,
before/alongside any raw install hint.

Content-guard sensor over shipped SKILL.md prose — a pure text grep, no
state-mutating operations. Modeled on
tests/skills/test_build_project_init_gate.py and using the shared
skill_doc_helpers (`PLUGIN_ROOT`, `grep`).

The #838 follow-up expands what `/project-init` installs: it now installs
the capability tools (semgrep, hadolint/trivy/grype, `adr`, `gh`, plus
Playwright) via its `references/capability-tools.md` registry. The
remediation shape is unchanged — onboarding is the discoverable first stop
and the tool-specific install command stays as the direct fallback — but
the old "onboarding does not install that tool" caveat is now false and
must be gone from every site.

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


# Sites whose remediation used to carry a "project-init does not install this
# tool" caveat — now false, since the #838 follow-up made project-init install
# the capability tools. The caveat must be gone.
_CAVEAT_SITES = (
    "semgrep-analyze/SKILL.md",
    "adr-tools/SKILL.md",
    "docker-image-audit/SKILL.md",
    "static-analysis-integration/SKILL.md",
)


@pytest.mark.parametrize("rel", _CAVEAT_SITES)
def test_no_site_claims_project_init_does_not_install_the_tool(rel):
    text = (SKILLS / rel).read_text()
    assert not grep(r"does\s*\**\s*not\s*\**\s*install", text, ignore_case=True), (
        f"{rel}: still claims project-init does not install the tool — "
        f"the #838 follow-up made project-init install the capability tools"
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
