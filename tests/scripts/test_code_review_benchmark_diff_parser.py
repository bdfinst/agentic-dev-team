"""Unit tests for the #821 benchmark harness's unified-diff hunk parser.

Asserted against the REAL Defects4J patch fetched this session
(`framework/projects/Lang/patches/1.src.patch`, LANG-747) — per the issue's
explicit instruction not to guess the parser against an assumed format.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HARNESS_DIR = Path(__file__).resolve().parents[2] / "evals" / "code-review-benchmark"
if str(_HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(_HARNESS_DIR))

from adapters.common import unified_diff_hunks  # noqa: E402

_FIXTURES = _HARNESS_DIR / "fixtures"


def test_parses_real_defects4j_patch() -> None:
    diff_text = (_FIXTURES / "lang-1.src.patch").read_text(encoding="utf-8")
    hunks = unified_diff_hunks(diff_text)

    assert len(hunks) == 1
    hunk = hunks[0]
    assert hunk.file == "src/main/java/org/apache/commons/lang3/math/NumberUtils.java"
    # @@ -464,20 +464,11 @@ -> old range 464..483, new range 464..474
    assert hunk.old_start == 464
    assert hunk.old_end == 483
    assert hunk.new_start == 464
    assert hunk.new_end == 474


def test_multiple_files_and_hunks() -> None:
    diff_text = """diff --git a/src/a.js b/src/a.js
--- a/src/a.js
+++ b/src/a.js
@@ -1,3 +1,3 @@
-old
+new
@@ -20,2 +20,2 @@
-old2
+new2
diff --git a/src/b.js b/src/b.js
--- a/src/b.js
+++ b/src/b.js
@@ -5 +5 @@
-x
+y
"""
    hunks = unified_diff_hunks(diff_text)
    assert [h.file for h in hunks] == ["src/a.js", "src/a.js", "src/b.js"]
    assert (hunks[0].old_start, hunks[0].old_end) == (1, 3)
    assert (hunks[1].old_start, hunks[1].old_end) == (20, 21)
    # No trailing ",count" means a single-line hunk.
    assert (hunks[2].old_start, hunks[2].old_end) == (5, 5)


def test_skips_dev_null_targets() -> None:
    diff_text = """diff --git a/deleted.js b/deleted.js
--- a/deleted.js
+++ /dev/null
@@ -1,2 +0,0 @@
-gone
-gone2
"""
    assert unified_diff_hunks(diff_text) == []


def test_empty_diff_returns_no_hunks() -> None:
    assert unified_diff_hunks("") == []
