"""Bash tool-call failure taxonomy classifier (issue #2038, epic #1999).

Establishes a falsifiable diagnostic baseline: categorizes failed Bash
`tool_result`s from session transcripts into a small set of named classes
so future remediation work has a real distribution to work against, not a
guess.

**Self-contained by design (post plan-review-design).**
`session_extract.py`'s module docstring states an explicit, enforced
contract -- "the digest holds METRICS ONLY ... no prompt text, code, file
contents, or command strings are ever emitted" -- reinforced by dedicated
sanitizers throughout that file. Threading raw Bash command/error text out
through a new map inside its `extract()` walker would violate that
contract. This module never imports from or threads data through
`extract()`; it reuses ONLY `session_extract.py`'s already-hardened,
public `resolve_transcripts`/`resolve_all_transcripts` functions for
transcript-PATH discovery (they resolve file paths, never command/error
text, so importing them does not touch the privacy contract). Everything
downstream of a resolved path -- record parsing, tool_use/tool_result
pairing, command and error text handling -- is this module's own code.

Raw command/error text is consumed in-process, for the duration of one
run, by the classifier this module builds toward (Step 1.2/1.3); it is
never written to a committed baseline snapshot, which carries class names
and counts only.

`resolve_transcripts`/`resolve_all_transcripts` are duck-typed on an
argparse `Namespace` (reading `args.transcript`, `args.project_dir`,
`args.projects_root`, `args.cwd`) rather than explicit parameters, so this
module's own CLI parser (`build_arg_parser`) defines matching attribute
names -- a silent-`AttributeError` risk if either script's flag names
drift; see `tests/scripts/test_bash_failure_taxonomy.py` for the contract
test guarding this.

## `timeout` and `genuine-command-error` are excluded from the addressable numerator

`timeout` and `genuine-command-error` are counted in the distribution like
any other class, but are EXCLUDED from `addressable_percentage`'s
numerator (`addressable_count`): a Bash call that timed out, or one that
ran as invoked and failed with a genuine, well-formed error from the tool
itself, is not a taxonomy problem this classifier's remediation work can
fix -- so the addressable percentage measures the share of classified
errors that remain once both excluded classes are subtracted out, matching
`churn_coupling_report.py`'s own "why this exists" convention of stating a
scoping decision's rationale directly in the docstring rather than leaving
it implicit in the code. A corpus with zero classified errors yields
`addressable_percentage: None` (the one true 0/0 case, never a
`ZeroDivisionError`); a non-empty corpus where every error happens to fall
into the two excluded classes yields a well-defined `0.0`.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.append(_HERE)
from session_extract import resolve_all_transcripts, resolve_transcripts


@dataclass(frozen=True)
class BashErrorPair:
    """A failed Bash `tool_result`, paired back to the command text of the
    `tool_use` block that produced it (matched by `tool_use_id`).

    `command`/`error_text` are `repr=False` so they never render verbatim
    via a default `repr()`/log/pytest-assertion-diff -- matching this
    module's stated privacy contract that this raw text is consumed
    in-process and never written out."""

    tool_use_id: str
    command: str = field(repr=False)
    error_text: str = field(repr=False)


@dataclass(frozen=True)
class UnpairedToolResult:
    """A failed `tool_result` with no matching pending Bash `tool_use` in
    this transcript (orphaned/truncated transcript) -- never guessed at,
    never matched to an unrelated command."""

    tool_use_id: str
    error_text: str = field(repr=False)


@dataclass
class PairingResult:
    pairs: list[BashErrorPair] = field(default_factory=list)
    unpaired: list[UnpairedToolResult] = field(default_factory=list)


def _iter_json_records(path: Path) -> Iterator[object]:
    """Yield each line of `path` decoded as JSON, in order.

    A line that fails to decode as JSON is skipped without raising -- a
    single corrupt line (a crashed session, a truncated write) must not
    abort classification of the rest of the corpus. An unreadable file
    (missing, permission-denied, or a decode error mid-character --
    `UnicodeDecodeError` is a `ValueError`) yields nothing rather than
    raising, matching `session_extract.py::_iter_records`'s own contract.
    """
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except (OSError, ValueError):
        return


def _text_of(content: object) -> str:
    """Flatten a `tool_result`'s `content` field (a plain string, or a list
    of content blocks carrying `text`) to plain text. Any other shape
    yields an empty string rather than raising."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return ""


