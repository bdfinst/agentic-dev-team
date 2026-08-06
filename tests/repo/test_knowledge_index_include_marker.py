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

import pytest

from _repo_root import REPO_ROOT

_HOOKS_LIB = REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"
if str(_HOOKS_LIB) not in sys.path:
    sys.path.insert(0, str(_HOOKS_LIB))

# type: ignore[import-not-found] below: a static type-checker resolves
# imports from sys.path at analysis time, before the sys.path.insert()
# above has run, so it cannot see build_knowledge_index — a real module at
# runtime, just not on the checker's search path.
from build_knowledge_index import (
    MAX_INCLUDE_DEPTH,  # type: ignore[import-not-found]
)

BUILDER = _HOOKS_LIB / "build_knowledge_index.py"


def _build(roots: Path, out: Path) -> dict:
    env = {
        **os.environ,
        "KNOWLEDGE_INDEX_CORPUS_ROOTS": str(roots),
        "KNOWLEDGE_INDEX_OUTPUT": str(out),
    }
    subprocess.run([sys.executable, str(BUILDER)], env=env, check=True)
    return json.loads(out.read_text())


def _build_capturing_stderr(roots: Path, out: Path) -> tuple[dict, str]:
    """Same as `_build`, but also returns the builder's stderr text — for
    tests asserting on the warning `_resolve_include_marker` prints when it
    refuses a symlink/escaping/unresolvable include target."""
    env = {
        **os.environ,
        "KNOWLEDGE_INDEX_CORPUS_ROOTS": str(roots),
        "KNOWLEDGE_INDEX_OUTPUT": str(out),
    }
    completed = subprocess.run(
        [sys.executable, str(BUILDER)],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(out.read_text()), completed.stderr


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


def test_include_marker_skips_fenced_code_block_in_included_file(
    tmp_path: Path,
) -> None:
    # An included file that opens with a fenced code block must not yield a
    # line from inside the fence as the "summary" — skip past it to the
    # first real prose line outside any fence.
    roots = tmp_path / "corpus"
    out = tmp_path / "index.json"
    skill_md = _skill_md(roots, "fake-skill")
    references = skill_md.parent / "references"
    references.mkdir()
    (references / "detail.md").write_text(
        "```\ncode_inside_the_fence()\n```\n\nThe real prose sentence.\n"
    )
    skill_md.write_text("## Some Section\n\n<!-- include: references/detail.md -->\n")

    data = _build(roots, out)

    key = "plugins/dev-team/skills/fake-skill/SKILL.md"
    assert data[key]["Some Section"]["summary"] == "The real prose sentence."


def test_include_marker_falls_back_to_literal_text_when_target_has_no_prose(
    tmp_path: Path,
) -> None:
    # An included file consisting only of a heading and blank lines has no
    # prose line to resolve to — fall back to the literal, unresolved
    # marker text rather than raising or indexing an empty string.
    roots = tmp_path / "corpus"
    out = tmp_path / "index.json"
    skill_md = _skill_md(roots, "fake-skill")
    references = skill_md.parent / "references"
    references.mkdir()
    (references / "detail.md").write_text("#### Just a heading\n\n\n")
    skill_md.write_text("## Some Section\n\n<!-- include: references/detail.md -->\n")

    data = _build(roots, out)

    key = "plugins/dev-team/skills/fake-skill/SKILL.md"
    assert (
        data[key]["Some Section"]["summary"]
        == "<!-- include: references/detail.md -->"
    )


def test_include_marker_with_traversal_segment_is_not_recognized_as_a_marker(
    tmp_path: Path,
) -> None:
    # A `../`-traversing path must not even match the marker grammar — the
    # single-path-segment regex forbids `/` between `references/` and the
    # `.md` suffix, so this degrades to the same "not a marker" fallback as
    # any other unrecognized `<!-- include: ... -->` line, never a read
    # outside the skill directory.
    roots = tmp_path / "corpus"
    out = tmp_path / "index.json"
    skill_md = _skill_md(roots, "fake-skill")
    outside_target = tmp_path / "outside.md"
    outside_target.write_text("Secret content that must never be indexed.\n")
    skill_md.write_text(
        "## Some Section\n\n"
        "<!-- include: references/../../outside.md -->\n"
    )

    data = _build(roots, out)

    key = "plugins/dev-team/skills/fake-skill/SKILL.md"
    assert (
        data[key]["Some Section"]["summary"]
        == "<!-- include: references/../../outside.md -->"
    )


def test_include_marker_with_backslash_traversal_segment_is_not_recognized(
    tmp_path: Path,
) -> None:
    # Same as the forward-slash traversal case above, but with a Windows
    # path separator: the marker grammar excludes `\` from the captured
    # segment too, not just `/`, so this closes off traversal at the regex
    # level on Windows rather than relying solely on the resolve()/
    # containment check as the only backstop there.
    roots = tmp_path / "corpus"
    out = tmp_path / "index.json"
    skill_md = _skill_md(roots, "fake-skill")
    outside_target = tmp_path / "outside.md"
    outside_target.write_text("Secret content that must never be indexed.\n")
    skill_md.write_text(
        "## Some Section\n\n"
        "<!-- include: references/..\\..\\outside.md -->\n"
    )

    data = _build(roots, out)

    key = "plugins/dev-team/skills/fake-skill/SKILL.md"
    assert (
        data[key]["Some Section"]["summary"]
        == "<!-- include: references/..\\..\\outside.md -->"
    )


def test_include_marker_with_embedded_nul_byte_falls_back_without_crashing(
    tmp_path: Path,
) -> None:
    # A NUL byte in the captured segment isn't excluded by the marker
    # grammar (only `/`, `\`, and whitespace are), and Path.resolve() raises
    # ValueError (not OSError) on an unencodable path — before this fix that
    # propagated uncaught, crashing a build tool whose own contract is that
    # it "must never crash" on malformed corpus content. Must fall back to
    # the literal marker text, same as any other rejected target, and the
    # build must still succeed (exit 0, verified by `_build`'s `check=True`).
    roots = tmp_path / "corpus"
    out = tmp_path / "index.json"
    skill_md = _skill_md(roots, "fake-skill")
    skill_md.write_text(
        "## Some Section\n\n"
        "<!-- include: references/x\x00y.md -->\n"
    )

    data = _build(roots, out)

    key = "plugins/dev-team/skills/fake-skill/SKILL.md"
    assert (
        data[key]["Some Section"]["summary"]
        == "<!-- include: references/x\x00y.md -->"
    )


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="symlink_to() needs Developer Mode or admin rights on Windows",
)
def test_include_marker_falls_back_to_literal_text_for_symlinked_target(
    tmp_path: Path,
) -> None:
    # A symlinked references/*.md target must never be followed — closes
    # off exfiltrating content from outside the skill directory via a
    # committed symlink (e.g. references/x.md -> ~/.ssh/config).
    roots = tmp_path / "corpus"
    out = tmp_path / "index.json"
    skill_md = _skill_md(roots, "fake-skill")
    references = skill_md.parent / "references"
    references.mkdir()
    outside_target = tmp_path / "outside.md"
    outside_target.write_text("Secret content that must never be indexed.\n")
    (references / "detail.md").symlink_to(outside_target)
    skill_md.write_text("## Some Section\n\n<!-- include: references/detail.md -->\n")

    data, stderr = _build_capturing_stderr(roots, out)

    key = "plugins/dev-team/skills/fake-skill/SKILL.md"
    assert (
        data[key]["Some Section"]["summary"]
        == "<!-- include: references/detail.md -->"
    )
    # The rejection is a distinct event class from an ordinary authoring
    # mistake (missing file, no prose line) — it must be visible, not
    # silent, so an operator debugging a stale-looking summary has a signal
    # to find. Confirms this warning path is actually reached, not just
    # documented in resolve_contained_target's docstring.
    assert "detail.md" in stderr
    assert "warning" in stderr.lower()


