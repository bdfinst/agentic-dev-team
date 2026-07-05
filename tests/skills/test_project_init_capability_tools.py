"""#838 follow-up — /project-init installs the capability tools that other
skills depend on, not just the four static-analysis lanes. The capability
tools (semgrep, Playwright, adr, gh, docker scanners) live in a new
detection-gated lane, and `references/capability-tools.md` is their single
source of truth (tool | skills | offer-when signal | OS-aware install |
verify probe).

Content-guard sensor over shipped SKILL.md + reference prose — a pure text
grep, no state-mutating operations. Models on the sibling project-init
document gates and uses skill_doc_helpers.
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, grep, section

INIT = PLUGIN_ROOT / "skills" / "project-init"
SKILL = INIT / "SKILL.md"
REF = INIT / "references" / "capability-tools.md"


def _skill() -> str:
    return SKILL.read_text()


# --- SKILL.md wires in the capability-tools lane -----------------------------


def test_skill_references_the_capability_tools_reference():
    assert "capability-tools.md" in _skill(), (
        "project-init SKILL.md must point at references/capability-tools.md"
    )


def test_skill_has_a_step_4b_install_capability_tools():
    assert grep(r"^### Step 4b: Install capability tools", _skill()), (
        "project-init must add a '### Step 4b: Install capability tools' step"
    )


def test_description_mentions_the_capability_tools():
    fm = section(_skill(), r"^description:", boundary_pattern=r"^[a-z-]+:")
    fm_lower = (fm or _skill().split("---", 2)[1]).lower()
    for tool in ("semgrep", "playwright", "adr", "gh"):
        assert tool in fm_lower, f"description does not mention capability tool: {tool}"
    assert grep(r"docker", fm_lower, ignore_case=True), (
        "description does not mention the docker scanners"
    )


def test_body_documents_the_playwright_repo_level_exception():
    text = _skill()
    assert grep(r"user/system", text, ignore_case=True), (
        "capability CLIs must be documented as user/system-level tools"
    )
    # Playwright is the explicit repo-level exception to the CLI rule.
    assert grep(r"[Pp]laywright.*repo-level|repo-level.*[Pp]laywright", text), (
        "Playwright must be documented as the repo-level exception"
    )


# --- the reference is the single source of truth -----------------------------


def test_reference_file_exists():
    assert REF.exists(), "references/capability-tools.md must exist"


def _ref() -> str:
    return REF.read_text()


def test_reference_registry_has_the_five_column_shape():
    ref = _ref()
    for header in ("skills", "offer", "install", "verify"):
        assert grep(header, ref, ignore_case=True), (
            f"capability-tools registry missing '{header}' column concept"
        )


def test_reference_names_each_capability_tool_with_install_and_verify():
    ref = _ref()
    # tool -> (install signal, verify probe)
    expected = {
        "semgrep": ("brew install semgrep", "semgrep --version"),
        "playwright": ("@playwright/test", "npx --no-install playwright --version"),
        "adr": ("brew install adr-tools", "adr help"),
        "gh": ("brew install gh", "gh --version"),
        "hadolint": ("brew install hadolint", "hadolint --version"),
        "trivy": ("trivy", "trivy --version"),
        "grype": ("grype", "grype --version"),
    }
    for tool, (install, verify) in expected.items():
        assert grep(tool, ref, ignore_case=True), f"capability tool absent: {tool}"
        assert install in ref, f"{tool}: missing install command '{install}'"
        assert verify in ref, f"{tool}: missing verify probe '{verify}'"


def test_reference_documents_the_linux_pipx_and_user_fallback_for_semgrep():
    ref = _ref()
    assert grep(r"pipx install semgrep", ref)
    assert grep(r"pip install --user semgrep", ref)


def test_reference_lists_the_offer_when_detection_signals():
    ref = _ref()
    for signal in ("Dockerfile", "playwright.config", "docs/adr", "github.com"):
        assert signal in ref, f"missing offer-when detection signal: {signal}"
