"""Issue #836 — --json is contractually non-interactive.

Step 6's non-interactive exception hard-gated only on the caller (/build, /pr),
so a direct --json run could block on the AskUserQuestion prompt. Add --json
(and --yes) to the exception, defaulting to report-only (non-destructive CI
default).
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, section

CODE_REVIEW = (
    PLUGIN_ROOT / "skills" / "code-review" / "SKILL.md"
).read_text(encoding="utf-8")


def _step6() -> str:
    # From the step-6 header up to the next `### ` header (step 6a).
    return section(CODE_REVIEW, r"^### 6\. Present findings", boundary_pattern=r"^### ")


def test_step6_names_json_in_noninteractive_exception():
    step6 = _step6()
    assert "--json" in step6, (
        "step 6 non-interactive exception must contractually name --json"
    )


def test_step6_json_defaults_to_report_only():
    step6 = _step6()
    assert "report only" in step6.lower(), (
        "--json/--yes must default to report only (non-destructive)"
    )
