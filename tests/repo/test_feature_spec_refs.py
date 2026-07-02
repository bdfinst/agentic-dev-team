"""Behavior-spec / bats-contract reference sensor.

The mutation-probe slice ACs (#284-#287) named Gherkin `.feature` specs under
evals/skills/. Those specs are not eval-grader fixtures - their executable
enforcement is a bats suite under tests/skills/ (see evals/skills/README.md).
This guard keeps the two from drifting apart:

  1. every evals/skills/**/*.feature carries an "# Enforced by:" header naming
     a tests/skills/<name>.bats file that exists;
  2. that referenced bats file is non-empty (i.e. a real suite, not a stub).

Model-free and deterministic. If a spec's enforcing suite is renamed or
removed, this fails loudly instead of leaving an orphaned spec on disk.

Ported from tests/repo/feature_spec_refs_test.bats (#673).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_DIR = REPO_ROOT / "evals" / "skills"

_ENFORCED_BY_RE = re.compile(r"# Enforced by: (tests/skills/[a-zA-Z0-9_./-]+\.bats)")


def test_every_feature_spec_names_an_existing_nonempty_bats_contract() -> None:
    if not SPEC_DIR.is_dir():
        pytest.skip("no evals/skills specs present")

    problems = []
    for feature in sorted(SPEC_DIR.rglob("*.feature")):
        text = feature.read_text()
        match = _ENFORCED_BY_RE.search(text)
        rel_feature = feature.relative_to(REPO_ROOT)
        if not match:
            problems.append(
                f"{rel_feature}  (missing '# Enforced by: tests/skills/<name>.bats' header)"
            )
            continue
        ref = match.group(1)
        ref_path = REPO_ROOT / ref
        if not (ref_path.is_file() and ref_path.stat().st_size > 0):
            problems.append(
                f"{rel_feature}  ->  {ref}  (referenced bats contract missing or empty)"
            )

    assert not problems, (
        "Behavior spec(s) not backed by a bats contract:\n" + "\n".join(problems)
    )
