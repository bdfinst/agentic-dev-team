#!/usr/bin/env python3
"""pre_commit_review — Claude Code PreToolUse:Bash hook (Python port).

Python port of hooks/pre-commit-review.sh (#583 / #572 Cluster B).
Extended under #709 to require and durably log a reason when the
`--no-verify`/`-n` bypass is used, closing the frictionless-bypass gap
identified by the gate-correlation evidence (bypassed commits correlate
with materially higher rework).

Blocks `git commit` (exit 2) unless a `.review-passed` file exists in
cwd with a hash matching the currently staged content. The /code-review
command auto-scopes to uncommitted changes and writes this file when
review passes.

Issue #1461 (raised bar, not full closure): the hash match alone (via
`review_gate_hash()` — see that module's own docstring for the full account)
only proves the staged content is unchanged since `.review-passed` was
written — it does not by itself prove an independent review agent actually
ran, since a caller could compute and write the same hash itself. That gap
was real and observed in production: an orchestrating agent with no
Agent/Task dispatch tool available silently self-applied review checklists
inline instead of hard-failing, then wrote a matching `.review-passed` and
committed/opened a PR off a self-certified pass that a later genuine
multi-agent review showed had missed real defects.

`_evaluate_gate()` now additionally requires the hash-matching write to be
corroborated by `hooks/lib/review_gate_corroboration.py`: >= 2 DISTINCT
registered review-agent dispatches recorded (via `hooks/agent_dispatch_ledger.py`)
in the `WINDOW_SECONDS` recency window before the gate file's own mtime, OR a
contemporaneous doc-only exemption event. This is a materially raised bar —
an agent can no longer merely *write plausible text* to pass the gate, it
must cause the harness to actually dispatch real review-agent types — but
not a cryptographic proof: a sufficiently motivated bypass could still
dispatch trivial/no-op review-agent calls purely to clear the gate without a
substantive review having occurred. Full closure needs harness-level
provenance (e.g. a signed dispatch receipt) outside this repo's control. The
upstream mitigation still matters too: `skills/code-review/SKILL.md`,
`skills/plan/SKILL.md`, and `skills/build/SKILL.md` each hard-require
confirming `Agent`/`Task` tool availability before dispatching any review
agent, and STOP — no self-applied review, no `.review-passed` write — when
that capability is absent.

KNOWN RESIDUAL GAPS (#1461 security re-review), disclosed rather than
silently accepted:

1. `hooks/agent_dispatch_ledger.py` is itself directly executable from Bash
   with a hand-crafted stdin payload — see that module's own docstring for
   the full account. Locking down `boundary_events.py`'s CLI closed one
   forgery path but not this sibling one; genuine harness-level provenance
   (a signed dispatch receipt) is still needed for full closure and is
   outside this repo's control.
2. `git commit -a`/`--all` and pathspec-form commits (e.g. `git commit -am
   ...` or `git commit path/to/file.txt -m ...`) commit tracked-file changes
   that were never staged via `git add` — `_staged_names()` sees an empty
   index and `main()` returns 0 (nothing to gate) before any corroboration
   logic runs, silently skipping this entire mechanism with no bypass-audit
   entry. This is pre-existing (predates #1461) but defeats the dispatch-
   ledger hardening just as completely as the hash-only gate it replaced.
   Tracked as a follow-up rather than fixed here — see the issue filed
   alongside this disclosure.
3. The recency window's anchor (`before_ts`, `.claude/memory/.review-passed`'s
   own mtime) is a filesystem timestamp fully controlled by the same party
   the gate constrains — `os.utime()`/`touch -d` can backdate it without
   touching the file's content or hash. Backdating the anchor into the past
   can shift the `WINDOW_SECONDS` window to overlap an old, otherwise-stale
   genuine dispatch for the SAME subject_hash (e.g. a review of this exact
   content from hours ago, correctly rejected today as stale), re-admitting
   it without any ledger forgery. No fix applied here: the mtime anchor is
   also what lets `test_rewritten_gate_file_anchors_on_its_own_new_mtime_not_
   original_dispatch` simulate time passage hermetically (without a real
   `sleep`), so switching to wall-clock `now()` isn't a drop-in improvement —
   it would need a redesign of that test contract too.
4. The `staged is None` fail-closed check runs BEFORE `has_bypass_flag()` in
   `main()`, so a gate-setup failure (corrupt/locked git index) also blocks
   the audited `GATE_BYPASS_REASON` escape hatch — unlike the sibling
   mkdir/hash-resolution failure further down, which still allows the
   audited bypass. Errs toward blocking, never toward a silent allow, but
   the two `gate-setup-failure` sites are inconsistent about whether the
   sanctioned escape stays reachable. Not restructured here to avoid
   weakening the fail-closed guarantee under time pressure.
5. `evidence.same_subject_dispatch_ever` in `review_gate_corroboration.py`
   is computed before the live-registry filter, so a same-subject,
   in-window dispatch whose `matched_rule` is no longer a registered agent
   (renamed/removed) reports `_STALE_MESSAGE` ("outside the window")
   instead of a more accurate "review agent no longer registered" message.
   The gate decision itself is still correctly fail-closed; only the
   operator-facing message and the `dispatch-evidence-stale` audit rule are
   imprecise in this one edge case.

Non-commit Bash commands pass through immediately (exit 0).
`git commit --no-verify` (or bare `-n`) is still allowed through — but
only when the process environment carries a non-empty `GATE_BYPASS_REASON`.
When present, the bypass is appended as one line to
`.claude/metrics/gate-bypass-audit.jsonl` (unconditional — not gated by
`DEV_TEAM_TELEMETRY`) and the commit proceeds. When absent, the commit is
blocked with a message naming `GATE_BYPASS_REASON` as the required
mechanism.

Contract (docs/python-hook-contract.md):
    Input : JSON on stdin (Claude Code PreToolUse:Bash payload)
    Exit 0: allow the tool call
    Exit 2: block the tool call (feedback returned to Claude on stdout,
            mirrored to stderr — some hook-error wrappers only surface
            stderr, and a stdout-only block message was going unseen)

Stdlib-only. Python 3.8+.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_HOOK_DIR = Path(__file__).resolve().parent
_LIB_DIR = _HOOK_DIR / "lib"

sys.path.insert(0, str(_LIB_DIR))
try:
    from artifact_paths import (
        resolve_file as _resolve_file,  # type: ignore[import-not-found]
    )
    from boundary_events import (  # type: ignore[import-not-found]
        emit_boundary_event as _emit_boundary_event,
    )
    from pre_commit_detect import (  # type: ignore[import-not-found]
        bypass_flag_name,
        has_bypass_flag,
        is_git_commit_command,
    )
    from review_gate_corroboration import (  # type: ignore[import-not-found]
        evaluate as _evaluate_ledger,
    )
    from review_gate_corroboration import (  # type: ignore[import-not-found]
        has_doc_only_exemption as _has_doc_only_exemption,
    )
    from review_gate_corroboration import (  # type: ignore[import-not-found]
        has_single_agent_exemption as _has_single_agent_exemption,
    )
    from review_gate_corroboration import (  # type: ignore[import-not-found]
        mtime_to_iso as _mtime_to_iso,
    )
    from review_gate_hash import review_gate_hash  # type: ignore[import-not-found]
    from stdin_json import read_stdin_json  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover

    def _resolve_file(  # type: ignore[misc]
        category: str, filename: str, root=None, migrate: bool = True
    ) -> Path:
        # Degraded-import fallback (artifact_paths itself failed to import).
        # The bare `Path(category) / filename` this used to return is the
        # exact bare-relative-path bug Step 4.4 fixed for the normal path —
        # reproduce that fix's `.claude/<category>/<filename>` shape here
        # too. `parents[3]` walks up from
        # `plugins/dev-team/hooks/pre_commit_review.py` to this repo's
        # root (hooks -> dev-team -> plugins -> repo root).
        repo_root = Path(__file__).resolve().parents[3]
        return repo_root / ".claude" / category / filename

    def is_git_commit_command(_: str) -> bool:  # type: ignore[misc]
        return False

    def has_bypass_flag(_: str) -> bool:  # type: ignore[misc]
        return False

    def bypass_flag_name(_: str) -> str | None:  # type: ignore[misc]
        return None

    def review_gate_hash(cwd=None) -> str:  # type: ignore[misc]
        return ""

    def read_stdin_json() -> dict | None:  # type: ignore[misc]
        return None

    def _emit_boundary_event(*_args, **_kwargs) -> None:  # type: ignore[misc]
        return None

    class _DegradedLedgerEvidence:  # type: ignore[misc]
        """Degraded-import stand-in for `review_gate_corroboration.LedgerEvidence`.

        A failed import means this module can't corroborate anything —
        fails CLOSED the same way the real module does on a read failure,
        reported as "unreadable" so the caller's rejection message points
        at an infra problem rather than implying no review happened.
        """

        agents_in_window: frozenset = frozenset()
        any_dispatch_ever = False
        same_subject_dispatch_ever = False
        read_failure_reason = "unreadable"

    def _evaluate_ledger(cwd, before_ts, window_seconds, subject_hash):  # type: ignore[misc]
        return _DegradedLedgerEvidence()

    def _has_doc_only_exemption(  # type: ignore[misc]
        cwd, before_ts, window_seconds, subject_hash
    ) -> bool:
        return False

    def _has_single_agent_exemption(  # type: ignore[misc]
        cwd, before_ts, window_seconds, subject_hash
    ) -> bool:
        return False

    def _mtime_to_iso(mtime: float) -> str:  # type: ignore[misc]
        return datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def emit_boundary_event(*args, **kwargs) -> None:
    """Local safety net (#859): even a misbehaving helper must never affect
    this hook's exit code, stdout, or stderr."""
    try:
        _emit_boundary_event(*args, **kwargs)
    except Exception:  # noqa: BLE001, S110 - fail-open by design
        pass


_BLOCK_MESSAGE = (
    "BLOCKED: Code review required before committing.\n"
    "\n"
    "Run /code-review to review staged files.\n"
    "If review passes, the commit will be allowed on the next attempt.\n"
    "\n"
    "To bypass: use git commit --no-verify\n"
)

_BYPASS_BLOCK_MESSAGE = (
    "BLOCKED: git commit --no-verify (or -n) requires a reason.\n"
    "\n"
    "Set GATE_BYPASS_REASON to a non-empty explanation and retry, e.g.:\n"
    '  GATE_BYPASS_REASON="hotfix, review to follow" git commit --no-verify -m ...\n'
    "\n"
    "The bypass is logged to .claude/metrics/gate-bypass-audit.jsonl once a\n"
    "reason is supplied.\n"
)

# Recency window (#1461): how far back before the gate file's own mtime a
# genuine review-agent dispatch still counts as corroborating evidence.
# Pinned at 30 minutes — generous enough to cover a real multi-agent
# /code-review pass's typical wall-clock duration without inviting stale
# evidence to satisfy the gate long after the fact. See the plan's Risks &
# Open Questions section for the rationale; not a tunable env var — a fixed
# security-relevant constant.
WINDOW_SECONDS = 1800

# Minimum number of DISTINCT registered review-agent dispatches required in
# the recency window (#1461). code-review/SKILL.md's change-size gate keeps
# at least 4 agents (security-review, correctness-review,
# spec-compliance-review, doc-review) even on its narrowest fast-path run, so
# a legitimately small, non-doc-only change already clears this bar under
# existing behavior. A sanctioned single-agent run (`--agent <name>`) is
# exempted separately below, since it deliberately dispatches exactly 1.
_MIN_DISTINCT_DISPATCHES = 2

# Pinned rejection message templates (#1461 plan) — each names the problem
# and ends in a stated next action. The hash-mismatch message (_BLOCK_MESSAGE
# above) is unchanged/untouched; these four are additive, dispatch-ledger-
# corroboration-specific rejections.
_NO_DISPATCH_MESSAGE = (
    f"BLOCKED: No genuine review-agent dispatch found in the last "
    f"{WINDOW_SECONDS}s — run /code-review before committing.\n"
)

_STALE_MESSAGE = (
    f"BLOCKED: Review-agent dispatch evidence found but outside the "
    f"{WINDOW_SECONDS}s window — run /code-review again before committing.\n"
)

# Distinct from _STALE_MESSAGE (#1461 second security re-review, correctness
# finding): _STALE_MESSAGE means "a genuine dispatch for THIS content
# happened, just too long ago" — this means "genuine dispatches exist, but
# only for DIFFERENT staged content" (the diff changed since that review).
# Conflating the two under _STALE_MESSAGE told the operator to wait/re-run
# for a staleness problem they didn't have, without naming the actual cause
# (the staged content changed).
_DIFFERENT_CONTENT_MESSAGE = (
    "BLOCKED: Review-agent dispatch evidence found, but for different "
    "staged content (the diff changed since that review) — run "
    "/code-review again before committing.\n"
)

_READ_FAILURE_MESSAGE = (
    "BLOCKED: Could not read the dispatch ledger "
    "(.claude/metrics/boundary-events.jsonl) — check hook registration; "
    "this is an infra problem, not evidence that no review happened.\n"
)

# Distinct from _READ_FAILURE_MESSAGE (#1461 security re-review, A09
# finding): the ledger read failure above means "the gate decision itself
# ran, but couldn't read the corroboration evidence"; this one means "the
# hook couldn't even determine the gate's own preconditions" — resolving
# the staged-file list or the gate-file path failed (a corrupt/locked git
# index, a `.claude/memory` path that exists as a non-directory, a
# read-only project tree). Reporting both under one rule ID would
# mislabel every gate-path-setup failure as a ledger problem in the audit
# trail (`.claude/metrics/boundary-events.jsonl` itself), pointing anyone
# reading it at the wrong file to fix.
_GATE_SETUP_FAILURE_MESSAGE = (
    "BLOCKED: Could not determine the review-gate's own state (staged "
    "files or the .claude/memory/.review-passed path) — check that "
    ".claude/memory is a writable directory and the git index is healthy; "
    "this is an infra problem, not evidence that no review happened.\n"
)


# Re-derives the doc-only exemption's OWN predicate on the verifier side
# (#1461 security review) rather than trusting the claim in the ledger
# event: `--event doc-only` (boundary_events.py) is written by the SAME
# untrusted party this gate exists to constrain, so an unconditional "the
# event exists, therefore trust it" check is the classic trust-the-client
# pattern — nothing previously verified the exempted diff was actually
# documentation.
#
# Deliberately a TIGHTER re-implementation of `code-review/SKILL.md`'s
# doc-only short-circuit and `skills/code-review/scripts/change_shape.py`'s
# `_is_documentation` (duplicated, not imported — scripts/ is not a
# dependency hooks/ should take on), not a lockstep copy (#1461 second
# security re-review found the original copy exploitable): those two only
# ever ADD a review lens or skip everything on already-honest input; this
# function is the sole gate deciding whether a "record zero dispatch
# evidence" exemption is honored at all, so it must be a STRICT SUBSET of
# what SKILL.md/change_shape.py would call documentation, never a superset.
# Concretely: (1) a root-doc EXACT NAME (README, LICENSE, ...) only counts
# at the repository root (`len(parts) == 1`) AND only when the stem carries
# NO extension at all — `license_manager.py` staged at the repo root must
# never match merely because its basename starts with "license", and
# (#1461 FOURTH security re-review) `license-check` or `readme-lint` must
# never match either, despite also being extensionless: an earlier fix
# used `stem.startswith(prefix)`, which still admitted any extensionless
# name merely beginning with a root-doc prefix. Exact membership in
# `_DOC_ROOT_NAMES` is the only form that matches this comment's own
# stated intent ("the genuinely extensionless case: LICENSE, NOTICE,
# AUTHORS") — a `README.txt`-shaped file is already covered by the
# `_DOC_EXTENSIONS` branch above, so this branch exists ONLY for those
# exact extensionless root docs, nothing glob-shaped; (2) a `docs/`
# directory membership alone is NOT sufficient — a doc extension is still
# required, since `docs/conf.py` or a doc-site build script is executable
# code that happens to live under `docs/`. Path segments are lower-cased
# once, matching the stem, so a case-insensitive checkout (`Agents/foo.md`,
# `.Claude/x.md`) can't escape the functional-config exclusion below by case
# alone. `_FUNCTIONAL_CONFIG_SEGMENTS`'s bare `"agents"` entry already
# matches `templates/agents/`, and any other `.../agents/...` path, exactly
# per `code-review/SKILL.md`'s literal stated rule — no separate
# templates-specific helper is needed. If this rule ever needs to change,
# change it here first and only loosen the lens-narrowing siblings to
# match — never the reverse.
_DOC_EXTENSIONS = {".md", ".mdx", ".markdown", ".rst", ".txt", ".adoc"}
_DOC_ROOT_NAMES = {
    "readme", "changelog", "contributing", "license", "notice",
    "authors", "code_of_conduct",
}
_FUNCTIONAL_CONFIG_SEGMENTS = {".claude", "agents", "skills", "prompts", "knowledge"}
_FUNCTIONAL_CONFIG_NAMES = {"claude.md", "agents.md"}

# `.txt` is in `_DOC_EXTENSIONS` for real plain-text docs (README.txt), but a
# `.txt`/`.md`-shaped dependency manifest or build file is executable/
# supply-chain surface, not documentation (#1461 fourth security re-review) —
# denylisted by exact name regardless of matching a doc extension above.
_NON_DOC_NAMES_DESPITE_EXTENSION = {
    "requirements.txt", "requirements-dev.txt", "constraints.txt",
    "cmakelists.txt",
}
# Same denylist, by directory instead of exact basename (#1461 fifth
# security re-review): the common multi-file pip layout
# (`requirements/base.txt`, `constraints/pins.txt`) escapes the exact-name
# check above while still matching `_DOC_EXTENSIONS`.
_NON_DOC_DIR_SEGMENTS = {"requirements", "constraints"}


def _is_doc_only_changeset(files: list[str]) -> bool:
    """True only when EVERY given path is provably documentation and none is
    functional Claude-config markdown. An empty list — or a list whose every
    entry is blank/unusable — is not doc-only: there is nothing to exempt,
    so this must never vacuously pass."""
    saw_any = False
    for raw in files:
        name = raw.strip()
        if not name:
            continue
        parts = [p.lower() for p in name.replace("\\", "/").split("/") if p]
        if not parts:
            continue
        saw_any = True
        stem = parts[-1]
        suffix = "." + stem.rsplit(".", 1)[-1] if "." in stem else ""
        in_non_doc_dir = suffix in _DOC_EXTENSIONS and any(
            seg in _NON_DOC_DIR_SEGMENTS for seg in parts[:-1]
        )
        if (
            stem in _FUNCTIONAL_CONFIG_NAMES
            or stem in _NON_DOC_NAMES_DESPITE_EXTENSION
            or in_non_doc_dir
            or any(seg in _FUNCTIONAL_CONFIG_SEGMENTS for seg in parts)
        ):
            return False
        if suffix in _DOC_EXTENSIONS:
            continue
        # A root-doc EXACT NAME (README, LICENSE, ...) only counts at the
        # repo root — never at any depth, never with an extension, and
        # never merely as a name PREFIX (`license-check` is not "license").
        if len(parts) == 1 and stem in _DOC_ROOT_NAMES:
            continue
        return False
    return saw_any


def _insufficient_message(n: int) -> str:
    return (
        f"BLOCKED: Only {n} distinct review agent(s) dispatched (need >= "
        f"{_MIN_DISTINCT_DISPATCHES}) — run /code-review before committing.\n"
    )


def _emit_block(message: str) -> None:
    """Write a block message to both stdout and stderr (#1367).

    Stdout stays the canonical UI channel; stderr is mirrored because some
    hook-error wrappers surface only stderr on a nonzero hook exit.
    """
    sys.stdout.write(message)
    sys.stderr.write(message)


def _staged_names(cwd: str | None = None) -> list[str] | None:
    """Return the staged file list, or `None` when git could not be asked at
    all (#1461 security re-review, correctness finding): a `None` return
    means "couldn't determine", a `[]` return means "genuinely nothing
    staged" — `main()` must fail CLOSED on the former and only silently
    pass through on the latter. A broad `except Exception` (not just
    `FileNotFoundError`/`OSError`) is deliberate here: any unexpected
    failure to even run `git` must be reported as "couldn't determine",
    never silently folded into "nothing staged"."""
    try:
        completed = subprocess.run(
            # `-c diff.relative=false` (#1461 third security re-review): a
            # repo/global `diff.relative=true` config silently scopes and
            # relativizes `git diff` output to the invocation's cwd,
            # truncating this list when the hook runs from a subdirectory.
            # `--ignore-submodules=none` (#1461 fifth security re-review —
            # a `-c diff.ignoreSubmodules=none` default was tried first and
            # found insufficient: it's overridden by a per-submodule
            # `submodule.<name>.ignore`, including one shipped in a
            # COMMITTED `.gitmodules`, which needs no local config-write
            # access). Without the command-line form, a staged
            # submodule-pointer-only change (importing arbitrary
            # third-party code) is omitted from this list entirely, routing
            # it through `main()`'s "nothing staged" path with no gate
            # evaluation at all. `review_gate_hash()` pins the same
            # override for the same reason, so the two functions stay in
            # agreement.
            [
                "git",
                "-c", "diff.relative=false",
                "diff", "--cached", "--name-only", "--ignore-submodules=none",
            ],
            cwd=cwd or None,
            capture_output=True,
            check=False,
            text=True,
        )
    except Exception:  # noqa: BLE001 - "couldn't determine", not "nothing staged"
        return None
    if completed.returncode != 0:
        return None
    return [line for line in completed.stdout.splitlines() if line]


def _current_branch(cwd: str | None = None) -> str:
    try:
        completed = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=cwd or None,
            capture_output=True,
            check=False,
            text=True,
        )
    except (FileNotFoundError, OSError):
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def _plugin_version() -> str:
    manifest = _HOOK_DIR / ".." / ".claude-plugin" / "plugin.json"
    try:
        data = json.loads(manifest.read_text())
        version = data.get("version")
        if isinstance(version, str) and version:
            return version
    except (OSError, ValueError):
        pass
    return "unknown"


