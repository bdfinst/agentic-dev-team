"""#1779 — `/session-review` must guard its dev-checkout-only dependency
(`scripts/session_extract.py`) instead of letting a downstream install hit a
raw `FileNotFoundError`.

`session_extract.py`/`eval_rawlog.py` are deliberately monorepo-only tooling
that is never shipped inside the plugin (`tests/repo/test_shipped_script_refs.py`'s
`ESCAPE_ALLOWLIST` documents why) — the original bug report proposed packaging
them, which would violate that existing, tested design decision. The actual
fix is a pre-flight guard that reports the real cause clearly instead of a
raw traceback.
"""

from __future__ import annotations

import re

from skill_doc_helpers import PLUGIN_ROOT, collapsed

SESSION_REVIEW = (PLUGIN_ROOT / "skills" / "session-review" / "SKILL.md").read_text(
    encoding="utf-8"
)


def test_pre_flight_guard_checks_for_session_extract_presence():
    body = collapsed(SESSION_REVIEW)
    section = re.search(r"Pre-flight — dev-checkout guard.*?(?=###|\Z)", body, flags=re.DOTALL)
    assert section, "expected a Pre-flight guard section before Step 0/2"
    assert "session_extract.py" in section.group(0)
    assert "eval_rawlog.py" in section.group(0)


def test_frontmatter_allowlists_test_and_echo_for_the_guard():
    frontmatter = SESSION_REVIEW.split("---")[1]
    assert "test *" in frontmatter
    assert "echo *" in frontmatter


def test_frontmatter_allowlists_bash_for_telemetry_sync():
    # Pre-existing gap (not introduced by #1779): Step 1's telemetry-sync.sh
    # calls were never in the Bash allowlist either.
    frontmatter = SESSION_REVIEW.split("---")[1]
    assert "bash *" in frontmatter


def test_pre_flight_guard_states_the_clear_user_facing_message():
    body = collapsed(SESSION_REVIEW)
    section = re.search(r"Pre-flight — dev-checkout guard.*?(?=###|\Z)", body, flags=re.DOTALL)
    assert section
    assert "monorepo dev checkout" in section.group(0)
    assert "not available from an installed plugin cache" in section.group(0)


def test_pre_flight_guard_forbids_a_raw_traceback():
    body = collapsed(SESSION_REVIEW)
    section = re.search(r"Pre-flight — dev-checkout guard.*?(?=###|\Z)", body, flags=re.DOTALL)
    assert section
    assert "FileNotFoundError" in section.group(0)
