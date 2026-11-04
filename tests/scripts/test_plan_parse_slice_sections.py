"""Contract for `plan_parse.slice_sections`: fence-aware slice bodies."""

from __future__ import annotations

import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[2] / "plugins" / "dev-team" / "scripts" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import plan_parse  # type: ignore[import-not-found]

_PLAN = """\
# Plan: Sample

### Slice 1: First

body one
```text
### Slice 9: inside a fence
```

## Other

### Slice 2: Second
body two
"""


def test_sections_run_from_heading_to_next_heading_and_ignore_fenced_headings():
    sections = plan_parse.slice_sections(_PLAN.split("\n"))

    assert [(sid, title) for sid, title, _ in sections] == [
        ("1", "First"),
        ("2", "Second"),
    ]
    assert sections[0][2] == [
        "",
        "body one",
        "```text",
        "### Slice 9: inside a fence",
        "```",
        "",
    ]
    assert sections[1][2] == ["body two", ""]
