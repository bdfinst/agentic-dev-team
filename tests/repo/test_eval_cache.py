"""Tests for scripts/eval_cache.py — the per-pair fingerprint replay cache that
lets the live eval gate skip unchanged pairs (issue #311), and the model-aware
fingerprint dimension (issue #881) that keeps per-band calibration results
memoized independently per model. Hermetic: every test builds a tiny
self-contained corpus + plugin tree under a tmp repo root, so no real model
dispatch and no real corpus is touched.

Ported from tests/repo/eval_cache_tests.bats (issue #572: bash -> Python).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CACHE = REPO_ROOT / "scripts" / "eval_cache.py"


PASSING_ACTUALS = """{ "demo": { "agents": { "demo-review": {
  "status": "fail",
  "issues": [{ "severity": "error", "message": "domain imports infra layer" }],
  "summary": "" } } } }
"""


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    (tmp_path / "plugins" / "dev-team" / "agents").mkdir(parents=True)
    (tmp_path / "plugins" / "dev-team" / "knowledge").mkdir(parents=True)
    (tmp_path / "plugins" / "dev-team" / "skills").mkdir(parents=True)
    (tmp_path / "evals" / "expected").mkdir(parents=True)
    (tmp_path / "evals" / "fixtures").mkdir(parents=True)
    (tmp_path / "plugins" / "dev-team" / "agents" / "demo-review.md").write_text(
        "# Demo Review\nRead `knowledge/demo-knowledge.md` before starting.\n"
    )
    (tmp_path / "plugins" / "dev-team" / "knowledge" / "demo-knowledge.md").write_text(
        "rule: flag layer violations\n"
    )
    (tmp_path / "evals" / "expected" / "demo.json").write_text(
        '{ "fixture": "demo.ts", "applicableAgents": ["demo-review"],\n'
        '  "agents": { "demo-review": { "expectedStatus": "fail", '
        '"mustMention": ["layer"] } } }\n'
    )
    (tmp_path / "evals" / "fixtures" / "demo.ts").write_text("const x = 1\n")
    return tmp_path


def _run(corpus: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CACHE), "--repo-root", str(corpus), *args],
        capture_output=True,
        text=True,
    )


def _fingerprint(corpus: Path) -> str:
    res = _run(corpus, "--fingerprint", "demo::demo-review")
    assert res.returncode == 0, res.stdout + res.stderr
    for line in res.stdout.splitlines():
        if line.startswith("fingerprint: "):
            return line[len("fingerprint: ") :]
    return ""


def _write_passing_actuals(corpus: Path) -> Path:
    p = corpus / "actuals.json"
    p.write_text(PASSING_ACTUALS)
    return p


def test_fingerprint_stable_across_runs(corpus: Path) -> None:
    a = _fingerprint(corpus)
    b = _fingerprint(corpus)
    assert a
    assert a == b


def test_fingerprint_editing_fixture_busts_sha(corpus: Path) -> None:
    a = _fingerprint(corpus)
    (corpus / "evals" / "fixtures" / "demo.ts").write_text("const x = 2\n")
    b = _fingerprint(corpus)
    assert a != b


def test_fingerprint_editing_agent_definition_busts_sha(corpus: Path) -> None:
    a = _fingerprint(corpus)
    with (corpus / "plugins" / "dev-team" / "agents" / "demo-review.md").open("a") as f:
        f.write("extra rule\n")
    b = _fingerprint(corpus)
    assert a != b


def test_fingerprint_editing_transitive_knowledge_dep_busts_sha(corpus: Path) -> None:
    a = _fingerprint(corpus)
    with (corpus / "plugins" / "dev-team" / "knowledge" / "demo-knowledge.md").open(
        "a"
    ) as f:
        f.write("new transitive rule\n")
    b = _fingerprint(corpus)
    assert a != b


def test_fingerprint_lists_transitive_contributors(corpus: Path) -> None:
    res = _run(corpus, "--fingerprint", "demo::demo-review")
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert "knowledge/demo-knowledge.md" in out
    assert "agents/demo-review.md" in out
    assert "fixtures/demo.ts" in out


def test_stored_pass_replays_as_cache_hit(corpus: Path) -> None:
    _write_passing_actuals(corpus)
    res = _run(corpus, "--store", "--actuals", str(corpus / "actuals.json"))
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert "stored 1 passing pair" in out
    # Plan now: the pair should be a hit (replayable), not a miss.
    res = _run(corpus, "--plan", "--replay-out", str(corpus / "replay.json"))
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert "1 cache hit" in out
    assert "miss demo::demo-review" not in out
    # The replay actuals reproduce the stored output for the hit.
    replay = json.loads((corpus / "replay.json").read_text())
    assert replay["demo"]["agents"]["demo-review"]["status"] == "fail"


def test_plan_changing_input_after_store_busts_cache(corpus: Path) -> None:
    _write_passing_actuals(corpus)
    _run(corpus, "--store", "--actuals", str(corpus / "actuals.json"))
    (corpus / "evals" / "fixtures" / "demo.ts").write_text("const x = 999\n")
    res = _run(corpus, "--plan")
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert "miss demo::demo-review" in out


def test_corrupt_cache_silently_ignored(corpus: Path) -> None:
    _write_passing_actuals(corpus)
    _run(corpus, "--store", "--actuals", str(corpus / "actuals.json"))
    (corpus / "evals" / ".eval-cache.json").write_text("not json {\n")
    res = _run(corpus, "--plan")
    out = res.stdout + res.stderr
    assert res.returncode == 0, out  # no crash
    assert "miss demo::demo-review" in out  # degrades to dispatch


def test_failing_pair_not_cached(corpus: Path) -> None:
    (corpus / "actuals.json").write_text(
        """{ "demo": { "agents": { "demo-review": {
  "status": "pass", "issues": [], "summary": "looks clean" } } } }
