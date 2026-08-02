r"""Widens `test_agent_implemented_by_resolves.py`'s bare-invocation guard
past `SKILL.md` files and the single-line `python3 scripts/....py` shape it
alone matches (#1655). Three gaps found during #1637's own triage: bare
invocations in maintainer-only docs under `plugins/dev-team/docs/`; in
skills' own `references/*.md`, not just the top-level `SKILL.md`; and in
unmatched forms (`bash scripts/x.sh`, `./scripts/x.py`, a genuine
`\`-continued two-line invocation).

Scans the same surface as `test_claude_plugin_root_quoting.py` — `docs/`,
`knowledge/`, `agents/`, and every skill's `**/*.md` — via
`_content_guard_scan.scanned_markdown_files`. Continuation is matched
per-line-pair, not via a blob-wide regex: an earlier draft's blob-wide regex
matched a fenced code block's own opening ` ```bash ` line against an
unrelated invocation two lines later. A continuation only counts when the
FIRST line itself ends in a real trailing backslash.

Reuses `INTENTIONAL_BARE_INVOCATION`/`INTENTIONAL_WORKTREE_RELATIVE` from the
original guard rather than re-tracking `SKILL.md` pairs a second time. Every
genuinely new exemption this wider scan needs is tracked in
`INTENTIONAL_WIDE_SCAN_INVOCATIONS`, keyed by `(relative_path,
invocation_line, category)`; like its two siblings, nothing in it is
expected to reach zero, and each category carries its own premise test below
re-checking the reason the exemption holds (docs/adr/0032's "mechanically,
not by comment alone").

A fourth category, `_COPIED_OUT_BY_OPERATOR`, covers ADR 0032 § "4. Shipped
for copy-out": docs instructing the operator to copy a script into their own
project, where a bare path is correct because the file no longer lives in
the plugin once copied.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

from _content_guard_scan import PLUGIN_MARKDOWN_SCAN_DIRS, scanned_markdown_files
from _repo_root import REPO_ROOT

PLUGIN_ROOT = REPO_ROOT / "plugins" / "dev-team"


def _load_sibling_module(name: str):
    """Load a sibling test module by file path, not bare-name import.

    This repo's `pytest.ini` sets `--import-mode=importlib` specifically so
    same-named test modules across two trees never collide at collection
    time — deliberately, per that config's own comment, at the cost of never
    putting a test file's own directory on `sys.path`. A bare
    `from test_agent_implemented_by_resolves import ...` is therefore
    unresolvable by design, not an oversight to work around; loading by path
    mirrors the pattern this repo's own tests already use for loading a
    module outside `pytest.ini`'s `pythonpath` list — though `test_import_
    probe_shipped.py` and `test_codebase_recon.py` apply it to *production*
    scripts, not a sibling *test* module as here (#1686 item 2); this is the
    same mechanism reused one layer over, not a literal precedent.
    """
    path = Path(__file__).resolve().parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"could not load sibling module {name}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_original_guard = _load_sibling_module("test_agent_implemented_by_resolves")
INTENTIONAL_BARE_INVOCATION = _original_guard.INTENTIONAL_BARE_INVOCATION
INTENTIONAL_WORKTREE_RELATIVE = _original_guard.INTENTIONAL_WORKTREE_RELATIVE

SCANNED_FILES = scanned_markdown_files(PLUGIN_ROOT, PLUGIN_MARKDOWN_SCAN_DIRS)
assert len(SCANNED_FILES) > 100, (
    f"only {len(SCANNED_FILES)} files found under {PLUGIN_MARKDOWN_SCAN_DIRS} — "
    "a typo'd or missing scan dir would silently disable this guard entirely"
)

#: A prefix token directly followed by a bare `scripts/....py`/`.sh` target on
#: the SAME line. `(?<![\w/$}{.])` stops a match starting mid-path (e.g. the
#: "bash" inside "```bash" alone, with no following scripts/ on that same
#: line, never matches this — it only fires when scripts/... genuinely
#: follows the prefix directly). `./` needs no separating whitespace
#: (`./scripts/x.py`, not `./ scripts/x.py`); the other three prefixes do.
_SAME_LINE_INVOCATION_RE = re.compile(
    r"(?<![\w/$}{.])(?:(?:python3?|bash|sh)\s+|\./)(scripts/[\w./-]+\.(?:py|sh))"
)
#: A line that both names one of the prefixes and ends in a real shell
#: line-continuation backslash — the opener half of a two-line invocation.
_CONTINUATION_OPENER_RE = re.compile(r"(?<![\w/$}{.])(?:python3?|bash|sh)\b.*\\\s*$")
#: The continued line must itself START with the bare script path (allowing
#: leading whitespace) — a `\`-ended line followed by unrelated prose is not
#: a continuation this pattern should absorb.
_CONTINUATION_TARGET_RE = re.compile(r"^\s*(scripts/[\w./-]+\.(?:py|sh))\b")


