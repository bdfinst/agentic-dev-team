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
from typing import Dict, Iterable, List, Optional, TextIO, Tuple


_SLICE_RE = re.compile(r"^#+\s+[Ss]lice\s+([^:]+)")
_SLICE_HEADING_RE = re.compile(r"^#{1,3}\s+[Ss]lice\s+([^:]+):\s*(.*)$")
_HEADING_RE = re.compile(r"^#{1,3}\s")
_STEP_RE = re.compile(r"^#{4,}\s")
# `\**\s*:\s*\**\s*` handles bold markup on *both* sides of the colon —
# `**Depends-on:**` puts the closing `**` right after the colon, not before
# it, so without the trailing `\**\s*` the leaked marker lands inside the
# captured value (see #865 AC9: a value may legitimately end in its own
# `**` glob suffix like `src/auth/**`, so blanket-stripping every asterisk
# in `_clean_value` is no longer safe — the regex must consume the label's
# own bold markers instead).
_DEPENDS_RE = re.compile(r"[Dd]epends-[Oo]n\**\s*:\s*\**\s*(.*)")
_FILES_RE = re.compile(r"[Ff]iles\**\s*:\s*\**\s*(.*)")
_INVARIANTS_RE = re.compile(r"[Ii]nvariants\**\s*:\s*\**\s*(.*)")
_ROLLBACK_RE = re.compile(r"[Rr]ollback[ _-][Pp]oint\**\s*:\s*\**\s*(.*)")
_BACKTICK_TOKEN_RE = re.compile(r"`([^`]+)`")
_TOKEN_SPLIT_RE = re.compile(r"[,\s]+")


def _clean_value(raw: str) -> str:
    """Strip backticks and bold-wrapping `**` / surrounding whitespace from a
    field value.

    Backticks are removed unconditionally (inline-code delimiters are never
    semantically meaningful). Bold markers are trickier since #865: a `Files`
    or `Invariants` value may legitimately end in a recursive glob like
    `src/auth/**`, so a lone trailing `**` must survive — only a **paired**
    `**...**` wrapping the *entire* value (both ends) is markdown bold and
    gets stripped.
    """
    value = raw.replace("`", "").strip()
    if value.startswith("**") and value.endswith("**") and len(value) > 3:
        value = value[2:-2].strip()
    return value


def _parse_invariant_commands(raw: str) -> List[str]:
    """Split an `**Invariants:**` value into individual shell commands.

    Each command is expected to be its own backtick-quoted token
    (`` `npm test` ``, `` `python3 scripts/foo.py` ``) so commas or spaces
    *inside* a command (e.g. `--grep "session"`) don't get misread as
    separators. Falls back to a plain comma split when no backtick tokens
    are present (no commands to run — an empty raw value — yields `[]`).
    """
    tokens = _BACKTICK_TOKEN_RE.findall(raw)
    if tokens:
        return [t.strip() for t in tokens if t.strip()]
    cleaned = _clean_value(raw)
    if not cleaned:
        return []
    return [c.strip() for c in cleaned.split(",") if c.strip()]


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


def parse_slice_optional_fields(lines: Iterable[str]) -> Dict[str, Dict[str, object]]:
    """Return `{slice_id: {"invariants": [...], "rollback_point": str}}`.

    Collects the two new (#865) optional slice-level fields — `**Invariants:**`
    and `**Rollback point:**` — using the same slice-level-only grammar as
    `parse_slices` (fields before the slice's first `#### Step` heading).
    A slice missing either field simply has an empty list / empty string in
    its entry; this is purely additive and never raises.
    """
    result: Dict[str, Dict[str, object]] = {}

    current_id: str = ""
    invariants: List[str] = []
    rollback: str = ""
    in_step: bool = False

    def flush() -> None:
        if current_id:
            result[current_id] = {
                "invariants": invariants,
                "rollback_point": rollback,
            }

    for raw in lines:
        line = raw.rstrip("\n")

        if _SLICE_RE.match(line):
            flush()
            current_id = _slice_id(line)
            invariants = []
            rollback = ""
            in_step = False
            continue

        if _STEP_RE.match(line):
            in_step = True
            continue

        if not current_id or in_step:
            continue

        lowered = line.lower()

        if not invariants and "invariants" in lowered:
            match = _INVARIANTS_RE.search(line)
            if match is not None:
                invariants = _parse_invariant_commands(match.group(1))
                continue

        if not rollback and "rollback" in lowered:
            match = _ROLLBACK_RE.search(line)
            if match is not None:
                rollback = _clean_value(match.group(1))

    flush()
    return result


def parse_step_files(lines: Iterable[str]) -> Dict[str, List[str]]:
    """Return `{slice_id: [raw per-step Files values...]}` — the *inferred*
    write set (#865). Each entry is the list of raw `**Files**:` line values
    found under that slice's `#### Step` headings, in source order and
    un-tokenized (callers split on `[,\\s]+` same as slice-level `files`).

    This is deliberately the mirror image of `parse_slices`, which stops
    collecting `Files` the moment a step heading is seen — here we only
    collect *after* a step heading, so the two never double-count the same
    line.
    """
    result: Dict[str, List[str]] = {}

    current_id: str = ""
    in_step: bool = False

    for raw in lines:
        line = raw.rstrip("\n")

        if _SLICE_RE.match(line):
            current_id = _slice_id(line)
            in_step = False
            continue

        if _STEP_RE.match(line):
            in_step = True
            continue

        if not current_id or not in_step:
            continue

        if "files" in line.lower():
            match = _FILES_RE.search(line)
            if match is not None:
                value = match.group(1).strip()
                if value:
                    result.setdefault(current_id, []).append(value)

    return result


def step_files_union(lines: Iterable[str]) -> Dict[str, List[str]]:
    """Return `{slice_id: sorted [tokenized inferred files]}` — the union of
    per-step `**Files**:` tokens for each slice, deduplicated and sorted.
    Convenience wrapper around `parse_step_files` for callers (`plan_waves.py`)
    that want the tokenized set directly rather than raw per-line values.
    """
    raw = parse_step_files(lines)
    unioned: Dict[str, List[str]] = {}
    for slice_id, values in raw.items():
        tokens: set = set()
        for value in values:
            tokens.update(t for t in _TOKEN_SPLIT_RE.split(_clean_value(value)) if t)
        unioned[slice_id] = sorted(tokens)
    return unioned


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
