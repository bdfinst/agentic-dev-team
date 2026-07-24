"""Guards on how agents reference dev-team knowledge/skill files.

Three invariants, all deterministic:

1. **Anchor discipline** — every `knowledge/X.md` or `skills/Y/SKILL.md`
   reference either cites a section anchor that exists in
   `knowledge/index.json`, OR the paragraph containing it holds the literal
   verbatim token "Whole-file load:" (case-sensitive, hyphen, colon).

2. **Packaged** — every referenced dev-team knowledge/skill file actually
   exists on disk under `plugins/dev-team/`. Catches renamed/deleted files
   an agent still points at (issue #1103).

3. **Runtime-resolvable path** — knowledge references must carry the
   `${CLAUDE_PLUGIN_ROOT}/` prefix, the only form that resolves when an
   agent runs with its cwd set to the *target repo* rather than the plugin
   dir. A bare `knowledge/X.md` silently resolves to
   `<target-repo>/knowledge/X.md`, doesn't exist, and the agent degrades to
   hardcoded fallbacks (issue #1103 root cause). Prose "lives in"
   pointers spelled `plugins/dev-team/knowledge/...` are allowed.

Ported from tests/agents/agent_knowledge_anchor_tests.bats (issue #675:
bats -> pytest); extended for #1103.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT

PLUGIN_ROOT = REPO_ROOT / "plugins" / "dev-team"
INDEX = PLUGIN_ROOT / "knowledge" / "index.json"
AGENTS_DIR = PLUGIN_ROOT / "agents"
WHOLE_FILE_TOKEN = "Whole-file load:"
RESOLVABLE_PREFIX = "${CLAUDE_PLUGIN_ROOT}/"

# A dev-team knowledge/skill reference, with an optional path prefix:
#   ${CLAUDE_PLUGIN_ROOT}/knowledge/X.md   (runtime-resolvable read)
#   plugins/<name>/knowledge/X.md          (prose location pointer)
#   knowledge/X.md                         (bare — a #1103 regression)
# Cross-plugin refs (prefix = plugins/<other>/) are filtered out in code.
REF_RE = re.compile(
    r"(?P<prefix>\$\{CLAUDE_PLUGIN_ROOT\}/|plugins/[a-z0-9-]+/)?"
    r"(?P<ref>knowledge/[a-z0-9-]+\.md|skills/[a-z0-9-]+/SKILL\.md)"
    r"(?P<anchor>#[a-z0-9-]+)?"
)


def _agent_files_to_check(agent_files: str | None = None) -> list[Path]:
    """Resolve which agent files to check.

    - Default: every *.md under agents/.
    - With agent_files: only the named basenames (each must exist).
    """
    if agent_files:
        raw = agent_files.replace(",", " ").split()
        result = []
        for name in raw:
            candidate = AGENTS_DIR / name
            if not candidate.is_file():
                raise ValueError(f"AGENT_FILES contains an unknown agent: {name}")
            result.append(candidate)
        return result
    return sorted(AGENTS_DIR.glob("*.md"))


def _violations_for_file(agent_file: Path, index: dict) -> list[tuple[str, str]]:
    """Return (category, message) pairs for one agent file.

    Categories: "anchor", "packaged", "prefix".
    """
    text = agent_file.read_text(encoding="utf-8")
    paragraphs = re.split(r"\n\s*\n", text)

    violations: list[tuple[str, str]] = []
    for para in paragraphs:
        for m in REF_RE.finditer(para):
            prefix = m.group("prefix")
            ref_file = m.group("ref")
            anchor = m.group("anchor")

            # Cross-plugin reference (e.g. plugins/security-assessment/...):
            # not governed by this plugin's index — skip.
            if (
                prefix
                and prefix.startswith("plugins/")
                and prefix != "plugins/dev-team/"
            ):
                continue

            # A bare `knowledge/`/`skills/` that is actually a suffix of some
            # unmodelled path (preceded by "/") is not a dev-team reference.
            if not prefix and m.start() > 0 and para[m.start() - 1] == "/":
                continue

            key = f"plugins/dev-team/{ref_file}"

            # (3) Runtime-resolvable prefix — knowledge refs must use
            # ${CLAUDE_PLUGIN_ROOT}/. Bare knowledge/ is the #1103 defect.
            if ref_file.startswith("knowledge/") and prefix != RESOLVABLE_PREFIX and not prefix:
                violations.append(
                    (
                        "prefix",
                        (
                            f"{agent_file}: bare `{ref_file}` does not resolve at "
                            f"runtime — prefix it with `{RESOLVABLE_PREFIX}`"
                        ),
                    )
                )
            # `plugins/dev-team/knowledge/...` (a prose location pointer)
            # is tolerated; fall through to the packaging check.

            # (2) Packaged — the referenced file must exist on disk.
            if not (PLUGIN_ROOT / ref_file).is_file():
                violations.append(
                    (
                        "packaged",
                        (
                            f"{agent_file}: references `{ref_file}` which is not "
                            f"packaged (no file at {key})"
                        ),
                    )
                )

            # (1) Anchor discipline.
            if anchor:
                anchor_slug = anchor.lstrip("#")
                section_data = index.get(key, {})
                anchors = {entry.get("anchor") for entry in section_data.values()}
                if anchor_slug in anchors:
                    continue
                violations.append(
                    ("anchor", f"{agent_file}: anchor '{anchor_slug}' not found in {key}")
                )
                continue
            if WHOLE_FILE_TOKEN in para:
                continue
            violations.append(
                (
                    "anchor",
                    (
                        f"{agent_file}: bare reference {ref_file} lacks an anchor AND "
                        f"no '{WHOLE_FILE_TOKEN}' in paragraph"
                    ),
                )
            )
    return violations


def _all_violations() -> list[tuple[str, str]]:
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    out: list[tuple[str, str]] = []
    for agent_file in _agent_files_to_check():
        out.extend(_violations_for_file(agent_file, index))
    return out


def test_agent_files_typo_guard_unknown_filename_fails_loudly() -> None:
    with pytest.raises(ValueError, match="unknown agent: does-not-exist.md"):
        _agent_files_to_check("does-not-exist.md")


def test_every_knowledge_skill_reference_cites_valid_anchor_or_whole_file_load() -> (
    None
):
    violations = [msg for cat, msg in _all_violations() if cat == "anchor"]
    assert not violations, (
        "Anchor-citation violations found. Every knowledge/X.md or "
        "skills/Y/SKILL.md reference in agents/ must:\n"
        "  - end with a #anchor fragment that exists in knowledge/index.json, OR\n"
        f"  - have the literal verbatim token '{WHOLE_FILE_TOKEN}' in the same "
        "paragraph.\n\n" + "\n".join(violations)
    )


def test_every_referenced_knowledge_skill_file_is_packaged() -> None:
    violations = [msg for cat, msg in _all_violations() if cat == "packaged"]
    assert not violations, (
        "Unpackaged-reference violations found (#1103). Every knowledge/X.md "
        "or skills/Y/SKILL.md an agent references must exist on disk under "
        "plugins/dev-team/. Ship the file or drop the reference:\n\n"
        + "\n".join(violations)
    )


def test_knowledge_references_use_resolvable_plugin_root_prefix() -> None:
    violations = [msg for cat, msg in _all_violations() if cat == "prefix"]
    assert not violations, (
        "Non-resolvable knowledge references found (#1103). A bare "
        "`knowledge/X.md` resolves against the target repo's cwd at runtime, "
        f"not the plugin dir, so the agent can't read it. Prefix with "
        f"`{RESOLVABLE_PREFIX}`:\n\n" + "\n".join(violations)
    )
