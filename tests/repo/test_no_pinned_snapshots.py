"""Enforcement: no pinned claude-* snapshot IDs anywhere in the repo outside
the approved files (the single source of truth + its docs).

Ported from tests/repo/no_pinned_snapshots_test.bats (#673).

#1840: `_SNAPSHOT_RE` originally matched any `claude-<tier>-<digit>` string,
which is broader than "pinned snapshot ID" — it also matches the bare,
undated, current-generation model ID (`claude-opus-5`, `claude-sonnet-5`,
`claude-haiku-4-5`, `claude-opus-4-8`, ...), which is not a snapshot at all —
under Anthropic's current naming scheme the un-dated alias IS the durable
model ID, not a placeholder for one. That collided with release-please's
auto-generated `CHANGELOG.md`, which echoes commit subjects verbatim: a
commit whose subject mentioned `claude-opus-5` (#1842) made every future
release PR fail this gate, since CHANGELOG.md is not (and should not become)
an approved path — the string appearing there is an artifact of the commit
message, not a hardcoded snapshot reference. The regex now requires the
trailing 8-digit date every genuine pinned snapshot carries
(`claude-opus-4-5-20251101`, `claude-haiku-4-5-20251001`,
`claude-opus-4-20250514`), so it stops matching the thing it was never meant
to police.
"""

from __future__ import annotations

import re
import subprocess

import pytest

from _repo_root import REPO_ROOT

# Genuine pinned snapshots — must keep matching after the #1840 tightening.
_REAL_SNAPSHOTS = [
    "claude-opus-4-5-20251101",
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-5-20250929",
    "claude-opus-4-1-20250805",
    "claude-opus-4-20250514",
    "claude-sonnet-4-20250514",
]

# Bare, undated, current-generation model IDs — must NOT match. Every one of
# these is a real alias from the model catalog, not a snapshot; before #1840
# the old regex (`claude-(haiku|sonnet|opus)-[0-9]`) matched all of them.
_BARE_CURRENT_ALIASES = [
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-haiku-4-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-sonnet-4-6",
]

# The plugin-source files allowed to contain a pinned snapshot ID:
#   knowledge/model-routing.json - single source of truth (the whole point)
#   docs/model-routing.md       - contract doc; illustrative examples
#   docs/model-routing-overrides.md - override guide; worked ladder examples
#   templates/agents/agent-template.md - commented documentation block
#
# Out-of-scope (legitimate references the AC does not police):
#   docs/specs/, plans/, docs/spikes/ - design artifacts that name the
#     values exactly because they describe the migration.
#   evals/ - semgrep fixtures for OTHER plugins' LLM model strings.
#   tests/  - bats + pytest fixtures that depend on the literal values.
#     Includes plugins/dev-team/tests/ (the plugin's own pytest suite) - same
#     exemption reason: fixture-test code legitimately names the literals to
#     assert byte-for-byte against them.
#   knowledge/model-pricing.json - cost meter's pricing table (#102); must key
#     by model snapshot because the transcript usage records emit snapshot
#     IDs.
#   marketplace-dev/knowledge/agent-contract.json - a verbatim capture of
#     Anthropic's own sub-agent frontmatter docs (#1285); its `model` field's
#     `also_accepts` value quotes their doc's own illustrative snapshot
#     examples. Same "illustrative examples" exemption reason as
#     docs/model-routing.md — editing the quote would break its fidelity as
#     a verbatim contract capture.
#   */CHANGELOG.md (dev-team, marketplace-dev, security-assessment) -
#     release-please auto-generates these from commit subjects verbatim
#     (#1840). The #1840 fix (requiring a trailing 8-digit date) stops a
#     BARE current-alias mention from tripping this gate, but a commit
#     subject naming a genuine DATED snapshot — e.g. "revert the
#     claude-opus-4-5-20251101 pin" — reproduces the identical failure at
#     the snapshot tier instead of the alias tier, and hand-editing a
#     generated changelog to dodge it doesn't stick (the next release
#     regenerates it). Same "artifact of the commit message, not a
#     hardcoded reference" exemption reason as the rest of this list, not a
#     new kind of exception.
ALLOWED_PATHS = [
    "plugins/dev-team/knowledge/model-routing.json",
    "plugins/dev-team/docs/model-routing.md",
    "plugins/dev-team/docs/model-routing-overrides.md",
    "plugins/dev-team/templates/agents/agent-template.md",
    "plugins/dev-team/knowledge/model-pricing.json",
    "plugins/marketplace-dev/knowledge/agent-contract.json",
    "plugins/dev-team/CHANGELOG.md",
    "plugins/marketplace-dev/CHANGELOG.md",
    "plugins/security-assessment/CHANGELOG.md",
]

