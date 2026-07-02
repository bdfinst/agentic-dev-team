"""ADR 0015 must explicitly scope the hook file-naming convention (issue #732).

`plugins/dev-team/hooks/*.py` and `plugins/security-assessment/hooks/*.sh`
use different file extensions/conventions. ADR 0015 already excludes
`plugins/security-assessment/` from the Python migration in its Non-goals,
but doesn't call out the hook file-naming convention specifically, which
invites a future reader to flag the divergence as an oversight. This guard
requires an explicit, findable sentence tying the two together.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ADR_0015 = REPO_ROOT / "docs" / "adr" / "0015-bash-removal-complete.md"


def test_adr_0015_scopes_hook_naming_convention_to_dev_team_only() -> None:
    text = ADR_0015.read_text(encoding="utf-8")
    assert "file-naming convention" in text, (
        f"{ADR_0015} should explicitly mention the hook file-naming "
        "convention difference between plugins/dev-team (.py) and "
        "plugins/security-assessment (.sh), so it isn't flagged as an "
        "oversight in a future audit."
    )
    assert "security-assessment" in text
