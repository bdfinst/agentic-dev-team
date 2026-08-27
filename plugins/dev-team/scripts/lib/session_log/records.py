"""JSONL record iteration and the ``usage``-block read contract (issue
#2042, epic #2040).

Usage-block contract: today nine modules across this repo read a
transcript's ``usage`` block with four different idioms —

  1. ``usage.get(field, 0) or 0``          -> 0 on missing key AND on null
  2. ``usage.get(field) or 0``              -> 0 on missing key AND on null
  3. ``usage.get(field, 0)``                -> 0 on missing key, but a
                                                PRESENT-and-null value
                                                survives as `None`
  4. ``usage[field]``                       -> raises `KeyError` on a
                                                missing key

``usage_field`` below is idiom 1/2 (they are equivalent) — the idiom already
used by BOTH extractors' own ``_accumulate_token_signals``/``_cost`` before
this package existed, so choosing it keeps golden output byte-identical
(#2042 acceptance criterion).

Why this one, not idiom 3 or 4: a real Claude Code transcript legitimately
omits a usage field two different ways. A `thinking`-only assistant message
carries no `usage` key at all (the corpus's record #2 in
`tests/fixtures/session_log/projects/.../99999999….jsonl`). A model turn
that doesn't support prompt caching has been observed to emit the field
explicitly as `usage: {"cache_creation_input_tokens": null, ...}` rather
than omitting the key (the corpus's record #3). Both cases mean the same
thing — "this field was not populated, count it as zero" — never a
legitimate non-zero value inferred from its absence. Idiom 3 would leave a
`None` sitting in an accumulator the moment a null-but-present field is hit,
raising a `TypeError` the next time arithmetic touches it (`+=`, `/ 1e6`).
Idiom 4 would abort the WHOLE extraction on the first transcript missing any
field — observed on real transcripts, not hypothetical. Idiom 1/2 is the
only one of the four that treats "missing" and "null" identically, which is
the behavior a `usage` block actually needs.
"""

from __future__ import annotations

import json
from pathlib import Path

#: The four fields every extractor's token accounting reads from a usage
#: block, in the order both extractors already declared them.
USAGE_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)


def iter_file_records(path: Path):
    """Yield every decodable JSON record in one transcript file, in order.

    Streams line by line rather than `read_text().splitlines()`: transcripts
    run to tens of MB and a recursive scan can visit thousands of them, where
    slurping costs ~3x the file's size in peak RSS before yielding anything.
    `ValueError` is caught alongside `OSError` because `UnicodeDecodeError`
    is a `ValueError` — a transcript truncated mid-character by a crashed
    session must not abort the whole run. `extract_session_report.py`'s
    pre-#2042 copy of this function caught only `OSError`; `session_extract.py`'s
    copy already had the wider catch (#1994 review) — this module keeps the
    wider, safer one for both callers."""
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


def usage_of(record: dict) -> dict | None:
    """Resolve one record's usage block: `message.usage` if it's a dict,
    else the record's own top-level `usage` if THAT's a dict, else `None`.
    Both extractors' `extract()` loops used this exact resolution order
    already — moved verbatim, not changed."""
    msg = record.get("message") if isinstance(record.get("message"), dict) else {}
    if isinstance(msg.get("usage"), dict):
        return msg["usage"]
    if isinstance(record.get("usage"), dict):
        return record["usage"]
    return None


def usage_field(usage: dict, field: str) -> int | float:
    """The one canonical reader for a single usage field. See module
    docstring for the chosen null-handling contract."""
    return usage.get(field, 0) or 0


def usage_fields(usage: dict) -> dict[str, int | float]:
    """Every `USAGE_FIELDS` entry read through `usage_field`, in order."""
    return {f: usage_field(usage, f) for f in USAGE_FIELDS}


def slim_by_name(mapping: dict) -> dict:
    """Sort a name-keyed dict of Counters into a deterministic, digest-ready
    shape: outer keys sorted, and each inner Counter's keys sorted too.
    Shared by `session_extract.py`'s `by_model`/`by_skill` and
    `extract_session_report.py`'s `by_model` — both built this exact shape
    independently (the former as a dedicated `_slim` helper, the latter
    inline)."""
    return {k: dict(sorted(v.items())) for k, v in sorted(mapping.items())}


