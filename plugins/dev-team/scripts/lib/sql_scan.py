"""Scan engine for the SQL anti-pattern detector.

``scan_text`` runs the script-owned rules over one SQL text. ``scan_paths``
reads files, scans them, and collects per-file errors without stopping.
``gate`` answers one question for ``/code-review``: is SQL present in the
changeset, and which hits does the detector have.

Dispatch is true when a ``.sql`` file is a target, or an extractor found a
SQL-shaped fragment. It stays true when the detector has no hits or cannot
read the file.

Stdlib-only. Python 3.10+.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

import sql_extract
from sql_dialect import infer_dialect, normalize_dialect, rule_applies
from sql_rules import OWNER_SCRIPT, Context, Rule, discover_rules
from sql_suppress import is_suppressed, suppressions
from sql_tokenize import COMMENT, tokenize

MAX_HIT_TEXT = 120


class ReadError(Exception):
    """A file the detector could not read. ``str(exc)`` is the reason."""


def read_text(path: str) -> str:
    """Read ``path`` as UTF-8 (a leading BOM is dropped). Raise ``ReadError``."""
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError as exc:
        raise ReadError(exc.strerror or type(exc).__name__) from exc
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ReadError("not valid UTF-8") from exc


def scan_text(
    text: str,
    path: str,
    dialect: str | None = None,
    rules: Sequence[Rule] | None = None,
    origin: str = sql_extract.ORIGIN_SQL,
    line_offset: int = 0,
) -> list[dict]:
    """Findings of the script-owned rules for one SQL text, sorted by line."""
    file_dialect = normalize_dialect(dialect) if dialect else infer_dialect(path, text)
    active = discover_rules() if rules is None else rules
    tokens = tokenize(text)
    marks = suppressions(tokens)
    ctx = Context([t for t in tokens if t.kind != COMMENT], file_dialect)
    findings: list[dict] = []
    for rule in active:
        if rule.owner != OWNER_SCRIPT or rule.check is None:
            continue
        if not rule_applies(rule.dialect, file_dialect):
            continue
        for hit in rule.check(ctx):
            if is_suppressed(marks, rule.id, hit.line):
                continue
            findings.append(
                {
                    "file": path,
                    "line": hit.line + line_offset,
                    "rule": rule.id,
                    "dialect": rule.dialect,
                    "origin": origin,
                    "severity": rule.severity,
                    "message": rule.message,
                    "fix": rule.fix,
                    "text": hit.text[:MAX_HIT_TEXT],
                }
            )
    findings.sort(key=lambda f: (f["line"], f["rule"]))
    return findings


@dataclass
class ScanResult:
    findings: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    skipped_fragments: dict[str, int] = field(default_factory=dict)
    dispatch: bool = False


def scan_paths(
    paths: Iterable[str],
    dialect: str | None = None,
    rules: Sequence[Rule] | None = None,
) -> ScanResult:
    """Scan every handled file. A read failure becomes an error entry only."""
    result = ScanResult()
    active = discover_rules() if rules is None else rules
    for path in paths:
        if not sql_extract.handles(path):
            continue
        try:
            text = read_text(path)
        except ReadError as exc:
            result.errors.append(f"cannot read {path}: {exc}")
            result.dispatch = result.dispatch or sql_extract.is_sql_file(path)
            continue
        extraction = sql_extract.extract(path, text)
        result.dispatch = result.dispatch or extraction.sql_present
        if extraction.skipped:
            result.skipped_fragments[path] = extraction.skipped
        for fragment in extraction.fragments:
            result.findings.extend(
                scan_text(
                    fragment.text,
                    path,
                    dialect,
                    active,
                    fragment.origin,
                    fragment.line_offset,
                )
            )
    return result


def gate(paths: Iterable[str], dialect: str | None = None) -> dict:
    """The ``--gate`` payload: status, dispatch, hits, errors, skipped_fragments."""
    result = scan_paths(paths, dialect)
    return {
        "status": "ok",
        "dispatch": result.dispatch,
        "hits": result.findings,
        "errors": result.errors,
        "skipped_fragments": result.skipped_fragments,
    }
