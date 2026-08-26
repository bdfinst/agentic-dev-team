#!/usr/bin/env python3
"""Deterministic contract validation for review-agent output (#1998).

Session-report analysis over 3,213 review runs found 585 (18.2%) returning
output that does not match the shared review-agent JSON contract
(`knowledge/review-agent-output-contract.md`). Those findings were discarded
without a diagnostic — the orchestrator eyeballs each agent's raw text
against the contract and, when it doesn't obviously fit, the loss is silent:
no agent name, no raw output, no reason is ever recorded, so the failure
shapes are unknown. #1980/#1982's per-lens `$/finding` figures divide by
that same lossy denominator, and the loss rate varies ~8x by agent
(`concurrency-review` 49%, `spec-compliance-review` 30%, `doc-review` 19%).

This module is the deterministic half of the fix: given an agent's raw text
output, decide whether it satisfies the contract and, when it doesn't,
classify *why* and log a diagnostic — agent name, a redacted prefix of the
raw output, and the specific validation error — to
`.claude/metrics/contract-failures.jsonl`. Per this repo's CLAUDE.md:
"instrument before fixing... the failure shapes are currently unknown, so a
fix written first would be a guess." Fixing by shape (a tolerant extractor
for the recoverable cases, a schema fix, a hard error for the unusable ones)
and recomputing `$/finding` on the repaired denominator are follow-on work
once this log has real data in it.

Two independent dimensions are tracked, not one:

- ``extraction`` — how the JSON was framed: ``clean`` (no wrapper), ``fenced``
  (a ` ```json ` block), or ``prose-preamble`` (a leading/trailing prose
  sentence around a balanced object). ``None`` when no JSON-like structure
  was ever recovered at all.
- ``shape`` — the outcome. On success it equals ``extraction``. On failure it
  is one of the loggable failure shapes (see ``FAILURE_SHAPES``) — including
  ``schema-drift`` and ``malformed-json``, both of which can co-occur with any
  extraction (``clean``/``fenced``/``prose-preamble``), so ``extraction``
  survives even when the object was recovered from a fenced block or a prose
  preamble and only then found to violate the contract or fail to parse.
  ``empty``/``truncated``/``not-json`` never carry an ``extraction`` — no
  JSON-shaped candidate was ever recovered for those. Collapsing these into
  one field was the original design and it silently discarded the extraction
  dimension on exactly the failures a tolerant extractor would need it for.

Stdlib-only. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# skills/code-review/scripts -> skills/code-review -> skills -> plugin root
_PLUGIN_ROOT = Path(__file__).resolve().parents[3]
_HOOKS_LIB_DIR = _PLUGIN_ROOT / "hooks" / "lib"
if str(_HOOKS_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_LIB_DIR))

try:
    import artifact_paths  # type: ignore[import-not-found]
    import atomic_state  # type: ignore[import-not-found]
    import review_agent_registry  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - degraded fallback, hooks/lib unreachable
    # Same guarded-import shape as `review_round_log.py`'s sibling pattern:
    # the `sys.path` setup above must run before this import, which is why
    # it isn't at the top of the file (`ruff.toml` suppresses E402 for this
    # whole directory for exactly that reason).
    artifact_paths = None
    atomic_state = None
    review_agent_registry = None

_STREAM_NAME = "contract-failures.jsonl"

#: How much of the (redacted) raw output a failure diagnostic carries — enough
#: to recognize the shape (a preamble sentence, a fence opener, truncation) at
#: a glance, without inflating the log with full agent output on every
#: failure.
_RAW_PREFIX_LEN = 200

#: Cap on the persisted/printed `error` string. `_validate_schema` interpolates
#: agent-controlled values (`status`, `severity`) with `!r` — unlike
#: `raw_prefix`, nothing bounded this field's length or redacted it before
#: #1998 wave-2-follow-up, so a drifting agent could write an arbitrarily
#: long, secret-bearing `error` straight into `contract-failures.jsonl` and
#: into every downstream `dispatchFailures[].error` consumer.
_ERROR_MAX_LEN = 256

_VALID_STATUSES = frozenset({"pass", "warn", "fail", "skip"})
_VALID_SEVERITIES = frozenset({"error", "warning", "suggestion"})

_FENCE_RE = re.compile(r"```(?:json)?\s*\n(.*?)```", re.DOTALL)

#: Secret-shaped substrings to scrub before any raw agent text is persisted.
#: Review-agent output is not independent of the reviewed repository — a
#: lens quoting a hardcoded-key finding verbatim reproduces the secret it
#: found — so `raw_prefix` is a transitive channel for repo content, not
#: "AI-authored text" in the sense of being free of user/repo material.
#: First pattern is this repo's own canonical hardcoded-key detector
#: (`knowledge/owasp-detection.md`'s "Hardcoded-key pattern"); the rest are
#: high-signal vendor token prefixes cheap enough to check unconditionally.
_SECRET_PATTERNS = (
    # No required closing quote (unlike the canonical pattern in
    # `knowledge/owasp-detection.md`): this module's own most common failure
    # shape, `truncated`, cuts output mid-string, and requiring a closing
    # quote before redacting would let exactly that secret through unredacted.
    re.compile(r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*['\"][^'\"]{8,}"),
    # `[A-Za-z0-9_-]`, not just alphanumeric: segmented vendor-key formats
    # (`sk-ant-...`, `sk-proj-...`) use `-`/`_` inside the token body and
    # would otherwise stop matching at the first separator.
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    # Complete PEM block, bounded by its own END marker.
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
    # A BEGIN marker with no matching END left in the text — the truncated
    # shape again: redact from BEGIN to EOF rather than leave the key body
    # unredacted because the block never closed.
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*$"),
)

#: Extraction shapes — how a successfully-recovered JSON object was framed.
#: These label *successful* extraction only; they never appear as a `shape`
#: value in a failure row (see ``FAILURE_SHAPES``) except indirectly via the
#: `extraction` field on a `schema-drift` failure.
SHAPE_CLEAN = "clean"
SHAPE_FENCED = "fenced"
SHAPE_PROSE_PREAMBLE = "prose-preamble"

#: Failure shapes this module distinguishes — the taxonomy #1998 asks for.
SHAPE_EMPTY = "empty"
SHAPE_TRUNCATED = "truncated"
SHAPE_MALFORMED_JSON = "malformed-json"
SHAPE_SCHEMA_DRIFT = "schema-drift"
SHAPE_NOT_JSON = "not-json"

#: The closed set of `shape` values `contract-failures.jsonl` can ever carry.
#: Kept here, not re-enumerated in prose, so `SKILL.md` and
#: `telemetry-schema.md` can be checked against one source of truth
#: (`repo_invariants.py::check_contract_failure_shapes_documented`).
FAILURE_SHAPES = frozenset(
    {SHAPE_EMPTY, SHAPE_TRUNCATED, SHAPE_MALFORMED_JSON, SHAPE_SCHEMA_DRIFT, SHAPE_NOT_JSON}
)

#: The closed set of `extraction` values a *successful* validation can carry.
SUCCESS_SHAPES = frozenset({SHAPE_CLEAN, SHAPE_FENCED, SHAPE_PROSE_PREAMBLE})


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _redact(text: str) -> str:
    """Scrub secret-shaped substrings from ``text`` before any further
    processing (including truncation) sees it — a secret straddling the
    ``_RAW_PREFIX_LEN`` cut must still be caught, so redaction runs on the
    full text first, never on the already-truncated slice."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def _extract_fenced_json(text: str) -> str | None:
    match = _FENCE_RE.search(text)
    return match.group(1).strip() if match else None


