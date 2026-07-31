"""token_efficiency_review.py — Metrics-based token efficiency reviewer.

Checks files for token-efficiency violations:
  - CLAUDE.md: character count > 5000 (error), top-level rule count > 200 (error)
  - Any file: line count > 500 (warning)
  - .md files: optional LLM quality review (unless --skip-llm)

Exit codes (matches review_result contract):
  0 = pass (clean)
  1 = fail (hard errors)
  2 = warnings only OR LLM check skipped

Usage:
  python3 scripts/token_efficiency_review.py --files <path> [<path>...] [--skip-llm]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
# review_result moved under plugins/dev-team/scripts/lib — see the note in
# progress_guardian.py. Explicit path, not `lib.`, so the two namespace-package
# `lib` directories never have to merge implicitly.
sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "plugins" / "dev-team" / "scripts" / "lib"),
)
from review_result import build_result, main_exit, make_issue, skipped_llm_warning

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "plugins" / "dev-team" / "hooks" / "lib"),
)
from token_efficiency_limits import (
    CLAUDE_MD_CHAR_LIMIT,
    FILE_LINE_LIMIT,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CLAUDE_MD_RULE_LIMIT: int = 200


# ---------------------------------------------------------------------------
# CLAUDE.md checks
# ---------------------------------------------------------------------------


def _strip_frontmatter(text: str) -> str:
    """Remove YAML frontmatter (--- ... ---) from the top of text."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text
    # Find closing ---
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            return "\n".join(lines[idx + 1 :])
    # No closing marker found — treat entire text as body
    return text


def _count_top_level_bullets(text: str) -> int:
    """Count top-level bullet/numbered list items at indent level 0.

    Patterns counted:
      - ^- (unordered bullet)
      - ^\\d+\\. (ordered list item)

    Excludes lines inside YAML frontmatter (already stripped by caller).
    """
    count = 0
    bullet_re = re.compile(r"^(-\s|\d+\.\s)")
    for line in text.splitlines():
        if bullet_re.match(line):
            count += 1
    return count


def check_claude_md(path: Path) -> list[dict]:
    """Run CLAUDE.md-specific checks. Returns list of issue dicts."""
    issues: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        issues.append(
            make_issue(
                "error",
                "high",
                str(path),
                0,
                f"Cannot read file: {exc}",
                rule_id="read-error",
            )
        )
        return issues

    # 1. Character count
    char_count = len(text)
    if char_count > CLAUDE_MD_CHAR_LIMIT:
        issues.append(
            make_issue(
                "error",
                "high",
                str(path),
                0,
                (
                    f"CLAUDE.md exceeds character limit: {char_count} chars "
                    f"(limit {CLAUDE_MD_CHAR_LIMIT}). Trim or move content to skills."
                ),
                "Extract procedures into skill files; remove duplicate or verbose sections.",
                rule_id="claude-md-char-limit",
            )
        )

    # 2. Top-level rule/bullet count
    body = _strip_frontmatter(text)
    rule_count = _count_top_level_bullets(body)
    if rule_count > CLAUDE_MD_RULE_LIMIT:
        issues.append(
            make_issue(
                "error",
                "high",
                str(path),
                0,
                (
                    f"CLAUDE.md has {rule_count} top-level bullet/rule items "
                    f"(limit {CLAUDE_MD_RULE_LIMIT}). Consolidate or move items to skills."
                ),
                "Group related rules into a skill file; remove duplicate instructions.",
                rule_id="claude-md-rule-limit",
            )
        )

    return issues


# ---------------------------------------------------------------------------
# Line count check
# ---------------------------------------------------------------------------


def check_line_counts(files: list[Path]) -> list[dict]:
    """Return warning findings for files exceeding FILE_LINE_LIMIT lines."""
    issues: list[dict] = []
    for path in files:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        line_count = len(lines)
        if line_count > FILE_LINE_LIMIT:
            issues.append(
                make_issue(
                    "warning",
                    "high",
                    str(path),
                    0,
                    (
                        f"File exceeds line limit: {line_count} lines "
                        f"(limit {FILE_LINE_LIMIT}). Consider splitting."
                    ),
                    "Extract sections into separate files or skills.",
                    rule_id="file-line-limit",
                )
            )
    return issues


# ---------------------------------------------------------------------------
# Token count (measure-tokens.sh integration)
# ---------------------------------------------------------------------------


