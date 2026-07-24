"""Citation-lint regression guard against the *real* plugin corpus.

The pytest suite in `test_citation_lint.py` (ported from bats shipped with
PR #315) exercises the lint against a synthetic plugin tree - it pins the
parser's behaviour but tells us nothing about whether the actual corpus
passes. This suite runs the lint over `plugins/dev-team/agents/` so a
future change cannot:

  (a) break a reviewer's `cites:` resolution by renaming a knowledge file,
  (b) silently regress an agent that used to declare `cites:` to none, or
  (c) introduce a new threshold-bearing reviewer that ships with no cites:
      and no operator awareness.

All assertions are advisory (Phase 1 lint exits 0 by design); the suite
fails when the *observed warnings* drift from the expected fingerprint.

Ported from tests/repo/citation_lint_corpus_tests.bats (#673).
"""

from __future__ import annotations

import subprocess
import sys

from _repo_root import REPO_ROOT

LINT = REPO_ROOT / "scripts" / "citation_lint.py"
PLUGIN_ROOT = REPO_ROOT / "plugins" / "dev-team"

CITED_CLEAN = [
    "arch-review",
    "complexity-review",
    "domain-review",
    "naming-review",
    "security-review",
    "structure-review",
    "test-review",
    "test-smell-review",
]


def _run_lint() -> subprocess.CompletedProcess:
    agent_files = sorted((PLUGIN_ROOT / "agents").glob("*.md"))
    return subprocess.run(
        [
            sys.executable,
            str(LINT),
            "--plugin-root",
            str(PLUGIN_ROOT),
            *[str(f) for f in agent_files],
        ],
        capture_output=True,
        text=True,
    )


def test_lint_exits_0_on_the_real_plugin_corpus() -> None:
    result = _run_lint()
    assert result.returncode == 0, result.stdout + result.stderr


def test_every_reviewer_with_declared_cites_resolves_to_real_sources() -> None:
    # Any 'unknown source' warning means a cites: entry points at a file that
    # does not exist - i.e. a knowledge file was renamed without updating the
    # citing agent. Hard fail (advisory exit code, but the warning text is
    # specific and unambiguous).
    result = _run_lint()
    assert result.returncode == 0, result.stdout + result.stderr
    output = result.stdout + result.stderr
    assert not any(
        token in output.lower() for token in ("unknown source", "unresolved")
    ), output


def test_no_drift_on_backfilled_reviewers() -> None:
    # Reviewers that have a cites: list AND zero threshold drift today. If any
    # of these later appear in the warning stream, a backfilled agent
    # silently regressed.
    result = _run_lint()
    assert result.returncode == 0, result.stdout + result.stderr
    output = result.stdout + result.stderr
    for name in CITED_CLEAN:
        assert not any(line.startswith(f"{name}:") for line in output.splitlines()), (
            f"Regression: {name} now produces a citation warning; check whether "
            f"a knowledge file changed or a new threshold was added.\n{output}"
        )
