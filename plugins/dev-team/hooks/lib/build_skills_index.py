#!/usr/bin/env python3
"""build_skills_index.py — generate docs/skills.md from the skills' frontmatter.

docs/skills.md is the human-readable skills catalog. It used to be hand-edited,
which drifted: skills were added on disk with no catalog row (14 missing at the
time this generator was introduced). This builder makes the catalog a derived
artifact — one row per skills/<name>/SKILL.md (and commands/<name>.md when the
directory exists), sourced from that file's `name` and `description` frontmatter,
split into the three sub-types the frontmatter already encodes:
  - user-invocable with argument-hint  → slash command, hint in Options column
  - user-invocable without argument-hint → slash command, "no flags — run directly"
  - agent-loaded (user-invocable absent or false) → "agent-loaded — not directly invocable"
No hand-curation survives in the output, so it can never silently drift.

Modes (argv[1]):
  (none) / write   rebuild docs/skills.md in place (atomic write)
  --check          diff a fresh build against the on-disk file; exit non-zero
                   with a unified diff on stderr if they differ. Writes nothing.

Flags:
  --plugin-dir <path>   Root directory of a plugin (default: two levels above this
                        file, i.e. the dev-team plugin). Overrides the default
                        SKILLS_DIR, OUTPUT, and CATEGORIES_FILE paths.

Env (TEST-ONLY injection seams — lower-level overrides, below --plugin-dir;
     production callers must NOT set these):
  SKILLS_INDEX_SKILLS_DIR   override the skills/ corpus root
  SKILLS_INDEX_OUTPUT       override the output path
  SKILLS_INDEX_CATEGORIES   override the skill_categories.yaml path
"""

from __future__ import annotations

import argparse
import difflib
import os
import sys
from pathlib import Path

from minimal_yaml import FrontmatterError as _NoMarkersError
from minimal_yaml import YamlError, extract_frontmatter_block, parse_yaml

_SCRIPT_DIR = Path(__file__).resolve().parent
_DEFAULT_PLUGIN_DIR = _SCRIPT_DIR.parents[1]  # lib -> hooks -> dev-team

# Options-column sentinel values
_OPT_NO_FLAGS = "no flags — run directly"
_OPT_AGENT_LOADED = "agent-loaded — not directly invocable"
_OPT_UNGROUPED_SECTION = "Ungrouped"
_OPT_OTHER = "Other"


def _resolve_paths(plugin_dir: Path) -> tuple[Path, Path, Path]:
    """Return (skills_dir, output, categories_file) for a plugin directory.

    Env vars are lower-level overrides, applied after --plugin-dir so the
    SKILLS_INDEX_* test seam keeps working without modification.
    """
    skills_dir = Path(
        os.environ.get(
            "SKILLS_INDEX_SKILLS_DIR", plugin_dir / "skills"
        )
    )
    output = Path(
        os.environ.get(
            "SKILLS_INDEX_OUTPUT", plugin_dir / "docs" / "skills.md"
        )
    )
    # For categories: env var wins, else <plugin>/hooks/lib/skill_categories.yaml,
    # falling back to the dev-team one when the plugin has none (only when the
    # env var is absent and the plugin-specific file does not exist the caller
    # should let it be missing — _load_categories handles that gracefully).
    cats_default = plugin_dir / "hooks" / "lib" / "skill_categories.yaml"
    categories_file = Path(
        os.environ.get("SKILLS_INDEX_CATEGORIES", cats_default)
    )
    return skills_dir, output, categories_file