def _same_line_matches(line: str):
    """[(line_text, subpath), ...] for every same-line bare invocation on
    `line` — a line may carry more than one invocation (e.g. two script
    paths in a comma-separated `allowed-tools`-style list), and each is
    reported independently rather than the line being treated as a single
    unit. `subpath` has its `scripts/` prefix stripped, matching
    `INTENTIONAL_BARE_INVOCATION`/`INTENTIONAL_WORKTREE_RELATIVE`'s own
    keying convention (see the original guard's own docstring)."""
    return [
        (line.strip(), match.group(1)[len("scripts/") :])
        for match in _SAME_LINE_INVOCATION_RE.finditer(line)
    ]


def _continuation_match(line: str, next_line: str):
    """`(joined_text, subpath)` if `line` ends in a genuine continuation
    backslash and `next_line` itself starts with a bare script path;
    `None` otherwise (no continuation, or `next_line` already qualifies the
    path with `${CLAUDE_PLUGIN_ROOT}`/`$CLAUDE_PLUGIN_ROOT`)."""
    if not _CONTINUATION_OPENER_RE.search(line):
        return None
    target = _CONTINUATION_TARGET_RE.match(next_line)
    if not target or "CLAUDE_PLUGIN_ROOT" in next_line:
        return None
    return (f"{line.strip()} \\ {next_line.strip()}", target.group(1)[len("scripts/") :])


