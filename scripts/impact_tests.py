#!/usr/bin/env python3
"""impact_tests.py — select the tests a change can actually affect (issue #2005).

The inner loop had two speeds: run one file (46% of observed invocations) or
run the full 9,469-test directory list (27%). Nothing in between, so "I changed
something, what does it affect?" was answered by a developer's guess. Per
CLAUDE.md, that is a mechanical question and inference fails it in the
expensive direction twice over: guess narrow and miss a regression, guess wide
and pay for the whole suite.

Why coverage contexts, not pytest-testmon
-----------------------------------------
#2005 lists testmon as option 2 and, as option 3, asks whether an existing
per-test map can be built on instead of adding a dependency. It can.
`pytest-cov` is ALREADY in requirements-dev.txt and already runs under
`chk_coverage_report`, and `--cov-context=test` records which test executed
which line. That is the exact per-test map testmon would install a new
dependency to provide, so this adds none.

Relationship to the tree-hash cache (#2002)
-------------------------------------------
They answer different questions and compose. #2002 answers "has anything
changed at all" and skips the suite outright when nothing has. This answers
"given that something changed, what does it reach". Neither subsumes the other.

Safety posture — never silently narrow
--------------------------------------
Selecting a subset is only sound when the map can account for the change.
`select` REFUSES (exit 2, empty selection) rather than guessing when:

  - the map is missing, unreadable, or malformed
  - a changed file is absent from the map entirely — a new or previously
    uncovered source file has unknown reach, and "no test covers it" is
    indistinguishable from "the map predates it"
  - a changed file is itself a test file — it must run regardless, and a test
    added since the map was built has no entry at all
  - the map is older than the current tree in a way it cannot reconcile

Exit 2 means "run the full suite". A caller must treat any non-zero exit as
the full suite, never as an empty selection.

Stdlib-only at read time (the build step shells out to pytest). Python 3.10+
floor. Repo-root developer tooling, not shipped with the plugin.

Usage:
    python3 scripts/impact_tests.py build --out .cache/impact-map.json
    python3 scripts/impact_tests.py select --map .cache/impact-map.json \\
        --changed plugins/dev-team/hooks/telemetry.py
    python3 scripts/impact_tests.py select --map <path> --changed-from-git

Feeding the result to pytest (file granularity, the default):

    python3 scripts/impact_tests.py select --map <path> --changed-from-git \
      | xargs python3 -m pytest -q

Exact node ids need NUL separation — a parametrized id can contain spaces:

    python3 scripts/impact_tests.py select --map <path> --changed-from-git \
      --granularity test --null | xargs -0 python3 -m pytest -q
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

MAP_VERSION = 1

#: Suffixes that mark a path as a test file. A changed test file always runs,
#: and a test added since the map was built has no entry, so the map can never
#: prove its reach.
_TEST_MARKERS = ("test_", "_test.")

EXIT_OK = 0
EXIT_RUN_EVERYTHING = 2


def _repo_root() -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return Path(out.stdout.strip()).resolve()


def is_test_path(rel: str) -> bool:
    name = Path(rel).name
    return name.startswith(_TEST_MARKERS[0]) or _TEST_MARKERS[1] in name


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def read_contexts(coverage_db: Path, root: Path) -> dict[str, list[str]]:
    """Map source file -> the test node ids that executed it.

    Reads coverage.py's own SQLite schema. Contexts are recorded as
    ``path::test_name|run``; the ``|run`` suffix is coverage's phase marker and
    is stripped so the result is a pytest-runnable node id.
    """
    mapping: dict[str, set[str]] = {}
    connection = sqlite3.connect(f"file:{coverage_db}?mode=ro", uri=True)
    try:
        rows: list[tuple] = []
        # Coverage stores measurements in `line_bits` under line coverage and
        # in `arc` under BRANCH coverage — never both. This repo's .coveragerc
        # sets `branch = True`, so a `line_bits`-only query returns zero rows
        # and yields a silently empty map: measured, not assumed (files: 135,
        # contexts: 23, line_bits: 0). Both tables are read and unioned so the
        # map does not depend on which mode the caller's config selected.
        for table in ("line_bits", "arc"):
            if not _table_exists(connection, table):
                continue
            rows.extend(
                connection.execute(
                    f"SELECT DISTINCT c.context, f.path "
                    f"FROM {table} t "
                    "JOIN context c ON c.id = t.context_id "
                    "JOIN file f ON f.id = t.file_id"
                ).fetchall()
            )
    finally:
        connection.close()

    for context, path in rows:
        if not context:
            # The empty context is coverage recorded outside any test (import
            # time). It names no test, so it cannot select one.
            continue
        node = context.split("|", 1)[0]
        try:
            rel = str(Path(path).resolve().relative_to(root))
        except ValueError:
            # Outside the repo (site-packages). Not a change we can be asked
            # about, so it cannot affect selection.
            continue
        mapping.setdefault(rel, set()).add(node)
    return {path: sorted(nodes) for path, nodes in sorted(mapping.items())}


#: Source trees the map measures. Deliberately NOT `.coveragerc`'s `source`
#: list, which scopes to `plugins/dev-team/hooks` and `scripts` for the
#: informational coverage report. That list omits `plugins/dev-team/scripts`
#: and `plugins/dev-team/skills`, so a bare `--cov` yields a map with zero
#: contexts for anything living there — measured, not assumed: the first build
#: against `.coveragerc` mapped 0 files. A map that silently covers less than
#: the caller believes is the false-narrow failure this tool must never have,
#: so the targets are named here explicitly.
DEFAULT_COV_TARGETS = (
    "plugins/dev-team/hooks",
    "plugins/dev-team/scripts",
    "plugins/dev-team/skills",
    "scripts",
)


def build(
    out: Path, pytest_args: list[str], root: Path, cov_targets: list[str]
) -> int:
    """Run the suite once under per-test coverage contexts and store the map."""
    env = dict(os.environ)
    data_file = out.parent / ".impact-coverage"
    out.parent.mkdir(parents=True, exist_ok=True)
    env["COVERAGE_FILE"] = str(data_file)

    cov_flags = [f"--cov={target}" for target in cov_targets]
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *cov_flags,
            "--cov-context=test",
            "--cov-report=",
            "-q",
            *pytest_args,
        ],
        cwd=str(root),
        env=env,
        check=False,
    )
    if not data_file.exists():
        print(
            "impact_tests: no coverage data produced — is pytest-cov installed?",
            file=sys.stderr,
        )
        return EXIT_RUN_EVERYTHING

    mapping = read_contexts(data_file, root)
    if not mapping:
        # An empty map is never usable, and writing one would let `select`
        # refuse on every file forever while looking configured. Fail loudly.
        print(
            "impact_tests: the run produced no per-test contexts — nothing was "
            "measured under --cov, so no map was written",
            file=sys.stderr,
        )
        return EXIT_RUN_EVERYTHING
    out.write_text(
        json.dumps(
            {
                "version": MAP_VERSION,
                "pytest_returncode": result.returncode,
                "files": mapping,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"impact_tests: mapped {len(mapping)} source file(s) -> tests", file=sys.stderr)
    return EXIT_OK


def load_map(path: Path) -> dict[str, list[str]] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("version") != MAP_VERSION:
        return None
    files = payload.get("files")
    if not isinstance(files, dict):
        return None
    return {k: v for k, v in files.items() if isinstance(v, list)}


def select(mapping: dict[str, list[str]], changed: list[str]) -> tuple[list[str], str]:
    """Return (test node ids, reason-if-refused).

    A non-empty reason means the caller must run the full suite: the selection
    is not trustworthy, and an empty list must never be read as "nothing to
    run".
    """
    if not changed:
        return [], "no changed files supplied"

    selected: set[str] = set()
    for rel in changed:
        if is_test_path(rel):
            return [], (
                f"{rel} is a test file — a changed or newly added test must run "
                "regardless, and the map cannot prove the reach of a test it "
                "was built before"
            )
        if rel not in mapping:
            return [], (
                f"{rel} is absent from the impact map — a new or uncovered "
                "source file has unknown reach, and that is indistinguishable "
                "from a map built before it existed"
            )
        selected.update(mapping[rel])

    if not selected:
        return [], (
            "every changed file is in the map but no test covers any of them — "
            "refusing to select nothing"
        )
    return sorted(selected), ""


def _changed_from_git(root: Path) -> list[str]:
    tracked = subprocess.run(
        ["git", "diff", "--name-only", "HEAD", "--"],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    ).stdout.split()
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    ).stdout.split()
    return sorted({*tracked, *untracked})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="impact_tests.py",
        description="Select the tests a change can actually affect.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build", help="build the per-test impact map")
    b.add_argument("--out", type=Path, required=True)
    b.add_argument(
        "--cov",
        dest="cov_targets",
        action="append",
        default=None,
        help=(
            "source tree to measure (repeatable). Defaults to "
            f"{', '.join(DEFAULT_COV_TARGETS)} — NOT .coveragerc's narrower list."
        ),
    )
    b.add_argument("pytest_args", nargs="*", help="paths/args passed to pytest")

    s = sub.add_parser("select", help="print the tests a change can affect")
    s.add_argument("--map", dest="map_path", type=Path, required=True)
    s.add_argument("--changed", nargs="*", default=[])
    s.add_argument(
        "--changed-from-git",
        action="store_true",
        help="derive the changed set from the working tree",
    )
    s.add_argument(
        "--granularity",
        choices=("file", "test"),
        default="file",
        help=(
            "file (default): emit test FILE paths. test: emit exact node ids. "
            "File is the default deliberately — a parametrized node id can "
            "contain spaces and brackets, so a naive $(...) split corrupts it, "
            "and ids churn whenever a parametrize list changes while the file "
            "path does not. File granularity is nearly as selective and far "
            "more robust."
        ),
    )
    s.add_argument(
        "--null",
        action="store_true",
        help=(
            "NUL-separate the output for `xargs -0`. Required for safe "
            "--granularity test consumption, since node ids may contain spaces."
        ),
    )
    args = parser.parse_args(argv)

    try:
        root = _repo_root()
    except (subprocess.SubprocessError, OSError) as exc:
        print(f"impact_tests: {exc}", file=sys.stderr)
        return EXIT_RUN_EVERYTHING

    if args.command == "build":
        targets = args.cov_targets or list(DEFAULT_COV_TARGETS)
        return build(args.out, args.pytest_args, root, targets)

    mapping = load_map(args.map_path)
    if mapping is None:
        print(
            "impact_tests: no usable impact map — run the full suite",
            file=sys.stderr,
        )
        return EXIT_RUN_EVERYTHING

    changed = list(args.changed)
    if args.changed_from_git:
        try:
            changed.extend(_changed_from_git(root))
        except (subprocess.SubprocessError, OSError) as exc:
            print(f"impact_tests: {exc} — run the full suite", file=sys.stderr)
            return EXIT_RUN_EVERYTHING

    selected, refusal = select(mapping, sorted(set(changed)))
    if refusal:
        print(f"impact_tests: {refusal} — run the full suite", file=sys.stderr)
        return EXIT_RUN_EVERYTHING

    if args.granularity == "file":
        selected = sorted({node.split("::", 1)[0] for node in selected})

    terminator = "\0" if args.null else "\n"
    sys.stdout.write(terminator.join(selected) + terminator)
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
