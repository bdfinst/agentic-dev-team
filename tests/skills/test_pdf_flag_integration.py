"""Content-guard: the `--pdf` flag is wired into every report-producing skill (#1114).

The `--pdf` behavior is skill-markdown (prompt) rather than code, so it is
verified the way the repo verifies other cross-skill contracts — by asserting
the required strings appear in each SKILL.md and in the shared contract doc.

Contracts:

1. Each of the five report-producing skills documents `--pdf` in its
   `argument-hint` and references the shared `report-pdf-integration.md`.
2. Each skill invokes the shared render module (`hooks/lib/report_pdf.py`) via
   `hooks/py.sh`, not a bare `python3`.
3. The shared contract doc pins the two distinct empty-result wordings (no-op
   vs. skip), the stderr-under-`--json` rule, and the per-skill report paths.
4. `/code-review` states the `--json`/`--internal` no-op explicitly.
"""

from __future__ import annotations

from _repo_root import REPO_ROOT

SKILLS = REPO_ROOT / "plugins" / "dev-team" / "skills"
KNOWLEDGE = REPO_ROOT / "plugins" / "dev-team" / "knowledge"

FIVE_SKILLS = [
    "code-review",
    "test-health",
    "cd-test-architecture",
    "triage",
    "harness-audit",
]


def _skill(name: str) -> str:
    return (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")


def _argument_hint(text: str) -> str:
    """Return the argument-hint value, joining folded (`>-`) continuation lines."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not line.startswith("argument-hint:"):
            continue
        value = line.split(":", 1)[1].strip()
        if value not in (">-", ">", "|", "|-"):
            return value
        # folded scalar: gather following more-indented lines
        collected = []
        for cont in lines[i + 1 :]:
            if cont.strip() and not cont.startswith((" ", "\t")):
                break
            collected.append(cont.strip())
        return " ".join(collected)
    return ""


INTEGRATION_DOC = (KNOWLEDGE / "report-pdf-integration.md").read_text(encoding="utf-8")


def test_shared_contract_doc_exists_and_pins_wording():
    # two distinct empty-result cases, kept lexically separate
    assert "no report file was written this run" in INTEGRATION_DOC  # no-op
    assert "No PDF engine found" in INTEGRATION_DOC  # skip
    # stdout stays pure JSON — status to stderr under --json
    assert "stderr" in INTEGRATION_DOC
    # per-skill paths are enumerated so a new skill inherits by adding a row
    for path_frag in (
        "DEV_TEAM_REPORTS/code-review.md",
        "DEV_TEAM_REPORTS/triage/<slug>.md",
        "reports/test-health-<date>.md",
        "reports/cd-test-architecture-<app>.md",
        "reports/harness-audit-<date>.md",
    ):
        assert path_frag in INTEGRATION_DOC


def test_every_skill_documents_pdf_flag_in_argument_hint():
    for name in FIVE_SKILLS:
        hint = _argument_hint(_skill(name))
        assert hint, f"{name} has no argument-hint"
        assert "--pdf" in hint, f"{name} argument-hint omits --pdf"


def test_every_skill_references_shared_doc_and_module():
    for name in FIVE_SKILLS:
        text = _skill(name)
        assert "report-pdf-integration.md" in text, f"{name} does not reference the shared doc"
        assert "hooks/lib/report_pdf.py" in text, f"{name} does not invoke the render module"
        assert 'hooks/py.sh"' in text, f"{name} must route through py.sh, not bare python3"


def test_code_review_states_json_internal_no_op():
    text = _skill("code-review")
    assert "--json" in text and "--internal" in text
    assert "no report file was written" in text
    # the no-op status is routed to stderr under --json
    assert "stderr" in text


def test_cd_test_architecture_states_chatonly_no_op():
    text = _skill("cd-test-architecture")
    assert "chat-only" in text or "chat for a single component" in text
    assert "no report file was written this run" in text


def test_harness_audit_resolves_against_output_override():
    text = _skill("harness-audit")
    # --pdf must render the actual path written (the --output override, else default).
    # Match a specific contract phrase, not the over-common word "actual".
    assert "--output" in text
    assert "`--output` override" in text
