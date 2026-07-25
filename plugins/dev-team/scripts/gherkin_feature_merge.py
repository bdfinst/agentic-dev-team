#!/usr/bin/env python3
"""gherkin_feature_merge.py — merge newly-derived scenarios into an existing
.feature file without destroying prior content (issue #1420).

`gherkin-derive` used to overwrite `features/<surface>.feature` unconditionally
on every run. This module gives it a safe alternative: read the existing file,
locate the named `Feature:` block, skip any candidate scenario whose title
already exists there (exact match, trimmed), and append only genuinely-new
scenarios after the block's last existing unit — never mid-block, never
rewriting untouched text.

Two failure causes are distinguished by construction, not inferred after the
fact: `feature-not-found` (the named `Feature:` title isn't in the existing
file at all — most likely a human renamed it) and `malformed-feature-block`
(the title is found, but the block's structure can't be bounded — a dangling
`@tag` line with no following `Scenario:`, or a `Scenario Outline:` whose
`Examples:` keyword has no table rows). Both refuse to write rather than
silently corrupting or duplicating content.

Stdlib-only. Python 3.8+ (ADR 0014/0015).

Usage:
    python3 gherkin_feature_merge.py merge --existing <path> --candidates <path> \
        --feature-title "<title>" [--dry-run] [--json]
    python3 gherkin_feature_merge.py check-stale --existing <path> \
        --observed "<title>=<value>" [--observed "<title>=<value>" ...] [--json]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "lib"))

from _gherkin_text import FEATURE_PREFIX as _FEATURE_PREFIX
from _gherkin_text import SCENARIO_OUTLINE_PREFIX as _SCENARIO_OUTLINE_PREFIX
from _gherkin_text import SCENARIO_PREFIX as _SCENARIO_PREFIX
from _gherkin_text import stripped as _stripped

_BACKGROUND_PREFIX = "Background:"
_SCENARIO_PREFIXES = (_SCENARIO_OUTLINE_PREFIX, _SCENARIO_PREFIX)
_EXAMPLES_PREFIX = "Examples:"

# The three error sentinels, named once so every return site shares one
# source of truth instead of a repeated raw literal. (Test assertions also
# import these directly rather than repeating the string values.)
ERROR_FEATURE_NOT_FOUND = "feature-not-found"
ERROR_MALFORMED_FEATURE_BLOCK = "malformed-feature-block"
ERROR_UNSAFE_PATH = "unsafe-path"
# _cmd_merge-only: parse_candidate_units reuses ERROR_MALFORMED_FEATURE_BLOCK
# internally for a malformed --candidates fragment (it shares _parse_units
# with the existing-block parser, which has only one malformed-shape error).
# The CLI remaps it to this distinct code so a --json caller can tell "your
# scratch candidates file is broken" from "the existing .feature file's
# structure is broken" — two different files, two different remediations —
# without parse_candidate_units itself needing a second error value.
ERROR_MALFORMED_CANDIDATES = "malformed-candidates"


@dataclass
class ScenarioUnit:
    """One `Scenario:`/`Scenario Outline:` unit — its title plus verbatim text
    (including any preceding `@tag` lines and, for an Outline, its Examples
    table) spanning from its start marker to the next unit or block end."""

    title: str
    line: int  # 1-based line number of the Scenario:/Scenario Outline: line
    text: str


@dataclass
class FeatureBlock:
    """A bounded `Feature:` block: header line, optional Background text
    (verbatim), and its ordered scenario units."""

    header_line: int  # 1-based
    end_index: int  # 0-based exclusive index (into split lines) where the
    # block's body ends — the boundary `merge_scenarios` splices at.
    # Carried on the parsed block itself so a caller that already has a
    # `FeatureBlock` never needs a second `_find_feature_header`/`_block_end`
    # scan to re-derive where it ends.
    background: str | None
    units: list


@dataclass
class ParseResult:
    block: FeatureBlock | None
    error: str | None


def _split_lines(text: str) -> list:
    """Split preserving original line endings so reconstruction is byte-exact."""
    return text.splitlines(keepends=True)


def _is_tag_line(line: str) -> bool:
    stripped = _stripped(line).strip()
    if not stripped:
        return False
    return all(tok.startswith("@") for tok in stripped.split())


def _scenario_title(line: str) -> str | None:
    """Return the title text if `line` is a Scenario:/Scenario Outline: line."""
    stripped = _stripped(line).strip()
    for prefix in _SCENARIO_PREFIXES:
        if stripped.startswith(prefix):
            return stripped[len(prefix) :].strip()
    return None


def _is_unit_start(line: str) -> bool:
    return _is_tag_line(line) or _scenario_title(line) is not None


def _find_feature_header(lines: list, feature_title: str) -> int | None:
    target = feature_title.strip()
    for i, line in enumerate(lines):
        stripped = _stripped(line).strip()
        if stripped.startswith(_FEATURE_PREFIX):
            title = stripped[len(_FEATURE_PREFIX) :].strip()
            if title == target:
                return i
    return None


def _block_end(lines: list, header_index: int) -> int:
    """Index (exclusive) where the block ends: the next Feature: header
    (any title), or end of file. A `@tag`/blank-line run immediately
    preceding that next header belongs to the *next* block (Gherkin tags
    attach to the declaration that follows them), so the boundary backs up
    before it rather than swallowing it into this block's body — otherwise
    a tagged Feature block anywhere but last in the file makes `_parse_units`
    see a dangling tag line and wrongly refuse the merge as
    malformed-feature-block."""
    for j in range(header_index + 1, len(lines)):
        if _stripped(lines[j]).strip().startswith(_FEATURE_PREFIX):
            end = j
            while end > header_index + 1:
                prev = lines[end - 1]
                if _stripped(prev).strip() == "" or _is_tag_line(prev):
                    end -= 1
                else:
                    break
            return end
    return len(lines)


def _find_next_unit_start(body: list, start: int, n: int) -> int:
    """Return the index of the next unit-start line (a tag line or a
    Scenario:/Scenario Outline: line) at or after `start`, or `n` if none
    remains before the block ends. Shared by `_find_background` (where does
    the Background section end) and `_locate_unit` (where does this unit
    end) — both are the same "scan forward for the next unit marker"
    question."""
    for m in range(start, n):
        if _is_unit_start(body[m]):
            return m
    return n


def _find_background(body: list) -> tuple:
    """Return (background_text_or_None, body_start_index) for the region
    of `body` before the first scenario unit."""
    n = len(body)
    for k, line in enumerate(body):
        if _stripped(line).strip().startswith(_BACKGROUND_PREFIX):
            bg_end = _find_next_unit_start(body, k + 1, n)
            return "".join(body[k:bg_end]), bg_end
        if _is_unit_start(line):
            return None, k
    return None, n


def _outline_missing_examples_table(body: list, title_offset: int, unit_end: int) -> bool:
    """True when the Scenario Outline starting at `title_offset` declares an
    `Examples:` keyword but the table has no rows before `unit_end` — the
    one structurally malformed shape a Scenario Outline unit can take.
    (A Scenario Outline with no `Examples:` keyword at all isn't this
    function's concern — that's a content choice, not a structural error.)"""
    examples_idx = None
    for m in range(title_offset + 1, unit_end):
        if _stripped(body[m]).strip().startswith(_EXAMPLES_PREFIX):
            examples_idx = m
            break
    if examples_idx is None:
        return False
    return not any(
        _stripped(body[m]).strip().startswith("|") for m in range(examples_idx + 1, unit_end)
    )


def _locate_unit(body: list, idx: int, n: int) -> tuple:
    """Find the `(title, title_offset, unit_end)` bounds of the unit
    starting at `idx` — the optional leading `@tag` line(s) through the
    `Scenario:`/`Scenario Outline:` line, up to the next unit-start marker
    or block end. `title` is `None` for a dangling run of tag lines with no
    following Scenario(-Outline) line before the block ends; the caller
    treats that as `malformed-feature-block`."""
    title = None
    title_offset = idx
    for scan in range(idx, n):
        t = _scenario_title(body[scan])
        if t is not None:
            title = t
            title_offset = scan
            break

    search_from = title_offset + 1 if title is not None else idx + 1
    unit_end = _find_next_unit_start(body, search_from, n)
    return title, title_offset, unit_end


def _parse_units(body: list, body_start: int, header_line_no: int):
    """Parse ordered ScenarioUnits from `body[body_start:]`.

    Returns (units, None) on success, or (None, "malformed-feature-block")
    on a dangling tag line or an unterminated Scenario Outline (Examples:
    keyword present with no table rows before the unit/block ends).
    """
    units = []
    idx = body_start
    n = len(body)
    while idx < n:
        if not _is_unit_start(body[idx]):
            idx += 1
            continue

        unit_start = idx
        title, title_offset, unit_end = _locate_unit(body, idx, n)

        if title is None:
            # A tag line (or run of tag lines) with no following
            # Scenario:/Scenario Outline: before the block ends.
            return None, ERROR_MALFORMED_FEATURE_BLOCK

        is_outline = _stripped(body[title_offset]).strip().startswith(_SCENARIO_OUTLINE_PREFIX)
        if is_outline and _outline_missing_examples_table(body, title_offset, unit_end):
            return None, ERROR_MALFORMED_FEATURE_BLOCK

        unit_text = "".join(body[unit_start:unit_end])
        units.append(ScenarioUnit(title=title, line=header_line_no + title_offset + 1, text=unit_text))
        idx = unit_end

    return units, None


def parse_feature_block(text: str, feature_title: str) -> ParseResult:
    """Locate and bound the `Feature: <feature_title>` block in `text`.

    The "not found" check runs before any structural parse: if no `Feature:`
    header matches `feature_title` anywhere, `error="feature-not-found"` is
    returned immediately. Only once the header is located does a structural
    failure (a dangling `@tag` line, or a `Scenario Outline:` missing its
    `Examples:` table) yield `error="malformed-feature-block"`.
    """
    lines = _split_lines(text)
    header_index = _find_feature_header(lines, feature_title)
    if header_index is None:
        return ParseResult(block=None, error=ERROR_FEATURE_NOT_FOUND)

    end_index = _block_end(lines, header_index)
    body = lines[header_index + 1 : end_index]

    background, body_start = _find_background(body)
    units, error = _parse_units(body, body_start, header_index + 1)
    if error is not None:
        return ParseResult(block=None, error=error)

    block = FeatureBlock(
        header_line=header_index + 1, end_index=end_index, background=background, units=units
    )
    return ParseResult(block=block, error=None)


def parse_candidate_units(text: str) -> tuple:
    """Parse headerless candidate scenario text (no `Feature:` wrapper) —
    the `--candidates` scratch-file shape — into ordered ScenarioUnits.
    Reuses the same unit-splitting logic `parse_feature_block` uses for the
    inside of a block, since a candidates file is exactly a block's body
    with no Background section expected.

    Returns `(units, error)`, mirroring `parse_feature_block`'s error
    contract: a structurally malformed candidates fragment (a dangling
    `@tag` line, or a `Scenario Outline:` missing its `Examples:` table) is
    reported as `error="malformed-feature-block"` with `units == []`, never
    silently collapsed to an empty, error-less list — a broken
    `--candidates` scratch file must surface as a diagnosable failure, not
    a silent "merged 0 scenarios" success."""
    body = _split_lines(text)
    units, error = _parse_units(body, 0, 0)
    if error is not None:
        return [], error
    return units, None


@dataclass
class MergeResult:
    text: str
    added_titles: list
    skipped_duplicate_titles: list
    error: str | None


def _dedupe_candidate_units(units: list) -> tuple:
    """Return `(deduped_units, self_duplicate_titles)`. Two candidates
    sharing a trimmed title would otherwise both be appended — silently
    making one invisible downstream (`find_then_step_text` keys its map by
    title, last-writer-wins), so a self-collision is dropped and reported
    the same way a collision against an existing title already is."""
    seen = set()
    deduped = []
    duplicates = []
    for unit in units:
        key = unit.title.strip()
        if key in seen:
            duplicates.append(unit.title)
            continue
        seen.add(key)
        deduped.append(unit)
    return deduped, duplicates


def _last_line_ending(lines: list) -> str:
    """Return the line ending of the last *terminated* line in `lines`
    (scanning from the end), defaulting to `"\\n"` — so a separator
    inserted at the splice point matches the existing file's convention
    instead of always injecting LF into a CRLF file. This is a last-line
    check, not a majority vote across the file (a mixed-ending file's
    splice separator follows whichever ending is nearest the insertion
    point, not whichever is more common) — only the inserted separator is
    normalized this way; a new candidate unit's own interior line endings
    (as authored) are passed through unchanged, so merging into a CRLF file
    can still yield a file with mixed endings overall."""
    for line in reversed(lines):
        if line.endswith("\r\n"):
            return "\r\n"
        if line.endswith("\n"):
            return "\n"
    return "\n"


def merge_scenarios(existing_text: str, feature_title: str, candidate_units: list) -> MergeResult:
    """Append-only merge of `candidate_units` into the named Feature block.

    Relays `parse_feature_block`'s error unchanged when the block can't be
    located or bounded — this function never re-derives or guesses the
    cause. When `existing_text` is empty, synthesizes a fresh
    `Feature: <feature_title>` block containing exactly the candidates (no
    parser call needed — nothing to locate).
    """
    candidate_units, self_duplicate_titles = _dedupe_candidate_units(candidate_units)

    if not existing_text:
        header = f"{_FEATURE_PREFIX} {feature_title}\n\n"
        body = "".join(unit.text for unit in candidate_units)
        return MergeResult(
            text=header + body,
            added_titles=[unit.title for unit in candidate_units],
            skipped_duplicate_titles=self_duplicate_titles,
            error=None,
        )

    result = parse_feature_block(existing_text, feature_title)
    if result.error is not None:
        return MergeResult(
            text=existing_text,
            added_titles=[],
            skipped_duplicate_titles=[],
            error=result.error,
        )
    # parse_feature_block's contract: block is set whenever error is None.
    assert result.block is not None

    existing_titles = {unit.title.strip() for unit in result.block.units}
    new_units = [u for u in candidate_units if u.title.strip() not in existing_titles]
    skipped = self_duplicate_titles + [
        u.title for u in candidate_units if u.title.strip() in existing_titles
    ]

    if not new_units:
        return MergeResult(
            text=existing_text, added_titles=[], skipped_duplicate_titles=skipped, error=None
        )

    # Reuse the boundary `parse_feature_block` already computed above rather
    # than re-deriving it with a second, type-unsafe `_find_feature_header`/
    # `_block_end` pass — `result.block` is guaranteed non-None here since
    # `result.error is None` was just checked.
    lines = _split_lines(existing_text)
    end_index = result.block.end_index
    ending = _last_line_ending(lines)

    insertion = "".join(unit.text for unit in new_units)
    # Insert right at the block's end boundary, preserving everything before
    # and after byte-for-byte — except that a missing line terminator right
    # at the splice point (existing_text has no trailing newline, or the
    # last new unit's text doesn't end in one) is restored, matching the
    # file's own dominant line ending, rather than left to fuse two Gherkin
    # lines into one. This never rewrites either line's content, only the
    # separator whose absence would otherwise corrupt it.
    prefix_lines = list(lines[:end_index])
    if prefix_lines and not prefix_lines[-1].endswith("\n"):
        prefix_lines[-1] += ending
    if insertion and not insertion.endswith("\n"):
        insertion += ending
    new_lines = prefix_lines + [insertion] + lines[end_index:]
    merged_text = "".join(new_lines)

    return MergeResult(
        text=merged_text,
        added_titles=[u.title for u in new_units],
        skipped_duplicate_titles=skipped,
        error=None,
    )


def find_then_step_text(existing_text: str, feature_title: str) -> dict:
    """Map each retained scenario's title to `(line, then_text)` — the
    verbatim `Then`/`And`/`But`-continuation step text (joined) plus the
    scenario's 1-based line number, for the stale-scenario check below.
    The line is threaded through (not just the text) so `check-stale` can
    report `<file>:<line>`, the format `gherkin-derive/SKILL.md` Step 6
    mandates — without it the line number `ScenarioUnit.line` already
    computes would be silently dropped on the floor. `But` is included
    alongside `And` because Gherkin permits either as a Then-continuation
    (e.g. `Then the request is rejected / But no partial record is
    written`) — omitting it would silently drop part of the asserted
    behavior from the comparison `is_stale` makes below."""
    result = parse_feature_block(existing_text, feature_title)
    if result.error is not None or result.block is None:
        return {}

    out = {}
    for unit in result.block.units:
        then_lines = []
        capturing = False
        for line in _split_lines(unit.text):
            stripped = _stripped(line).strip()
            if stripped.startswith("Then "):
                capturing = True
                then_lines.append(line)
            elif capturing and stripped.startswith(("And ", "But ")):
                then_lines.append(line)
            elif capturing:
                capturing = False
        out[unit.title] = (unit.line, "".join(then_lines))
    return out


def is_stale(then_text: str, observed_value: str) -> bool:
    """Best-effort, case-insensitive substring containment check: `False`
    (not stale) when `observed_value` appears in `then_text`, `True`
    otherwise. A scenario with no Then step (`then_text == ""`) is never
    reported stale — nothing to compare."""
    if not then_text:
        return False
    return observed_value.lower() not in then_text.lower()


def _write_error(message: str) -> None:
    sys.stderr.write(message + "\n")


def _reject_path_traversal(raw: str) -> str | None:
    """Return an error message if `raw` contains a `..` path component,
    else `None`. `--existing` is not always typed by a human — gherkin-
    derive/SKILL.md Step 2 composes it from a surface name derived from the
    *target repository's* own content (OpenAPI paths, route strings,
    exported symbol names), so a hostile or malformed segment containing
    `../` must not be allowed to steer the write (or the read) outside the
    intended directory."""
    if ".." in Path(raw).parts:
        return f"--existing {raw!r} must not contain a '..' path component"
    return None


def _merge_payload(written: bool, added=(), skipped=(), error=None) -> dict:
    """The one JSON shape every `merge` response uses (`check-stale` has its
    own distinct `{findings, unmatched_titles}` shape, built separately in
    `_cmd_check_stale` — not this helper), named once so a future field
    addition or rename to the `merge` response touches this single place
    instead of every `merge`-side call site rebuilding the dict by hand."""
    return {
        "written": written,
        "added_titles": list(added),
        "skipped_duplicate_titles": list(skipped),
        "error": error,
    }


def _write_atomic(path: Path, text: str) -> None:
    """Write `text` to `path` via a same-directory temp file + os.replace, so a
    crash or kill mid-write can never leave a truncated/corrupted .feature
    file — the one failure mode this module exists to rule out."""
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            tmp_file.write(text)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def _cmd_merge(args: argparse.Namespace) -> int:
    # Known limitation (concurrency-review, issue #1420 follow-up review):
    # read-then-write here is still a TOCTOU race if two `merge` invocations
    # ever target the same --existing path concurrently — whichever writes
    # last silently wins (the atomic write below only rules out a truncated
    # file, not a lost update between two racing invocations). Not fixed:
    # gherkin-derive's own design invokes this once per surface,
    # sequentially, never in parallel against the same file (see
    # gherkin-derive/SKILL.md's Output step), so there is no known live
    # trigger; a cross-platform lock (fcntl vs. msvcrt) would close this
    # remaining gap but is a design call for a human to make, not a
    # mechanical fix — deliberately left to a human decision rather than
    # guessed at here.
    path_error = _reject_path_traversal(args.existing)
    if path_error is not None:
        if args.json:
            print(json.dumps(_merge_payload(written=False, error=ERROR_UNSAFE_PATH)))
        else:
            _write_error(f"gherkin_feature_merge: {path_error} — no scenarios merged")
        return 2

    existing_path = Path(args.existing)
    existing_text = existing_path.read_text(encoding="utf-8") if existing_path.is_file() else ""
    candidates_text = Path(args.candidates).read_text(encoding="utf-8")
    candidate_units, candidates_error = parse_candidate_units(candidates_text)

    if candidates_error is not None:
        if args.json:
            print(json.dumps(_merge_payload(written=False, error=ERROR_MALFORMED_CANDIDATES)))
        else:
            _write_error(
                f"gherkin_feature_merge: candidates file {args.candidates} is malformed "
                f"(error={candidates_error}) — no scenarios merged, existing file left untouched"
            )
        return 2

    result = merge_scenarios(existing_text, args.feature_title, candidate_units)

    if result.error is not None:
        if args.json:
            print(json.dumps(_merge_payload(written=False, error=result.error)))
        elif result.error == ERROR_FEATURE_NOT_FOUND:
            _write_error(
                f"gherkin_feature_merge: could not locate Feature: {args.feature_title!r} "
                f"in {args.existing} — no scenarios merged, existing file left untouched "
                f"(error={result.error})"
            )
        else:
            _write_error(
                f"gherkin_feature_merge: found Feature: {args.feature_title!r} in {args.existing} "
                f"but its structure could not be parsed — no scenarios merged, existing file "
                f"left untouched (error={result.error})"
            )
        return 2

    if args.dry_run:
        if args.json:
            print(
                json.dumps(
                    _merge_payload(
                        written=False,
                        added=result.added_titles,
                        skipped=result.skipped_duplicate_titles,
                    )
                )
            )
        else:
            sys.stdout.write(result.text)
        return 0

    existing_path.parent.mkdir(parents=True, exist_ok=True)
    _write_atomic(existing_path, result.text)

    if args.json:
        print(
            json.dumps(
                _merge_payload(
                    written=True,
                    added=result.added_titles,
                    skipped=result.skipped_duplicate_titles,
                )
            )
        )
    else:
        print(f"OK: merged {len(result.added_titles)} new scenario(s) into {args.existing}")
    return 0


def _cmd_check_stale(args: argparse.Namespace) -> int:
    # Same untrusted, SKILL.md-composed provenance as --existing in _cmd_merge
    # (security-review) — the guard applies to both subcommands, not just the
    # one that writes, so a future change that starts echoing parsed content
    # here doesn't quietly reopen the gap.
    path_error = _reject_path_traversal(args.existing)
    if path_error is not None:
        if args.json:
            print(json.dumps({"findings": [], "unmatched_titles": [], "error": ERROR_UNSAFE_PATH}))
        else:
            _write_error(f"gherkin_feature_merge: {path_error}")
        return 2

    existing_path = Path(args.existing)
    existing_text = existing_path.read_text(encoding="utf-8") if existing_path.is_file() else ""

    observed = {}
    for raw in args.observed:
        # rpartition (not partition): the title is the untrusted, arbitrary-
        # content half of "<title>=<value>", so a title containing its own
        # "=" (e.g. "Create order fails when qty=0") must not be truncated
        # at the first "=" — split at the last one instead.
        title, _, value = raw.rpartition("=")
        observed[title.strip()] = value

    then_texts = find_then_step_text(existing_text, args.feature_title)

    findings = []
    unmatched_titles = []
    for title, value in observed.items():
        entry = then_texts.get(title)
        if entry is None:
            # The observed title isn't an exact key in the retained block —
            # e.g. the caller's title-extraction diverged from the retained
            # scenario's exact text. Report this distinctly rather than
            # silently treating it the same as "nothing to compare"; drift
            # detection is the entire point of this command, so a
            # title-match failure must be diagnosable, not invisible.
            unmatched_titles.append(title)
            continue
        line, then_text = entry
        if is_stale(then_text, value):
            findings.append(
                {
                    "title": title,
                    "line": line,
                    "then_text": then_text.strip(),
                    "observed": value,
                }
            )

    if args.json:
        print(json.dumps({"findings": findings, "unmatched_titles": unmatched_titles}))
    else:
        for entry in findings:
            print(
                f"possibly stale: {args.existing}:{entry['line']} ({entry['title']!r}) — "
                f"asserts {entry['then_text']!r}, code now does {entry['observed']!r}"
            )
        for title in unmatched_titles:
            print(
                f"unmatched: --observed title {title!r} not found among retained scenarios "
                f"in {args.feature_title!r} — check for a title mismatch between the "
                f"observed title and the scenario it should describe"
            )
    return 0


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gherkin_feature_merge.py")
    sub = parser.add_subparsers(dest="command", required=True)

    merge_parser = sub.add_parser("merge")
    merge_parser.add_argument("--existing", required=True)
    merge_parser.add_argument("--candidates", required=True)
    merge_parser.add_argument("--feature-title", required=True)
    merge_parser.add_argument("--dry-run", action="store_true")
    merge_parser.add_argument("--json", action="store_true")
    merge_parser.set_defaults(func=_cmd_merge)

    stale_parser = sub.add_parser("check-stale")
    stale_parser.add_argument("--existing", required=True)
    stale_parser.add_argument("--feature-title", required=True)
    stale_parser.add_argument("--observed", action="append", default=[])
    stale_parser.add_argument("--json", action="store_true")
    stale_parser.set_defaults(func=_cmd_check_stale)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
