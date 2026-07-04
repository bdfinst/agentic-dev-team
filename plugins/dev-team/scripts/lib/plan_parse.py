"""plan_parse — extract per-slice (id, depends_on, files) from a plan markdown.

Python port of `plugins/dev-team/scripts/lib/plan-parse.sh` (#579).

Contract mirrors the bash: emit one TSV row per slice:

    id<TAB>depends<TAB>files

- `depends` is `"none"`, a raw list (`"1, 2"`), or the sentinel `"__MISSING__"`
  when the slice has no `Depends-on` line at the slice level.
- `files` is a raw list (`"a, b"`) or the empty string when the slice has no
  slice-level `Files` line.

Slice-level fields are the first `Depends-on` / `Files` lines under a
`### Slice <id>:` heading and BEFORE that slice's first `#### Step` heading,
so per-step `**Files**:` lines are ignored.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable, List, Optional, TextIO, Tuple


_SLICE_RE = re.compile(r"^#+\s+[Ss]lice\s+([^:]+)")
_SLICE_HEADING_RE = re.compile(r"^#{1,3}\s+[Ss]lice\s+([^:]+):\s*(.*)$")
_HEADING_RE = re.compile(r"^#{1,3}\s")
_STEP_RE = re.compile(r"^#{4,}\s")
_DEPENDS_RE = re.compile(r"[Dd]epends-[Oo]n\**\s*:\s*(.*)")
_FILES_RE = re.compile(r"[Ff]iles\**\s*:\s*(.*)")
_MARKDOWN_NOISE_RE = re.compile(r"[*`]")


def _clean_value(raw: str) -> str:
    """Strip `**` / backticks and surrounding whitespace from a field value."""
    return _MARKDOWN_NOISE_RE.sub("", raw).strip()


def _slice_id(header_line: str) -> str:
    """Extract the slice id from a `### Slice <id>:` header line.

    Mirrors the bash sed pipeline: strip the leading `#+ Slice ` prefix, then
    everything after (and including) the first colon, then trim whitespace.
    """
    match = _SLICE_RE.match(header_line)
    if not match:
        return ""
    tail = match.group(1)
    # Trim leading whitespace already stripped by `\s+` in the pattern; strip
    # trailing content after `:` and whitespace.
    return tail.split(":", 1)[0].strip()


def parse_slices(lines: Iterable[str]) -> List[Tuple[str, str, str]]:
    """Return a list of `(id, depends, files)` rows in source order."""
    rows: List[Tuple[str, str, str]] = []

    current_id: str = ""
    deps: str = ""
    deps_seen: bool = False
    files: str = ""
    in_step: bool = False

    def flush() -> None:
        if current_id:
            rows.append((current_id, deps if deps_seen else "__MISSING__", files))

    for raw in lines:
        line = raw.rstrip("\n")

        # New slice header — flush the previous slice's row.
        if _SLICE_RE.match(line):
            flush()
            current_id = _slice_id(line)
            deps = ""
            deps_seen = False
            files = ""
            in_step = False
            continue

        # #### Step heading turns off slice-level field collection for the
        # rest of this slice — mirrors the bash `instep=1` flag.
        if _STEP_RE.match(line):
            in_step = True
            continue

        if not current_id or in_step:
            continue

        lowered = line.lower()

        if not deps_seen and "depends-on" in lowered:
            match = _DEPENDS_RE.search(line)
            if match is not None:
                deps = _clean_value(match.group(1))
                deps_seen = True
                continue

        if not files and "files" in lowered:
            match = _FILES_RE.search(line)
            if match is not None:
                files = _clean_value(match.group(1))

    flush()
    return rows


class _SliceSection:
    """The slice section currently being walked."""

    def __init__(self, slice_id: str, title: str) -> None:
        self.slice_id = slice_id
        self.title = title
        self.gherkin: Optional[str] = None

    def wants_gherkin(self) -> bool:
        return self.gherkin is None

    def row(self) -> Tuple[str, str, Optional[str]]:
        return (self.slice_id, self.title, self.gherkin)


class _FenceState:
    """Tracks fenced code blocks and collects a gherkin fence's content."""

    def __init__(self) -> None:
        self.active = False
        self._collecting = False
        self._lines: List[str] = []

    def enter(self, line: str, wants_gherkin: bool) -> None:
        self.active = True
        self._collecting = wants_gherkin and line[3:].strip().lower() == "gherkin"
        self._lines = []

    def consume(self, line: str) -> Optional[str]:
        """Advance one in-fence line; return the collected block (with one
        trailing newline) when a collecting fence closes, else None."""
        if line.startswith("```"):
            self.active = False
            block = "\n".join(self._lines) + "\n" if self._collecting else None
            self._collecting = False
            self._lines = []
            return block
        if self._collecting:
            self._lines.append(line)
        return None


def slice_gherkin_blocks(
    lines: Iterable[str],
) -> List[Tuple[str, str, Optional[str]]]:
    """Return `(id, title, gherkin)` per `### Slice <id>: <title>` heading.

    `gherkin` is the raw content of the slice's first fenced ```gherkin
    block (fences excluded, exactly one trailing newline), or None when the
    slice has no such block. Fence-aware: heading-like lines inside fenced
    code blocks never start or end a slice section.

    Grammar note — this walker intentionally differs from `parse_slices`:
    it requires the template shape (H1–H3 heading, colon after the id) and
    is fence-aware, while `parse_slices` keeps its looser, fence-blind
    grammar bug-for-bug with the bash original because `plan_waves.py`
    depends on it. For template-conformant plans the two agree on the slice
    set (pinned by `test_both_plan_walkers_agree_on_a_template_conformant_plan`);
    they diverge only on malformed input, where the exporter's stricter
    read is the safer one.
    """
    blocks: List[Tuple[str, str, Optional[str]]] = []
    current: Optional[_SliceSection] = None
    fence = _FenceState()

    for raw in lines:
        line = raw.rstrip("\n")

        if fence.active:
            block = fence.consume(line)
            if block is not None and current is not None:
                current.gherkin = block
            continue

        if line.startswith("```"):
            fence.enter(line, current is not None and current.wants_gherkin())
            continue

        match = _SLICE_HEADING_RE.match(line)
        if match:
            if current is not None:
                blocks.append(current.row())
            current = _SliceSection(match.group(1).strip(), match.group(2).strip())
            continue

        # Any other level-1..3 heading ends the current slice section.
        if current is not None and _HEADING_RE.match(line):
            blocks.append(current.row())
            current = None

    if current is not None:
        blocks.append(current.row())
    return blocks


def plan_parse(path: Path) -> str:
    """Return the TSV rendering of `parse_slices` on the file at `path`."""
    with open(path, encoding="utf-8") as handle:
        rows = parse_slices(handle)
    return "".join(f"{sid}\t{deps}\t{files}\n" for sid, deps, files in rows)


def _write_rows(rows: List[Tuple[str, str, str]], stream: TextIO) -> None:
    for sid, deps, files in rows:
        stream.write(f"{sid}\t{deps}\t{files}\n")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="plan_parse.py",
        description="Extract slice (id, Depends-on, Files) tuples from a plan markdown.",
    )
    parser.add_argument("plan", type=Path, help="Path to the plan markdown file")
    args = parser.parse_args(argv)
    with open(args.plan, encoding="utf-8") as handle:
        rows = parse_slices(handle)
    _write_rows(rows, sys.stdout)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
