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

``--verify`` mode (registry-table parsing against ``knowledge/agent-registry.md``)
is a later step (2.2) and is intentionally not implemented here.

Tokenizer selection (first available wins), matching the bash script exactly:

1. ``tiktoken`` (cl100k_base) — industry-standard approximation of Claude
   tokenizer behavior.
2. Byte-count heuristic (``len(text.encode("utf-8")) // 4``) — coarse
   fallback. The bash script computed this via ``wc -c`` (UTF-8 *byte*
   length), not a character count, so this ports the same divisor over the
   same unit — using ``len(text) // 4`` instead would measure non-ASCII-heavy
   files (em dashes, ``·``, ``→``) slightly low relative to the bash
   script's numbers.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = REPO_ROOT / "plugins" / "dev-team"

# UTF-8 byte length divided by this is the heuristic-fallback token estimate.
HEURISTIC_BYTES_PER_TOKEN = 4


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
            "character-count heuristic (UTF-8 bytes / "
            f"{HEURISTIC_BYTES_PER_TOKEN}) — APPROXIMATE. "
            "Install tiktoken for better accuracy: pip install tiktoken",
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
    plugin_root = repo_root / "plugins" / "dev-team"
    targets: list[Path] = [
        plugin_root / "CLAUDE.md",
        plugin_root / "knowledge" / "agent-registry.md",
    ]
    targets.extend(sorted((plugin_root / "agents").glob("*.md")))
    targets.extend(sorted((plugin_root / "skills").glob("*/SKILL.md")))
    targets.extend(sorted((plugin_root / "knowledge").glob("*.md")))
    prompts_dir = plugin_root / "prompts"
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
    print(f"# date: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Count tokens in plugin context files. With no PATH args, "
            "measures the repo's default file set (see module docstring). "
            "With PATH args, measures just those paths."
        )
    )
    parser.add_argument("paths", nargs="*", help="Explicit paths to measure")
    args = parser.parse_args(argv)

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