def _make_header(plugin_dir: Path) -> str:
    """Return a header block appropriate for `plugin_dir`.

    When targeting the default dev-team plugin the header uses the short form
    without --plugin-dir.  For any other plugin the header includes the
    relative plugin path so readers know how to regenerate the file.
    """
    rel = str(plugin_dir.relative_to(Path.cwd())) if plugin_dir != _DEFAULT_PLUGIN_DIR else None
    if rel:
        return (
            "# Skills\n\n"
            "<!-- GENERATED FILE — do not edit by hand.\n"
            f"     Rows: each {rel}/skills/<name>/SKILL.md (and {rel}/commands/<name>.md if present).\n"
            f"     Grouping: {rel}/skill_categories.yaml (by capability).\n"
            f"     Regenerate: python3 plugins/dev-team/hooks/lib/build_skills_index.py --plugin-dir {rel}\n"
            "     A CI freshness gate (--check) fails if this file drifts from the skills on disk. -->\n\n"
            "Skills are the unified reusable capability layer in this plugin. "
            "Skills live in `skills/<name>/SKILL.md`; user-invocable commands live "
            "in `commands/<name>.md`. This catalog groups them **by capability** (the "
            "sections below); each row's description is the file's own frontmatter "
            "`description`, verbatim.\n\n"
            "Most skills are **user-invocable** as slash commands — shown as `/name`; run them "
            "directly or let the Orchestrator dispatch them. The rest are **agent-loaded** "
            "knowledge modules — shown as a plain `name` — that agents read for domain expertise.\n"
        )
    return (
        "# Skills\n\n"
        "<!-- GENERATED FILE — do not edit by hand.\n"
        "     Rows: each plugins/dev-team/skills/<name>/SKILL.md frontmatter (name, description).\n"
        "     Grouping: plugins/dev-team/hooks/lib/skill_categories.yaml (by capability).\n"
        "     Regenerate: python3 plugins/dev-team/hooks/lib/build_skills_index.py\n"
        "     A CI freshness gate (--check) fails if this file drifts from the skills on disk. -->\n\n"
        "Skills are the unified reusable capability layer in this system. Every skill lives "
        "in `skills/<name>/SKILL.md`. This catalog groups them **by capability** (the "
        "sections below); each row's description is the skill's own frontmatter "
        "`description`, verbatim.\n\n"
        "Most skills are **user-invocable** as slash commands — shown as `/name`; run them "
        "directly or let the Orchestrator dispatch them. The rest are **agent-loaded** "
        "knowledge modules — shown as a plain `name` — that agents read for domain expertise.\n"
    )


# Keep a module-level constant for the dev-team default (used by tests that
# import HEADER directly).
HEADER = _make_header(_DEFAULT_PLUGIN_DIR)


class FrontmatterError(ValueError):
    """A SKILL.md whose frontmatter can't be parsed — fail loudly, never emit a
    silent empty/miscategorized catalog row."""


def _frontmatter(path: Path) -> dict:
    """Parse the YAML frontmatter block of a SKILL.md (between the first `---`s)."""
    text = path.read_text(encoding="utf-8")
    try:
        block = extract_frontmatter_block(text)
    except _NoMarkersError as e:
        raise FrontmatterError(f"{path}: {e}") from e
    try:
        data = parse_yaml(block)
    except YamlError as e:
        # Almost always an unquoted scalar with a bare `: ` (e.g. a description
        # like "...agent: this skill..."). Use a `>-` block scalar to fix it.
        raise FrontmatterError(f"{path}: invalid frontmatter YAML: {e}") from e
    if not isinstance(data, dict):
        raise FrontmatterError(f"{path}: frontmatter is not a mapping")
    return data


def _cell(text: str) -> str:
    """Collapse a description to one table-safe line."""
    return " ".join(str(text).split()).replace("|", "\\|")


def _options_value(fm: dict) -> str:
    """Return the Options column value for a skill/command's frontmatter."""
    if fm.get("user-invocable") is True:
        hint = fm.get("argument-hint")
        if hint:
            return _cell(str(hint))
        return _OPT_NO_FLAGS
    return _OPT_AGENT_LOADED


def _load_categories(categories_file: Path) -> list[tuple[str, list[str]]]:
    """Ordered [(category_name, [skill, ...]), ...] from skill_categories.yaml.

    Returns an empty list when the file does not exist, which causes all entries
    to land in a trailing Ungrouped section (see _collect).
    """
    if not categories_file.exists():
        return []
    data = parse_yaml(categories_file.read_text(encoding="utf-8")) or {}
    return [
        (c["name"], list(c.get("skills") or [])) for c in (data.get("categories") or [])
    ]