def _advance_in_string(ch: str, escape: bool) -> tuple[bool, bool]:
    """One character step of the in-string/escape state machine, given the
    current character and whether the previous one was an unconsumed
    backslash. Returns ``(still_in_string, escape)`` for the next character."""
    if escape:
        return True, False
    if ch == "\\":
        return True, True
    if ch == '"':
        return False, False
    return True, False


def _scan_balanced(text: str, start: int) -> str | None:
    """Scan forward from ``start`` (must index a ``{``), tracking string/escape
    state so a brace inside a quoted string value doesn't corrupt depth
    counting. Returns the balanced ``{...}`` substring, or ``None`` if depth
    never returns to zero before EOF."""
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            in_string, escape = _advance_in_string(ch, escape)
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _find_first_json_object(text: str) -> tuple[str | None, bool]:
    """Return ``(candidate, truncated)``: ``candidate`` is the first balanced
    ``{...}`` substring in ``text``, tolerating leading/trailing prose, or
    ``None`` if no starting ``{`` ever balances. Every ``{`` in ``text`` is
    tried as a candidate start, not just the first — a ``{`` inside leading
    prose (e.g. quoted code in a review lens's preamble sentence) that never
    balances must not prevent recovery of a real, later JSON object; only
    when *no* starting position balances does this report failure.
    ``truncated`` is True only when at least one ``{`` was found but none of
    them ever balanced back to depth zero before EOF — the
    token-limit-truncation shape, distinguished here (by the same
    string-aware scanner, not a separate naive brace count) rather than left
    for a caller to re-derive."""
    start = text.find("{")
    saw_unbalanced = False
    while start != -1:
        candidate = _scan_balanced(text, start)
        if candidate is not None:
            return candidate, False
        saw_unbalanced = True
        start = text.find("{", start + 1)
    return None, saw_unbalanced