def _record_tool_use(
    block: dict, pending_tool_use: dict[str, tuple[str | None, str | None]]
) -> None:
    """Record one `tool_use` block's `(name, command)` under its
    `tool_use_id` in `pending_tool_use`, mutating it in place. Skipped
    without effect if `id` is missing/non-string."""
    tool_use_id = block.get("id")
    if not isinstance(tool_use_id, str):
        return
    name = block.get("name")
    inp = block.get("input")
    command = inp.get("command") if isinstance(inp, dict) else None
    pending_tool_use[tool_use_id] = (
        name if isinstance(name, str) else None,
        command if isinstance(command, str) else None,
    )


def _record_tool_result(
    block: dict,
    pending_tool_use: dict[str, tuple[str | None, str | None]],
    pairs: list[BashErrorPair],
    unpaired: list[UnpairedToolResult],
) -> None:
    """Resolve one failed `tool_result` block against `pending_tool_use`
    (popping its entry), appending to `pairs` or `unpaired` in place.

    A `tool_result` missing `content`/`tool_use_id`, or not `is_error`, is
    skipped without effect. A non-Bash tool's error, or a Bash `tool_use`
    with no usable command text, is excluded entirely -- never counted as a
    pair, never as unpaired (the originating `tool_use` IS known; it just
    isn't a classifiable Bash failure)."""
    if "content" not in block or "tool_use_id" not in block:
        return
    if not block.get("is_error"):
        return
    tool_use_id = block.get("tool_use_id")
    if not isinstance(tool_use_id, str):
        return
    error_text = _text_of(block.get("content"))
    originating = pending_tool_use.pop(tool_use_id, None)
    if originating is None:
        unpaired.append(UnpairedToolResult(tool_use_id=tool_use_id, error_text=error_text))
        return
    name, command = originating
    if name == "Bash" and command is not None:
        pairs.append(BashErrorPair(tool_use_id=tool_use_id, command=command, error_text=error_text))


def _pair_transcript_records(
    records: Iterable[object],
) -> tuple[list[BashErrorPair], list[UnpairedToolResult]]:
    """Pair failed Bash `tool_result`s to their originating command text
    within ONE transcript's records.

    `pending_tool_use` is scoped to this call (per-transcript, per the
    REFACTOR note: local, not global) -- it maps a `tool_use_id` to
    `(name, command)` for every `tool_use` block seen so far, regardless of
    tool, so a failed non-Bash tool call can be told apart from a genuinely
    orphaned `tool_result` (no `tool_use` seen at all for that id) rather
    than conflating the two. `_record_tool_use`/`_record_tool_result` do the
    per-block pairing policy; this function only walks the JSON shape.

    A `tool_result`/`tool_use` block that decodes as valid JSON but is not
    a dict, or is a dict missing the fields this function reads
    (`type`/`content`/`tool_use_id` for a `tool_result`), is skipped without
    raising -- mirroring `session_extract.py::_read_synced_records`'s
    existing `isinstance(rec, dict)` guard.
    """
    pairs: list[BashErrorPair] = []
    unpaired: list[UnpairedToolResult] = []
    pending_tool_use: dict[str, tuple[str | None, str | None]] = {}

    for rec in records:
        if not isinstance(rec, dict):
            continue
        message = rec.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue

        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")

            if btype == "tool_use":
                _record_tool_use(block, pending_tool_use)
            elif btype == "tool_result":
                _record_tool_result(block, pending_tool_use, pairs, unpaired)

    return pairs, unpaired


def pair_bash_errors(paths: Iterable[Path | str]) -> PairingResult:
    """Read every transcript in `paths` and pair each failed Bash
    `tool_result` back to its originating command text.

    Each transcript is read and paired independently (fresh, local
    `pending_tool_use` state per file) before its results are folded into
    the aggregate `PairingResult` -- a `tool_use_id` never leaks across
    transcript files.
    """
    result = PairingResult()
    for raw_path in paths:
        pairs, unpaired = _pair_transcript_records(_iter_json_records(Path(raw_path)))
        result.pairs.extend(pairs)
        result.unpaired.extend(unpaired)
    return result