def _collect(
    skills_dir: Path,
    categories_file: Path,
) -> list[tuple[str, list]]:
    """Group skills and commands by capability.

    Returns ordered [(category, rows), ...] where each row is
    (name, key, link, desc, slash, options).
    A skill/command whose key isn't in the taxonomy lands in a trailing section
    so it stays visible in the diff:
      - "Other" when a categories file exists (taxonomy gap)
      - "Ungrouped" when no categories file exists at all
    """
    cats = _load_categories(categories_file)
    has_categories = bool(cats)
    order = [name for name, _ in cats]
    lookup = {skill: name for name, skills in cats for skill in skills}
    buckets: dict[str, list] = {name: [] for name in order}

    def _add_entry(key: str, fm: dict, link: str) -> None:
        if not fm.get("description"):
            raise FrontmatterError(f"{link}: frontmatter has no `description`")
        name = str(fm.get("name") or key)
        desc = _cell(fm["description"])
        slash = fm.get("user-invocable") is True
        opts = _options_value(fm)
        fallback = _OPT_OTHER if has_categories else _OPT_UNGROUPED_SECTION
        buckets.setdefault(lookup.get(key, fallback), []).append(
            (name, key, link, desc, slash, opts)
        )

    # skills/<name>/SKILL.md — keyed by folder name
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        folder = skill_md.parent.name
        fm = _frontmatter(skill_md)
        link = f"[`{folder}/SKILL.md`](../skills/{folder}/SKILL.md)"
        _add_entry(folder, fm, link)

    # commands/<name>.md — keyed by frontmatter `name`
    commands_dir = skills_dir.parent / "commands"
    if commands_dir.is_dir():
        for cmd_md in sorted(commands_dir.glob("*.md")):
            fm = _frontmatter(cmd_md)
            key = str(fm.get("name") or cmd_md.stem)
            link = f"[`commands/{cmd_md.name}`](../commands/{cmd_md.name})"
            _add_entry(key, fm, link)

    display = [(name, buckets[name]) for name in order if buckets.get(name)]
    # Trailing ungrouped/other bucket
    fallback_key = _OPT_OTHER if has_categories else _OPT_UNGROUPED_SECTION
    if buckets.get(fallback_key):
        display.append((fallback_key, buckets[fallback_key]))
    for _name, rows in display:
        rows.sort(key=lambda r: r[1])
    return display


def _table(rows: list) -> str:
    head = "| Skill | Options | File | Description |\n| --- | --- | --- | --- |\n"
    body = []
    for name, _key, link, desc, slash, opts in rows:
        label = f"`/{name}`" if slash else name
        body.append(f"| {label} | {opts} | {link} | {desc} |")
    return head + "\n".join(body) + "\n"


def build(plugin_dir: Path) -> str:
    skills_dir, _output, categories_file = _resolve_paths(plugin_dir)
    parts = [_make_header(plugin_dir)]
    for cat_name, rows in _collect(skills_dir, categories_file):
        parts += ["", f"## {cat_name}", "", _table(rows)]
    return "\n".join(parts).rstrip("\n") + "\n"


def _atomic_write(output: Path, text: str) -> None:
    tmp = output.with_suffix(output.suffix + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, output)
    finally:
        if tmp.exists():
            tmp.unlink()


def _parse_args(argv: list[str]) -> tuple[str, Path]:
    """Return (mode, plugin_dir)."""
    parser = argparse.ArgumentParser(
        prog="build_skills_index.py",
        description="Generate docs/skills.md from plugin skill/command frontmatter.",
        add_help=True,
    )
    parser.add_argument(
        "mode",
        nargs="?",
        default="write",
        choices=["write", "--check"],
        help="write (default) or --check",
    )
    parser.add_argument(
        "--plugin-dir",
        type=Path,
        default=None,
        help="Root directory of the plugin (default: dev-team plugin).",
    )
    # argparse doesn't handle '--check' as a positional value gracefully when
    # it looks like a flag. Accept it via a dedicated flag too.
    parser.add_argument(
        "--check",
        action="store_true",
        default=False,
        help="Alias for mode=--check.",
    )
    ns = parser.parse_args(argv[1:])
    mode = "--check" if (ns.mode == "--check" or ns.check) else "write"
    plugin_dir = ns.plugin_dir.resolve() if ns.plugin_dir else _DEFAULT_PLUGIN_DIR
    return mode, plugin_dir


def main(argv: list) -> int:
    try:
        mode, plugin_dir = _parse_args(argv)
    except SystemExit as e:
        return int(e.code) if e.code is not None else 2

    _skills_dir, output, _cats = _resolve_paths(plugin_dir)

    try:
        actual = build(plugin_dir)
    except FrontmatterError as e:
        sys.stderr.write(f"[skills-index] {e}\n")
        return 1

    if mode == "--check":
        if not output.exists():
            sys.stderr.write(f"[skills-index] index file missing: {output}\n")
            return 1
        current = output.read_text(encoding="utf-8")
        if current == actual:
            return 0
        diff = difflib.unified_diff(
            current.splitlines(keepends=True),
            actual.splitlines(keepends=True),
            fromfile=str(output),
            tofile="<fresh build>",
        )
        sys.stderr.writelines(diff)
        sys.stderr.write(
            "\n[skills-index] docs/skills.md is stale. Regenerate: "
            "python3 plugins/dev-team/hooks/lib/build_skills_index.py\n"
        )
        return 1

    # write mode
    _atomic_write(output, actual)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
