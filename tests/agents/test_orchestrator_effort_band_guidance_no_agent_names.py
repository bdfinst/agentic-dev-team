"""Drift guard for the "Effort guidance" section of orchestrator.md (#1182).

The guidance section used to carry a per-band list of example agent names
(``low`` — ...(naming-review, complexity-review, ...)). That list drifted out
of sync with agent frontmatter — agents were listed under the wrong band and
new agents were never added — and nothing caught it.

The fix removes the agent-name examples entirely (the three rubric definitions
are the actual decision criteria). This test keeps the section agent-name-free
so the drifting list cannot be reintroduced: if a future edit re-adds an agent
basename under a band, the list can silently disagree with frontmatter again,
so it fails here instead.

The value a given agent's `effort:` frontmatter declares is guarded separately
by ``test_agent_effort_frontmatter.py`` (the frontmatter is the single source
of truth); this test only guards the prose from re-mirroring it.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / "plugins" / "dev-team" / "agents"
ORCH = AGENTS_DIR / "orchestrator.md"

GUIDANCE_HEADING = "### Effort guidance"


def _guidance_section() -> str:
    """Return the body of the Effort-band guidance section.

    From the ``### Effort-band guidance`` heading up to (but not including) the
    next ``##``/``###`` heading. Raises if the section is missing so the guard
    fails loudly rather than vacuously passing on an empty string.
    """
    text = ORCH.read_text(encoding="utf-8")
    start = text.find(GUIDANCE_HEADING)
    assert start != -1, (
        f"'{GUIDANCE_HEADING}' section not found in {ORCH.relative_to(REPO_ROOT)}. "
        "If it was renamed, update GUIDANCE_HEADING here."
    )
    body_start = start + len(GUIDANCE_HEADING)
    next_heading = re.search(r"^#{2,3} ", text[body_start:], re.MULTILINE)
    end = body_start + next_heading.start() if next_heading else len(text)
    return text[body_start:end]


def _agent_basenames() -> list[str]:
    return sorted(p.stem for p in AGENTS_DIR.glob("*.md"))


def test_effort_band_guidance_names_no_agents() -> None:
    section = _guidance_section()
    offenders = [
        name
        for name in _agent_basenames()
        if re.search(rf"\b{re.escape(name)}\b", section)
    ]
    assert not offenders, (
        "The Effort guidance section in orchestrator.md must not name "
        "specific agents — a per-agent list drifts out of sync with frontmatter "
        "(the drift #1182 fixed). Describe the *kind* of work per level instead.\n"
        f"Agent names found in the section: {', '.join(offenders)}"
    )
