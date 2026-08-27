"""Transcript path classification and enumeration (issue #2042, epic #2040).

Answers one question: given a ``~/.claude/projects``-shaped tree, which
``.jsonl`` files under it are transcripts this extraction pipeline reads, and
which of those belong to a dispatched agent's own run rather than a
main-thread session.

Reconciliation (issue #2042):

- ``is_transcript_path`` was already byte-identical between
  ``scripts/session_extract.py`` and
  ``plugins/dev-team/scripts/extract_session_report.py`` — moved verbatim.
- ``is_subagent_transcript`` was semantically equivalent but structurally
  divergent (0.22 similarity between the two copies). This module keeps the
  shipped (``extract_session_report.py``) copy's shape: it factors out
  ``relative_parts`` — the path's components below the root, with a
  ``path.parts`` (not ``False``) fallback when the path isn't actually under
  the root — and both original bodies computed exactly
  ``"subagents" in <that>``, so behavior is unchanged.
- ``_AGENT_TRANSCRIPT_RE`` is grouped under the classify.py 14-symbol list in
  ADR 0036 / issue #2043, but it is used ONLY inside ``is_transcript_path``
  above, which landed here in slice #2042 — so it lands here too rather than
  being duplicated into classify.py. Issue #2043's commit body notes this
  explicitly rather than silently deviating from the ADR's grouping.
"""

from __future__ import annotations

import re
from pathlib import Path

# Agent transcripts are named `agent-<id>.jsonl` (see is_transcript_path).
AGENT_TRANSCRIPT_RE = re.compile(r"^agent-[0-9A-Za-z_-]{1,64}\.jsonl$")


def relative_parts(root: Path, path: Path) -> tuple[str, ...]:
    """The path's components BELOW `root`.

    Every layout question here is about the tree under the root, so never ask
    it of the absolute path: `root` defaults to `~/.claude/projects` and
    carries the user's home directory, so a matching segment anywhere in that
    prefix would answer for the whole tree."""
    try:
        return path.relative_to(root).parts
    except ValueError:
        return path.parts


def is_transcript_path(root: Path, path: Path) -> bool:
    """Whether a `.jsonl` under `root` is a transcript this extractor reads.

    Decided by DEPTH, not by filename shape. A `.jsonl` sitting directly in a
    project directory is a main-thread session whatever it is called — the
    harness uses `<sessionId>.jsonl`, but nothing guarantees that and a
    name-shape filter silently drops any session that differs, which is a
    worse failure than the one it prevents.

    Below `subagents/` the rule tightens, because that is the only place the
    harness writes NON-transcript bookkeeping next to transcripts:
    `subagents/workflows/<runId>/journal.jsonl` holds `{"type", "key",
    "agentId"}` records with no `cwd`. Counting it as an agent run inflated the
    run tally and, having no `cwd`, sent project labelling down a fallback that
    leaked a path-derived slug (#1991). Agent transcripts are `agent-<id>.jsonl`.
    """
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return False
    if len(parts) < 2:
        return False
    if "subagents" in parts:
        return bool(AGENT_TRANSCRIPT_RE.match(path.name))
    return len(parts) == 2


def is_subagent_transcript(root: Path, path: Path) -> bool:
    """A dispatched agent's own run, at any nesting depth below `root`.

    A plain Agent dispatch writes `<project>/<sessionId>/subagents/agent-*.jsonl`;
    a Workflow's agents nest one level further under `subagents/workflows/<runId>/`.
    Ask the path BELOW the root: `root` defaults to `~/.claude/projects` and
    carries the user's home directory, so a matching segment in that prefix
    would answer for the whole tree.
    """
    return "subagents" in relative_parts(root, path)


def sorted_paths(paths) -> list[Path]:
    """Total order over transcript paths. Sorting on `Path.name` alone is not
    a total order once subagent transcripts (a second directory level) are in
    the mix — sort on the full path string instead, which both extractors'
    determinism guarantee (byte-identical output for the same inputs)
    depends on."""
    return sorted(paths, key=lambda p: str(p))


def all_transcripts(root: Path) -> list[Path]:
    """Every transcript under `root`, main-thread and subagent alike.

    Globbing only `*/*.jsonl` made every dispatched agent invisible (#1990) —
    silently, since subagent records ARE marked `isSidechain: true`; they simply
    live in files nothing opened. Recurse rather than enumerate known depths.
    """
    return sorted_paths(
        p
        for p in root.glob("*/**/*.jsonl")
        if p.is_file() and not p.is_symlink() and is_transcript_path(root, p)
    )