def _record_bypass_audit(flag: str, reason: str, staged_count: int, cwd: str) -> None:
    """Append one accountability line to <project-root>/.claude/metrics/gate-bypass-audit.jsonl.

    Unconditional (not gated by DEV_TEAM_TELEMETRY) — mirrors the existing
    metrics/override-audit.jsonl precedent for a bypass a human/agent
    actively chose, not passive usage telemetry.

    Resolves against `cwd` (the payload's project cwd) via the shared
    artifact_paths helper — not a bare relative path, which previously
    resolved against the process's real OS cwd and could disagree with the
    project root when this hook is invoked from a subdirectory. Fail-open:
    any failure to resolve the path, create the directory, or write the
    line logs a diagnostic to stderr and never blocks the commit.
    """
    entry = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "branch": _current_branch(cwd),
        "triggeredBy": flag,
        "reason": reason,
        "stagedFileCount": staged_count,
        "pluginVersion": _plugin_version(),
    }
    try:
        audit_log_path = _resolve_file("metrics", "gate-bypass-audit.jsonl", cwd)
        audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(audit_log_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, separators=(",", ":")) + "\n")
    except OSError as exc:
        sys.stderr.write(f"[pre_commit_review] failed to record bypass audit: {exc}\n")


class GateVerdict:
    """One evaluated outcome of `_evaluate_gate`: whether the gate passes,
    and — when it doesn't — the message and `matched_rule` to report."""

    __slots__ = ("passed", "message", "matched_rule")

    def __init__(self, passed: bool, message: str = "", matched_rule: str = "") -> None:
        self.passed = passed
        self.message = message
        self.matched_rule = matched_rule