"""
    )
    res = _run(corpus, "--store", "--actuals", str(corpus / "actuals.json"))
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert "stored 0 passing pair" in out
    res = _run(corpus, "--plan")
    out = res.stdout + res.stderr
    assert "miss demo::demo-review" in out


def test_cache_file_lives_at_evals_dot_eval_cache_json(corpus: Path) -> None:
    _write_passing_actuals(corpus)
    _run(corpus, "--store", "--actuals", str(corpus / "actuals.json"))
    assert (corpus / "evals" / ".eval-cache.json").is_file()


# --------------------------------------------------------------------------
# Model-aware fingerprint (#881, band calibration slice 2).
# --------------------------------------------------------------------------

MODEL_A = "claude-haiku-4-5-20251001"
MODEL_B = "claude-sonnet-4-6"


def test_different_model_is_a_cache_miss(corpus: Path) -> None:
    """A PASS memoized at one model does not replay for another model."""
    _write_passing_actuals(corpus)
    _run(corpus, "--store", "--actuals", str(corpus / "actuals.json"), "--model", MODEL_A)
    res = _run(corpus, "--plan", "--model", MODEL_B)
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert "miss demo::demo-review" in out


def test_same_model_replay_is_unaffected(corpus: Path) -> None:
    """Same-model replay with unchanged transitive inputs still hits."""
    _write_passing_actuals(corpus)
    _run(corpus, "--store", "--actuals", str(corpus / "actuals.json"), "--model", MODEL_A)
    res = _run(corpus, "--plan", "--model", MODEL_A, "--replay-out", str(corpus / "replay.json"))
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert "1 cache hit" in out
    assert "miss demo::demo-review" not in out
    replay = json.loads((corpus / "replay.json").read_text())
    assert replay["demo"]["agents"]["demo-review"]["status"] == "fail"


def test_model_dimension_changes_fingerprint(corpus: Path) -> None:
    """The fingerprint itself differs across models for the same inputs."""
    a = _run(corpus, "--fingerprint", "demo::demo-review", "--model", MODEL_A)
    b = _run(corpus, "--fingerprint", "demo::demo-review", "--model", MODEL_B)
    sha_a = next(line for line in a.stdout.splitlines() if line.startswith("fingerprint: "))
    sha_b = next(line for line in b.stdout.splitlines() if line.startswith("fingerprint: "))
    assert sha_a != sha_b


def test_legacy_entry_without_model_dimension_busts_once(corpus: Path) -> None:
    """A cache entry stored before the model dimension existed (no "model" key,
    sha computed without folding in any model identity) is a guaranteed miss
    the first time it is replayed against a model-aware fingerprint — then a
    fresh --store re-populates it as model-aware, and it replays normally
    thereafter."""
    cache_path = corpus / "evals" / ".eval-cache.json"
    legacy_sha = "0" * 64  # any old-format SHA never matches a fresh model-aware one
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps({
        "version": 1,
        "entries": {
            "demo::demo-review": {
                "sha": legacy_sha,
                "passed": True,
                "actual": {"status": "fail", "issues": [], "summary": ""},
                "recorded_at": "2020-01-01T00:00:00Z",
            }
        },
    }))
    # One-time bust: the legacy entry (no model dimension) cannot match any
    # freshly computed, model-aware fingerprint.
    res = _run(corpus, "--plan", "--model", MODEL_A)
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert "miss demo::demo-review" in out
    # Re-store under the model-aware scheme, then replay hits normally.
    _write_passing_actuals(corpus)
    _run(corpus, "--store", "--actuals", str(corpus / "actuals.json"), "--model", MODEL_A)
    res = _run(corpus, "--plan", "--model", MODEL_A)
    out = res.stdout + res.stderr
    assert "miss demo::demo-review" not in out
