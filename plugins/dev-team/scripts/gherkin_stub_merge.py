#!/usr/bin/env python3
"""gherkin_stub_merge.py — merge newly-derived step-definition stubs into an
existing step-definition file without clobbering an already-implemented step
(issue #1421).

`gherkin-derive`'s `bdd-runner` mode used to regenerate step-definition stubs
unconditionally on every run, silently discarding any step a human (or
`/build`) had already implemented. This module gives it a safe alternative,
mirroring `gherkin_feature_merge.py`'s read-before-write/merge discipline:
parse the existing file via `scripts/lib/stub_extractors` (one
lexically-aware, brace-balance-bounded extractor per language), skip any
candidate whose step-pattern text already exists there — regardless of
whether that existing binding is pending or already implemented — and append
only genuinely-new candidates as pending stubs after the last existing
binding. An existing binding's body is never rewritten or reordered.

`stub_extractors.parse_existing_steps` refuses to guess a span when a file's
brackets don't lexically balance, or a marker has no attached, boundable
body — reported as one of two structural-error sentinels
(`unbalanced-braces`, `dangling-annotation`, re-exported here), plus
`unsafe-path` at this script's own level for a `--existing` path containing a
`..` component, `malformed-candidates` when the `--candidates` scratch
file itself can't be bounded, `unreadable-candidates` when that file is
missing or can't be read at all, and `unsupported-extension` for an `--ext`
naming no known step-definition language. Every error leaves the existing
file completely untouched.

Stdlib-only. Python 3.8+ (ADR 0014/0015).

Usage:
    python3 gherkin_stub_merge.py merge --existing <path> --candidates <path> \
        --ext <.js|.ts|.mjs|.cjs|.java|.cs|.go> [--dry-run] [--json]
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

from _gherkin_text import safe_for_terminal as _safe_for_terminal
from stub_extractors import (
    ERROR_DANGLING_ANNOTATION,  # noqa: F401
    ERROR_UNBALANCED_BRACES,  # noqa: F401
    parse_existing_steps,
)
from stub_extractors import go as _go_extractor

# This script's own error sentinels — distinct from the two structural
# sentinels stub_extractors returns (re-exported above), the same split
# gherkin_feature_merge.py makes between its own ERROR_UNSAFE_PATH/
# ERROR_MALFORMED_CANDIDATES and the parser's ERROR_FEATURE_NOT_FOUND/
# ERROR_MALFORMED_FEATURE_BLOCK.
ERROR_UNSAFE_PATH = "unsafe-path"
ERROR_MALFORMED_CANDIDATES = "malformed-candidates"
# issue #1421 bug 6: a missing/unreadable --candidates path and an
# unrecognized --ext (argparse has no `choices=` for it) used to escape
# _cmd_merge as raw, uncaught Python exceptions instead of one of these
# sentinels through the same exit-2 --json contract every other structural
# problem uses.
ERROR_UNREADABLE_CANDIDATES = "unreadable-candidates"
ERROR_UNSUPPORTED_EXTENSION = "unsupported-extension"


@dataclass
class StepCandidate:
    """One newly-derived step-definition stub to merge in — pre-composed,
    language-appropriate source text (the caller, `gherkin-derive/SKILL.md`
    Step 4, is responsible for its exact shape), plus the step-pattern text
    used to detect whether it already exists.

    `decl_text` is Go-only (`None` for JS/TS, Java, C#): Go's registration
    call and the top-level function it references are non-adjacent source
    regions, so `text` (the registration call alone) is insufficient on its
    own — `decl_text` carries the function declaration that must be spliced
    in at a different, top-level-safe position (see `merge_steps`).
    `parse_candidate_steps` populates it automatically from a `--candidates`
    scratch file; a caller building `StepCandidate` by hand for Go must
    supply it explicitly or the merged file will fail to compile."""

    pattern: str
    text: str
    decl_text: str | None = None


@dataclass
class MergeResult:
    text: str
    added_patterns: list
    skipped_duplicate_patterns: list
    error: str | None


def _dedupe_candidates(candidates: list) -> tuple:
    """Return `(deduped_candidates, self_duplicate_patterns)`. Two candidates
    sharing a trimmed pattern would otherwise both be appended, mirroring the
    identical fix `gherkin_feature_merge._dedupe_candidate_units` applies to
    scenario titles."""
    seen = set()
    deduped = []
    duplicates = []
    for candidate in candidates:
        key = candidate.pattern.strip()
        if key in seen:
            duplicates.append(candidate.pattern)
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped, duplicates


def _insert_at(text: str, idx: int, insertion: str) -> str:
    """Splice `insertion` into `text` at char offset `idx`, restoring a
    missing line terminator right at the splice point (matching
    `gherkin_feature_merge.merge_scenarios`'s identical guard) so neither
    side's content is ever rewritten — only the separator whose absence
    would otherwise fuse two lines together. No-op when `insertion` is empty."""
    if not insertion:
        return text
    prefix = text[:idx]
    suffix = text[idx:]
    if prefix and not prefix.endswith("\n"):
        prefix += "\n"
    if not insertion.endswith("\n"):
        insertion += "\n"
    return prefix + insertion + suffix


def _splice_single_point(existing_text: str, bindings: list, new_candidates: list) -> str:
    """The default splice: append every new candidate's text as one block
    right after the last existing binding (or at file end with no existing
    bindings) — correct whenever a binding's `text` already contains
    everything the language needs (JS/TS, Java, C#)."""
    insertion_point = bindings[-1].end if bindings else len(existing_text)
    insertion = "".join(candidate.text for candidate in new_candidates)
    return _insert_at(existing_text, insertion_point, insertion)


def _splice_go_two_part(existing_text: str, bindings: list, new_candidates: list) -> str:
    """Go-only splice: a new step needs its function declaration inserted
    at the top level (safe anywhere alongside the other existing step
    functions — Go has no forward-declaration ordering requirement) and its
    `sc.Step(...)` registration inserted separately, inside the existing
    registration function (right after the last existing registration,
    `bindings[-1].end` — unchanged from the single-point case). Applying
    the two splices from the higher offset down means neither invalidates
    the other's not-yet-applied position.

    When `bindings` is empty — an existing, non-empty `.go` file whose
    `InitializeScenario` has no `sc.Step(...)` calls yet (issue #1421 bug 1)
    — there is no existing binding to anchor against. Anchor the call just
    before `InitializeScenario`'s own closing brace (so it lands inside a
    function body, not as an invalid top-level statement) and the
    declaration at that function's own top-level start. Falls back to
    appending both at file end (declaration first) only if
    `InitializeScenario` itself can't be found or bounded — a shape this
    module's own tests never produce, but still handled rather than raising."""
    decl_text = "".join(c.decl_text or "" for c in new_candidates)
    call_text = "".join(c.text for c in new_candidates)

    if bindings:
        decl_starts = [b.decl_start for b in bindings if b.decl_start is not None]
        call_anchor = bindings[-1].end
        decl_anchor = min(decl_starts) if decl_starts else call_anchor
    else:
        registration_body = _go_extractor.find_scenario_initializer_body(existing_text)
        if registration_body is not None and registration_body.error is None:
            call_anchor = registration_body.end - 1  # just before the closing '}'
            decl_anchor = registration_body.decl_start
        else:
            call_anchor = decl_anchor = len(existing_text)

    if call_anchor >= decl_anchor:
        text = _insert_at(existing_text, call_anchor, call_text)
        text = _insert_at(text, decl_anchor, decl_text)
    else:
        text = _insert_at(existing_text, decl_anchor, decl_text)
        text = _insert_at(text, call_anchor, call_text)
    return text


def merge_steps(existing_text: str, ext: str, candidate_steps: list) -> MergeResult:
    """Append-only merge of `candidate_steps` into `existing_text`.

    Relays `parse_existing_steps`'s structural-error sentinel unchanged when
    the existing file can't be bounded — this function never re-derives or
    guesses the cause. When `existing_text` is empty, the candidates' own
    text is the entire file (no skeleton is synthesized — that is the
    caller's concern, mirroring `merge_scenarios`'s identical empty-file
    branch; for Go specifically this means a caller composing a genuinely
    new file must supply a complete registration-function wrapper in one
    candidate's `text`/`decl_text` — this function only concatenates, it
    never synthesizes one)."""
    candidate_steps, self_duplicate_patterns = _dedupe_candidates(candidate_steps)

    if not existing_text:
        decl_body = "".join(candidate.decl_text or "" for candidate in candidate_steps)
        call_body = "".join(candidate.text for candidate in candidate_steps)
        return MergeResult(
            text=decl_body + call_body,
            added_patterns=[candidate.pattern for candidate in candidate_steps],
            skipped_duplicate_patterns=self_duplicate_patterns,
            error=None,
        )

    result = parse_existing_steps(existing_text, ext)
    if result.error is not None:
        return MergeResult(
            text=existing_text,
            added_patterns=[],
            skipped_duplicate_patterns=[],
            error=result.error,
        )

    existing_patterns = {binding.pattern.strip() for binding in result.bindings}
    new_candidates = [c for c in candidate_steps if c.pattern.strip() not in existing_patterns]
    skipped = self_duplicate_patterns + [
        c.pattern for c in candidate_steps if c.pattern.strip() in existing_patterns
    ]

    if not new_candidates:
        return MergeResult(
            text=existing_text, added_patterns=[], skipped_duplicate_patterns=skipped, error=None
        )

    is_go = ext.lower() == ".go"
    if is_go:
        merged_text = _splice_go_two_part(existing_text, result.bindings, new_candidates)
    else:
        merged_text = _splice_single_point(existing_text, result.bindings, new_candidates)

    return MergeResult(
        text=merged_text,
        added_patterns=[c.pattern for c in new_candidates],
        skipped_duplicate_patterns=skipped,
        error=None,
    )


def parse_candidate_steps(text: str, ext: str) -> tuple:
    """Parse a `--candidates` scratch file's step-definition text (the same
    syntax as an existing file's bindings — a candidates file is just
    syntactically-valid step-definition fragments, no separate schema)
    into `(candidates, error)`. Mirrors
    `gherkin_feature_merge.parse_candidate_units`'s reuse of the same parser
    used for existing content."""
    result = parse_existing_steps(text, ext)
    if result.error is not None:
        return [], result.error
    candidates = [
        StepCandidate(pattern=b.pattern, text=b.text, decl_text=b.decl_text) for b in result.bindings
    ]
    return candidates, None


def _write_error(message: str) -> None:
    sys.stderr.write(message + "\n")


def _reject_path_traversal(raw: str) -> str | None:
    """Return an error message if `raw` contains a `..` path component, else
    `None`. `--existing` is composed by `gherkin-derive/SKILL.md` Step 4 from
    a surface name derived from the target repository's own content, not
    always typed by a human — mirrors
    `gherkin_feature_merge._reject_path_traversal` exactly."""
    if ".." in Path(raw).parts:
        return f"--existing {raw!r} must not contain a '..' path component"
    return None


def _merge_payload(written: bool, added=(), skipped=(), error=None) -> dict:
    """The one JSON shape every `merge` response uses, named once so a future
    field addition touches this single place rather than every call site
    rebuilding the dict by hand — mirrors `gherkin_feature_merge._merge_payload`."""
    return {
        "written": written,
        "added_patterns": list(added),
        "skipped_duplicate_patterns": list(skipped),
        "error": error,
    }


def _write_atomic(path: Path, text: str) -> None:
    """Write `text` to `path` via a same-directory temp file + os.replace, so
    a crash or kill mid-write can never leave a truncated/corrupted
    step-definition file — identical pattern to
    `gherkin_feature_merge._write_atomic`."""
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            tmp_file.write(text)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def _cmd_merge(args: argparse.Namespace) -> int:
    # Known limitation (concurrency-review, issue #1421 consistency with
    # gherkin_feature_merge.py): read-then-write here is still a TOCTOU race
    # if two `merge` invocations ever target the same --existing path
    # concurrently — whichever writes last silently wins (the atomic write
    # below only rules out a truncated file, not a lost update between two
    # racing invocations). Not fixed: gherkin-derive's own design invokes
    # this once per surface, sequentially, never in parallel against the
    # same file (see gherkin-derive/SKILL.md Step 4), so there is no known
    # live trigger; a cross-platform lock (fcntl vs. msvcrt) would close
    # this remaining gap but is a design call for a human to make, not a
    # mechanical fix — deliberately left to a human decision rather than
    # guessed at here.
    path_error = _reject_path_traversal(args.existing)
    if path_error is not None:
        if args.json:
            print(json.dumps(_merge_payload(written=False, error=ERROR_UNSAFE_PATH)))
        else:
            _write_error(f"gherkin_stub_merge: {path_error} — no steps merged")
        return 2

    existing_path = Path(args.existing)
    existing_text = existing_path.read_text(encoding="utf-8") if existing_path.is_file() else ""

    try:
        candidates_text = Path(args.candidates).read_text(encoding="utf-8")
    except OSError as exc:
        # Missing/unreadable --candidates (not found, a directory, denied
        # permission, bad encoding, ...) used to escape as a raw traceback —
        # issue #1421 bug 6.
        if args.json:
            print(json.dumps(_merge_payload(written=False, error=ERROR_UNREADABLE_CANDIDATES)))
        else:
            _write_error(
                f"gherkin_stub_merge: --candidates {_safe_for_terminal(args.candidates)} "
                f"could not be read ({exc}) — no steps merged"
            )
        return 2

    try:
        candidate_steps, candidates_error = parse_candidate_steps(candidates_text, args.ext)
    except ValueError:
        # An --ext with no known step-definition language (argparse has no
        # `choices=` for it) used to escape parse_existing_steps's
        # ValueError as a raw traceback — issue #1421 bug 6.
        if args.json:
            print(json.dumps(_merge_payload(written=False, error=ERROR_UNSUPPORTED_EXTENSION)))
        else:
            _write_error(
                f"gherkin_stub_merge: --ext {args.ext!r} is not a supported "
                "step-definition extension — no steps merged"
            )
        return 2

    if candidates_error is not None:
        if args.json:
            print(json.dumps(_merge_payload(written=False, error=ERROR_MALFORMED_CANDIDATES)))
        else:
            _write_error(
                f"gherkin_stub_merge: candidates file {_safe_for_terminal(args.candidates)} "
                f"is malformed (error={candidates_error}) — no steps merged, existing file "
                f"left untouched"
            )
        return 2

    result = merge_steps(existing_text, args.ext, candidate_steps)

    if result.error is not None:
        if args.json:
            print(json.dumps(_merge_payload(written=False, error=result.error)))
        else:
            _write_error(
                f"gherkin_stub_merge: {_safe_for_terminal(args.existing)} structure could not "
                f"be parsed (error={result.error}) — no steps merged, existing file left "
                f"untouched"
            )
        return 2

    if args.dry_run:
        if args.json:
            print(
                json.dumps(
                    _merge_payload(
                        written=False,
                        added=result.added_patterns,
                        skipped=result.skipped_duplicate_patterns,
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
                    added=result.added_patterns,
                    skipped=result.skipped_duplicate_patterns,
                )
            )
        )
    else:
        print(
            f"OK: merged {len(result.added_patterns)} new step(s) into "
            f"{_safe_for_terminal(args.existing)}"
        )
    return 0


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gherkin_stub_merge.py")
    sub = parser.add_subparsers(dest="command", required=True)

    merge_parser = sub.add_parser("merge")
    merge_parser.add_argument("--existing", required=True)
    merge_parser.add_argument("--candidates", required=True)
    merge_parser.add_argument("--ext", required=True)
    merge_parser.add_argument("--dry-run", action="store_true")
    merge_parser.add_argument("--json", action="store_true")
    merge_parser.set_defaults(func=_cmd_merge)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
