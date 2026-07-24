"""#813 — shipped documentation matches the code-first default.

After the cadence switch, no shipped doc may present RED-GREEN-REFACTOR as
the unconditional default: every shipped markdown file that names the TDD
cycle must also carry the code-first-default / opt-in framing, and the core
docs state the default explicitly, citing the recommendations synthesis.
"""

from __future__ import annotations

import re
import subprocess
import sys

from _repo_root import REPO_ROOT

PLUGIN_ROOT = REPO_ROOT / "plugins" / "dev-team"

_RGR_RE = re.compile(r"RED[-\s]*(?:→|->)?[-\s]*GREEN[-\s]*(?:→|->)?[-\s]*REFACTOR")
_FRAMING_RE = re.compile(r"code-first|Code-First|opt-in", re.IGNORECASE)

_BANNED_UNCONDITIONAL_CLAIMS = (
    "Every step must be TDD",
    "must follow RED-GREEN-REFACTOR for every unit",
    "All code follows **RED-GREEN-REFACTOR**",
    "Implement with TDD (RED-GREEN-REFACTOR)",
    "invoke for every unit of work: RED-GREEN-REFACTOR",
)


def _shipped_markdown() -> list:
    tracked = subprocess.run(
        ["git", "ls-files", "plugins/dev-team"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    return [REPO_ROOT / rel for rel in tracked if rel.endswith(".md")]


def test_every_shipped_cycle_mention_carries_the_code_first_framing() -> None:
    offenders = []
    for path in _shipped_markdown():
        content = path.read_text(encoding="utf-8")
        if _RGR_RE.search(content) and not _FRAMING_RE.search(content):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == [], (
        "shipped files naming RED-GREEN-REFACTOR without the code-first "
        f"default / opt-in framing: {offenders}"
    )


def test_no_shipped_doc_makes_an_unconditional_tdd_default_claim() -> None:
    offenders = []
    for path in _shipped_markdown():
        content = path.read_text(encoding="utf-8")
        for claim in _BANNED_UNCONDITIONAL_CLAIMS:
            if claim in content:
                offenders.append(
                    f"{path.relative_to(REPO_ROOT)}: {claim!r}"
                )
    assert offenders == [], (
        "unconditional-TDD-default claims remain in shipped docs:\n"
        + "\n".join(offenders)
    )


def test_plugin_claude_md_names_the_code_first_default_citing_recommendations() -> None:
    claude_md = (PLUGIN_ROOT / "CLAUDE.md").read_text()
    flat = re.sub(r"\s+", " ", claude_md)
    assert "Code-First Small Batches" in claude_md
    assert "docs/experiments/RECOMMENDATIONS.md" in claude_md
    assert re.search(r"sole build cadence", flat, re.IGNORECASE)


def test_orchestrator_fast_path_uses_the_resolved_cadence() -> None:
    orchestrator = (PLUGIN_ROOT / "agents" / "orchestrator.md").read_text()
    start = orchestrator.index("### No-plan fast path")
    end = orchestrator.index("### Demonstration of saving")
    section = re.sub(r"\s+", " ", orchestrator[start:end])
    assert re.search(r"code-first", section, re.IGNORECASE)
    assert re.search(r"sole build cadence", section, re.IGNORECASE)


def test_request_processing_flow_states_the_default_cadence() -> None:
    flow = (PLUGIN_ROOT / "knowledge" / "request-processing-flow.md").read_text()
    assert "Code-First Small Batches" in flow
    assert "docs/experiments/RECOMMENDATIONS.md" in flow


def test_knowledge_index_is_current_after_the_sweep() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(PLUGIN_ROOT / "hooks" / "lib" / "build_knowledge_index.py"),
            "--check",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
