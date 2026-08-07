#!/usr/bin/env python3
"""measure_tokens.py — count tokens in files this plugin loads into agent
context, replacing the retired ``scripts/measure-tokens.sh`` (see
``plans/test-improve-context-loading-strategy.md`` Slice 2, issue #1797).

This is Step 2.1 of that plan: it ports only the bash script's tokenizer
selection and its two no-``--verify`` call shapes —

1. **Explicit paths** (``measure_tokens.py <path>...``) — measure exactly the
   given paths.
2. **Zero args** (``measure_tokens.py``) — auto-discover the same fixed file
   set the bash script's ``discover_budget_targets()`` globbed: every
   ``plugins/dev-team/agents/*.md``, every ``plugins/dev-team/skills/*/SKILL.md``,
   every ``plugins/dev-team/knowledge/*.md``, every
   ``plugins/dev-team/prompts/*.md`` (if that directory exists), plus the two
   fixed files ``plugins/dev-team/CLAUDE.md`` and
   ``plugins/dev-team/knowledge/agent-registry.md``. This is a plain
   filesystem glob — not a parse of any CLAUDE.md section — so it needed no
   change for the "### Baseline Budget" section's removal and is unaffected
   by it.

Step 2.2 adds ``--verify`` mode: parse ``knowledge/agent-registry.md``'s
"## Team Agents", "## Skills Registry", and "## Knowledge Files" markdown
tables, measure each single-file row's real file, and fail if any row's
declared ``~Tokens`` estimate has drifted from the measured value by more
than ``DEVIATION_THRESHOLD_PCT``. A "## Knowledge Files" row whose File
cell is a glob (multiple files summed into one declared value) is reported
as ``"unsupported_glob"`` rather than measured — see ``_build_verify_row``.
This mode never reads ``CLAUDE.md`` — it sources data from the registry
table alone, which is the whole point: the old bash script's ``--verify``
(retired along with it) parsed a "### Baseline Budget" section of
``CLAUDE.md`` that no longer exists. ``--verify`` always measures with the
heuristic tokenizer regardless of environment — see ``run_verify``.

Tokenizer selection (first available wins), matching the bash script exactly:

1. ``tiktoken`` (cl100k_base) — industry-standard approximation of Claude
   tokenizer behavior.
2. Byte-count heuristic (``len(text.encode("utf-8")) // 4``) — coarse
   fallback. The bash script computed this via ``wc -c`` (UTF-8 *byte*
   length), not a character count, so this ports the same divisor over the
   same unit — using ``len(text) // 4`` instead would measure non-ASCII-heavy
   files (em dashes, ``·``, ``→``) slightly low relative to the bash
   script's numbers.

Future work: a ``--write``/``--fix`` mode that rewrites drifted registry
values in place, and ``--root``/``--registry`` CLI flags for portability,
are both out of scope for this pass.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

REPO_ROOT = Path(__file__).resolve().parent.parent

# UTF-8 byte length divided by this is the heuristic-fallback token estimate.
HEURISTIC_BYTES_PER_TOKEN = 4

# --verify fails a row whose declared value deviates from the measured value
# by more than this percentage.
DEVIATION_THRESHOLD_PCT = 10

# Populated in Step 2.4, after running --verify for real against the live
# registry. Maps a row's File cell exactly as it appears in the registry
# table (e.g. "agents/adr-author.md") to a one-line reason the row is
# exempted from failing the --verify exit code. An exempted row still
# appears in the report, tagged "exempt" — it is never silently dropped.
VERIFY_EXCEPTIONS: dict[str, str] = {}


def plugin_root(repo_root: Path) -> Path:
    """Single source of truth for the plugin root path, resolved from a
    given repo root. Replaces three independent inline reconstructions of
    ``repo_root / "plugins" / "dev-team"`` (a former module constant and two
    duplicated local variables)."""
    return repo_root / "plugins" / "dev-team"


def detect_tokenizer() -> tuple[str, str]:
    """Pure tokenizer-selection function: given the current environment,
    always returns the same ``(name, note)`` pair — no globals read or set.
    Factored out so later steps (e.g. Step 2.2's ``--verify`` mode) can reuse
    the same fallback chain without duplicating it.
    """
    try:
        import tiktoken  # noqa: F401
    except ImportError:
        return (
            "heuristic",
            (
                "byte-count heuristic (UTF-8 bytes / "
                f"{HEURISTIC_BYTES_PER_TOKEN}) — APPROXIMATE. "
                "Install tiktoken for better accuracy: pip install tiktoken"
            ),
        )
    return "tiktoken", "tiktoken cl100k_base (approximation of Claude tokenizer)"


def count_tokens(path: Path, tokenizer: str) -> int:
    """Count tokens in ``path`` using the given tokenizer name. Caller is
    responsible for confirming ``path`` exists and is a file.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    if tokenizer == "tiktoken":
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    return len(text.encode("utf-8")) // HEURISTIC_BYTES_PER_TOKEN


def discover_budget_targets(repo_root: Path) -> list[str]:
    """Port of the bash script's ``discover_budget_targets()``: a plain
    filesystem glob, returning repo-root-relative path strings, sorted and
    deduplicated (matching the bash version's ``sort -u``).
    """
    root = plugin_root(repo_root)
    targets: list[Path] = [
        root / "CLAUDE.md",
        root / "knowledge" / "agent-registry.md",
    ]
    targets.extend(sorted((root / "agents").glob("*.md")))
    targets.extend(sorted((root / "skills").glob("*/SKILL.md")))
    targets.extend(sorted((root / "knowledge").glob("*.md")))
    prompts_dir = root / "prompts"
    if prompts_dir.is_dir():
        targets.extend(sorted(prompts_dir.glob("*.md")))

    return sorted({str(t.relative_to(repo_root)) for t in targets})


def resolve_target(repo_root: Path, raw: str) -> Path:
    """Resolve a raw path argument against ``repo_root``. An already-absolute
    path is returned unchanged (``Path.__truediv__`` drops the left operand
    when the right one is absolute); a relative path is joined to
    ``repo_root``, matching the bash script's ``${REPO_ROOT}/${rel}``.
    """
    return repo_root / raw


def measure_paths(
    repo_root: Path, raw_paths: list[str], tokenizer: str
) -> tuple[list[tuple[str, int | None]], int, int]:
    """Measure each raw path. Returns ``(rows, total, error_count)`` where
    each row is ``(label, tokens)`` with ``tokens`` as ``None`` for a path
    that does not exist on disk (reported as an error, not a crash).
    """
    rows: list[tuple[str, int | None]] = []
    total = 0
    errors = 0
    for raw in raw_paths:
        target = resolve_target(repo_root, raw)
        if not target.is_file():
            rows.append((raw, None))
            errors += 1
            continue
        tokens = count_tokens(target, tokenizer)
        rows.append((raw, tokens))
        total += tokens
    return rows, total, errors


def print_report(
    repo_root: Path,
    tokenizer_note: str,
    rows: list[tuple[str, int | None]],
    total: int,
) -> None:
    print("# measure_tokens.py output")
    print(f"# tokenizer: {tokenizer_note}")
    print(f"# repo root: {repo_root}")
    print(f"# date: {datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    print()
    print(f"{'FILE':<70} {'TOKENS':>10}")
    print(f"{'-' * 70} {'-' * 10}")
    for label, tokens in rows:
        if tokens is None:
            print(f"{label:<70} {'ERROR':>10}")
        else:
            print(f"{label:<70} {tokens:>10}")
    print(f"{'-' * 70} {'-' * 10}")
    print(f"{'TOTAL':<70} {total:>10}")


# ---------------------------------------------------------------------------
# --verify mode (Step 2.2): registry-table-sourced comparison
# ---------------------------------------------------------------------------


def extract_table_block(text: str, heading: str) -> str | None:
    """Return the text between the line ``## {heading}`` and the next ``##``
    heading (or end of file), exclusive of both heading lines.

    ``None`` when ``## {heading}`` isn't found at all — the caller reports
    this as a clear "section not found" error rather than crashing. Shared
    by every caller of this function; there is exactly one block-extraction
    implementation, called once per heading (see ``verify_registry``) rather
    than duplicated per table name.

    Known follow-up: ``scripts/check_registry_sync.py`` has its own,
    similar ``section_text()`` helper doing the same kind of heading-block
    extraction. Consolidating the two into a shared ``scripts/lib/`` module
    is a real improvement but out of scope for this pass — deliberately not
    done here to avoid touching that sibling script's own behavior/tests.
    """
    lines = text.splitlines()
    target = f"## {heading}"
    start = None
    for i, line in enumerate(lines):
        if line.strip() == target:
            start = i + 1
            break
    if start is None:
        return None

    end = len(lines)
    for i in range(start, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break
    return "\n".join(lines[start:end])


def parse_declared_value(raw: str) -> int | None:
    """Permissive parse of a registry table's ``~Tokens`` cell: strips bold
    markers and surrounding whitespace, strips a leading ``~`` if present,
    strips thousands-separator commas, and accepts a bare integer.
    ``None`` if the cleaned text still isn't an integer.
    """
    cleaned = raw.strip().strip("*").strip()
    cleaned = cleaned.removeprefix("~")
    cleaned = cleaned.replace(",", "")
    try:
        return int(cleaned)
    except ValueError:
        return None


def parse_registry_rows(section_text: str) -> list[tuple[str, str, int]]:
    """Parse a registry markdown table block into ``(name, file_path,
    declared_n)`` tuples.

    Skips the header row and the separator row (the first two
    ``|``-prefixed lines in the block), and skips any data row whose File
    cell (2nd column) is empty after stripping backticks/whitespace — a
    non-file summary row such as ``| **All team agents** | | **~7,910** |
    |``. A row whose declared-value cell doesn't parse to an integer is
    skipped too, rather than raising.
    """
    table_lines = [line for line in section_text.splitlines() if line.strip().startswith("|")]
    data_lines = table_lines[2:]  # skip header row + separator row

    rows: list[tuple[str, str, int]] = []
    for line in data_lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        name = cells[0].strip("*").strip()
        file_path = cells[1].strip("`").strip()
        if not file_path:
            continue
        declared_n = parse_declared_value(cells[2])
        if declared_n is None:
            continue
        rows.append((name, file_path, declared_n))
    return rows


# The closed set of statuses a VerifyRow can carry. A Literal (rather than a
# bare `str`) makes this the single canonical definition of the valid set,
# instead of re-typing the same four-going-on-five string literals at each
# assignment site and in compute_verify_exit_code's membership check.
VerifyStatus = Literal["ok", "deviated", "exempt", "missing_file", "unsupported_glob"]


@dataclass
class VerifyRow:
    """One --verify comparison row: a registry table entry plus its
    measured token count."""

    section: str
    name: str
    file_path: str
    declared_n: int
    measured_n: int | None
    deviation_pct: float | None
    status: VerifyStatus
    reason: str | None = None


def _build_verify_row(
    heading: str,
    name: str,
    file_path: str,
    declared_n: int,
    base_dir: Path,
    tokenizer: str,
    exceptions: dict[str, str],
) -> VerifyRow:
    """Measure and classify a single registry row. Extracted from
    ``verify_registry`` so that function stays a thin per-section loop."""
    if "*" in file_path:
        # Glob rows (e.g. `knowledge/test-matrix-examples/*.md`) sum tokens
        # across multiple files — that summation logic is not built in this
        # pass (a known, documented limitation, not a defect). Reported
        # visibly as "unsupported_glob" rather than silently dropped, and
        # excluded from the --verify exit code by compute_verify_exit_code.
        return VerifyRow(heading, name, file_path, declared_n, None, None, "unsupported_glob")

    target = base_dir / file_path
    if not target.is_file():
        return VerifyRow(heading, name, file_path, declared_n, None, None, "missing_file")

    measured_n = count_tokens(target, tokenizer)
    # Normalized against measured_n, not declared_n: the module treats the
    # measured value as ground truth (see DEVIATION_THRESHOLD_PCT's own
    # comment), so the deviation percentage must be relative to it — a fixed
    # 100-token gap must fail or pass the same way regardless of which side
    # (declared or measured) happens to be larger.
    if measured_n:
        deviation_pct = abs(measured_n - declared_n) / measured_n * 100
    else:
        deviation_pct = 0.0 if declared_n == 0 else float("inf")

    reason = exceptions.get(file_path)
    status: VerifyStatus
    if reason:
        status = "exempt"
    elif deviation_pct > DEVIATION_THRESHOLD_PCT:
        status = "deviated"
    else:
        status = "ok"

    return VerifyRow(heading, name, file_path, declared_n, measured_n, deviation_pct, status, reason)


def verify_registry(
    base_dir: Path,
    registry_path: Path,
    tokenizer: str,
    exceptions: dict[str, str] | None = None,
) -> tuple[list[VerifyRow], list[str]]:
    """Parse ``registry_path``'s "## Team Agents", "## Skills Registry", and
    "## Knowledge Files" tables, measure each row's real file (resolved
    against ``base_dir``), and compare against the declared value using
    ``DEVIATION_THRESHOLD_PCT``.

    Returns ``(rows, section_errors)``. Never raises for a missing heading,
    a heading with zero parsed rows, or a missing file — all three are
    reported in the return value instead of crashing. This function never
    reads ``CLAUDE.md``; ``registry_path`` is its only input file.
    """
    exceptions = exceptions or {}

    if not registry_path.is_file():
        return [], [f"registry file not found: {registry_path}"]

    text = registry_path.read_text(encoding="utf-8", errors="replace")

    rows: list[VerifyRow] = []
    section_errors: list[str] = []

    for heading in ("Team Agents", "Skills Registry", "Knowledge Files"):
        block = extract_table_block(text, heading)
        if block is None:
            section_errors.append(f"section not found: ## {heading}")
            continue

        section_rows = parse_registry_rows(block)
        if not section_rows:
            section_errors.append(f"'## {heading}' found but zero rows parsed — check table format")
            continue

        for name, file_path, declared_n in section_rows:
            rows.append(_build_verify_row(heading, name, file_path, declared_n, base_dir, tokenizer, exceptions))

    return rows, section_errors


def compute_verify_exit_code(rows: list[VerifyRow], section_errors: list[str]) -> int:
    """0 when every row is ok/exempt/unsupported_glob and no expected
    section is missing or empty; 1 when any row deviated past threshold, any
    row's file is missing, or any expected heading wasn't found or parsed
    zero rows. A glob row (status "unsupported_glob") is a known, documented
    limitation, not a failure, so it never contributes to a non-zero exit."""
    if section_errors:
        return 1
    if any(row.status in ("deviated", "missing_file") for row in rows):
        return 1
    return 0


def print_verify_report(
    registry_path: Path,
    tokenizer_note: str,
    rows: list[VerifyRow],
    section_errors: list[str],
) -> None:
    print("# measure_tokens.py --verify output")
    print(f"# tokenizer: {tokenizer_note}")
    print(f"# registry: {registry_path}")
    print()
    header = (
        f"{'SECTION':<16} {'NAME':<38} {'FILE':<42} "
        f"{'DECLARED':>9} {'MEASURED':>9} {'DEV%':>7}  STATUS"
    )
    print(header)
    print("-" * len(header))
    for row in rows:
        measured_str = "ERROR" if row.measured_n is None else str(row.measured_n)
        dev_str = "n/a" if row.deviation_pct is None else f"{row.deviation_pct:.1f}"
        status = row.status.upper()
        if row.reason:
            status += f" ({row.reason})"
        print(
            f"{row.section:<16} {row.name:<38} {row.file_path:<42} "
            f"{row.declared_n:>9} {measured_str:>9} {dev_str:>7}  {status}"
        )
    print("-" * len(header))
    if section_errors:
        print()
        print("Section errors:")
        for err in section_errors:
            print(f"  ERROR: {err}")


def run_verify(repo_root: Path) -> int:
    """CLI entry point for --verify. Sources data from
    ``knowledge/agent-registry.md`` only — it never reads ``CLAUDE.md``,
    which is the actual regression this mode exists to catch (the retired
    bash script's ``--verify`` parsed a CLAUDE.md section that no longer
    exists).

    Always measures with the heuristic tokenizer, ignoring whatever
    ``detect_tokenizer()`` would select in this environment: ``tiktoken`` is
    not in requirements-dev.txt and not installed in CI, so a contributor
    who happens to have it pip-installed locally (for unrelated reasons)
    would otherwise get a different tokenizer — and potentially a different
    pass/fail verdict on borderline rows — from the exact same tree. A
    gate's verdict must not depend on what happens to be installed locally
    (same rationale as this repo's own requirements-dev.txt ruff pin).
    """
    registry_path = repo_root / "plugins" / "dev-team" / "knowledge" / "agent-registry.md"
    base_dir = repo_root / "plugins" / "dev-team"

    tokenizer = "heuristic"
    tokenizer_note = (
        "byte-count heuristic (UTF-8 bytes / "
        f"{HEURISTIC_BYTES_PER_TOKEN}) — forced for --verify regardless of "
        "environment (see run_verify docstring)"
    )

    rows, section_errors = verify_registry(base_dir, registry_path, tokenizer, VERIFY_EXCEPTIONS)
    print_verify_report(registry_path, tokenizer_note, rows, section_errors)
    return compute_verify_exit_code(rows, section_errors)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Count tokens in plugin context files. With no PATH args, "
            "measures the repo's default file set (see module docstring). "
            "With PATH args, measures just those paths."
        )
    )
    parser.add_argument("paths", nargs="*", help="Explicit paths to measure")
    parser.add_argument(
        "--verify",
        action="store_true",
        help=(
            "Verify knowledge/agent-registry.md's declared ~Tokens values "
            "against measured file sizes instead of printing a bare report."
        ),
    )
    args = parser.parse_args(argv)

    if args.verify:
        return run_verify(REPO_ROOT)

    tokenizer, tokenizer_note = detect_tokenizer()
    raw_paths = args.paths if args.paths else discover_budget_targets(REPO_ROOT)

    rows, total, errors = measure_paths(REPO_ROOT, raw_paths, tokenizer)
    print_report(REPO_ROOT, tokenizer_note, rows, total)

    if errors:
        for label, tokens in rows:
            if tokens is None:
                print(f"ERROR: {label}: not found", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