def _validate_schema(parsed) -> str | None:
    """Check a successfully-`json.loads`-ed value against the contract's
    required shape. Deliberately permissive on optional fields (`category`
    is documented optional; `confidence`/`file`/`line`/`suggestedFix` are not
    re-validated here) — this function's job is to catch schema *drift*
    (wrong status enum, missing issues array, unrecognized severity), not to
    re-implement the full contract as a strict schema.

    Returns the drift error string, or ``None`` when ``parsed`` satisfies the
    contract.
    """
    if not isinstance(parsed, dict):
        return f"top-level value is {type(parsed).__name__}, expected an object"
    status = parsed.get("status")
    if status not in _VALID_STATUSES:
        return f"status={status!r} not one of {sorted(_VALID_STATUSES)}"
    issues = parsed.get("issues")
    if not isinstance(issues, list):
        return "issues field missing or not an array"
    for i, issue in enumerate(issues):
        if not isinstance(issue, dict):
            return f"issues[{i}] is not an object"
        severity = issue.get("severity")
        if severity not in _VALID_SEVERITIES:
            return f"issues[{i}].severity={severity!r} not one of {sorted(_VALID_SEVERITIES)}"
    if "summary" not in parsed:
        return "summary field missing"
    return None


def _success(shape: str) -> dict:
    return {"valid": True, "shape": shape, "extraction": shape, "error": None}


def _schema_drift(extraction: str, error: str) -> dict:
    return {"valid": False, "shape": SHAPE_SCHEMA_DRIFT, "extraction": extraction, "error": error}


def _failure(shape: str, extraction: str | None, error: str) -> dict:
    return {"valid": False, "shape": shape, "extraction": extraction, "error": error}


def _try_parse(candidate: str, extraction: str) -> dict:
    """Parse and validate a recovered JSON-shaped candidate. ``candidate`` is
    always a complete text span (a fenced code block's contents, or a
    balanced ``{...}`` substring) — a ``json.loads`` failure here means the
    JSON is malformed, not truncated (truncation is decided earlier, by
    whether a balanced candidate was found at all)."""
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        return _failure(SHAPE_MALFORMED_JSON, extraction, str(exc))
    error = _validate_schema(parsed)
    return _success(extraction) if error is None else _schema_drift(extraction, error)


