#!/usr/bin/env python3
"""Resolve which review lenses apply to a set of changed files (#1516).

Given changed file paths, return the review-agent lenses whose ``Scope:``
declaration matches, ordered cheap-first (non-opus before opus). ``/build``'s
inline review checkpoints call this to avoid dispatching lenses with no
matching surface in the diff (a backend-only diff should not spend tokens on
frontend/UI lenses). ``/code-review`` adoption is tracked separately (#1523).

Roster source: the **Review Agents** table in ``knowledge/agent-registry.md``
(the curated lens list), minus the shared ``NON_REVIEW_AGENTS`` boundary and
the manifest-governed framework-reactivity agents — see ``MANIFEST_GOVERNED``.

Design: ``parse_scope`` and ``applicable_lenses`` are pure (unit-testable with
a synthetic roster); ``build_review_roster`` is the only I/O and fails open
(a read error never raises — the affected lens is include-biased with a
warning).

Stdlib-only. Python 3.8+. See docs/python-hook-contract.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "lib"))

import review_roster

# Framework-reactivity lenses declare bare ``**/*.ts`` / ``**/*.js`` globs, but
# their real trigger is a dependency-manifest match (``/code-review`` Step 3's
# separate rule), not a file-path match. Keep them OUT of this resolver's remit
# so a plain Node/TS backend with no React/Vue/Angular does not get reactivity
# lenses. MAINTENANCE: any new manifest-governed framework-reactivity agent
# with bare ``**/*.ts|js`` globs must be added here.
MANIFEST_GOVERNED = {
    "react-reactivity-review",
    "vue-reactivity-review",
    "angular-reactivity-review",
}

_SCOPE_RE = re.compile(r"^\s*Scope\s*:\s*(.*)$")
_MODEL_RE = re.compile(r"^\s*model\s*:\s*(.*)$")
_BULLET_RE = re.compile(r"^\s*-\s*(\S+)")
_EXT_TOKEN_RE = re.compile(r"`?(\.\w[\w.]*)`?")
# Review Agents table rows look like: | <name> | `agents/<name>.md` | ... |
# The name must start with a letter so the markdown separator row
# (| ------- | ------ | ... |) is not captured as a bogus "-------" lens.
_TABLE_ROW_RE = re.compile(r"^\|\s*([a-z][a-z0-9-]*)\s*\|")

# The sentinel an agent uses to declare it applies to every diff (`Scope: always`).
SCOPE_ALWAYS = "always"
# Heading substring that marks the Review Agents section of agent-registry.md.
# Named so a heading rename over there is greppable from here (the coupling).
_REVIEW_AGENTS_HEADING_MARKER = "review agent"


def _consume_bullet_block(lines, start_index):
    """Collect a contiguous ``- <glob>`` bullet block starting after
    ``start_index``; stop at the first non-bullet line. Returns the globs."""
    globs = []
    for nxt in lines[start_index + 1:]:
        b = _BULLET_RE.match(nxt)
        if not b:
            break
        globs.append(b.group(1).strip("`"))
    return globs


def parse_scope(text: str):
    """Return ``"always"`` | ``list[str]`` (globs) | ``None`` from agent markdown.

    The **first** ``Scope:`` line is authoritative. An empty inline value
    followed by a ``- **/*.ext`` bullet block yields that structured,
    fnmatch-ready list (preferred over the free-text second ``Scope:`` line some
    agents also carry). ``Scope: always`` -> ``"always"``. Other inline prose ->
    ``.ext`` tokens extracted as a fallback (``None`` if it names no extension).
    No ``Scope:`` line -> ``None``.
    """
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = _SCOPE_RE.match(line)
        if not m:
            continue
        value = m.group(1).strip()
        if value.lower() == SCOPE_ALWAYS:
            return SCOPE_ALWAYS
        if value:
            tokens = _EXT_TOKEN_RE.findall(value)
            return [f"**/*{t}" for t in tokens] or None
        # Empty inline value: consume the following bullet block (authoritative).
        return _consume_bullet_block(lines, i) or None
    return None


