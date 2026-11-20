#!/usr/bin/env python3
"""coverage_evidence_detect.py — classify a coverage or mutation evidence path.

`/system-test-design` accepts per-test coverage and mutation evidence and
falls back to `static-judgment` when it cannot use a path. This script makes
that decision deterministic: it detects the format by CONTENT (never by file
extension) and, when the path is unusable, returns the exact reason string the
report quotes.

Accepted formats (v1):

    coverage  coveragepy-json   coverage.py JSON written with --show-contexts
              cobertura-dir     a directory of per-test Cobertura XML, one
                                file per test id
              istanbul-dir      a directory of per-test Istanbul JSON, one
                                file per test id
              lcov-dir          a directory of per-test lcov files, one file
                                per test id
              v8-dir            a directory of per-test raw V8 coverage JSON
                                (`NODE_V8_COVERAGE` output), one file per test id
              jacoco-dir        a directory of per-test JaCoCo XML (root
                                `<report>`), one file per test id
    mutation  stryker           Stryker mutation-report.json whose mutants
                                carry killedBy/coveredBy
              mutmut            mutmut 3 `mutants/mutmut-stats.json`,
                                recognised by its `tests_by_mangled_function_name`
                                map (function to the tests that reach it) and
                                usable only when some function names a test. It records
                                reach, not kills: no file names the test that
                                killed a mutant. A
                                per-file `mutants/**/*.meta` file (it holds
                                `exit_code_by_key`, the kill results, and no
                                test map) is recognised but has no per-test
                                data. Probed against mutmut 3.8.1 output.

A directory whose reports record no covered line or statement is `no contexts`
(Cobertura `<line hits>`, JaCoCo `<line ci>`, Istanbul `s`, lcov `DA`, V8 range
`count`), as is a single Istanbul, lcov, or V8 file (an aggregate has no per-test
data). A single Cobertura or JaCoCo XML file is `unrecognised format`: only a
directory of per-test XML is accepted. A report whose values have the wrong
type is unusable, not a crash.

Reasons when `format` is null (verbatim in the report):

    missing                 the path does not exist
    unrecognised format     readable, but none of the formats above
    malformed: <error>      a parser error (truncated JSON, invalid XML)
    no contexts             a recognised format with no per-test data (for
                            example coverage.py JSON written without
                            --show-contexts)

Output is one JSON object on stdout:
    {"kind": ..., "path": ..., "format": <name or null>, "reason": <str or null>}
Exit 0 whenever the path was classified (an unusable path is data, not an
error); exit 2 for a usage error. Stdlib only (ADR 0014/0015).
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

EXIT_OK = 0
EXIT_USAGE = 2

MISSING = "missing"
UNRECOGNISED = "unrecognised format"
NO_CONTEXTS = "no contexts"


class _Malformed(Exception):
    pass


def _result(kind: str, path: str, fmt: str | None, reason: str | None) -> dict:
    return {"kind": kind, "path": path, "format": fmt, "reason": reason}


def _load_json(raw: bytes):
    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, RecursionError) as exc:  # bad JSON or bytes, oversized integer, deep nesting
        raise _Malformed(f"malformed: {exc}") from exc


def _load_xml_root(raw: bytes):
    try:
        return ET.fromstring(raw)
    except (ET.ParseError, ValueError, LookupError) as exc:  # bad or unsupported encoding
        raise _Malformed(f"malformed: {exc}") from exc


def _is_coveragepy(data) -> bool:
    return isinstance(data, dict) and isinstance(data.get("meta"), dict) and isinstance(
        data.get("files"), dict
    )


def _has_contexts(data: dict) -> bool:
    """True when some line carries a non-empty context label. Data recorded
    without dynamic test contexts maps every line to the empty static context
    `[""]`, which names no test."""
    for entry in data["files"].values():
        contexts = entry.get("contexts") if isinstance(entry, dict) else None
        if isinstance(contexts, dict) and any(
            label for labels in contexts.values() if isinstance(labels, list) for label in labels
        ):
            return True
    return False


def _is_stryker(data) -> bool:
    return isinstance(data, dict) and "schemaVersion" in data and isinstance(data.get("files"), dict)


def _stryker_has_per_test_data(data: dict) -> bool:
    for entry in data["files"].values():
        for mutant in entry.get("mutants", []) if isinstance(entry, dict) else []:
            if isinstance(mutant, dict) and (mutant.get("killedBy") or mutant.get("coveredBy")):
                return True
    return False


def _is_mutmut(data) -> bool:
    return isinstance(data, dict) and (
        isinstance(data.get("tests_by_mangled_function_name"), dict)
        or isinstance(data.get("exit_code_by_key"), dict)
    )


def _mutmut_has_per_test_data(data: dict) -> bool:
    tests = data.get("tests_by_mangled_function_name")
    return isinstance(tests, dict) and any(
        isinstance(names, list) and names for names in tests.values()
    )


def _is_istanbul(data) -> bool:
    return (
        isinstance(data, dict)
        and bool(data)
        and all(
            isinstance(v, dict) and "statementMap" in v and isinstance(v.get("s"), dict)
            for v in data.values()
        )
    )


def _starts_with(raw: bytes, char: str) -> bool:
    """True when the report's first non-blank character is `char`. Bytes that
    cannot be decoded as text are neither JSON nor XML, so it is False."""
    try:
        return raw.decode("utf-8").lstrip().startswith(char)
    except UnicodeDecodeError:
        return False


LCOV_SOURCE_FILE = "SF:"
LCOV_LINE_DATA = "DA:"
LCOV_END_OF_RECORD = "end_of_record"


def _is_v8(data) -> bool:
    result = data.get("result") if isinstance(data, dict) else None
    return (
        isinstance(result, list)
        and bool(result)
        and all(isinstance(r, dict) and "functions" in r for r in result)
    )


def _is_lcov(text: str) -> bool:
    return LCOV_SOURCE_FILE in text and LCOV_END_OF_RECORD in text


def _is_count(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_positive_int(value: str) -> bool:
    """True for a string of ASCII digits above zero. It never calls `int()`, which
    raises on superscript digits and on strings past the interpreter's digit limit."""
    return value.isascii() and value.isdigit() and value.strip("0") != ""