def classify_and_validate(raw_text: str) -> dict:
    """Classify ``raw_text`` (an agent's raw final-turn text) against the
    review-agent output contract.

    Returns ``{"valid": bool, "shape": str, "extraction": str|None, "error":
    str|None}``. Tries, in order: (1) a strict parse of the stripped text as
    -is, (2) a fenced ```json code block, (3) the first balanced ``{...}``
    object, tolerating a prose preamble or trailing prose. Each
    successfully-recovered candidate is then checked against the contract's
    required shape; a ``schema-drift`` or ``malformed-json`` failure carries
    the ``extraction`` shape that recovered the candidate, rather than
    discarding that information — including when the candidate came from a
    fenced block that itself failed to parse (no further fallback is
    attempted once a fence is found; a fence match requires a closing
    delimiter, so its contents are a complete span, never a truncation). A
    ``{`` that never balances (in the fenceless path) is reported as
    ``truncated``; a balanced object that still fails to parse (unquoted
    keys, a trailing comma, a Python-repr dict) is reported as
    ``malformed-json`` — distinct from ``truncated``, since the output
    finished, it just wasn't valid JSON.
    """
    stripped = raw_text.strip()
    if not stripped:
        return _failure(SHAPE_EMPTY, None, "output was empty or whitespace-only")

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        pass
    else:
        error = _validate_schema(parsed)
        return _success(SHAPE_CLEAN) if error is None else _schema_drift(SHAPE_CLEAN, error)

    fenced = _extract_fenced_json(stripped)
    if fenced is not None:
        return _try_parse(fenced, SHAPE_FENCED)

    candidate, unbalanced = _find_first_json_object(stripped)
    if candidate is not None:
        extraction = SHAPE_CLEAN if candidate == stripped else SHAPE_PROSE_PREAMBLE
        return _try_parse(candidate, extraction)

    if unbalanced:
        return _failure(SHAPE_TRUNCATED, None, "unbalanced braces — output likely truncated at a token limit")

    return _failure(SHAPE_NOT_JSON, None, "no JSON object found in output")


def _resolve_stream(cwd: Path, *, migrate: bool = True) -> Path:
    if artifact_paths is not None:
        return artifact_paths.resolve_file("metrics", _STREAM_NAME, cwd, migrate=migrate)
    return cwd / ".claude" / "metrics" / _STREAM_NAME


def _normalize_agent(agent: str) -> str:
    """Strip this plugin's own `dev-team:` dispatch qualifier so this
    stream's `agent` field matches `boundary-events.jsonl`'s `matched_rule`
    vocabulary — the field `contract_failure_report.py` joins against.
    Without this, an orchestrator passing the real dispatch form
    (`dev-team:<agent-name>`) silently produces a phantom agent with 0
    dispatches and inflates the reported total-failure rate (same class of
    bug #1461 found in the ledger hook itself)."""
    if review_agent_registry is not None:
        return review_agent_registry.strip_plugin_prefix(agent)
    return agent


def _safe_error(error: str) -> str:
    """Redact and cap a diagnostic ``error`` string before it is persisted or
    printed. `_validate_schema` interpolates agent-controlled values (e.g.
    ``status={status!r}``) into this string, so — unlike a fixed-format
    message — it can carry secret-shaped or unbounded content the same way
    `raw_prefix` can; apply the same two controls here rather than leaving
    this sibling field as the one channel that bypasses both."""
    return _redact(str(error))[:_ERROR_MAX_LEN]


