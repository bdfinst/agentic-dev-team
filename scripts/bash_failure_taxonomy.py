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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from session_extract import resolve_all_transcripts, resolve_transcripts


@dataclass(frozen=True)
class BashErrorPair:
    """A failed Bash `tool_result`, paired back to the command text of the
    `tool_use` block that produced it (matched by `tool_use_id`)."""

    tool_use_id: str
    command: str
    error_text: str


@dataclass(frozen=True)
class UnpairedToolResult:
    """A failed `tool_result` with no matching pending Bash `tool_use` in
    this transcript (orphaned/truncated transcript) -- never guessed at,
    never matched to an unrelated command."""

    tool_use_id: str
    error_text: str


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
    than conflating the two.

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
                tool_use_id = block.get("id")
                if not isinstance(tool_use_id, str):
                    continue
                name = block.get("name")
                inp = block.get("input")
                command = inp.get("command") if isinstance(inp, dict) else None
                pending_tool_use[tool_use_id] = (
                    name if isinstance(name, str) else None,
                    command if isinstance(command, str) else None,
                )
            elif btype == "tool_result":
                if "content" not in block or "tool_use_id" not in block:
                    continue
                if not block.get("is_error"):
                    continue
                tool_use_id = block.get("tool_use_id")
                if not isinstance(tool_use_id, str):
                    continue
                error_text = _text_of(block.get("content"))
                originating = pending_tool_use.pop(tool_use_id, None)
                if originating is None:
                    unpaired.append(
                        UnpairedToolResult(tool_use_id=tool_use_id, error_text=error_text)
                    )
                    continue
                name, command = originating
                # A non-Bash tool's error, or a Bash tool_use with no
                # usable command text, is excluded here -- never counted
                # as a pair, never as unpaired (the originating tool_use
                # IS known; it just isn't a classifiable Bash failure).
                if name == "Bash" and command is not None:
                    pairs.append(
                        BashErrorPair(
                            tool_use_id=tool_use_id, command=command, error_text=error_text
                        )
                    )

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
    r"(?P<prefix>[^\n]*):\s*No such file or directory", re.IGNORECASE
)
_CD_FAILURE_RE = re.compile(r"\bcd:\s*.+?:\s*No such file or directory", re.IGNORECASE)

_TIMEOUT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\btimed out\b", re.IGNORECASE),
    re.compile(r"\btimeout\b", re.IGNORECASE),
    re.compile(r"deadline exceeded", re.IGNORECASE),
    re.compile(r"\betimedout\b", re.IGNORECASE),
)

_BARE_EXIT_CODE_LINE_RE = re.compile(
    r"^\s*(?:exit\s*(?:code|status)\s*[:=]?\s*)?-?\d+\.?\s*$", re.IGNORECASE
)
_GENUINE_ERROR_MIN_LEN = 10


def _invoked_binary(command: str) -> str:
    """Best-effort first token (the invoked binary) of a shell command
    line, skipping leading `VAR=value` environment assignments.

    Tokenizes with `shlex.split` so a quoted assignment containing
    whitespace (`VAR="a b" ./mytool arg`) isn't split on the space inside
    the quotes -- a plain `str.split()` would mis-tokenize it and hand back
    a fragment instead of the real invoked binary. Falls back to a naive
    whitespace split if the command itself has unbalanced quoting (that
    shape is `quoting`'s own signature, already resolved before this
    function is ever called)."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.strip().split()
    idx = 0
    while idx < len(tokens) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[idx]):
        idx += 1
    return tokens[idx] if idx < len(tokens) else ""


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


def _is_tool_not_present(command: str, error_text: str) -> bool:
    """PATH lookup failure: `command not found` (bash-style or sh-style),
    or a `No such file or directory` message where the failing token IS
    the invoked command itself (a relative/absolute path exec failure)."""
    if _COMMAND_NOT_FOUND_RE.search(error_text) or _SH_STYLE_NOT_FOUND_RE.search(
        error_text
    ):
        return True
    token = _no_such_file_token(error_text)
    if token is None:
        return False
    return _tokens_match(token, _invoked_binary(command))


def _is_working_directory_error(command: str, error_text: str) -> bool:
    """A `cd` failure, or a `No such file or directory` message where the
    failing token is an ARGUMENT of the invoked command, not the command
    itself (already ruled out by `_is_tool_not_present`)."""
    if _CD_FAILURE_RE.search(error_text):
        return True
    if _invoked_binary(command).lower() == "cd":
        return "no such file or directory" in error_text.lower()
    return _no_such_file_token(error_text) is not None


def _is_timeout(error_text: str) -> bool:
    return any(p.search(error_text) for p in _TIMEOUT_PATTERNS)


def _is_genuine_command_error(error_text: str) -> bool:
    return len(_strip_bare_exit_code_lines(error_text)) > _GENUINE_ERROR_MIN_LEN


def classify(command: str, error_text: str) -> str:
    """Classify one failed Bash call into one of six buckets: `quoting`,
    `tool-not-present`, `working-directory`, `timeout`,
    `genuine-command-error`, or `unclassified` -- see the precedence-order
    comment above this section."""
    text = (error_text or "").strip()
    cmd = command or ""

    if _is_quoting_error(text):
        return "quoting"
    if _is_tool_not_present(cmd, text):
        return "tool-not-present"
    if _is_working_directory_error(cmd, text):
        return "working-directory"
    if _is_timeout(text):
        return "timeout"
    if _is_genuine_command_error(text):
        return "genuine-command-error"
    return "unclassified"


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
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    paths = resolve_all_transcripts(args) if args.all_projects else resolve_transcripts(args)
    result = pair_bash_errors(paths)
    # Counts only -- never raw command/error text -- even at this stage,
    # ahead of Step 1.2's classifier and Step 1.3's baseline emission.
    print(json.dumps({"pairs": len(result.pairs), "unpaired": len(result.unpaired)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
