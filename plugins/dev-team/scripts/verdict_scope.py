#!/usr/bin/env python3
"""Scope a review dispatch to the delta the verdict ledger hasn't already
cleared (#2167).

Given a candidate `{lens: [file, ...], ...}` dispatch plan, consult
`hooks/lib/review_verdicts.py`'s per-lens verdict ledger
(`.claude/metrics/review-verdicts.jsonl`, written by
`hooks/review_verdict_recorder.py` on every real review-agent dispatch) and
split each lens's file list into the files that still need a live dispatch
and the ones an exact `(lens, file_path, current file_content_hash)` match
already cleared with outcome `"pass"`.

Shared by both call sites the epic (#2164) names: `/code-review` step 4 (a
repeat run over an unchanged target set should dispatch nothing) and
`/build`'s own inline checkpoints (sub-steps 4/6) plus its Step 6 backstop
(a slice already cleared at a checkpoint has nothing left for the backstop
to review) -- one resolver, not two independently-drifting copies, mirroring
`select_lenses.py`'s own shared-between-both-skills precedent.

## Fail-closed, by design (#2167 acceptance criteria)

A file is skipped ONLY on an exact `(lens, file_path, file_content_hash)`
match whose most-recent ledger row (rows are append-only; the last matching
row in file order is the most recent) has `outcome == "pass"`. Every other
case dispatches normally:

- No ledger, an unreadable ledger, or a line `load_verdicts` couldn't parse
  -- `load_verdicts` itself already degrades these to "no usable rows"
  (see that function's own docstring); this module inherits that posture
  without adding a second one.
- A row whose `plugin_version` is older than the version running now --
  same source: `load_verdicts` has already excluded it before this module
  ever sees the row.
- The file can't be hashed right now (deleted, unreadable, not a regular
  file, or over `review_verdicts.MAX_HASH_FILE_BYTES`) -- `hash_file`
  returns `None`, and a `None` hash never matches anything, so the file
  always stays in `toDispatch`.
- The most-recent matching row's outcome is `"findings"`, not `"pass"`.
- No row at all shares this exact `(lens, file_path, file_content_hash)`
  triple -- a different lens, a different file, or the same file at
  different content (a hash mismatch) are all "no match".

This is the same ambiguity-resolves-toward-more-work posture
`select_lenses.py`'s own docstring already documents for its resolver --
just applied to *whether* a lens/file needs a fresh dispatch rather than
*which* lenses apply at all.

## Canonicalization (#2167 correctness/security/arch review)

The ledger's own `file_path` is always the writer's canonical, `root`-
relative POSIX form (`hooks/review_verdict_recorder.py`'s own
`_resolve_under_cwd`/`canonical_path`). Every candidate file this module is
handed is canonicalized the SAME way (`_canonicalize_lens_files`,
`compute_file_hashes`) before either hashing or matching it against a
ledger row -- comparing a caller's raw spelling (`./a.py`, an absolute
path) against the writer's canonical one would otherwise silently never
match, defeating the whole point of this module without ever being wrong
(a missed skip, never a false one). A file that can't be canonicalized
(escapes `root`, unresolvable) keeps its raw string as a deliberately
unmatchable placeholder rather than raising or guessing.

Stdlib-only. See ADR 0014 / ADR 0015.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_HOOKS_LIB_DIR = _HERE.parent / "hooks" / "lib"
if str(_HOOKS_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_LIB_DIR))

# No `except ImportError` fallback (matches `select_lenses.py`'s own rule,
# #1968): `hooks/lib/` ships inside this same plugin, always present
# wherever this script runs. A hand-written second copy of
# `hash_file`/`load_verdicts` is exactly the kind of independently-drifting
# duplicate that rule exists to prevent -- here it would silently turn every
# lookup into a guaranteed miss (safe, but defeats the entire point of this
# module) rather than raising loudly.
try:
    from review_verdicts import (  # type: ignore[import-not-found]
        canonical_path,
        hash_file,
        load_verdicts,
    )
except ImportError as exc:  # pragma: no cover - broken install, not a supported mode
    raise ImportError(
        f"{__name__} requires 'review_verdicts' from the dev-team plugin's "
        f"hooks/lib, which could not be imported.\n"
        f"  searched: {_HOOKS_LIB_DIR}\n"
        f"  exists:   {_HOOKS_LIB_DIR.is_dir()}\n"
        "This module deliberately has no fallback copy of the hashing/ledger "
        "read logic -- a divergent stand-in would make every skip decision "
        "silently wrong. Fix the install or the path rather than re-adding a "
        "local implementation."
    ) from exc

_PASS_OUTCOME = "pass"


def _latest_matching_verdict(
    verdicts: list[dict], lens: str, file_path: str, file_hash: str
) -> dict | None:
    """The most-recent row (last one in append order) sharing the exact
    `(lens, file_path, file_content_hash)` triple, or `None` if no row
    matches at all."""
    match: dict | None = None
    for row in verdicts:
        if (
            row.get("lens") == lens
            and row.get("file_path") == file_path
            and row.get("file_content_hash") == file_hash
        ):
            match = row
    return match


def resolve_dispatch(
    lens_files: dict[str, list[str]],
    verdicts: list[dict],
    file_hashes: dict[str, str | None],
) -> dict:
    """Pure resolver. `lens_files` maps a lens name to the candidate files
    already matched to it (by `Scope:`/change-shape/etc. gating upstream --
    this function narrows *within* that set, it never widens it).
    `file_hashes` maps each candidate file to its current content hash, or
    `None` when it couldn't be hashed (see module docstring).

    Returns `{"toDispatch": {lens: [file, ...]}, "skipped": {lens: [{"file":
    ..., "verdict": <the matched row>}, ...]}, "fullySkippedLenses":
    [lens, ...]}`. A lens with at least one file left to dispatch appears in
    `toDispatch` with only those files (its ledger-cleared files are simply
    absent from that list, not present-but-empty); a lens with EVERY
    candidate file cleared is absent from `toDispatch` entirely and named in
    `fullySkippedLenses` -- the caller's signal to not dispatch that lens
    this round at all. `lens_files` is preserved as the source of truth for
    "was this lens even a candidate": a lens with an empty candidate list to
    begin with never appears in any of the three outputs.
    """
    to_dispatch: dict[str, list[str]] = {}
    skipped: dict[str, list[dict]] = {}

    for lens, files in lens_files.items():
        keep: list[str] = []
        skip_entries: list[dict] = []
        for file_path in files:
            file_hash = file_hashes.get(file_path)
            row = (
                _latest_matching_verdict(verdicts, lens, file_path, file_hash)
                if file_hash
                else None
            )
            if row is not None and row.get("outcome") == _PASS_OUTCOME:
                skip_entries.append({"file": file_path, "verdict": row})
            else:
                keep.append(file_path)
        if keep:
            to_dispatch[lens] = keep
        if skip_entries:
            skipped[lens] = skip_entries

    fully_skipped = [lens for lens in lens_files if lens in skipped and lens not in to_dispatch]

    return {
        "toDispatch": to_dispatch,
        "skipped": skipped,
        "fullySkippedLenses": fully_skipped,
    }


def compute_file_hashes(files, root: Path) -> dict[str, str | None]:
    """I/O boundary: hash every file in `files` (deduped), canonicalizing
    each against `root` first (`review_verdicts.canonical_path` -- #2167
    review: an absolute path, a `./`-prefixed path, or one outside `root`
    entirely must never be naively joined onto `root` and hashed as-is). A
    file that can't be canonicalized, doesn't exist under `root`, or that
    `hash_file` otherwise can't read, maps to `None` -- never omitted, so a
    caller iterating `file_hashes` can always find every candidate file's
    entry."""
    root_resolved = Path(root).resolve()
    hashes: dict[str, str | None] = {}
    for f in dict.fromkeys(files):
        canonical = canonical_path(f, root)
        hashes[f] = hash_file(root_resolved / canonical) if canonical is not None else None
    return hashes


def _load_json_arg(value: str):
    """Load JSON from an inline JSON string, or from a file path when it
    isn't one.

    Tries the inline parse FIRST (#2167 correctness review): the previous
    check-path-first order called `Path(value).exists()` on the raw
    argument, and `Path.exists()` raises `OSError` (`ENAMETOOLONG` on
    Linux) rather than returning `False` once `value` is a string longer
    than `PATH_MAX` -- which any real `--lens-files` JSON for a multi-lens,
    multi-file round easily is (a ~30-file, 10-lens round is already
    several KB). A JSON literal is never also a path a caller would pass
    here, so trying the inline parse first costs nothing in the common case
    and never stats the filesystem with an oversized string."""
    try:
        return json.loads(value)
    except ValueError:
        return json.loads(Path(value).read_text())


def _canonicalize_lens_files(
    lens_files: dict[str, list[str]], root: Path
) -> dict[str, list[str]]:
    """Canonicalize every candidate file against `root` before matching it
    to the ledger (#2167 review: correctness/security/arch all
    independently flagged that the writer always stores a canonical,
    `root`-relative POSIX `file_path`, so comparing a caller's raw string
    against it -- `./a.py`, an absolute path -- silently never matches a
    genuine row). A file that can't be canonicalized keeps its RAW string
    as a deliberately unmatchable placeholder: no genuine ledger row's
    `file_path` can ever equal an un-canonicalizable string, so it always
    falls through to `toDispatch` (fail-closed, never a false skip).

    The caller sees the CANONICAL form back in `toDispatch`/`skipped`, not
    its original spelling -- for every real call site (SKILL.md's own
    already-`root`-relative file lists, from `changed_file_list.py`'s git
    diff output) canonicalization is a no-op, so this is not a behavior
    change there; only a caller passing an absolute or `./`-prefixed path
    sees its spelling normalized in the response, which still names the
    same file."""
    return {
        lens: [canonical_path(f, root) or f for f in files] for lens, files in lens_files.items()
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repo/worktree root the ledger lives under")
    parser.add_argument(
        "--lens-files",
        required=True,
        help='JSON (file or inline) mapping lens name to its candidate file list: {"<lens>": ["<file>", ...], ...}',
    )
    args = parser.parse_args(argv)

    root = Path(args.root)
    lens_files = _canonicalize_lens_files(_load_json_arg(args.lens_files), root)

    all_files = [f for files in lens_files.values() for f in files]
    file_hashes = compute_file_hashes(all_files, root)
    verdicts = load_verdicts(root)

    result = resolve_dispatch(lens_files, verdicts, file_hashes)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