def _evaluate_gate(
    gate_file: Path, current_hash: str, cwd: str, staged: list[str]
) -> GateVerdict:
    """Decide whether `.review-passed` corroborates a genuine, recent,
    multi-agent review (#1461) — extracted from `main()` so the decision
    logic is unit-testable independent of stdin/subprocess plumbing.

    `staged` is `main()`'s own already-computed staged-file list (#1461
    fifth structure re-review) — this function used to re-derive it with a
    second `_staged_names(cwd)` call (a second `git diff --cached` per
    commit) for data the caller already had. Passing it through is cheaper
    and correct for every non-concurrent path; it does shift *when* the
    doc-only exemption's file list is sampled to slightly before, rather
    than slightly after, `review_gate_hash(cwd)`'s own read — a difference
    that only matters under concurrent staging in the same working tree,
    already dominated by the pre-existing commit-time TOCTOU this module's
    KNOWN RESIDUAL GAPS block discloses (item 2, `git commit -a`).

    The existing hash-match check is preserved unchanged and evaluated
    FIRST, independent of dispatch-ledger evidence — a hash mismatch (or a
    missing/unreadable gate file) always rejects with the original,
    untouched `_BLOCK_MESSAGE`/`"pre-commit-review"` rule, regardless of how
    much genuine dispatch evidence exists (Gherkin: "Gate still rejects on
    hash mismatch even with ample genuine dispatch evidence"). Only once the
    hash matches does this function consult the dispatch ledger — as
    additive corroboration, never a substitute for the hash check.
    """
    if not gate_file.is_file():
        return GateVerdict(False, _BLOCK_MESSAGE, "pre-commit-review")
    try:
        stored = gate_file.read_text().strip()
    except OSError:
        stored = ""
    if not stored or stored != current_hash:
        return GateVerdict(False, _BLOCK_MESSAGE, "pre-commit-review")

    # Hash matches — everything from here on is the dispatch-ledger
    # corroboration path (#1461 security review): wrapped in its own
    # exception handler so this stays fail-CLOSED on any unexpected error
    # (a stat race if the gate file is unlinked between is_file() and
    # stat(), an out-of-range mtime, a malformed timestamp, a MemoryError
    # from an oversized ledger, ...) — none of those should silently fall
    # through to main()'s top-level `except Exception: sys.exit(0)`, which
    # would convert a should-reject into an allow. Contrast with
    # `emit_boundary_event`'s write-side fail-open: this is the read/verdict
    # side, and it must never let "something went wrong evaluating
    # corroboration" look the same as "corroboration passed".
    try:
        # Anchor the recency window on the gate file's OWN mtime, not "when
        # the diff was staged" (git has no such native value). A later
        # rewrite of .review-passed (new mtime, no fresh dispatch) is
        # therefore evaluated against ITS OWN new anchor, never the original
        # write's — so a hash rewrite alone is never itself dispatch
        # evidence.
        before_ts = _mtime_to_iso(gate_file.stat().st_mtime)

        evidence = _evaluate_ledger(cwd, before_ts, WINDOW_SECONDS, current_hash)
        if evidence.read_failure_reason is not None:
            return GateVerdict(False, _READ_FAILURE_MESSAGE, "dispatch-ledger-read-failure")

        n = len(evidence.agents_in_window)

        # Doc-only exemption (#1461 security review): the ledger event alone
        # is a self-asserted claim from the same party the gate constrains —
        # re-derive the predicate here against the ACTUAL staged files
        # before honoring it. A claimed-but-unproven exemption does not
        # block outright; it just falls through to the normal dispatch-
        # evidence requirement below, same as if no exemption were claimed.
        if _has_doc_only_exemption(
            cwd, before_ts, WINDOW_SECONDS, current_hash
        ) and _is_doc_only_changeset(staged):
            return GateVerdict(True)

        # Single-agent exemption: the sanctioned `--agent <name>` path
        # deliberately dispatches exactly 1 review agent, which can never
        # clear the `>= 2` floor on its own — but it must still have
        # dispatched at least 1 genuine, corroborated agent (#1461 security
        # review). Requiring `n >= 1` here closes the gap where the
        # exemption event alone, with zero dispatch evidence, passed the
        # gate for an arbitrary changeset.
        if n >= 1 and _has_single_agent_exemption(
            cwd, before_ts, WINDOW_SECONDS, current_hash
        ):
            return GateVerdict(True)

        if n >= _MIN_DISTINCT_DISPATCHES:
            return GateVerdict(True)
        if n >= 1:
            return GateVerdict(
                False, _insufficient_message(n), "dispatch-evidence-insufficient"
            )
        if evidence.same_subject_dispatch_ever:
            return GateVerdict(False, _STALE_MESSAGE, "dispatch-evidence-stale")
        if evidence.any_dispatch_ever:
            return GateVerdict(
                False, _DIFFERENT_CONTENT_MESSAGE, "dispatch-evidence-different-content"
            )
        return GateVerdict(False, _NO_DISPATCH_MESSAGE, "dispatch-evidence-missing")
    except Exception:  # noqa: BLE001 - fail CLOSED: an unexpected error is not a pass
        return GateVerdict(False, _READ_FAILURE_MESSAGE, "dispatch-ledger-read-failure")


