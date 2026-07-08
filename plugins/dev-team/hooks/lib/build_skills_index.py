#!/usr/bin/env python3
"""build_skills_index.py — generate docs/skills.md from the skills' frontmatter.

docs/skills.md is the human-readable skills catalog. It used to be hand-edited,
which drifted: skills were added on disk with no catalog row (14 missing at the
time this generator was introduced). This builder makes the catalog a derived
artifact — one row per skills/<name>/SKILL.md (and commands/<name>.md when the
plugin has a commands/ directory), sourced from that file's `name` and
`description` frontmatter, split into the two sub-types the frontmatter already
encodes (`user-invocable: true` → slash command, else agent-loaded). No
hand-curation survives in the output, so it can never silently drift.

Modes:
  (none) / write   rebuild docs/skills.md in place (atomic write)
  --check          diff a fresh build against the on-disk file; exit non-zero
                   with a unified diff on stderr if they differ. Writes nothing.

Flags:
  --plugin-dir <path>   target a plugin other than dev-team. Derives skills_dir,
                        commands_dir, output path, and categories file from <path>.
                        The categories file is expected at <path>/skill_categories.yaml.

Env (TEST-ONLY injection seams — production callers must NOT set these):
  SKILLS_INDEX_SKILLS_DIR   override the skills/ corpus root
  SKILLS_INDEX_OUTPUT       override the output path
"""

from __future__ import annotations

import difflib
import os
import sys
from pathlib import Path

from minimal_yaml import FrontmatterError as _NoMarkersError
from minimal_yaml import YamlError, extract_frontmatter_block, parse_yaml

PLUGIN_DIR = Path(__file__).resolve().parents[2]  # lib -> hooks -> dev-team
SKILLS_DIR = Path(os.environ.get("SKILLS_INDEX_SKILLS_DIR", PLUGIN_DIR / "skills"))
OUTPUT = Path(os.environ.get("SKILLS_INDEX_OUTPUT", PLUGIN_DIR / "docs" / "skills.md"))
CATEGORIES_FILE = Path(
    os.environ.get(
        "SKILLS_INDEX_CATEGORIES",
        Path(__file__).resolve().parent / "skill_categories.yaml",
    )
)
OTHER = "Other"

HEADER = """\
# Skills

<!-- GENERATED FILE — do not edit by hand.
     Rows: each plugins/dev-team/skills/<name>/SKILL.md frontmatter (name, description).
     Grouping: plugins/dev-team/hooks/lib/skill_categories.yaml (by capability).
     Regenerate: python3 plugins/dev-team/hooks/lib/build_skills_index.py
     A CI freshness gate (--check) fails if this file drifts from the skills on disk. -->

Skills are the unified reusable capability layer in this system. Every skill lives \
in `skills/<name>/SKILL.md`. This catalog groups them **by capability** (the \
sections below); each row's description is the skill's own frontmatter \
`description`, verbatim.

Most skills are **user-invocable** as slash commands — shown as `/name`; run them \
directly or let the Orchestrator dispatch them. The rest are **agent-loaded** \
knowledge modules — shown as a plain `name` — that agents read for domain expertise.
"""


def _plugin_header(plugin_dir: Path) -> str:
    """Return a generated-file header for the given plugin directory."""
    try:
        rel = plugin_dir.relative_to(Path.cwd())
    except ValueError:
        rel = plugin_dir
    return (
        "# Skills\n"
        "\n"
        "<!-- GENERATED FILE — do not edit by hand.\n"
        f"     Rows: each {rel}/skills/<name>/SKILL.md"
        f" (and {rel}/commands/<name>.md if present).\n"
        f"     Grouping: {rel}/skill_categories.yaml (by capability).\n"
        f"     Regenerate: python3 plugins/dev-team/hooks/lib/build_skills_index.py"
        f" --plugin-dir {rel}\n"
        "     A CI freshness gate (--check) fails if this file drifts from the"
        " skills on disk. -->\n"
        "\n"
        "Skills are the unified reusable capability layer in this plugin. "
        "Skills live in `skills/<name>/SKILL.md`; user-invocable commands live "
        "in `commands/<name>.md`. This catalog groups them **by capability** (the "
        "sections below); each row's description is the file's own frontmatter "
        "`description`, verbatim.\n"
        "\n"
        "Most skills are **user-invocable** as slash commands — shown as `/name`; "
        "run them directly or let the Orchestrator dispatch them. The rest are "
        "**agent-loaded** knowledge modules — shown as a plain `name` — that agents "
        "read for domain expertise.\n"
    )


def _parse_argv(argv: list) -> tuple:
    """Returns (mode: str, plugin_dir: Path | None).

    Accepts: [--plugin-dir <path>] [--check | write]
    """
    args = list(argv[1:])
    mode = "write"
    plugin_dir = None
    i = 0
    while i < len(args):
        if args[i] == "--plugin-dir":
            if i + 1 >= len(args):
                sys.stderr.write("--plugin-dir requires a path argument\n")
                sys.exit(2)
            plugin_dir = Path(args[i + 1]).resolve()
            i += 2
        elif args[i] in ("--check", "write"):
            mode = args[i]
            i += 1
        else:
            sys.stderr.write(f"Unknown mode: {args[i]}\n")
            sys.exit(2)
    return mode, plugin_dir


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


