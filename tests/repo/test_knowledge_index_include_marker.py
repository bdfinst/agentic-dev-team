"""The knowledge-index builder must resolve `<!-- include: <path> -->`
marker lines when computing a section's summary, instead of indexing the
literal, unresolved marker text.

Background: /test-improve's SKILL.md was split into `references/*.md`
files, spliced back in at build/render time via `<!-- include: <path> -->`
marker lines (plans/test-improve-context-loading-strategy.md Step 1.1; the
splice mechanics are mirrored for tests in
tests/skills/skill_include_resolver.py). The knowledge-index builder's
summary extraction ran against SKILL.md's raw text, which now contains only
the marker line at that point in the document — so the summary field for
every phase header that uses this convention was the literal string
`"<!-- include: references/phase-N-....md -->"` instead of a real preview
sentence (found during review of that split; not test-improve-specific —
the fix in build_knowledge_index.py is general to any corpus file using this
convention).

Uses the `KNOWLEDGE_INDEX_CORPUS_ROOTS` / `KNOWLEDGE_INDEX_OUTPUT` test-only
injection seams (declared in build_knowledge_index.py's own module
docstring) to build a synthetic, isolated corpus rather than depending on
the real test-improve files, which may change shape independently of this
regression test.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT

BUILDER = (
    REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib" / "build_knowledge_index.py"
)


def _build(roots: Path, out: Path) -> dict:
    env = {
        **os.environ,
        "KNOWLEDGE_INDEX_CORPUS_ROOTS": str(roots),
        "KNOWLEDGE_INDEX_OUTPUT": str(out),
    }
    subprocess.run([sys.executable, str(BUILDER)], env=env, check=True)
    return json.loads(out.read_text())


def _skill_md(roots: Path, name: str) -> Path:
    skill_dir = roots / "skills" / name
    skill_dir.mkdir(parents=True)
    return skill_dir / "SKILL.md"


def test_include_marker_resolves_to_included_files_summary(tmp_path: Path) -> None:
    roots = tmp_path / "corpus"
    out = tmp_path / "index.json"
    skill_md = _skill_md(roots, "fake-skill")
    references = skill_md.parent / "references"
    references.mkdir()
    (references / "detail.md").write_text(
        "This is the real summary sentence. More prose follows here.\n"
    )
    skill_md.write_text(
        "## Some Section\n"
        "\n"
        "<!-- include: references/detail.md -->\n"
        "\n"
        "## Another Section\n"
        "Body two.\n"
    )

    data = _build(roots, out)

    key = "plugins/dev-team/skills/fake-skill/SKILL.md"
    assert data[key]["Some Section"]["summary"] == "This is the real summary sentence."
    assert data[key]["Another Section"]["summary"] == "Body two."


def test_include_marker_resolves_recursively_through_nested_includes(
    tmp_path: Path,
) -> None:
    # Mirror-matching fixture shape: the authoritative marker syntax
    # (tests/skills/skill_include_resolver.py's INCLUDE_RE) requires the
    # `references/` prefix on every marker, at every recursion depth — a
    # nested marker inside outer.md still resolves against the SAME root
    # (the skill directory) as the outer marker, never against outer.md's
    # own directory.
    roots = tmp_path / "corpus"
    out = tmp_path / "index.json"
    skill_md = _skill_md(roots, "fake-skill")
    references = skill_md.parent / "references"
    references.mkdir()
    (references / "outer.md").write_text("<!-- include: references/inner.md -->\n")
    (references / "inner.md").write_text("The nested sentence wins. Trailing text.\n")
    skill_md.write_text("## Some Section\n\n<!-- include: references/outer.md -->\n")

    data = _build(roots, out)

    key = "plugins/dev-team/skills/fake-skill/SKILL.md"
    assert data[key]["Some Section"]["summary"] == "The nested sentence wins."


def test_include_marker_falls_back_to_literal_text_at_cycle_exhaustion(
    tmp_path: Path,
) -> None:
    # A mutual include cycle (a.md <-> b.md) never resolves to real prose.
    # Unlike the mirror (tests/skills/skill_include_resolver.py), which
    # raises RecursionError on a cycle/over-depth include, the shipped
    # builder must never crash on a corpus containing a cycle — it falls
    # back to the literal, unresolved marker text at the point recursion
    # stops, same as the missing-file-fallback case above.
    roots = tmp_path / "corpus"
    out = tmp_path / "index.json"
    skill_md = _skill_md(roots, "fake-skill")
    references = skill_md.parent / "references"
    references.mkdir()
    (references / "a.md").write_text("<!-- include: references/b.md -->\n")
    (references / "b.md").write_text("<!-- include: references/a.md -->\n")
    skill_md.write_text("## Some Section\n\n<!-- include: references/a.md -->\n")

    data = _build(roots, out)

    key = "plugins/dev-team/skills/fake-skill/SKILL.md"
    assert (
        data[key]["Some Section"]["summary"]
        == "<!-- include: references/a.md -->"
    )


def test_include_marker_skips_leading_heading_in_included_file(
    tmp_path: Path,
) -> None:
    # An included file that opens with a markdown heading (e.g. the plan's
    # own review-loop.md, which opens with `#### `) must not yield the
    # heading text as the "summary" — skip to the first real prose line.
    roots = tmp_path / "corpus"
    out = tmp_path / "index.json"
    skill_md = _skill_md(roots, "fake-skill")
    references = skill_md.parent / "references"
    references.mkdir()
    (references / "detail.md").write_text(
        "#### Something\n\nThe real prose sentence. More prose follows.\n"
    )
    skill_md.write_text("## Some Section\n\n<!-- include: references/detail.md -->\n")

    data = _build(roots, out)

    key = "plugins/dev-team/skills/fake-skill/SKILL.md"
    assert data[key]["Some Section"]["summary"] == "The real prose sentence."


def test_include_marker_falls_back_to_literal_text_when_target_missing(
    tmp_path: Path,
) -> None:
    roots = tmp_path / "corpus"
    out = tmp_path / "index.json"
    skill_md = _skill_md(roots, "fake-skill")
    skill_md.write_text(
        "## Some Section\n\n<!-- include: references/does-not-exist.md -->\n"
    )

    data = _build(roots, out)

    key = "plugins/dev-team/skills/fake-skill/SKILL.md"
    assert (
        data[key]["Some Section"]["summary"]
        == "<!-- include: references/does-not-exist.md -->"
    )