def main() -> int:
    payload = read_stdin_json()
    if payload is None:
        return 0

    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0
    command = str(tool_input.get("command") or "")

    cwd = payload.get("cwd") or "."
    session_id = payload.get("session_id")

    if not is_git_commit_command(command):
        return 0

    # Resolved with the payload's own `cwd` (#1461 security review) — a bare
    # `git diff --cached` without `cwd=` runs against this process's real OS
    # cwd, which can silently disagree with the payload's project root when
    # this hook is invoked from a subdirectory. Before this fix, that
    # divergence meant `_staged_names()` could return `[]` (nothing staged
    # in the process's cwd) even though the payload's project root had a
    # real staged commit in flight — silently skipping the entire review
    # gate, corroboration included, with no audit trail at all.
    staged = _staged_names(cwd)
    # `None` means git itself could not answer this question (corrupt/locked
    # index, bad cwd, ...) — that must fail CLOSED, never be folded into
    # "nothing staged" (#1461 security re-review): a should-block commit
    # must not slip through just because the precondition check itself
    # broke.
    if staged is None:
        _emit_block(_GATE_SETUP_FAILURE_MESSAGE)
        emit_boundary_event(
            cwd, "pre_commit_review", "Bash", "block", "gate-setup-failure", session_id
        )
        return 2
    # Genuinely nothing staged → nothing to gate.
    if not staged:
        return 0

    if has_bypass_flag(command):
        flag = bypass_flag_name(command) or "--no-verify"
        reason = os.environ.get("GATE_BYPASS_REASON", "").strip()
        if reason:
            _record_bypass_audit(flag, reason, len(staged), cwd)
            emit_boundary_event(
                cwd, "pre_commit_review", "Bash", "bypass", flag, session_id
            )
            return 0
        _emit_block(_BYPASS_BLOCK_MESSAGE)
        return 2

    # Everything from here to `verdict = ...` is wrapped in its own
    # exception handler (#1461 security review) so a failure resolving or
    # preparing the gate path can never escape to this module's top-level
    # `except Exception: sys.exit(0)` in `__main__` — that top-level handler
    # exists to protect against a bug in the pre-detection stdin/argument
    # plumbing above, not to swallow a failure in the actual gate decision.
    # Before this fix, `gate_file.parent.mkdir(...)` ran unguarded: a
    # `.claude/memory` path that exists as a regular file (not a directory),
    # or a read-only project tree, raised `FileExistsError`/
    # `NotADirectoryError`/`PermissionError` here, which propagated straight
    # past `_evaluate_gate`'s own fail-closed try/except (never entered) to
    # the top-level fail-open — deterministically turning a should-block
    # commit into an allow, with no gate file written and no bypass-audit
    # entry recorded at all.
    try:
        current_hash = review_gate_hash(cwd)

        # Resolved via the shared artifact_paths helper (#1461 security
        # review), not a bare relative path — the latter resolves against
        # the process's real OS cwd, which can silently disagree with `cwd`
        # (the payload's project root) when this hook runs from a
        # subdirectory. This now matters beyond cosmetics: the gate file's
        # mtime anchors the dispatch-ledger recency window, and the ledger
        # itself resolves through this same helper — a root mismatch here
        # would let the two silently compare against different projects.
        gate_file = _resolve_file("memory", ".review-passed", cwd)
        gate_file.parent.mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001 - fail CLOSED: setup failure is not a pass
        _emit_block(_GATE_SETUP_FAILURE_MESSAGE)
        emit_boundary_event(
            cwd,
            "pre_commit_review",
            "Bash",
            "block",
            "gate-setup-failure",
            session_id,
        )
        return 2

    verdict = _evaluate_gate(gate_file, current_hash, cwd, staged)
    if verdict.passed:
        # Review passed for these exact files, corroborated by genuine
        # dispatch evidence (or a doc-only exemption) — consume + allow.
        try:
            gate_file.unlink()
        except OSError:
            pass
        return 0

    # Block. Message goes to stdout (matching the .sh's `printf` — the .sh
    # writes to stdout, not stderr, so Claude sees it in the tool-call
    # feedback stream).
    _emit_block(verdict.message)
    emit_boundary_event(
        cwd, "pre_commit_review", "Bash", "block", verdict.matched_rule, session_id
    )
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 - fail-open: a hook bug must never block a commit
        sys.exit(0)