def _istanbul_has_hits(data: dict) -> bool:
    return any(
        _is_count(n) and n > 0
        for v in data.values()
        for n in v["s"].values()
    )


def _v8_has_hits(data: dict) -> bool:
    functions = (
        fn
        for entry in data["result"]
        for fn in (entry["functions"] if isinstance(entry["functions"], list) else ())
        if isinstance(fn, dict)
    )
    return any(
        isinstance(r, dict) and _is_count(r.get("count")) and r["count"] > 0
        for fn in functions
        for r in (fn.get("ranges") if isinstance(fn.get("ranges"), list) else ())
    )


def _js_json_report(data) -> tuple[str | None, bool]:
    """(report format, has_hits) for parsed JS coverage JSON; (None, False) if neither."""
    if _is_istanbul(data):
        return "istanbul", _istanbul_has_hits(data)
    if _is_v8(data):
        return "v8", _v8_has_hits(data)
    return None, False


def _lcov_has_hits(text: str) -> bool:
    for line in text.splitlines():
        if line.startswith(LCOV_LINE_DATA):
            _, _, rest = line.removeprefix(LCOV_LINE_DATA).partition(",")
            count = rest.split(",")[0].strip()
            if _is_positive_int(count):
                return True
    return False


def _xml_line_has_hits(root, attribute: str) -> bool:
    """True when some `<line>` element carries `attribute` (Cobertura `hits`,
    JaCoCo `ci`) as an integer above zero."""
    for line in root.iter("line"):
        if _is_positive_int(line.get(attribute, "")):
            return True
    return False