def _load_categories(categories_file: Path | None = None) -> list:
    """Ordered [(category_name, [skill, ...]), ...] from skill_categories.yaml."""
    path = categories_file if categories_file is not None else CATEGORIES_FILE
    data = parse_yaml(path.read_text(encoding="utf-8")) or {}
    return [
        (c["name"], list(c.get("skills") or [])) for c in (data.get("categories") or [])
    ]


def _collect(
    skills_dir: Path | None = None,
    commands_dir: Path | None = None,
    categories_file: Path | None = None,
) -> list:
    """Group skills and commands by capability.

    Returns ordered [(category, rows), ...] where each row is
    (name, sort_key, link, desc, slash). A skill whose key isn't in the
    taxonomy lands in a trailing `Other` section so it stays visible in the diff.
    """
    effective_skills_dir = skills_dir if skills_dir is not None else SKILLS_DIR
    cats = _load_categories(categories_file)
    order = [name for name, _ in cats]
    lookup = {skill: name for name, skills in cats for skill in skills}
    buckets = {name: [] for name in order}

    # Scan skills/<name>/SKILL.md
    for skill_md in sorted(effective_skills_dir.glob("*/SKILL.md")):
        folder = skill_md.parent.name
        fm = _frontmatter(skill_md)
        if not fm.get("description"):
            raise FrontmatterError(f"{skill_md}: frontmatter has no `description`")
        name = str(fm.get("name") or folder)
        desc = _cell(fm["description"])
        link = f"[`{folder}/SKILL.md`](../skills/{folder}/SKILL.md)"
        slash = fm.get("user-invocable") is True
        buckets.setdefault(lookup.get(folder, OTHER), []).append(
            (name, folder, link, desc, slash)
        )

    # Scan commands/<name>.md (only when the plugin has a commands/ dir)
    if commands_dir is not None and commands_dir.is_dir():
        for cmd_md in sorted(commands_dir.glob("*.md")):
            key = cmd_md.stem
            fm = _frontmatter(cmd_md)
            if not fm.get("description"):
                raise FrontmatterError(f"{cmd_md}: frontmatter has no `description`")
            name = str(fm.get("name") or key)
            desc = _cell(fm["description"])
            link = f"[`commands/{cmd_md.name}`](../commands/{cmd_md.name})"
            slash = fm.get("user-invocable") is True
            buckets.setdefault(lookup.get(key, OTHER), []).append(
                (name, key, link, desc, slash)
            )

    display = [(name, buckets[name]) for name in order if buckets.get(name)]
    if buckets.get(OTHER):
        display.append((OTHER, buckets[OTHER]))
    for _name, rows in display:
        rows.sort(key=lambda r: r[1])
    return display


def _table(rows) -> str:
    head = "| Skill | File | Description |\n| --- | --- | --- |\n"
    body = []
    for name, _sort_key, link, desc, slash in rows:
        label = f"`/{name}`" if slash else name
        body.append(f"| {label} | {link} | {desc} |")
    return head + "\n".join(body) + "\n"


def build(
    header: str | None = None,
    skills_dir: Path | None = None,
    commands_dir: Path | None = None,
    categories_file: Path | None = None,
) -> str:
    effective_header = header if header is not None else HEADER
    parts = [effective_header]
    for cat_name, rows in _collect(skills_dir, commands_dir, categories_file):
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


def main(argv: list) -> int:
    mode, plugin_dir_override = _parse_argv(argv)

    if plugin_dir_override is not None:
        skills_dir = plugin_dir_override / "skills"
        commands_dir = plugin_dir_override / "commands"
        output = plugin_dir_override / "docs" / "skills.md"
        categories_file = plugin_dir_override / "skill_categories.yaml"
        header = _plugin_header(plugin_dir_override)
    else:
        skills_dir = None  # use module-level SKILLS_DIR (env-override aware)
        commands_dir = None  # dev-team has no commands/ dir
        output = OUTPUT
        categories_file = None  # use module-level CATEGORIES_FILE
        header = None  # use module-level HEADER

    try:
        actual = build(
            header=header,
            skills_dir=skills_dir,
            commands_dir=commands_dir,
            categories_file=categories_file,
        )
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
        regen = "python3 plugins/dev-team/hooks/lib/build_skills_index.py"
        if plugin_dir_override is not None:
            try:
                rel = plugin_dir_override.relative_to(Path.cwd())
            except ValueError:
                rel = plugin_dir_override
            regen += f" --plugin-dir {rel}"
        sys.stderr.write(
            f"\n[skills-index] docs/skills.md is stale. Regenerate: {regen}\n"
        )
        return 1

    if mode in ("write", ""):
        output.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(output, actual)
        return 0

    sys.stderr.write(f"Unknown mode: {mode}\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