# ---------------------------------------------------------------------------
# Step 1.2: six-bucket classifier core
#
# `classify()` checks in a fixed precedence order so each bucket has a
# positive, disambiguating signal rather than being "whatever isn't the
# other four" -- see the plan's Step 1.2 IMPLEMENT note:
#   1. quoting              -- unbalanced quotes / shell syntax error
#   2. tool-not-present      -- PATH lookup failure on the invoked command
#                                itself (`command not found`, or a
#                                `No such file or directory` message whose
#                                failing token IS the invoked command)
#   3. working-directory     -- a `cd` failure, or a `No such file or
#                                directory` message whose failing token is
#                                an ARGUMENT of a (by elimination, already
#                                ruled-in) resolvable invoked command --
#                                never real PATH resolution, which would be
#                                environment-dependent and non-deterministic
#   4. timeout                -- a shell/process timeout marker
#   5. genuine-command-error  -- none of 1-4 matched and the error text's
#                                stderr portion (after stripping any bare
#                                exit-code line) is longer than a short
#                                fixed threshold
#   6. unclassified            -- the true fallback
# ---------------------------------------------------------------------------

_QUOTING_ERROR_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"unexpected eof while looking for matching", re.IGNORECASE),
    re.compile(r"unterminated quoted string", re.IGNORECASE),
    # Bash's own quoting-syntax-error phrasing, not the bare "unexpected
    # token" fragment -- that phrase alone is generic parser-error language
    # shared by Node/V8, TypeScript, and other non-shell tools, and would
    # misclassify their syntax errors as shell quoting failures.
    re.compile(r"syntax error near unexpected token", re.IGNORECASE),
    re.compile(r"bad substitution", re.IGNORECASE),
    re.compile(r"parse error near", re.IGNORECASE),
)

_COMMAND_NOT_FOUND_RE = re.compile(
    r"(?:^|\s)[^\s:]+:\s*command not found", re.IGNORECASE
)
_SH_STYLE_NOT_FOUND_RE = re.compile(
    r"^[^:\n]+:\s*\d+:\s*[^\s:]+:\s*not found", re.IGNORECASE | re.MULTILINE
)
_NO_SUCH_FILE_RE = re.compile(
    # `{1,500}` bounds the prefix capture so a long non-matching line costs
    # at most O(500) backtracking steps per scan start rather than the
    # unbounded, quadratic-shaped cost an unanchored `[^\n]*` has against
    # arbitrarily long untrusted transcript text; real prefixes (a command
    # name plus a path) are always far shorter than 500 characters.
    r"(?P<prefix>[^\n]{1,500}):\s*No such file or directory", re.IGNORECASE
)
_CD_FAILURE_RE = re.compile(r"\bcd:\s*.+?:\s*No such file or directory", re.IGNORECASE)

_TIMEOUT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\btimed out\b", re.IGNORECASE),
    # Marker-shaped forms only -- a bare "timeout" mention (e.g. a
    # "--timeout" CLI flag named in an "unrecognized option" error) is not
    # itself a timeout signal.
    re.compile(r"\btimeout\s+(?:after|exceeded|expired)\b", re.IGNORECASE),
    re.compile(r"\bcommand timed out\b", re.IGNORECASE),
    re.compile(r"deadline exceeded", re.IGNORECASE),
    re.compile(r"\betimedout\b", re.IGNORECASE),
)

_BARE_EXIT_CODE_LINE_RE = re.compile(
    r"^\s*(?:exit\s*(?:code|status)\s*[:=]?\s*)?-?\d+\.?\s*$", re.IGNORECASE
)
_GENUINE_ERROR_MIN_LEN = 10


_SHELL_OPERATORS: frozenset[str] = frozenset({"&&", "||", ";", "|", "&"})


