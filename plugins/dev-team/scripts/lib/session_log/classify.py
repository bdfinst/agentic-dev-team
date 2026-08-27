"""Text/name classification vocabulary shared by both session-log
extractors (issue #2043, epic #2040) — the "shared classification core" ADR
0036 deliberately left as an open question, decided here.

ADR 0036 / issue #2043's own symbol list names 14 symbols. Two of them —
`_is_transcript_path` / `_is_subagent_transcript` — already landed in
`session_log.discovery` in slice #2042, because they are used only by
enumeration/path logic that belongs there; this module does not duplicate
them (grouping them under classify.py in the ADR's original text predates
that split). `_AGENT_TRANSCRIPT_RE` is the same story: it's used only inside
`discovery.is_transcript_path`, so it also lives in `discovery.py`, not
here. That leaves 12 symbols for this module, reconciled below.

Per-symbol reconciliation (measured by diffing the two forked copies
directly against the live tree, not from memory):

| symbol                    | similarity | chosen behavior / source                                   |
|----------------------------|-----------|--------------------------------------------------------------|
| `_VERIFY_RE`               | 1.00      | byte-identical constant — moved verbatim                     |
| `_CORRECTION_RE`           | 1.00      | byte-identical constant — moved verbatim                     |
| `_PERMISSION_RE`           | 1.00      | byte-identical constant — moved verbatim                     |
| `_OLDSTRING_RE`            | 1.00      | byte-identical constant — moved verbatim                     |
| `_COMMIT_RE`/`_BYPASS_RE`  | 1.00      | ADR 0036 names these two regexes; neither exists as a literal|
|                            |           | symbol in the current tree (#2036 replaced a regex-based     |
|                            |           | commit/bypass detector with an argv-shaped one — the same    |
|                            |           | staleness class as the `_is_transcript_path` note above). The|
|                            |           | modern equivalent — `_statement_break_newlines`,              |
|                            |           | `_bash_segments`, `_is_git_commit_argv`,                      |
|                            |           | `_GIT_GLOBAL_OPTS_WITH_ARG`, `_COMMIT_BYPASS_TOKENS` — is     |
|                            |           | byte-identical between the two copies (confirmed by direct   |
|                            |           | diff) and lands here instead, under its current names.       |
| `_strip_ns`                | ~1.00     | logic identical; session_extract.py's docstring kept (more   |
|                            |           | detailed — extract_session_report.py's copy had none)        |
| `_text_of`                 | 0.98      | logic identical; docstring wording merged (session_extract's |
|                            |           | "digest" -> generic "output", correct for both callers)      |
| `_safe_name`               | 1.00      | byte-identical — moved verbatim, with its `_SAFE_NAME_RE`/    |
|                            |           | `_UNSAFE_NAME` dependencies                                   |
| `_basename`                | logic     | **the highest-stakes symbol**: ADR 0036 / issue #2043 flags   |
|                            | 1.00,     | this as carrying #1991's Windows-path privacy fix that the    |
|                            | docstring | #1994 port allegedly dropped. Direct diff of the CURRENT tree |
|                            | differs   | (not git archaeology) shows both copies already compute      |
|                            |           | `re.split(r"[\\/]", path_str)[-1] or path_str` — identical    |
|                            |           | logic, byte-identical behavior. The historical gap was closed |
|                            |           | in a later commit (subagent-transcript-count fixes #1995/     |
|                            |           | #2017) before this refactor started. session_extract.py's     |
|                            |           | docstring (which names the #1994 history) is kept as the      |
|                            |           | canonical one; pinned by the corpus's Windows-path fixture    |
|                            |           | (`C:\\Users\\SENTINEL_USER\\...` in                            |
|                            |           | `tests/fixtures/session_log/projects/.../99999999….jsonl`)    |
|                            |           | via the golden harness AND this module's own unit test.       |
| `_AGENT_TRANSCRIPT_RE`     | n/a       | already unified in `discovery.py` (#2042) — not duplicated    |
|                            |           | here; see module docstring above                              |
| `_HARNESS_ATTRIBUTIONS`    | 1.00      | byte-identical constant — moved verbatim                      |

Golden diffs: none. This slice is behavior-preserving, same as #2042 — every
moved symbol is either byte-identical or logic-identical between the two
forked copies, so the golden harness stays byte-for-byte unchanged (verified
below in the test suite).
"""

from __future__ import annotations

import re
import shlex

# --- verification / classification vocabularies (counted, never emitted) ---
VERIFY_RE = re.compile(
    r"\b(npm (run )?(test|lint|build)|pytest|bats|eslint|tsc|go test|cargo "
    r"(test|build)|mvn|gradle|make( |$)|vitest|jest|ruff|mypy|shellcheck)\b"
)
CORRECTION_RE = re.compile(
    r"\b(no|actually|revert|undo|not what i (asked|wanted)|that's wrong|"
    r"that is wrong|wrong|stop|don't|do not)\b"
)
PERMISSION_RE = re.compile(r"permission|denied|not allowed|blocked by", re.IGNORECASE)
OLDSTRING_RE = re.compile(r"old_string|not found|no match|string to replace", re.IGNORECASE)