def _wide_scan_matches(path):
    """[(lineno, line_text, subpath), ...] for every bare invocation in
    `path`, same-line or genuinely `\\`-continued.

    Each line is checked independently for same-line matches (there may be
    several) and, separately, for a continuation into the next line — a
    qualified invocation (`${CLAUDE_PLUGIN_ROOT}`/`$CLAUDE_PLUGIN_ROOT`)
    elsewhere on the SAME line never suppresses a genuine bare invocation
    also present on it, since `_SAME_LINE_INVOCATION_RE` only matches where
    `scripts/...` genuinely follows a prefix directly — a qualified
    invocation's `${CLAUDE_PLUGIN_ROOT}/` prefix never satisfies that.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    hits = []
    for i, line in enumerate(lines):
        for line_text, subpath in _same_line_matches(line):
            hits.append((i + 1, line_text, subpath))
        if i + 1 < len(lines):
            continuation = _continuation_match(line, lines[i + 1])
            if continuation is not None:
                hits.append((i + 1, continuation[0], continuation[1]))
    return hits


#: Categories for `INTENTIONAL_WIDE_SCAN_INVOCATIONS`, each with its own
#: premise test below (docs/adr/0032's "mechanically, not by comment alone").
_MONOREPO_ONLY = "monorepo-only"
_BRANCH_LOCAL = "branch-local"
_COPIED_OUT_BY_OPERATOR = "copied-out-by-operator"

#: (relative-to-plugin-root path, exact invocation line as `_wide_scan_matches`
#: reports it, category) triples exempted from the wide scan, beyond whatever
#: `INTENTIONAL_BARE_INVOCATION`/`INTENTIONAL_WORKTREE_RELATIVE` already
#: covers for `SKILL.md` files. Justified exemptions, not tracked defects —
#: like the two sibling registries, nothing here is expected to shrink to
#: zero on its own; an entry is removed only when the invocation itself is
#: removed or requalified (checked by `test_no_stale_wide_scan_exemptions`),
#: and each category's premise is re-checked below rather than trusted from
#: the comment alone.
#:
#: Keyed by exact line text (not `(rel_path, subpath)` like its sibling
#: `INTENTIONAL_BARE_INVOCATION`) on purpose, not by oversight — reviewed in
#: #1686 item 1: a line-text key churns on any cosmetic edit to the
#: invocation, which did cost 7 re-transcribed entries during the #1656
#: quoting sweep. Re-keying to `(rel_path, subpath)` was deliberately deferred
#: rather than spent here, pending a second churn event that would prove the
#: cost recurring rather than a one-off.
INTENTIONAL_WIDE_SCAN_INVOCATIONS = {
    # _MONOREPO_ONLY — these scripts only exist at, and only make sense run
    # from, this repo's own root; none of them ship under
    # plugins/dev-team/scripts/, matching agent-eval's own established
    # exemption for the same scripts. Premise checked by
    # test_monorepo_only_exemptions_scripts_do_not_ship.
    (
        "docs/eval-maintenance.md",
        "3. `python3 scripts/eval_grade.py --check-corpus` (every expectation must be",
        _MONOREPO_ONLY,
    ),
    (
        "docs/eval-running-guide.md",
        "bash scripts/run-full-eval.sh [TRIALS]   # default TRIALS=1; default mode = full sweep",
        _MONOREPO_ONLY,
    ),
    ("docs/eval-running-guide.md", "bash scripts/run-full-eval.sh", _MONOREPO_ONLY),
    (
        "docs/eval-running-guide.md",
        "bash scripts/run-full-eval.sh 5 --agent security-review   # just this agent, 5 trials",
        _MONOREPO_ONLY,
    ),
    (
        "docs/eval-running-guide.md",
        "bash scripts/run-full-eval.sh 5 --agent arch-review       # next time, another agent",
        _MONOREPO_ONLY,
    ),
    (
        "docs/eval-running-guide.md",
        "bash scripts/eval-changed.sh BASE HEAD   # evals only the agents/skills the diff touched",
        _MONOREPO_ONLY,
    ),
    # These two are same-line matches whose trailing backslash continues into
    # more CLI flags, not a second script-path line — the scanner records
    # only the opener line itself, not a joined pair.
    (
        "docs/eval-running-guide.md",
        "python3 scripts/eval_variance.py --trials-dir <dir-of-trial-actuals> \\",
        _MONOREPO_ONLY,
    ),
    (
        "docs/telemetry-ci-access.md",
        "python3 scripts/session_extract.py --cost-log /tmp/telemetry/digests \\",
        _MONOREPO_ONLY,
    ),
    (
        "docs/telemetry-ci-access.md",
        "run: bash scripts/ci-local.sh --only=chk_cost_regression",
        _MONOREPO_ONLY,
    ),
    # _BRANCH_LOCAL — setup/SKILL.md's dev-setup.sh call is reached ONLY
    # inside the Step 2 `in-repo` branch: it fires exclusively when /setup
    # has already detected it is running inside this monorepo's own
    # checkout, so a bare, repo-root-relative path is the correct (and only
    # working) form. Premise checked by
    # test_branch_local_exemption_is_still_gated_behind_in_repo_detection.
    ("skills/setup/SKILL.md", "bash scripts/dev-setup.sh", _BRANCH_LOCAL),
    # _COPIED_OUT_BY_OPERATOR — a fourth, distinct case (see module
    # docstring): documentation instructing the OPERATOR to copy this file
    # into THEIR OWN project before running it there — the bare path is
    # correct because the file deliberately no longer lives in the plugin
    # once copied. Premise checked by
    # test_copied_out_exemption_still_instructs_operator_to_copy.
    (
        "skills/mutation-testing/references/languages/csharp-stryker-net.md",
        "python3 scripts/csharp_stryker_net_wrapper.py \\",
        _COPIED_OUT_BY_OPERATOR,
    ),
}


def _is_known_skill_pair_exemption(rel_path: str, subpath: str) -> bool:
    """True if `rel_path` is a `skills/<name>/SKILL.md` already classified by
    the original guard's own registries — reused, not duplicated."""
    match = re.fullmatch(r"skills/([^/]+)/SKILL\.md", rel_path)
    if not match:
        return False
    skill_name = match.group(1)
    return (skill_name, subpath) in INTENTIONAL_BARE_INVOCATION or (
        skill_name,
        subpath,
    ) in INTENTIONAL_WORKTREE_RELATIVE


def _wide_scan_exemption_lines(rel_path: str):
    return {line for path, line, _category in INTENTIONAL_WIDE_SCAN_INVOCATIONS if path == rel_path}