# POSIX ERE, not PCRE: this pattern is fed to `git grep -E` below, which on
# this platform is compiled without PCRE2 support — no `(?:...)` non-capturing
# group and no `\b` word boundary (verified by running `git grep` directly;
# both are silently accepted by Python's `re` and by BSD `grep -E`, so testing
# only against `re.search` would have shipped a pattern the actual gate
# couldn't run). Plain capturing groups only; no trailing boundary — matching
# one extra character on some tail explosion is the safe direction for a
# guard whose job is to flag, not to be precise about the exact span.
_SNAPSHOT_RE = re.compile(r"claude-(haiku|sonnet|opus)-[0-9]+(-[0-9]+)*-[0-9]{8}")


def test_no_pinned_snapshot_ids_in_plugin_source_outside_approved_files() -> None:
    cmd = [
        "git",
        "grep",
        "-nE",
        _SNAPSHOT_RE.pattern,
        "--",
        "plugins/",
    ]
    for allowed in ALLOWED_PATHS:
        cmd.append(f":!{allowed}")
    cmd.append(":!plugins/dev-team/tests/")

    result = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, check=False)
    # git grep exits 1 when no matches are found - that is the success case.
    assert result.returncode in (0, 1), result.stderr
    raw = result.stdout.strip()
    assert not raw, (
        "Pinned snapshot IDs found in non-approved plugin source files:\n" + raw
    )


@pytest.mark.parametrize("snapshot_id", _REAL_SNAPSHOTS)
def test_snapshot_regex_matches_genuine_pinned_snapshots(snapshot_id: str) -> None:
    assert _SNAPSHOT_RE.search(snapshot_id), (
        f"{snapshot_id!r} is a real pinned snapshot and must still be caught"
    )


@pytest.mark.parametrize("model_id", _BARE_CURRENT_ALIASES)
def test_snapshot_regex_does_not_match_bare_current_aliases(model_id: str) -> None:
    assert not _SNAPSHOT_RE.search(model_id), (
        f"{model_id!r} is a bare, undated current model ID, not a pinned "
        "snapshot — the regex must not flag it"
    )


@pytest.mark.parametrize(
    "sample,expect_match",
    [(s, True) for s in _REAL_SNAPSHOTS] + [(s, False) for s in _BARE_CURRENT_ALIASES],
)
def test_pattern_is_valid_ere_and_matches_the_same_via_git_grep(
    tmp_path, sample: str, expect_match: bool
) -> None:
    """Regression guard for the ERE-incompatibility defect described in the
    comment above `_SNAPSHOT_RE` — see that comment for the "why"; this test
    is the "prove it stays fixed". Exercises the identical `git grep -E`
    invocation the real gate uses, not just the Python regex object, so a
    future edit that reintroduces PCRE-only syntax fails here even though
    `re.search` alone would not catch it."""
    target = tmp_path / "sample.txt"
    target.write_text(sample + "\n")
    # `--no-index` searches files not managed by git (or ignores that they
    # are) — it does not, by itself, avoid needing a resolvable pathspec.
    # `cwd=tmp_path` is what makes the relative `-- sample.txt` pathspec
    # resolve correctly against the file this test just wrote.
    result = subprocess.run(
        ["git", "grep", "-nE", "--no-index", _SNAPSHOT_RE.pattern, "--", "sample.txt"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    # Guard the exit code before deriving `found` from it: collapsing every
    # non-zero code into "no match" would silently misreport an unexpected
    # git-grep failure (a third code beyond the two real outcomes) as a
    # legitimate negative result for every expect_match=False case.
    assert result.returncode in (0, 1), (
        f"git grep exited {result.returncode} (expected 0=match or 1=no-match): "
        f"{result.stderr}"
    )
    found = result.returncode == 0
    assert found == expect_match, (
        f"{sample!r}: git grep found={found}, expected={expect_match}\n"
        f"{result.stdout}{result.stderr}"
    )


def test_generated_changelogs_are_exempt_even_for_a_genuine_dated_snapshot() -> None:
    """Regression guard for the gap found reviewing this fix: tightening the
    regex to require a dated suffix stops a BARE alias mention from tripping
    the gate, but does nothing for a commit subject that genuinely names a
    DATED snapshot (e.g. "revert the claude-opus-4-5-20251101 pin") — that
    reproduces the identical #1840 failure once release-please echoes it into
    a generated changelog. Confirmed by directly planting that exact string
    into the live changelog and re-running the gate before this fix landed:
    it failed. This test pins the durable fix (the exemption), not that one
    reproduction, so it doesn't touch the working tree."""
    for changelog in (
        "plugins/dev-team/CHANGELOG.md",
        "plugins/marketplace-dev/CHANGELOG.md",
        "plugins/security-assessment/CHANGELOG.md",
    ):
        assert changelog in ALLOWED_PATHS, (
            f"{changelog!r} is release-please-generated and echoes commit "
            "subjects verbatim — it must be exempt or a future commit naming "
            "a real dated snapshot reproduces #1840's failure mode"
        )
