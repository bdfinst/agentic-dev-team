"""review_verdicts.py — per-lens review verdict store (#2166).

Step 2.1 scope: this module currently holds only `SCOPE_MARKER_PREFIX`, the
literal text prefix `skills/code-review/SKILL.md` step 4 renders into each
per-agent dispatch prompt (`Files in scope for this review: <path>, ...`)
and that Step 2.3's SubagentStop verdict recorder will parse back out of the
transcript. Sharing one constant between the renderer's test (this step) and
the future parser (Step 2.3) keeps the marker format and its parser from
silently drifting apart.

Step 2.2 adds `emit_review_verdict()`/`load_verdicts()` (the writer/reader
for `.claude/metrics/review-verdicts.jsonl`) to this module. Nothing else
belongs here yet.
"""

from __future__ import annotations

SCOPE_MARKER_PREFIX = "Files in scope for this review: "
