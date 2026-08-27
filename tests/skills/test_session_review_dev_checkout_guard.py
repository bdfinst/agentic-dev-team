"""#1779 — `/session-review`'s core dependency used to be dev-checkout-only
(`scripts/session_extract.py`), so a downstream install would hit a raw
`FileNotFoundError`. #2046/#2047 close #1779 at the root instead of guarding
it per-invocation: `session_report.py --profile maintainer` ships inside the
plugin package, so core extraction (Steps 0, 2, 3, 4, 5, 6) runs on every
install, not just this monorepo's own checkout.

What genuinely remains monorepo-only (by design, ADR 0032 Category 2 --
self-referential to this marketplace repo's own cross-machine telemetry
database) is `--cross-machine` sync/rollup (`telemetry-sync.sh`) and the
raw-log semantic tier it gates (`eval_rawlog.py`) -- both already opt-in and
off by default. This file now pins THAT narrower guard, replacing the old
whole-skill dev-checkout guard #1779 originally needed.
"""

from __future__ import annotations

import re

from skill_doc_helpers import PLUGIN_ROOT, collapsed

SESSION_REVIEW = (PLUGIN_ROOT / "skills" / "session-review" / "SKILL.md").read_text(
    encoding="utf-8"
)

_PRE_FLIGHT_HEADING_RE = r"Pre-flight — session_report\.py ships.*?(?=###|\Z)"


def test_pre_flight_section_names_the_shipped_maintainer_profile_entry_point():
    body = collapsed(SESSION_REVIEW)
    section = re.search(_PRE_FLIGHT_HEADING_RE, body, flags=re.DOTALL)
    assert section, "expected a Pre-flight section before Step 0/2"
    assert "session_report.py --profile maintainer" in section.group(0)
    assert "shipped" in section.group(0)


def test_pre_flight_section_scopes_the_remaining_guard_to_cross_machine_and_rawlog():
    body = collapsed(SESSION_REVIEW)
    section = re.search(_PRE_FLIGHT_HEADING_RE, body, flags=re.DOTALL)
    assert section
    assert "--cross-machine" in section.group(0)
    assert "eval_rawlog.py" in section.group(0)
    assert "monorepo dev checkout" in section.group(0)


def test_frontmatter_allowlists_test_and_echo_for_the_guard():
    frontmatter = SESSION_REVIEW.split("---")[1]
    assert "test *" in frontmatter
    assert "echo *" in frontmatter


def test_frontmatter_allowlists_bash_for_telemetry_sync():
    # Pre-existing gap (not introduced by #1779): Step 1's telemetry-sync.sh
    # calls were never in the Bash allowlist either.
    frontmatter = SESSION_REVIEW.split("---")[1]
    assert "bash *" in frontmatter


def test_core_extract_step_uses_the_shipped_session_report_maintainer_profile():
    """Step 2 (Extract) must run session_report.py, not the retired,
    monorepo-only session_extract.py -- the actual #1779 fix."""
    body = collapsed(SESSION_REVIEW)
    assert "session_report.py" in body
    assert "--profile maintainer" in body
    assert "session_extract.py" not in body