def _split_shell_segments(command: str) -> list[list[str]]:
    """Split `command` into shell sub-command segments on top-level control
    operators (`&&`, `||`, `;`, `|`, `&`), respecting quoting so an operator
    embedded inside a quoted string is not treated as a delimiter.

    Uses `shlex.shlex` with `punctuation_chars=True` so multi-character
    operators (`&&`, `||`) tokenize as single tokens rather than two
    adjacent single-character ones. A command with unbalanced quoting (that
    shape is `quoting`'s own signature, already resolved before this is
    ever reached in `classify()`) falls back to a single, naively
    whitespace-split segment -- mirroring `_invoked_binary`/
    `_command_arguments`'s prior standalone `ValueError` fallback."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        stripped = command.strip()
        return [stripped.split()] if stripped else []

    segments: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        if token in _SHELL_OPERATORS:
            if current:
                segments.append(current)
                current = []
        else:
            current.append(token)
    if current:
        segments.append(current)
    return segments


def _skip_env_assignment_prefix(tokens: list[str]) -> int:
    """Index of the first token in `tokens` that is not a leading
    `VAR=value` environment assignment."""
    idx = 0
    while idx < len(tokens) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[idx]):
        idx += 1
    return idx


def _invoked_binaries(command: str) -> list[str]:
    """The invoked binary of EVERY shell segment of `command` (see
    `_split_shell_segments`), skipping each segment's own leading
    `VAR=value` assignments.

    Checks span the WHOLE chain rather than picking one segment as "the"
    invoked command, because a compound command's error can originate
    from ANY segment -- not only the last one. Tokenizing the whole line
    as a single command (the original approach) always named the FIRST
    sub-command as "the invoked binary" and every later token -- including
    a later sub-command's own binary -- as "its argument", so
    `cd /tmp && ./missing_binary --flag` misclassified a genuine
    tool-not-present failure of `./missing_binary` as a `cd`-attributable
    `working-directory` error purely because the command STARTED with
    `cd`. Picking only the LAST segment instead (a first fix attempt) just
    moved the same bug: `cat missing.txt && rm -rf /tmp/foo` (where `cat`
    fails and `rm` never runs, per `&&` semantics) would then have named
    `rm` as "the invoked binary", missing `cat`'s own missing-argument
    failure entirely. Checking every segment's tokens for a match handles
    both directions without needing to guess which segment actually ran
    (see `tests/scripts/test_bash_failure_taxonomy.py`'s compound-command
    regression coverage for both cases)."""
    binaries = []
    for tokens in _split_shell_segments(command):
        idx = _skip_env_assignment_prefix(tokens)
        if idx < len(tokens):
            binaries.append(tokens[idx])
    return binaries


def _tokens_match(a: str, b: str) -> bool:
    """Compare two command/path tokens for the tool-not-present /
    working-directory disambiguation: exact match, or matching basenames
    (`./foo` vs `foo`, `/usr/bin/foo` vs `foo`)."""
    return bool(a) and bool(b) and (a == b or Path(a).name == Path(b).name)


def _no_such_file_token(error_text: str) -> str | None:
    """Extract the failing path/token from a `<prog>: <token>: No such
    file or directory` style message (any number of colon-delimited
    prefixes) -- the LAST colon-delimited segment before the phrase."""
    match = _NO_SUCH_FILE_RE.search(error_text)
    if match is None:
        return None
    segments = [seg.strip() for seg in match.group("prefix").split(":") if seg.strip()]
    return segments[-1] if segments else None


def _strip_bare_exit_code_lines(error_text: str) -> str:
    """Drop lines that are nothing but a bare exit code (`1`, `exit code:
    127`) so `genuine-command-error` measures actual descriptive message
    text, not the exit-code echo alone."""
    kept = [
        ln for ln in error_text.splitlines() if not _BARE_EXIT_CODE_LINE_RE.match(ln)
    ]
    return "\n".join(kept).strip()


def _is_quoting_error(error_text: str) -> bool:
    return any(p.search(error_text) for p in _QUOTING_ERROR_PATTERNS)


def _is_tool_not_present(command: str, error_text: str, no_such_file_token: str | None) -> bool:
    """PATH lookup failure: `command not found` (bash-style or sh-style),
    or a `No such file or directory` message where the failing token IS
    the invoked command itself (a relative/absolute path exec failure).

    `no_such_file_token` is computed once by `classify()` and shared with
    `_is_working_directory_error` rather than each predicate re-scanning
    `error_text` with `_NO_SUCH_FILE_RE` independently."""
    if _COMMAND_NOT_FOUND_RE.search(error_text) or _SH_STYLE_NOT_FOUND_RE.search(
        error_text
    ):
        return True
    if no_such_file_token is None:
        return False
    return any(_tokens_match(no_such_file_token, b) for b in _invoked_binaries(command))


def _all_arguments(command: str) -> list[str]:
    """Every argument token (i.e. every token after each segment's own
    invoked binary, past its own leading `VAR=value` assignments) across
    EVERY shell segment of `command` -- see `_invoked_binaries`'s
    docstring for why this spans the whole chain rather than one
    segment."""
    arguments: list[str] = []
    for tokens in _split_shell_segments(command):
        idx = _skip_env_assignment_prefix(tokens)
        arguments.extend(tokens[idx + 1 :])
    return arguments


def _is_working_directory_error(
    command: str, error_text: str, no_such_file_token: str | None
) -> bool:
    """A `cd` failure, or a `No such file or directory` message where the
    failing token is an ARGUMENT of the invoked command, not the command
    itself (already ruled out by `_is_tool_not_present`).

    A `No such file or directory` token that matches neither the invoked
    binary nor any of its arguments is incidental to the tool's own error
    (e.g. an import failure inside `python -m pytest` naming an unrelated
    file) -- not a cd/relative-path failure of the invocation itself -- and
    must fall through to `genuine-command-error` instead.

    `no_such_file_token` is computed once by `classify()` and shared with
    `_is_tool_not_present` -- see that function's docstring."""
    if _CD_FAILURE_RE.search(error_text):
        return True
    # The bare "invoked binary is cd, so any 'no such file' phrase in the
    # error must be cd's own failure" shortcut only holds for a SINGLE,
    # non-compound command: extending it to "cd is ANY segment of the
    # chain" reintroduces the original compound-command bug this module
    # exists to avoid (`cd /tmp && ./missing-tool` would match on `cd`
    # again). Restricted to the one-segment case, this is just the
    # ordinary single-command `cd badpath` scenario.
    segments = _split_shell_segments(command)
    if len(segments) == 1:
        idx = _skip_env_assignment_prefix(segments[0])
        binary = segments[0][idx] if idx < len(segments[0]) else ""
        if binary.lower() == "cd":
            return "no such file or directory" in error_text.lower()
    if no_such_file_token is None:
        return False
    return any(_tokens_match(no_such_file_token, arg) for arg in _all_arguments(command))