def parse_model_is_opus(text: str) -> bool:
    """True if the agent's ``model:`` frontmatter resolves to an opus tier."""
    for line in text.splitlines():
        m = _MODEL_RE.match(line)
        if m:
            return "opus" in m.group(1).strip().lower()
    return False


def _matches(file_path: str, pattern: str) -> bool:
    """Extension-aware glob match, robust to directory depth.

    ``**/*.tsx`` -> match any path ending ``.tsx``; ``**/*.component.ts`` ->
    ending ``.component.ts``. Directory-insensitive on purpose (fnmatch's ``*``
    would otherwise require a ``/`` for a ``**/`` prefix and miss top-level
    files). A non-glob pattern matches by exact path or basename.
    """
    if "*" in pattern:
        suffix = pattern.rsplit("*", 1)[-1]
        return bool(suffix) and file_path.endswith(suffix)
    return file_path == pattern or Path(file_path).name == pattern


def _scope_matches(scope, changed_files) -> bool:
    """True if a glob-list ``scope`` matches any changed file (``"always"`` is
    handled by the caller, not here)."""
    return any(_matches(f, g) for f in changed_files for g in scope)


def applicable_lenses(changed_files, roster):
    """Pure resolver. ``roster`` = ``[(name, scope, is_opus)]``. Returns
    ``(lenses, warnings)`` with lenses ordered cheap-first (non-opus, then opus).

    An empty ``changed_files`` yields ``([], [])`` — nothing to review, so no
    lens (not even ``Scope: always``) is selected. ``scope is None`` ->
    include-biased + warn; ``"always"`` -> include; glob list -> include iff any
    changed file matches.
    """
    if not changed_files:
        return [], []
    selected: list[tuple[str, bool]] = []
    warnings: list[str] = []
    for name, scope, is_opus in roster:
        if scope is None:
            warnings.append(name)
            selected.append((name, is_opus))
        elif scope == SCOPE_ALWAYS or _scope_matches(scope, changed_files):
            selected.append((name, is_opus))
    # Stable cheap-first: False (non-opus) sorts before True (opus).
    selected.sort(key=lambda pair: pair[1])
    return [name for name, _ in selected], warnings


def _registry_lens_names(registry_text: str) -> list[str]:
    """Names in the Review Agents table section of agent-registry.md."""
    names: list[str] = []
    in_section = False
    for line in registry_text.splitlines():
        if line.startswith("## "):
            in_section = _REVIEW_AGENTS_HEADING_MARKER in line.lower()
            continue
        if in_section:
            m = _TABLE_ROW_RE.match(line)
            if m:
                names.append(m.group(1))
    return names


def build_review_roster(agents_dir: Path, registry_path: Path):
    """I/O boundary: build ``roster = [(name, scope, is_opus)]`` from disk.

    Fails open: an unreadable registry yields ``([], [warning])``; an unreadable
    agent file is include-biased (``scope=None`` -> included + warned) rather
    than raising.
    """
    warnings: list[str] = []
    try:
        registry_text = registry_path.read_text(encoding="utf-8")
    except OSError:
        return [], [f"unreadable-registry:{registry_path.name}"]
    roster = []
    for name in _registry_lens_names(registry_text):
        if name in review_roster.NON_REVIEW_AGENTS or name in MANIFEST_GOVERNED:
            continue
        try:
            text = (agents_dir / f"{name}.md").read_text(encoding="utf-8")
        except OSError:
            roster.append((name, None, False))  # include-biased fail-open
            continue
        roster.append((name, parse_scope(text), parse_model_is_opus(text)))
    return roster, warnings


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Resolve applicable review lenses.")
    parser.add_argument("--files", nargs="*", default=[], help="Changed file paths")
    parser.add_argument("--agents-dir", type=Path, default=_HERE.parent / "agents")
    parser.add_argument(
        "--registry",
        type=Path,
        default=_HERE.parent / "knowledge" / "agent-registry.md",
    )
    args = parser.parse_args(argv)
    roster, enum_warnings = build_review_roster(args.agents_dir, args.registry)
    lenses, warnings = applicable_lenses(args.files, roster)
    print(json.dumps({"lenses": lenses, "warnings": enum_warnings + warnings}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
