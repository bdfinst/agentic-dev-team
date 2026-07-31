"""claude_setup_review.py — deterministic validator for Claude Code plugin layout.

Checks:
  - CLAUDE.md present in plugin root
  - Agent frontmatter: required fields (name, description, effort)
  - Effort value membership in VALID_EFFORT
  - Unsupported top-level fields (hooks/mcpServers/permissionMode → warning)
  - Filename kebab-case convention
  - name field matches filename stem
  - Path references in CLAUDE.md exist on disk (with file+line)
  - Duplicate name fields across agent files

Exit codes:
  0 = pass (all checks pass)
  1 = fail (hard structural errors)
  2 = warn (warnings only, or LLM check skipped)
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
# `minimal_yaml` rather than PyYAML: this script ships with the plugin, and
# shipped code is stdlib-only (ADR 0014). It parses agent frontmatter, which is
# exactly the subset `minimal_yaml` exists to cover.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks" / "lib"))
from lib.review_result import make_issue
from minimal_yaml import YamlError, parse_yaml

# ---------------------------------------------------------------------------
# Module-level constants (REFACTOR: extracted here for easy maintenance)
# ---------------------------------------------------------------------------

REQUIRED_FIELDS: list[str] = ["name", "description", "effort"]

VALID_EFFORT: list[str] = ["low", "medium", "high"]

# Fields that are valid in native Claude Code agents but silently ignored
# when an agent is shipped as part of a plugin — warn, do not error. `model`
# is NOT in this list: per the verified contract (agent-contract.json), a
# plugin agent's `model:` alias/full-ID/inherit value is honored normally —
# only hooks/mcpServers/permissionMode are ignored for plugin-supplied agents.
UNSUPPORTED_FIELDS: list[str] = ["hooks", "mcpServers", "permissionMode"]

# Regex for valid kebab-case agent filenames (e.g. my-agent.md)
KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*\.md$")

# Pattern for skill/path references in CLAUDE.md we want to resolve:
# matches strings like `skills/foo/SKILL.md` or `agents/bar.md`
PATH_REF_RE = re.compile(
    r"(?:skills|agents|hooks|knowledge)/[^\s`\)\"\']+\.(?:md|sh|json|yaml|yml|py|js|ts)"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_frontmatter(text: str) -> dict | None:
    """Extract YAML frontmatter from markdown. Returns dict or None."""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    try:
        parsed = parse_yaml(text[3:end])
    except YamlError:
        return None
    return parsed if isinstance(parsed, dict) else None


# ---------------------------------------------------------------------------
# Check functions
# ---------------------------------------------------------------------------


def check_claude_md_exists(root: Path) -> list[dict]:
    """Exit 1 with message if CLAUDE.md is missing from root."""
    claude_md = root / "CLAUDE.md"
    if not claude_md.exists():
        return [
            make_issue(
                "error",
                message=f"CLAUDE.md not found at {root}",
                file=str(claude_md),
            )
        ]
    return []


def check_frontmatter(agents_dir: Path) -> list[dict]:
    """Check frontmatter required fields, effort values, and unsupported fields."""
    errors: list[dict] = []
    warnings: list[dict] = []

    if not agents_dir.exists():
        return []

    for agent_file in sorted(agents_dir.glob("*.md")):
        text = agent_file.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        rel = str(agent_file)

        if fm is None:
            errors.append(
                make_issue(
                    "error",
                    message=f"Could not parse YAML frontmatter in {agent_file.name}",
                    file=rel,
                )
            )
            continue

        # Required fields
        for field in REQUIRED_FIELDS:
            if field not in fm or fm[field] is None or str(fm[field]).strip() == "":
                errors.append(
                    make_issue(
                        "error",
                        message=f"Missing required frontmatter field '{field}' in {agent_file.name}",
                        file=rel,
                        suggested_fix=f"Add '{field}: <value>' to the frontmatter.",
                    )
                )

        # Effort value validation (only if present — missing already flagged above)
        if "effort" in fm and fm["effort"] is not None:
            effort_val = str(fm["effort"])
            if effort_val not in VALID_EFFORT:
                errors.append(
                    make_issue(
                        "error",
                        message=(
                            f"Invalid effort value '{effort_val}' in {agent_file.name}. "
                            f"Must be one of: {', '.join(VALID_EFFORT)}"
                        ),
                        file=rel,
                        suggested_fix=f"Set effort to one of: {', '.join(VALID_EFFORT)}",
                    )
                )

        # Unsupported fields — warning only
        for field in UNSUPPORTED_FIELDS:
            if field in fm:
                warnings.append(
                    make_issue(
                        "warning",
                        message=(
                            f"Plugin-unsupported field '{field}' in {agent_file.name}. "
                            f"This field is ignored for plugin agents."
                        ),
                        file=rel,
                        suggested_fix=(
                            f"Remove '{field}' or move agent to .claude/agents/ "
                            f"if you need this field to take effect."
                        ),
                    )
                )

    return errors + warnings


def check_naming(agents_dir: Path) -> list[dict]:
    """Check filenames are kebab-case and name field matches stem."""
    errors: list[dict] = []

    if not agents_dir.exists():
        return []

    for agent_file in sorted(agents_dir.glob("*.md")):
        rel = str(agent_file)
        fname = agent_file.name

        # Kebab-case filename check
        if not KEBAB_RE.match(fname):
            errors.append(
                make_issue(
                    "error",
                    message=(
                        f"Agent filename '{fname}' is not kebab-case. "
                        f"Filenames must match ^[a-z0-9]+(-[a-z0-9]+)*\\.md$"
                    ),
                    file=rel,
                    suggested_fix=f"Rename to '{fname.lower()}' or use hyphens between words.",
                )
            )
            # Don't also check name/stem mismatch for non-conforming files
            continue

        # name field vs filename stem mismatch
        text = agent_file.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        if fm is not None and "name" in fm and fm["name"] is not None:
            declared_name = str(fm["name"]).strip()
            stem = agent_file.stem  # filename without .md
            if declared_name != stem:
                errors.append(
                    make_issue(
                        "error",
                        message=(
                            f"Agent name field '{declared_name}' does not match "
                            f"filename stem '{stem}' in {fname}"
                        ),
                        file=rel,
                        suggested_fix=(
                            f"Either rename the file to '{declared_name}.md' "
                            f"or change the name field to '{stem}'."
                        ),
                    )
                )

    return errors


def check_path_references(root: Path) -> list[dict]:
    """Check that path references in CLAUDE.md resolve to existing files."""
    errors: list[dict] = []
    claude_md = root / "CLAUDE.md"
    if not claude_md.exists():
        return []

    text = claude_md.read_text(encoding="utf-8")
    lines = text.splitlines()

    for lineno, line in enumerate(lines, start=1):
        for match in PATH_REF_RE.finditer(line):
            ref_path = match.group(0)
            # Strip trailing punctuation that might follow the path
            ref_path = ref_path.rstrip(".,;:!?")
            resolved = root / ref_path
            if not resolved.exists():
                errors.append(
                    make_issue(
                        "error",
                        message=f"Unresolvable path reference '{ref_path}' in CLAUDE.md",
                        file=str(claude_md),
                        line=lineno,
                        suggested_fix=f"Create the file at '{resolved}' or remove the reference.",
                    )
                )

    return errors


def check_duplicate_names(agents_dir: Path) -> list[dict]:
    """Check for duplicate name fields across agent files."""
    errors: list[dict] = []

    if not agents_dir.exists():
        return []

    name_to_files: dict = {}

    for agent_file in sorted(agents_dir.glob("*.md")):
        text = agent_file.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        if fm is None or "name" not in fm or fm["name"] is None:
            continue
        name = str(fm["name"]).strip()
        if name not in name_to_files:
            name_to_files[name] = []
        name_to_files[name].append(str(agent_file))

    for name, files in name_to_files.items():
        if len(files) > 1:
            errors.append(
                make_issue(
                    "error",
                    message=(
                        f"Duplicate agent name '{name}' declared in multiple files: "
                        + ", ".join(files)
                    ),
                    file=files[0],
                    suggested_fix="Rename one of the agents to a unique name.",
                )
            )

    return errors


def check_llm(root: Path, skip_llm: bool, errors: list[dict]) -> list[dict]:
    """Run LLM quality check if structural checks passed and --skip-llm not set."""
    sys.path.insert(0, str(Path(__file__).parent))
    from lib.review_result import skipped_llm_warning

    if skip_llm:
        return [skipped_llm_warning()]

    # LLM only fires when no structural errors exist
    if errors:
        return []

    prompt = (
        f"Review the Claude Code plugin at '{root}' for quality issues in CLAUDE.md "
        f"and agent files. Report any significant concerns as JSON with fields: "
        f"message, severity (warning only), file. Be brief."
    )

    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return [
                make_issue(
                    "warning",
                    message="LLM quality check unavailable (claude returned non-zero or empty output)",
                )
            ]
        # LLM findings are always warnings
        return [
            make_issue(
                "warning",
                message=f"LLM quality review: {result.stdout.strip()[:500]}",
            )
        ]
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return [
            make_issue(
                "warning",
                message="LLM quality check unavailable (claude not on PATH or timed out)",
            )
        ]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a Claude Code plugin's structural layout."
    )
    parser.add_argument(
        "--plugin-root",
        default=os.getcwd(),
        help="Root directory of the plugin (default: CWD)",
    )
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="Skip the LLM quality check and add a warning finding instead.",
    )
    args = parser.parse_args(argv)

    root = Path(args.plugin_root).resolve()
    print(f"plugin-root: {root}", file=sys.stderr)

    agents_dir = root / "agents"

    errors: list[dict] = []
    warnings: list[dict] = []

    # --- Structural checks ---
    claude_md_issues = check_claude_md_exists(root)
    for issue in claude_md_issues:
        if issue["severity"] == "error":
            errors.append(issue)
        else:
            warnings.append(issue)

    frontmatter_issues = check_frontmatter(agents_dir)
    for issue in frontmatter_issues:
        if issue["severity"] == "error":
            errors.append(issue)
        else:
            warnings.append(issue)

    naming_issues = check_naming(agents_dir)
    for issue in naming_issues:
        if issue["severity"] == "error":
            errors.append(issue)
        else:
            warnings.append(issue)

    path_issues = check_path_references(root)
    for issue in path_issues:
        if issue["severity"] == "error":
            errors.append(issue)
        else:
            warnings.append(issue)

    dup_issues = check_duplicate_names(agents_dir)
    for issue in dup_issues:
        if issue["severity"] == "error":
            errors.append(issue)
        else:
            warnings.append(issue)

    # --- LLM check (fires only when structural checks pass) ---
    llm_issues = check_llm(root, args.skip_llm, errors)
    for issue in llm_issues:
        if issue["severity"] == "error":
            errors.append(issue)
        else:
            warnings.append(issue)

    # Build result and exit
    sys.path.insert(0, str(Path(__file__).parent))
    from lib.review_result import build_result, main_exit

    result = build_result(errors, warnings)
    return main_exit(result)


if __name__ == "__main__":
    sys.exit(main())