def build_failure_entry(agent: str, raw_text: str, diagnostic: dict, timestamp: str | None = None) -> dict:
    """Assemble one `contract-failures.jsonl` row. ``diagnostic`` must be a
    non-valid result from `classify_and_validate`."""
    if diagnostic.get("valid") or diagnostic.get("shape") not in FAILURE_SHAPES:
        raise ValueError(
            f"build_failure_entry requires a failing classify_and_validate() result, got {diagnostic!r}"
        )
    redacted = _redact(raw_text.strip())
    return {
        "timestamp": timestamp or _now_iso(),
        "agent": _normalize_agent(agent),
        "shape": diagnostic["shape"],
        "extraction": diagnostic.get("extraction"),
        "error": _safe_error(diagnostic["error"]),
        "raw_prefix": redacted[:_RAW_PREFIX_LEN],
    }


def log_failure(entry: dict, cwd: Path | None = None) -> Path | None:
    """Append one diagnostic row to `.claude/metrics/contract-failures.jsonl`.

    Delegates to `atomic_state.append_line_locked` — the plugin's hardened,
    symlink-safe, lock-serialized JSONL append (#1889) every other metrics
    emitter in this plugin uses (`boundary_events.py`, `review_round_log.py`,
    et al.) — rather than a bare `open(..., "a")`, which would reintroduce
    the exact symlink-follow / unsynchronized-write gap #1889 closed
    elsewhere. Passes `fail_open=False` so a write rejected inside the lock
    (e.g. the O_NOFOLLOW check refusing a planted symlink) raises instead of
    being silently swallowed there — this function's own `except Exception`
    below is where fail-open is applied, so the swallowed case and the
    successful case stay distinguishable and this docstring's contract
    holds. A full disk or a read-only metrics directory must still never
    fail a review. Returns the path written, or `None` when the write
    failed or `hooks/lib` is unreachable.
    """
    try:
        base = cwd or Path.cwd()
        log = _resolve_stream(base)
        log.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry, separators=(",", ":"), sort_keys=True) + "\n"
        if atomic_state is not None:
            atomic_state.append_line_locked(log, line, fail_open=False)
        else:  # pragma: no cover - degraded fallback, hooks/lib unreachable
            with open(log, "a", encoding="utf-8") as handle:
                handle.write(line)
        return log
    except Exception:  # noqa: BLE001 - fail-open: telemetry never blocks a review
        return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", required=True, help="Name of the review agent whose output is being validated")
    parser.add_argument(
        "--file",
        required=True,
        help="Path to the agent's raw final-turn text output; '-' for stdin",
    )
    parser.add_argument("--cwd", default=None)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Classify only; never write the failure diagnostic",
    )
    args = parser.parse_args(argv)

    raw_text = sys.stdin.read() if args.file == "-" else Path(args.file).read_text(encoding="utf-8")
    result = classify_and_validate(raw_text)

    if not result["valid"] and not args.dry_run:
        entry = build_failure_entry(args.agent, raw_text, result)
        log_failure(entry, Path(args.cwd) if args.cwd else None)

    printed = {"agent": _normalize_agent(args.agent), **result}
    if not result["valid"]:
        # SKILL.md step 4 carries this printed `error` forward, unmodified,
        # into `dispatchFailures[].error` — sanitize it at the source so
        # every downstream consumer (the report, the aggregate, the log)
        # inherits the same redaction/cap `raw_prefix` gets, rather than
        # relying on each consumer to re-apply it.
        printed["error"] = _safe_error(result["error"])
    print(json.dumps(printed, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


__all__ = (
    "FAILURE_SHAPES",
    "SHAPE_CLEAN",
    "SHAPE_EMPTY",
    "SHAPE_FENCED",
    "SHAPE_MALFORMED_JSON",
    "SHAPE_NOT_JSON",
    "SHAPE_PROSE_PREAMBLE",
    "SHAPE_SCHEMA_DRIFT",
    "SHAPE_TRUNCATED",
    "SUCCESS_SHAPES",
    "build_failure_entry",
    "classify_and_validate",
    "log_failure",
)