@pytest.mark.parametrize("path", SCANNED_FILES, ids=lambda p: p.relative_to(PLUGIN_ROOT).as_posix())
def test_wide_scan_bare_invocations_are_all_exempted_or_absent(path):
    rel = path.relative_to(PLUGIN_ROOT).as_posix()
    exempt_lines = _wide_scan_exemption_lines(rel)
    offenders = [
        f"{lineno}: {line}"
        for lineno, line, subpath in _wide_scan_matches(path)
        if not _is_known_skill_pair_exemption(rel, subpath) and line not in exempt_lines
    ]
    assert not offenders, (
        f"{rel}: invokes a plugin script by a bare relative path outside any "
        "documented exemption; use ${{CLAUDE_PLUGIN_ROOT}}/scripts/… or add a "
        "justified entry to INTENTIONAL_WIDE_SCAN_INVOCATIONS:\n  " + "\n  ".join(offenders)
    )


def test_no_stale_wide_scan_exemptions():
    """Shrink-only: an exemption whose exact line no longer appears in its
    file has been fixed (or the line changed) — remove it here rather than
    let it become unchecked, permanent slack."""
    still_present = set()
    for path in SCANNED_FILES:
        rel = path.relative_to(PLUGIN_ROOT).as_posix()
        for _lineno, line, _subpath in _wide_scan_matches(path):
            for entry in INTENTIONAL_WIDE_SCAN_INVOCATIONS:
                if entry[0] == rel and entry[1] == line:
                    still_present.add(entry)
    stale = INTENTIONAL_WIDE_SCAN_INVOCATIONS - still_present
    assert not stale, (
        "INTENTIONAL_WIDE_SCAN_INVOCATIONS entries no longer reproduce — remove them:\n"
        + "\n".join(f"  {rel!r}: {line!r} ({category})" for rel, line, category in sorted(stale))
    )


def test_wide_scan_exemption_paths_exist_on_disk():
    for rel, _line, _category in INTENTIONAL_WIDE_SCAN_INVOCATIONS:
        assert (PLUGIN_ROOT / rel).is_file(), f"exempted path missing: {rel}"


def _exempted_subpath(rel_path: str, line: str) -> str | None:
    """The `subpath` `_wide_scan_matches` computed for this exact
    `(rel_path, line)` pair — re-derived rather than hand-transcribed a
    second time, so a premise check can never disagree with the scanner
    about which script an entry actually names."""
    for _lineno, matched_line, subpath in _wide_scan_matches(PLUGIN_ROOT / rel_path):
        if matched_line == line:
            return subpath
    return None


def test_monorepo_only_exemptions_scripts_do_not_ship():
    """Premise for `_MONOREPO_ONLY` entries: the named script must not exist
    under `plugins/dev-team/scripts/` — the moment it does, it ships, and a
    bare invocation of it becomes a real #1637-shaped defect rather than a
    correct monorepo-only reference."""
    for rel_path, line, category in INTENTIONAL_WIDE_SCAN_INVOCATIONS:
        if category != _MONOREPO_ONLY:
            continue
        subpath = _exempted_subpath(rel_path, line)
        assert subpath is not None, f"{rel_path}: exemption line no longer matches any invocation: {line!r}"
        assert not (PLUGIN_ROOT / "scripts" / subpath).is_file(), (
            f"{subpath} now ships under plugins/dev-team/scripts/ — the monorepo-only "
            f"premise behind {rel_path}'s exemption no longer holds; qualify the "
            "invocation with ${CLAUDE_PLUGIN_ROOT} instead of keeping this exemption."
        )


def test_branch_local_exemption_is_still_gated_behind_in_repo_detection():
    """Premise for `_BRANCH_LOCAL` entries: the exempted invocation must
    still sit after the file's own in-repo-detection branch, not run
    unconditionally."""
    for rel_path, line, category in INTENTIONAL_WIDE_SCAN_INVOCATIONS:
        if category != _BRANCH_LOCAL:
            continue
        lines = (PLUGIN_ROOT / rel_path).read_text(encoding="utf-8").splitlines()
        matching = [i for i, text in enumerate(lines) if line in text]
        assert matching, f"{rel_path}: exemption line no longer found: {line!r}"
        preceding = "\n".join(lines[: matching[0]])
        assert "in-repo" in preceding, (
            f"{rel_path}: the branch-local exemption for {line!r} no longer sits after an "
            "'in-repo' detection branch — the premise that this invocation only ever runs "
            "inside this monorepo's own checkout no longer holds."
        )