# Gate signal (#111): a `git commit`, and whether it bypassed the pre-commit
# review gate (--no-verify, or a bare -n). #2036: the review-corroboration
# gate itself moved from `git commit` time to `gh pr create` time in #1886 —
# `hooks/telemetry.py` now keys its bypass signal off `PR_GATE_BYPASS_REASON`
# on a `gh pr create` invocation, an unrelated mechanism this no longer
# mirrors. This signal stays commit-time on purpose: it measures how often a
# commit itself skips local review, which is a real and different question
# from whether a PR was opened without one.
#
# Detection is argv-shaped, not a substring search over the whole command —
# see bash_segments()/is_git_commit_argv() below. A prior version searched
# `\bgit\s+commit\b` and `--no-verify|(^|\s)-n(\s|$)` against the raw string,
# which matched inside unrelated flags in a compound command (`grep -n`,
# `ls -n`) and even inside an unrelated string (`echo "git commit"`).
GIT_GLOBAL_OPTS_WITH_ARG = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
COMMIT_BYPASS_TOKENS = {"--no-verify", "-n"}

# Every string that becomes a digest/report KEY passes safe_name: these
# arrive from transcript files this code does not author, and the privacy
# contract of both extractors is names-only.
SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
UNSAFE_NAME = "other"

# `attributionAgent` values naming a harness ROLE rather than an agent. Every
# real Workflow-dispatched transcript carries "workflow-subagent"; unfiltered
# they become phantom agents while the agent that actually ran stays in
# never_observed_agents — the #1990 symptom itself.
HARNESS_ATTRIBUTIONS = frozenset({"workflow-subagent", "claude"})


def statement_break_newlines(cmd: str) -> str:
    """Replace a bare (unquoted) newline with ';' so a tokenizer sees a
    statement boundary there — a newline embedded inside a quoted argument
    (e.g. a multi-line commit message) is left untouched."""
    out = []
    in_single = in_double = False
    i, n = 0, len(cmd)
    while i < n:
        ch = cmd[i]
        if ch == "'" and not in_double:
            in_single = not in_single
            out.append(ch)
        elif ch == '"' and not in_single:
            in_double = not in_double
            out.append(ch)
        elif ch == "\\" and in_double and i + 1 < n:
            out.append(ch)
            out.append(cmd[i + 1])
            i += 1
        elif ch == "\n" and not in_single and not in_double:
            out.append(";")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def bash_segments(cmd: str) -> list[list[str]]:
    """Split `cmd` into argv-shaped segments at top-level shell operators
    (&&, ||, ;, |, and bare newlines), respecting quoting throughout — a
    quoted operator or newline inside a commit message never splits the
    command, and a quoted flag never crosses a segment boundary."""
    lex = shlex.shlex(statement_break_newlines(cmd), posix=True, punctuation_chars="&|;")
    lex.whitespace_split = True
    try:
        tokens = list(lex)
    except ValueError:
        # Malformed shell syntax (e.g. an unbalanced quote) — cannot be
        # segmented reliably. Fall back to a single opaque whitespace-split
        # segment rather than losing the signal outright.
        return [cmd.split()]
    segments: list[list[str]] = []
    current: list[str] = []
    for tok in tokens:
        if tok in ("&&", "||", ";", "|", "&"):
            if current:
                segments.append(current)
            current = []
        else:
            current.append(tok)
    if current:
        segments.append(current)
    return segments


def is_git_commit_argv(tokens: list[str]) -> bool:
    """True if `tokens` invokes `git ... commit ...` — walks past git's
    global options (including ones taking a separate argument, e.g. `-C`)
    to find the subcommand, so `git -C path commit` is recognized."""
    if not tokens or tokens[0] != "git":
        return False
    i = 1
    while i < len(tokens):
        tok = tokens[i]
        if tok in GIT_GLOBAL_OPTS_WITH_ARG:
            i += 2
            continue
        if tok.startswith("-"):
            i += 1
            continue
        return tok == "commit"
    return False


def strip_ns(name: str) -> str:
    """Drop known plugin namespace prefixes so invoked names match the
    registry (registry entries are bare dir/file stems). `dev-team:plan` ->
    `plan`; `agentic-dev-team:plan` -> `plan`; other names pass through."""
    for prefix in ("agentic-dev-team:", "dev-team:"):
        if name.startswith(prefix):
            return name[len(prefix) :]
    return name


def text_of(content) -> str:
    """Flatten a message ``content`` (str or list of blocks) to plain text.
    Used only for keyword CLASSIFICATION; never emitted into either
    extractor's output."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if isinstance(block.get("text"), str):
                    parts.append(block["text"])
                elif isinstance(block.get("content"), str):
                    parts.append(block["content"])
        return " ".join(parts)
    return ""


def safe_name(value: str) -> str:
    """Reduce an input-derived string to something safe to emit as a key."""
    # fullmatch, not match: `$` also matches immediately BEFORE a single
    # trailing newline, so `.match()` admitted "name\n" through the allowlist
    # and split the key space (#1994 review).
    return value if SAFE_NAME_RE.fullmatch(value) else UNSAFE_NAME


def basename(path_str: str) -> str:
    """Last component of a path recorded on ANY platform.

    `os.path.basename` splits on `/` only, so a Windows-form path comes back
    whole — an absolute path, username included, in a field both extractors'
    docstrings promise is a basename. Reachable whenever Windows-written
    transcripts are read under WSL, a devcontainer, or a bind-mounted
    `~/.claude`. #1991 fixed this in the shipped extractor first; #1994's
    port to session_extract.py initially left it behind (the same defect
    class crossing the fork twice) but a later fix closed the gap — both
    copies compute the same `re.split` before this module unified them (see
    module docstring's reconciliation table).
    """
    return re.split(r"[\\/]", path_str)[-1] or path_str