EMPTY_REPORT = "empty"


def _read_dir_report(file: Path) -> tuple[str | None, bool]:
    """(evidence format, has_hits) for one per-test report; (None, False) if
    unrecognised. A test that loaded no instrumented code leaves an empty file or
    an empty JSON object: format `EMPTY_REPORT`, which fits any directory."""
    raw = file.read_bytes()
    text = raw.decode("utf-8", errors="replace").lstrip()
    if not text:
        return EMPTY_REPORT, False
    if text.startswith("<"):
        root = _load_xml_root(raw)
        if root.tag == "coverage":
            return "cobertura-dir", _xml_line_has_hits(root, "hits")
        if root.tag == "report":
            return "jacoco-dir", _xml_line_has_hits(root, "ci")
        return None, False
    if text.startswith("{"):
        data = _load_json(raw)
        if data == {}:
            return EMPTY_REPORT, False
        report, has_hits = _js_json_report(data)
        return (f"{report}-dir" if report else None), has_hits
    if _is_lcov(text):
        return "lcov-dir", _lcov_has_hits(text)
    return None, False


def _classify_coverage_file(file: Path) -> tuple[str | None, str | None]:
    raw = file.read_bytes()
    if not _starts_with(raw, "{"):
        is_lcov = _is_lcov(raw.decode("utf-8", errors="replace"))
        return (None, NO_CONTEXTS) if is_lcov else (None, UNRECOGNISED)
    data = _load_json(raw)
    if _is_coveragepy(data):
        return ("coveragepy-json", None) if _has_contexts(data) else (None, NO_CONTEXTS)
    if _js_json_report(data)[0]:
        return None, NO_CONTEXTS
    return None, UNRECOGNISED


def _classify_coverage_dir(directory: Path) -> tuple[str | None, str | None]:
    files = sorted(p for p in directory.iterdir() if p.is_file() and not p.name.startswith("."))
    if not files:
        return None, UNRECOGNISED
    formats: set[str] = set()
    any_hits = False
    for file in files:
        fmt, has_hits = _read_dir_report(file)
        if fmt is None:
            return None, UNRECOGNISED
        if fmt != EMPTY_REPORT:
            formats.add(fmt)
        any_hits = any_hits or has_hits
    if len(formats) > 1:
        return None, UNRECOGNISED
    return (formats.pop(), None) if formats and any_hits else (None, NO_CONTEXTS)


def _classify_mutation_file(file: Path) -> tuple[str | None, str | None]:
    raw = file.read_bytes()
    if not _starts_with(raw, "{"):
        return None, UNRECOGNISED
    data = _load_json(raw)
    if _is_stryker(data):
        return ("stryker", None) if _stryker_has_per_test_data(data) else (None, NO_CONTEXTS)
    if _is_mutmut(data):
        return ("mutmut", None) if _mutmut_has_per_test_data(data) else (None, NO_CONTEXTS)
    return None, UNRECOGNISED


def classify(kind: str, path: str) -> dict:
    """Classify `path` as evidence of `kind` ('coverage' or 'mutation')."""
    target = Path(path)
    if not target.exists():
        return _result(kind, path, None, MISSING)
    try:
        if kind == "coverage":
            if target.is_dir():
                fmt, reason = _classify_coverage_dir(target)
            else:
                fmt, reason = _classify_coverage_file(target)
        else:
            if target.is_dir():
                fmt, reason = None, UNRECOGNISED
            else:
                fmt, reason = _classify_mutation_file(target)
    except _Malformed as exc:
        return _result(kind, path, None, str(exc))
    except OSError as exc:
        return _result(kind, path, None, f"malformed: {exc}")
    return _result(kind, path, fmt, reason)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--kind", required=True, choices=("coverage", "mutation"))
    parser.add_argument("path")
    args = parser.parse_args(argv)
    print(json.dumps(classify(args.kind, args.path)))
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
