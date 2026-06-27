#!/usr/bin/env python3
"""build_skills_index.py — generate docs/skills.md from the skills' frontmatter.

docs/skills.md is the human-readable skills catalog. It used to be hand-edited,
which drifted: skills were added on disk with no catalog row (14 missing at the
time this generator was introduced). This builder makes the catalog a derived
artifact — one row per skills/<name>/SKILL.md, sourced from that file's `name`
and `description` frontmatter, split into the two sub-types the frontmatter
already encodes (`user-invocable: true` → slash command, else agent-loaded). No
hand-curation survives in the output, so it can never silently drift.

Modes (argv[1]):
  (none) / write   rebuild docs/skills.md in place (atomic write)
  --check          diff a fresh build against the on-disk file; exit non-zero
                   with a unified diff on stderr if they differ. Writes nothing.

Env (TEST-ONLY injection seams — production callers must NOT set these):
  SKILLS_INDEX_SKILLS_DIR   override the skills/ corpus root
  SKILLS_INDEX_OUTPUT       override the output path
"""

from __future__ import annotations

import difflib
import os
import sys
from pathlib import Path

import yaml

PLUGIN_DIR = Path(__file__).resolve().parents[2]  # lib -> hooks -> dev-team
SKILLS_DIR = Path(os.environ.get("SKILLS_INDEX_SKILLS_DIR", PLUGIN_DIR / "skills"))
OUTPUT = Path(os.environ.get("SKILLS_INDEX_OUTPUT", PLUGIN_DIR / "docs" / "skills.md"))

HEADER = """\
# Skills

<!-- GENERATED FILE — do not edit by hand.
     Source: each plugins/dev-team/skills/<name>/SKILL.md frontmatter (name, description).
     Regenerate: bash plugins/dev-team/hooks/lib/build-skills-index.sh
     A CI freshness gate (--check) fails if this file drifts from the skills on disk. -->

Skills are the unified reusable capability layer in this system. Every skill lives \
in `skills/<name>/SKILL.md`; its frontmatter sorts it into one of two sub-types:

- **User-invocable skills** (`user-invocable: true`) — slash-command workflows \
(e.g. `/code-review`), run under Orchestrator direction.
- **Agent-loaded skills** — knowledge modules an agent reads for domain expertise.

Each row's description is the skill's own frontmatter `description`, verbatim.
"""


class FrontmatterError(ValueError):
    """A SKILL.md whose frontmatter can't be parsed — fail loudly, never emit a
    silent empty/miscategorized catalog row."""


def _frontmatter(path: Path) -> dict:
    """Parse the YAML frontmatter block of a SKILL.md (between the first `---`s)."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise FrontmatterError(f"{path}: no `---` frontmatter block")
    end = text.find("\n---", 3)
    if end == -1:
        raise FrontmatterError(f"{path}: unterminated frontmatter block")
    try:
        data = yaml.safe_load(text[3:end])
    except yaml.YAMLError as e:
        # Almost always an unquoted scalar with a bare `: ` (e.g. a description
        # like "...agent: this skill..."). Use a `>-` block scalar to fix it.
        raise FrontmatterError(f"{path}: invalid frontmatter YAML: {e}") from e
    if not isinstance(data, dict):
        raise FrontmatterError(f"{path}: frontmatter is not a mapping")
    return data


def _cell(text: str) -> str:
    """Collapse a description to one table-safe line."""
    return " ".join(str(text).split()).replace("|", "\\|")


def _collect():
    invocable, agent_loaded = [], []
    for skill_md in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        folder = skill_md.parent.name
        fm = _frontmatter(skill_md)
        if not fm.get("description"):
            raise FrontmatterError(f"{skill_md}: frontmatter has no `description`")
        name = str(fm.get("name") or folder)
        desc = _cell(fm["description"])
        link = f"[`{folder}/SKILL.md`](../skills/{folder}/SKILL.md)"
        row = (name, folder, link, desc)
        (invocable if fm.get("user-invocable") is True else agent_loaded).append(row)
    invocable.sort(key=lambda r: r[1])
    agent_loaded.sort(key=lambda r: r[1])
    return invocable, agent_loaded


def _table(rows, slash: bool) -> str:
    head = "| Skill | File | Description |\n| --- | --- | --- |\n"
    body = []
    for name, _folder, link, desc in rows:
        label = f"`/{name}`" if slash else name
        body.append(f"| {label} | {link} | {desc} |")
    return head + "\n".join(body) + "\n"


def build() -> str:
    invocable, agent_loaded = _collect()
    parts = [HEADER, "", "## User-invocable skills", "", _table(invocable, slash=True)]
    parts += ["", "## Agent-loaded skills", "", _table(agent_loaded, slash=False)]
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
    mode = argv[1] if len(argv) > 1 else "write"
    try:
        actual = build()
    except FrontmatterError as e:
        sys.stderr.write(f"[skills-index] {e}\n")
        return 1

    if mode == "--check":
        if not OUTPUT.exists():
            sys.stderr.write(f"[skills-index] index file missing: {OUTPUT}\n")
            return 1
        current = OUTPUT.read_text(encoding="utf-8")
        if current == actual:
            return 0
        diff = difflib.unified_diff(
            current.splitlines(keepends=True),
            actual.splitlines(keepends=True),
            fromfile=str(OUTPUT),
            tofile="<fresh build>",
        )
        sys.stderr.writelines(diff)
        sys.stderr.write(
            "\n[skills-index] docs/skills.md is stale. Regenerate: "
            "bash plugins/dev-team/hooks/lib/build-skills-index.sh\n"
        )
        return 1

    if mode in ("write", ""):
        _atomic_write(OUTPUT, actual)
        return 0

    sys.stderr.write(f"Unknown mode: {mode}\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