def test_include_marker_resolves_a_legitimate_chain_at_exactly_max_depth(
    tmp_path: Path,
) -> None:
    # The passing side of the recursion-depth boundary: a legitimate,
    # non-cyclic chain of exactly MAX_INCLUDE_DEPTH nested includes must
    # still resolve to real prose, not fall back to literal marker text —
    # only cycle/over-depth cases should hit the fallback (see the
    # cycle-exhaustion test above for the failing side of this boundary).
    roots = tmp_path / "corpus"
    out = tmp_path / "index.json"
    skill_md = _skill_md(roots, "fake-skill")
    references = skill_md.parent / "references"
    references.mkdir()
    depth = MAX_INCLUDE_DEPTH
    for i in range(depth):
        (references / f"level{i}.md").write_text(
            f"<!-- include: references/level{i + 1}.md -->\n"
        )
    (references / f"level{depth}.md").write_text("The deepest legitimate sentence.\n")
    skill_md.write_text("## Some Section\n\n<!-- include: references/level0.md -->\n")

    data = _build(roots, out)

    key = "plugins/dev-team/skills/fake-skill/SKILL.md"
    assert data[key]["Some Section"]["summary"] == "The deepest legitimate sentence."


def test_include_marker_falls_back_to_literal_text_one_level_past_max_depth(
    tmp_path: Path,
) -> None:
    # The failing side of the recursion-depth boundary, distinguished from
    # an infinite cycle: a non-cyclic chain of exactly MAX_INCLUDE_DEPTH + 1
    # nested includes never reaches its (real, non-cyclic) leaf prose —
    # falls back to literal marker text purely because it's one level too
    # deep, not because anything loops.
    roots = tmp_path / "corpus"
    out = tmp_path / "index.json"
    skill_md = _skill_md(roots, "fake-skill")
    references = skill_md.parent / "references"
    references.mkdir()
    depth = MAX_INCLUDE_DEPTH + 1
    for i in range(depth):
        (references / f"level{i}.md").write_text(
            f"<!-- include: references/level{i + 1}.md -->\n"
        )
    (references / f"level{depth}.md").write_text("Never reached.\n")
    skill_md.write_text("## Some Section\n\n<!-- include: references/level0.md -->\n")

    data = _build(roots, out)

    key = "plugins/dev-team/skills/fake-skill/SKILL.md"
    # The recursion budget is spent walking level0..level5 (6 hops, one per
    # recursive call); the 7th call — resolving the marker naming level6.md
    # — is the one that finally exceeds MAX_INCLUDE_DEPTH and falls back,
    # so the literal text names level6.md, not an earlier level.
    assert (
        data[key]["Some Section"]["summary"]
        == "<!-- include: references/level6.md -->"
    )


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
