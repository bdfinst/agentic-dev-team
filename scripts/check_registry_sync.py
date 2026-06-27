#!/usr/bin/env python3
"""Registry-completeness sensor — keep knowledge/agent-registry.md in sync with disk.

The registry tables are hand-maintained (by /agent-create, /agent-remove, or by
hand). When an agent or skill is added or removed without updating the matching
table, the catalog silently drifts: the orchestrator then routes against a roster
that no longer matches the filesystem. This check makes that drift fail loudly.

For agents (the Team Agents + Review Agents tables) and skills (the Skills
Registry table) it asserts a bijection between the files on disk and the rows in
the registry:

  * MISSING — a file exists on disk with no registry row (added, not registered).
  * ORPHAN  — a registry row points at a file that does not exist (removed but
              not de-registered, or a typo'd path).

Exit 0 when both sets match exactly; exit 1 with a per-discrepancy report
otherwise. Effort bands are deliberately NOT checked here — they live only in
agent frontmatter (read live via /model-routing-check), never mirrored in the
registry.
"""

from __future__ import annotations

import argparse
import os
import re
import sys

PLUGIN = "plugins/dev-team"


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def section_text(doc, heading):
    """Body of a '## <heading>' section, up to the next '## ' heading or EOF."""
    out, capturing = [], False
    for line in doc.splitlines():
        if line.startswith("## "):
            if capturing:
                break
            capturing = line[3:].strip() == heading
            continue
        if capturing:
            out.append(line)
    return "\n".join(out)


def registry_paths(doc, headings, pattern):
    found = set()
    for heading in headings:
        found.update(re.findall(pattern, section_text(doc, heading)))
    return found


def disk_agents(root):
    folder = os.path.join(root, PLUGIN, "agents")
    return {f"agents/{name}" for name in os.listdir(folder) if name.endswith(".md")}


def disk_skills(root):
    folder = os.path.join(root, PLUGIN, "skills")
    out = set()
    for name in sorted(os.listdir(folder)):
        if os.path.isfile(os.path.join(folder, name, "SKILL.md")):
            out.add(f"skills/{name}/SKILL.md")
    return out


def discrepancies(kind, on_disk, in_registry):
    lines = []
    for path in sorted(on_disk - in_registry):
        lines.append(
            f"  MISSING  {kind}: {path} exists on disk but has no registry row"
        )
    for path in sorted(in_registry - on_disk):
        lines.append(f"  ORPHAN   {kind}: registry row '{path}' has no file on disk")
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check agent-registry.md matches the agents/ and skills/ on disk."
    )
    parser.add_argument("--root", default=".", help="Repo root (default: cwd).")
    parser.add_argument(
        "--registry",
        help="Path to agent-registry.md "
        "(default: <root>/plugins/dev-team/knowledge/agent-registry.md).",
    )
    args = parser.parse_args(argv)

    registry = args.registry or os.path.join(
        args.root, PLUGIN, "knowledge", "agent-registry.md"
    )
    doc = read(registry)

    problems = []
    problems += discrepancies(
        "agent",
        disk_agents(args.root),
        registry_paths(
            doc, ["Team Agents", "Review Agents"], r"agents/[A-Za-z0-9._-]+\.md"
        ),
    )
    # Skills are catalogued across three surfaces: agent-loaded knowledge skills in
    # agent-registry.md, user-invocable slash commands in the plugin CLAUDE.md
    # table, and (since the size reduction) in knowledge/skills-registry.md.
    # A skill counts as registered if it appears in any of the three sources.
    skill_pat = r"skills/[A-Za-z0-9._-]+/SKILL\.md"
    claude_md = os.path.join(args.root, PLUGIN, "CLAUDE.md")
    skills_registry_md = os.path.join(
        args.root, PLUGIN, "knowledge", "skills-registry.md"
    )
    skill_sources = [doc, read(claude_md)]
    if os.path.exists(skills_registry_md):
        skill_sources.append(read(skills_registry_md))
    registered_skills = set().union(
        *[set(re.findall(skill_pat, s)) for s in skill_sources]
    )
    problems += discrepancies("skill", disk_skills(args.root), registered_skills)

    if problems:
        print("Registry out of sync with disk:")
        print("\n".join(problems))
        print(
            f"\n{len(problems)} discrepancy(ies). Update "
            f"{os.path.relpath(registry, args.root)} "
            f"(or use /agent-create, /agent-remove, which maintain it)."
        )
        return 1

    print("Registry in sync: agents/ and skills/ match agent-registry.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