# --- issue #2050: sidechain/attribution primitives, made public -----------
#
# `hooks/lib/cost_meter.py`, `hooks/context_ceiling_guard.py`, and
# `scripts/measure_full_file_duplication.py` each independently read the
# harness's `isSidechain`/`attributionAgent` fields and (`cost_meter.py`/
# `measure_full_file_duplication.py`) the Task/Agent-dispatch join. Folded
# here so `skills/code-review/scripts/repo_invariants.py`'s
# `check_transcript_parsing_confined_to_session_log` (#2048) has one real
# home to point at instead of three independent copies.

#: Tool names the harness uses for subagent dispatch (both spellings appear
#: in real transcripts depending on harness version).
TASK_TOOL_NAMES = ("Task", "Agent")


def is_sidechain(record: dict) -> bool:
    """True for a subagent (sidechain) transcript record — the native
    top-level `isSidechain` flag, true on subagent/sidechain turns under
    the older inline-record harness layout."""
    return bool(record.get("isSidechain"))


def attribution_agent_of(record: dict) -> str | None:
    """The record's own `attributionAgent` value when it's a string
    (possibly empty), else `None`. Deliberately does not filter on
    truthiness here — callers that require a non-empty value check it
    themselves (`agent_type_for` below does; a caller collecting the first
    attribution seen across a file, so it can prefer a later non-empty one,
    does not)."""
    value = record.get("attributionAgent")
    return value if isinstance(value, str) else None


def join_dispatch_agent_ids(
    record: dict, dispatch_types: dict[str, str], agent_types: dict[str, str]
) -> None:
    """Fold one record's subagent-dispatch metadata into the two join maps,
    in place.

    Two harness-recorded halves of the join (#1094):
      * an assistant `tool_use` block named Task/Agent carries
        `input.subagent_type` — keyed here by the block's tool-use id;
      * the paired `tool_result` user record carries top-level
        `toolUseResult.agentId` — completing agentId -> subagent_type.

    Only the identifiers are read; prompts/descriptions are never touched.
    Previously duplicated independently by `hooks/lib/cost_meter.py`'s
    `_harvest_agent_dispatch` and `scripts/measure_full_file_duplication.py`'s
    `_join_dispatch_agent_ids` — the latter's own docstring already conceded
    the duplication "since that algorithm's own module keeps it private"
    (#2050 makes it public here instead, so both consumers share one
    implementation)."""
    message = record.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return
    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "tool_use" and block.get("name") in TASK_TOOL_NAMES:
            block_id = block.get("id")
            block_input = block.get("input")
            subagent_type = (
                block_input.get("subagent_type")
                if isinstance(block_input, dict)
                else None
            )
            if (
                isinstance(block_id, str)
                and isinstance(subagent_type, str)
                and subagent_type
            ):
                dispatch_types[block_id] = subagent_type
        elif block_type == "tool_result":
            tool_use_id = block.get("tool_use_id")
            tool_use_result = record.get("toolUseResult")
            agent_id = (
                tool_use_result.get("agentId")
                if isinstance(tool_use_result, dict)
                else None
            )
            if (
                isinstance(tool_use_id, str)
                and isinstance(agent_id, str)
                and tool_use_id in dispatch_types
            ):
                agent_types[agent_id] = dispatch_types[tool_use_id]


def agent_type_for(record: dict, agent_types: dict[str, str]) -> str:
    """Agent-type bucket for one usage-bearing record (#1094).

    `main` for main-loop turns. For sidechain turns: the native
    `attributionAgent` field (primary), else the agentId -> subagent_type
    join built from Task/Agent dispatches via `join_dispatch_agent_ids`
    (fallback), else the honest `unattributed` bucket — never a guess.
    """
    if not is_sidechain(record):
        return "main"
    attribution_agent = attribution_agent_of(record)
    if attribution_agent:
        return attribution_agent
    agent_id = record.get("agentId")
    if isinstance(agent_id, str) and agent_id in agent_types:
        return agent_types[agent_id]
    return "unattributed"