def _is_timeout(error_text: str) -> bool:
    return any(p.search(error_text) for p in _TIMEOUT_PATTERNS)


def _is_genuine_command_error(error_text: str) -> bool:
    return len(_strip_bare_exit_code_lines(error_text)) > _GENUINE_ERROR_MIN_LEN


_MAX_ERROR_TEXT_LEN = 8192


def classify(command: str, error_text: str) -> str:
    """Classify one failed Bash call into one of six buckets: `quoting`,
    `tool-not-present`, `working-directory`, `timeout`,
    `genuine-command-error`, or `unclassified` -- see the precedence-order
    comment above this section.

    `error_text` is truncated to `_MAX_ERROR_TEXT_LEN` characters before any
    regex runs: classification signals are near the start of stderr, so
    this costs no accuracy while bounding the cost of `_NO_SUCH_FILE_RE`
    (backtracking-shaped on a long non-matching single line) against
    arbitrarily long, untrusted transcript text. The `_no_such_file_token`
    scan itself runs at most once here -- skipped entirely for a `quoting`
    match, since that bucket never consults it -- and is shared by
    `_is_tool_not_present` and `_is_working_directory_error` rather than
    each re-scanning."""
    text = (error_text or "").strip()[:_MAX_ERROR_TEXT_LEN]
    cmd = command or ""

    if _is_quoting_error(text):
        return "quoting"

    no_such_file_token = _no_such_file_token(text)
    if _is_tool_not_present(cmd, text, no_such_file_token):
        return "tool-not-present"
    if _is_working_directory_error(cmd, text, no_such_file_token):
        return "working-directory"
    if _is_timeout(text):
        return "timeout"
    if _is_genuine_command_error(text):
        return "genuine-command-error"
    return "unclassified"