def test_copied_out_exemption_still_instructs_operator_to_copy():
    """Premise for `_COPIED_OUT_BY_OPERATOR` entries: the doc must still
    tell the operator to copy the script into their OWN project — the
    premise that makes a bare path correct rather than merely unqualified."""
    for rel_path, _line, category in INTENTIONAL_WIDE_SCAN_INVOCATIONS:
        if category != _COPIED_OUT_BY_OPERATOR:
            continue
        text = (PLUGIN_ROOT / rel_path).read_text(encoding="utf-8")
        assert "your repo" in text or "your project" in text, (
            f"{rel_path} no longer instructs the operator to copy the script into their own "
            "project — the premise behind its bare-invocation exemption no longer holds."
        )


class TestGenuineTwoLineContinuation:
    """No file in the shipped tree currently exercises the shape #1655 named
    as a gap — `python3 \\` alone on one line, the bare `scripts/...` path
    starting the NEXT line (as opposed to every real instance found here,
    where the interpreter and the path share one line and only trailing
    FLAGS continue). Exercised synthetically so this branch of
    `_wide_scan_matches` isn't untested, unreachable-looking code."""

    def test_a_path_starting_the_continued_line_is_caught(self, tmp_path):
        fixture = tmp_path / "fixture.md"
        fixture.write_text(
            "```bash\n"
            "python3 \\\n"
            "  scripts/some_future_script.py --flag value\n"
            "```\n",
            encoding="utf-8",
        )
        hits = _wide_scan_matches(fixture)
        assert len(hits) == 1
        lineno, line, subpath = hits[0]
        assert lineno == 2
        assert subpath == "some_future_script.py"
        assert "scripts/some_future_script.py" in line

    def test_a_trailing_backslash_followed_by_prose_is_not_a_false_positive(self, tmp_path):
        """A `\\`-ended line whose next line is NOT a bare script path (just
        continuation prose, or a CLI flag) must not be absorbed as if it
        were one — matching every real instance actually found in this
        repo's own docs, where the interpreter+path already share one line
        and only trailing flags continue."""
        fixture = tmp_path / "fixture.md"
        fixture.write_text(
            "```bash\n"
            "python3 scripts/real_script.py --flag \\\n"
            "  --another-flag value\n"
            "```\n",
            encoding="utf-8",
        )
        hits = _wide_scan_matches(fixture)
        assert len(hits) == 1
        lineno, _line, subpath = hits[0]
        assert lineno == 2  # the same-line match, not a continuation join
        assert subpath == "real_script.py"

    def test_continuation_opener_with_non_script_next_line_is_not_absorbed(self, tmp_path):
        """The genuine negative branch of the continuation check: an opener
        line with NO same-line invocation (so `_same_line_matches` finds
        nothing and the scanner actually reaches the continuation check),
        followed by a next line that is prose rather than a bare script
        path. Must produce zero hits."""
        fixture = tmp_path / "fixture.md"
        fixture.write_text(
            "```bash\n"
            "bash \\\n"
            "  some prose that is not a script path\n"
            "```\n",
            encoding="utf-8",
        )
        assert _wide_scan_matches(fixture) == []


class TestSameLineDotSlashInvocation:
    """`./scripts/x.py` (no separating whitespace between the prefix and the
    path) is one of the three invocation forms #1655's own docstring names
    as a gap this file closes — pinned so a regex refactor can't silently
    make it unreachable again."""

    def test_dot_slash_prefix_with_no_space_is_caught(self, tmp_path):
        fixture = tmp_path / "fixture.md"
        fixture.write_text("```bash\n./scripts/some_future_script.py --flag\n```\n", encoding="utf-8")
        hits = _wide_scan_matches(fixture)
        assert len(hits) == 1
        assert hits[0][2] == "some_future_script.py"


class TestSameLineMultipleInvocations:
    """A qualified invocation elsewhere on the SAME line must never suppress
    a genuine bare invocation also on it — the whole-line suppression an
    earlier draft used (`if "CLAUDE_PLUGIN_ROOT" not in line`) hid exactly
    this shape; see `plugins/dev-team/skills/agent-eval/SKILL.md`'s own
    comma-separated allowed-tools line for a live (already-exempted)
    instance of it."""

    def test_bare_invocation_sharing_a_line_with_a_qualified_one_is_still_caught(self, tmp_path):
        fixture = tmp_path / "fixture.md"
        fixture.write_text(
            "```bash\n"
            "python3 scripts/bare_one.py *, python3 ${CLAUDE_PLUGIN_ROOT}/scripts/qualified_one.py *,\n"
            "```\n",
            encoding="utf-8",
        )
        hits = _wide_scan_matches(fixture)
        assert len(hits) == 1
        assert hits[0][2] == "bare_one.py"