def get_token_count(path: Path) -> int | None:
    """Run measure-tokens.sh on path and return token count, or None on failure."""
    script = Path(__file__).parent / "measure-tokens.sh"
    if not script.exists():
        return None
    try:
        result = subprocess.run(
            ["bash", str(script), str(path)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            return None
        # The script outputs a table; extract the last numeric line
        for line in reversed(result.stdout.splitlines()):
            parts = line.strip().split()
            if parts:
                try:
                    return int(parts[-1])
                except ValueError:
                    continue
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


# ---------------------------------------------------------------------------
# LLM review
# ---------------------------------------------------------------------------


def is_prose_file(path: Path) -> bool:
    """Return True when the file is a prose/markdown file suitable for LLM review."""
    return path.suffix.lower() == ".md"


def run_llm_review(path: Path) -> list[dict]:
    """Call claude CLI to review a prose file. Returns warning-severity findings.

    LLM unavailability → returns a single warning finding (exit 2, not 1).
    """
    prompt = (
        "Review this file for LLM anti-patterns that waste tokens in Claude Code config files:\n"
        "- Role preambles (You are a..., Act as...)\n"
        "- Conversational filler (Please note, It's important to)\n"
        "- Redundant context (same info repeated)\n"
        "- Hedging language (You might want to, Consider)\n"
        "- Verbose explanations before instructions\n\n"
        f"File: {path}\n"
        f"Content:\n{path.read_text(encoding='utf-8', errors='replace')[:3000]}\n\n"
        "Output a JSON array of findings (may be empty []). Each finding: "
        '{"message": "...", "line": 0, "suggestedFix": "..."}. '
        "Do NOT include any text outside the JSON array."
    )
    issues: list[dict] = []
    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            issues.append(
                make_issue(
                    "warning",
                    "high",
                    str(path),
                    0,
                    "LLM review unavailable (claude exited non-zero or no output)",
                    rule_id="llm-unavailable",
                )
            )
            return issues
        # Parse JSON output from LLM
        import json

        raw = result.stdout.strip()
        # Extract JSON array if surrounded by extra text
        start = raw.find("[")
        end = raw.rfind("]")
        if start == -1 or end == -1:
            return issues
        findings = json.loads(raw[start : end + 1])
        for f in findings:
            if not isinstance(f, dict):
                continue
            issues.append(
                make_issue(
                    "warning",  # LLM findings are always warning severity
                    "medium",
                    str(path),
                    int(f.get("line", 0)),
                    str(f.get("message", "LLM finding")),
                    str(f.get("suggestedFix", "")),
                    rule_id="llm-quality",
                )
            )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        issues.append(
            make_issue(
                "warning",
                "high",
                str(path),
                0,
                "LLM review skipped (claude not found or timed out)",
                rule_id="llm-unavailable",
            )
        )
    return issues


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--files",
        nargs="+",
        metavar="PATH",
        default=[],
        help="Files to review (required)",
    )
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="Skip LLM quality review; add an llm-skipped warning instead",
    )
    args = parser.parse_args(argv)

    if not args.files:
        print(
            '{"status":"fail","issues":[{"severity":"error","confidence":"high","file":"","line":0,"message":"No files specified. Use --files <path>...","suggestedFix":"","rule_id":"no-files"}],"summary":""}'
        )
        return 1

    files = [Path(p) for p in args.files]
    errors: list[dict] = []
    warnings: list[dict] = []

    for path in files:
        # CLAUDE.md-specific checks
        if path.name == "CLAUDE.md":
            for issue in check_claude_md(path):
                if issue["severity"] == "error":
                    errors.append(issue)
                else:
                    warnings.append(issue)

    # Line count checks for all files
    warnings.extend(check_line_counts(files))

    # LLM review for prose (.md) files
    prose_files = [p for p in files if is_prose_file(p)]
    if args.skip_llm:
        if prose_files or any(is_prose_file(p) for p in files):
            warnings.append(skipped_llm_warning())
        else:
            # Even if no prose files, add the skipped warning when flag is set
            # (the flag is explicit intent to skip)
            warnings.append(skipped_llm_warning())
    else:
        for path in prose_files:
            warnings.extend(run_llm_review(path))

    summary_parts = []
    if errors:
        summary_parts.append(f"{len(errors)} error(s)")
    if warnings:
        summary_parts.append(f"{len(warnings)} warning(s)")
    summary = ", ".join(summary_parts) if summary_parts else "No issues found."

    result = build_result(errors, warnings, summary)
    return main_exit(result)


if __name__ == "__main__":
    sys.exit(main())