# ---------------------------------------------------------------------------
# Step 1.3: corpus distribution + excluded-numerator reporting
#
# See the module docstring's "`timeout` and `genuine-command-error` are
# excluded from the addressable numerator" section for why those two
# classes are counted but never contribute to `addressable_percentage`'s
# numerator (`addressable_count`).
# ---------------------------------------------------------------------------

ADDRESSABLE_EXCLUDED_CLASSES: frozenset[str] = frozenset({"timeout", "genuine-command-error"})

ALL_CLASSES: tuple[str, ...] = (
    "quoting",
    "tool-not-present",
    "working-directory",
    "timeout",
    "genuine-command-error",
    "unclassified",
)


@dataclass(frozen=True)
class Distribution:
    """Per-class failure counts over a corpus, plus the addressable
    percentage.

    `addressable_percentage` is `None` only when `total` is zero (an empty
    corpus -- the one true 0/0 case). When `total` is non-zero but every
    error falls into the two excluded classes, `addressable_count` is
    zero and `addressable_percentage` is a well-defined `0.0`.
    """

    counts: dict[str, int]
    total: int
    addressable_count: int
    addressable_percentage: float | None

    def to_dict(self) -> dict[str, object]:
        """Class names, counts, and percentages only -- never raw
        command/error text, matching this module's committed-baseline
        privacy contract."""
        return {
            "counts": dict(self.counts),
            "total": self.total,
            "addressable_count": self.addressable_count,
            "addressable_percentage": self.addressable_percentage,
        }


def build_distribution(pairs: Iterable[BashErrorPair]) -> Distribution:
    """Classify every pair in `pairs` (Step 1.2's `classify`) and tally the
    six-class distribution, with the addressable count (the numerator of
    `addressable_percentage`: `total - timeout - genuine-command-error`)
    computed alongside it."""
    counts: dict[str, int] = dict.fromkeys(ALL_CLASSES, 0)
    total = 0
    for pair in pairs:
        counts[classify(pair.command, pair.error_text)] += 1
        total += 1

    excluded = sum(counts[cls] for cls in ADDRESSABLE_EXCLUDED_CLASSES)
    addressable_count = total - excluded
    addressable_percentage = (
        None if total == 0 else round((addressable_count / total) * 100, 2)
    )

    return Distribution(
        counts=counts,
        total=total,
        addressable_count=addressable_count,
        addressable_percentage=addressable_percentage,
    )


def build_distribution_from_corpus(paths: Iterable[Path | str]) -> Distribution:
    """Walk a corpus of transcript paths through `pair_bash_errors` (Step
    1.1's pairing) and `build_distribution` (Step 1.2's classifier) to emit
    one `Distribution` for the whole corpus window."""
    return build_distribution(pair_bash_errors(paths).pairs)


def build_arg_parser() -> argparse.ArgumentParser:
    """CLI surface for transcript-path discovery.

    `--transcript`/`--project-dir`/`--cwd`/`--projects-root` deliberately
    match `session_extract.py`'s own flag names and `dest`s -- required for
    `resolve_transcripts`/`resolve_all_transcripts` to duck-type correctly
    against the parsed `Namespace` (see module docstring).
    """
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--transcript",
        action="append",
        help="explicit transcript JSONL file(s); repeatable",
    )
    ap.add_argument("--project-dir", help="a directory of *.jsonl transcripts")
    ap.add_argument("--cwd", help="project cwd to match (default: $PWD)")
    ap.add_argument(
        "--projects-root",
        help="root of Claude Code project transcripts (default: ~/.claude/projects)",
    )
    ap.add_argument(
        "--all-projects",
        action="store_true",
        help="aggregate transcripts across ALL projects, not just the current cwd's",
    )
    ap.add_argument(
        "--baseline",
        action="store_true",
        help=(
            "classify pairs and emit the full Distribution (Step 1.3) as "
            "JSON, instead of just pairing counts -- this is what makes a "
            "committed baseline snapshot regeneratable"
        ),
    )
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    paths = resolve_all_transcripts(args) if args.all_projects else resolve_transcripts(args)

    if args.baseline:
        distribution = build_distribution_from_corpus(paths)
        print(json.dumps(distribution.to_dict(), indent=2))
        return 0

    result = pair_bash_errors(paths)
    # Counts only -- never raw command/error text.
    print(json.dumps({"pairs": len(result.pairs), "unpaired": len(result.unpaired)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
