"""Behavior-spec / test-contract reference sensor.

The mutation-probe slice ACs (#284-#287) named Gherkin `.feature` specs under
evals/skills/. Those specs are not eval-grader fixtures - their executable
enforcement is a bats or pytest suite under tests/skills/ (see
evals/skills/README.md). This guard keeps the two from drifting apart:

  1. every evals/skills/**/*.feature carries an "# Enforced by:" header naming
     a tests/skills/<name>.bats or tests/skills/<name>.py file — or, per this
     repo's own established convention of placing agent-frontmatter
     content-guard tests under tests/agents/ (issue #1463), a
     tests/agents/<name>.py file — that exists;
  2. that referenced contract file is non-empty (i.e. a real suite, not a
     stub).

Model-free and deterministic. If a spec's enforcing suite is renamed or
removed, this fails loudly instead of leaving an orphaned spec on disk.

Ported from tests/repo/feature_spec_refs_test.bats (#673).

Issue #674 ported tests/skills/*.bats to pytest (test_*.py); the accepted
extensions widened from .bats-only to .bats|.py so those ports don't orphan
their "# Enforced by:" references. Issue #1463 widened the accepted root
from tests/skills/ only to also accept tests/agents/*.py, matching where
agent-frontmatter content-guard tests actually live in this repo.

The regex's path-segment character class deliberately excludes `.` (each
segment is `[A-Za-z0-9_-]+`, joined by literal `/`), so a `..` segment can
never match — a `# Enforced by:` header naming a path outside the two
accepted roots cannot satisfy this guard by traversal (security-review
finding, issue #1463's widening). `ref_path` is also checked for repo
containment before use, as defense in depth.
"""

from __future__ import annotations

import re

import pytest

from _repo_root import REPO_ROOT

SPEC_DIR = REPO_ROOT / "evals" / "skills"

_PATH_SEGMENT = r"[A-Za-z0-9_-]+"
_ENFORCED_BY_RE = re.compile(
    r"# Enforced by: (tests/(?:"
    rf"skills/(?:{_PATH_SEGMENT}/)*{_PATH_SEGMENT}\.(?:bats|py)"
    r"|"
    rf"agents/(?:{_PATH_SEGMENT}/)*{_PATH_SEGMENT}\.py"
    r"))"
)


def test_every_feature_spec_names_an_existing_nonempty_bats_or_pytest_contract() -> (
    None
):
    if not SPEC_DIR.is_dir():
        pytest.skip("no evals/skills specs present")

    problems = []
    for feature in sorted(SPEC_DIR.rglob("*.feature")):
        text = feature.read_text()
        match = _ENFORCED_BY_RE.search(text)
        rel_feature = feature.relative_to(REPO_ROOT)
        if not match:
            problems.append(
                f"{rel_feature}  (missing '# Enforced by: tests/skills/<name>.bats|.py "
                f"or tests/agents/<name>.py' header)"
            )
            continue
        ref = match.group(1)
        ref_path = (REPO_ROOT / ref).resolve()
        if not ref_path.is_relative_to(REPO_ROOT):
            problems.append(f"{rel_feature}  ->  {ref}  (reference escapes the repository)")
            continue
        if not (ref_path.is_file() and ref_path.stat().st_size > 0):
            problems.append(
                f"{rel_feature}  ->  {ref}  (referenced test contract missing or empty)"
            )

    assert not problems, (
        "Behavior spec(s) not backed by a bats or pytest contract:\n"
        + "\n".join(problems)
    )


class TestEnforcedByRegex:
    """Synthetic-fixture unit coverage for `_ENFORCED_BY_RE`, independent of
    whatever `.feature` files currently exist under evals/skills/ — a regex
    regression that doesn't happen to violate any file that exists today
    would otherwise go undetected (test-review finding, issue #1463)."""

    def test_accepts_tests_skills_bats(self) -> None:
        match = _ENFORCED_BY_RE.search("# Enforced by: tests/skills/foo.bats\n")
        assert match and match.group(1) == "tests/skills/foo.bats"

    def test_accepts_tests_skills_py(self) -> None:
        match = _ENFORCED_BY_RE.search("# Enforced by: tests/skills/foo.py\n")
        assert match and match.group(1) == "tests/skills/foo.py"

    def test_accepts_tests_agents_py(self) -> None:
        match = _ENFORCED_BY_RE.search("# Enforced by: tests/agents/foo.py\n")
        assert match and match.group(1) == "tests/agents/foo.py"

    def test_rejects_tests_agents_bats(self) -> None:
        assert _ENFORCED_BY_RE.search("# Enforced by: tests/agents/foo.bats\n") is None

    def test_rejects_traversal_segments(self) -> None:
        """A `..` segment can never match — each path segment's character
        class excludes `.` entirely (security-review finding, #1463)."""
        for attempt in (
            "tests/agents/../../../../etc/passwd.py",
            "tests/skills/../../../../etc/passwd.bats",
            "tests/agents/..%2f..%2fetc/passwd.py",
        ):
            assert _ENFORCED_BY_RE.search(f"# Enforced by: {attempt}\n") is None, attempt

    def test_missing_header_is_reported(self, tmp_path) -> None:
        problems = []
        feature = tmp_path / "orphan.feature"
        feature.write_text("Feature: orphan\n")
        text = feature.read_text()
        match = _ENFORCED_BY_RE.search(text)
        if not match:
            problems.append(f"{feature}  (missing header)")
        assert problems == [f"{feature}  (missing header)"]

    def test_reference_escaping_the_repo_is_rejected(self) -> None:
        """Even if a future edit widened the character class again, the
        containment check is the last line of defense — verify it fires."""
        outside = (REPO_ROOT / ".." / "outside.py").resolve()
        assert not outside.is_relative_to(REPO_ROOT)
