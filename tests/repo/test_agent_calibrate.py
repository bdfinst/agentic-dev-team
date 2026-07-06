"""Tests for scripts/agent_calibrate.py — band calibration (#882, slice 3 of
epic #879). Hermetic: every test builds a tiny self-contained corpus + plugin
tree under a tmp repo root and stubs the fixture-dispatch step, so no real
subprocess/model call is ever made.

Covers the six Gherkin scenarios from issue #882 plus unit tests for the cost
preflight arithmetic and the calibration-record routing hash.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import agent_calibrate as ac  # noqa: E402
from eval_cache import Dirs  # noqa: E402


# ---------------------------------------------------------------------------
# Corpus fixture — mirrors test_eval_cache.py's `corpus` fixture style.
# ---------------------------------------------------------------------------

@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    plugin = tmp_path / "plugins" / "dev-team"
    (plugin / "agents").mkdir(parents=True)
    (plugin / "skills").mkdir(parents=True)
    (plugin / "knowledge").mkdir(parents=True)
    (tmp_path / "evals" / "expected").mkdir(parents=True)
    (tmp_path / "evals" / "fixtures").mkdir(parents=True)
    (tmp_path / ".claude").mkdir(parents=True)

    # A routing map + no ladder -> resolve_band falls back to the default map.
    (plugin / "knowledge" / "model-routing.json").write_text(json.dumps({
        "low": "model-low",
        "medium": "model-medium",
        "high": "model-high",
    }))

    return tmp_path


def _write_agent(corpus: Path, name: str, effort: str) -> None:
    (corpus / "plugins" / "dev-team" / "agents" / f"{name}.md").write_text(
        f"---\nname: {name}\neffort: {effort}\n---\n# {name}\n"
    )


def _write_fixture(corpus: Path, stem: str, target: str) -> None:
    (corpus / "evals" / "expected" / f"{stem}.json").write_text(json.dumps({
        "fixture": f"{stem}.ts",
        "applicableAgents": [target],
        "agents": {target: {"expectedStatus": "fail", "issueCount": {"min": 1, "max": 5}}},
    }))
    (corpus / "evals" / "fixtures" / f"{stem}.ts").write_text("const x = 1\n")


def _write_floors(corpus: Path, entries: dict) -> None:
    (corpus / "plugins" / "dev-team" / "knowledge" / "calibration-floors.json").write_text(
        json.dumps(entries)
    )


def _dirs(corpus: Path) -> Dirs:
    return Dirs(corpus)


def _routing_paths(corpus: Path):
    routing = corpus / "plugins" / "dev-team" / "knowledge" / "model-routing.json"
    ladder = corpus / ".claude" / "model-ladder.json"  # absent -> default map
    return routing, ladder


# ---------------------------------------------------------------------------
# Scenario 1 — a cheaper band clears the floor.
# ---------------------------------------------------------------------------

def test_downgrade_available_when_cheaper_band_clears_floor(corpus: Path) -> None:
    _write_agent(corpus, "test-review", "medium")
    _write_fixture(corpus, "fx1", "test-review")
    _write_floors(corpus, {"test-review": {"riskClass": "standard", "floor": 0.9}})

    dirs = _dirs(corpus)
    routing_path, ladder_path = _routing_paths(corpus)

    def dispatch_fn(pair: str, model: str) -> bool:
        return True  # passes at every band, including the cheapest (low)

    pass_rate_fn = ac.make_pass_rate_fn(dispatch_fn)
    result = ac.calibrate_target(
        "test-review", dirs, ac.load_floors(corpus / "plugins" / "dev-team" / "knowledge" / "calibration-floors.json"),
        set(), pass_rate_fn, routing_path, ladder_path,
    )

    assert result["verdict"] == "downgrade-available"
    assert result["calibrated_band"] == "low"
    assert result["declared_band"] == "medium"

    # Report carries a ready-to-apply diff.
    report = ac.render_report([result], "2026-01-01T00-00-00Z")
    assert "- effort: medium" in report
    assert "+ effort: low" in report

    # No agent file under plugins/dev-team/agents/ is modified by calibration.
    agent_file = corpus / "plugins" / "dev-team" / "agents" / "test-review.md"
    before = agent_file.read_text()
    before_mtime = agent_file.stat().st_mtime
    ac.calibrate_target(
        "test-review", dirs, ac.load_floors(corpus / "plugins" / "dev-team" / "knowledge" / "calibration-floors.json"),
        set(), pass_rate_fn, routing_path, ladder_path,
    )
    assert agent_file.read_text() == before
    assert agent_file.stat().st_mtime == before_mtime


# ---------------------------------------------------------------------------
# Scenario 2 — the declared band is the cheapest that clears the floor.
# ---------------------------------------------------------------------------

def test_aligned_when_declared_band_is_cheapest_passing(corpus: Path) -> None:
    _write_agent(corpus, "test-review", "medium")
    _write_fixture(corpus, "fx1", "test-review")
    _write_floors(corpus, {"test-review": {"riskClass": "standard", "floor": 0.9}})

    dirs = _dirs(corpus)
    routing_path, ladder_path = _routing_paths(corpus)
    routing = ac.resolve_band  # for readability only

    def dispatch_fn(pair: str, model: str) -> bool:
        # Fails at "model-low", passes at "model-medium" and "model-high".
        return model != "model-low"

    pass_rate_fn = ac.make_pass_rate_fn(dispatch_fn)
    floors = ac.load_floors(corpus / "plugins" / "dev-team" / "knowledge" / "calibration-floors.json")
    result = ac.calibrate_target("test-review", dirs, floors, set(), pass_rate_fn, routing_path, ladder_path)

    assert result["verdict"] == "aligned"
    assert result["calibrated_band"] == "medium"
    report = ac.render_report([result], "2026-01-01T00-00-00Z")
    assert "diff" not in report.lower() or "Apply-ready diff" not in report


# ---------------------------------------------------------------------------
# Scenario 3 — no band clears the floor.
# ---------------------------------------------------------------------------

def test_floor_failure_when_no_band_clears(corpus: Path) -> None:
    _write_agent(corpus, "security-review", "high")
    _write_fixture(corpus, "fx1", "security-review")
    _write_floors(corpus, {"security-review": {"riskClass": "high", "floor": 1.0}})

    dirs = _dirs(corpus)
    routing_path, ladder_path = _routing_paths(corpus)

    def dispatch_fn(pair: str, model: str) -> bool:
        return False  # fails everywhere

    pass_rate_fn = ac.make_pass_rate_fn(dispatch_fn)
    floors = ac.load_floors(corpus / "plugins" / "dev-team" / "knowledge" / "calibration-floors.json")
    result = ac.calibrate_target("security-review", dirs, floors, set(), pass_rate_fn, routing_path, ladder_path)

    assert result["verdict"] == "floor-failure"
    assert result["calibrated_band"] is None


# ---------------------------------------------------------------------------
# Scenario 4 — target has no fixtures.
# ---------------------------------------------------------------------------

def test_uncalibratable_when_no_fixtures(corpus: Path) -> None:
    _write_agent(corpus, "software-engineer", "medium")
    # No eval fixture written for software-engineer.

    dirs = _dirs(corpus)
    routing_path, ladder_path = _routing_paths(corpus)

    def dispatch_fn(pair: str, model: str) -> bool:
        raise AssertionError("dispatch must never be called for a fixture-less target")

    pass_rate_fn = ac.make_pass_rate_fn(dispatch_fn)
    floors = ac.load_floors(corpus / "plugins" / "dev-team" / "knowledge" / "calibration-floors.json")
    result = ac.calibrate_target("software-engineer", dirs, floors, set(), pass_rate_fn, routing_path, ladder_path)

    assert result["verdict"] == "uncalibratable"
    assert result["fixture_gap"] == 0

    # A full sweep across all targets lists it as uncalibratable too.
    _write_agent(corpus, "test-review", "medium")
    _write_fixture(corpus, "fx1", "test-review")
    _write_floors(corpus, {"test-review": {"riskClass": "standard", "floor": 0.9}})
    all_targets = ac.target_universe(dirs)
    assert "software-engineer" in all_targets
    assert "test-review" in all_targets


# ---------------------------------------------------------------------------
# Scenario 5 — in-session dispatch is refused.
# ---------------------------------------------------------------------------

def test_in_session_refused(corpus: Path) -> None:
    rc = ac.main(["--repo-root", str(corpus), "--in-session"])
    assert rc != 0


def test_in_session_refused_message(corpus: Path, capsys) -> None:
    ac.main(["--repo-root", str(corpus), "--in-session"])
    captured = capsys.readouterr()
    assert "fresh-subprocess dispatch" in (captured.err + captured.out)


# ---------------------------------------------------------------------------
# Scenario 6 — quarantined fixtures do not move the floor.
# ---------------------------------------------------------------------------

def test_quarantined_fixture_excluded_from_pass_rate(corpus: Path) -> None:
    _write_agent(corpus, "test-review", "medium")
    _write_fixture(corpus, "fx1", "test-review")  # will flap / be quarantined
    _write_fixture(corpus, "fx2", "test-review")  # always passes
    _write_floors(corpus, {"test-review": {"riskClass": "standard", "floor": 0.9}})

    dirs = _dirs(corpus)
    routing_path, ladder_path = _routing_paths(corpus)
    quarantined = {"fx1::test-review"}

    def dispatch_fn(pair: str, model: str) -> bool:
        # fx1 would fail (flap) if it counted; fx2 always passes.
        if pair == "fx1::test-review":
            return False
        return True

    pass_rate_fn = ac.make_pass_rate_fn(dispatch_fn)
    floors = ac.load_floors(corpus / "plugins" / "dev-team" / "knowledge" / "calibration-floors.json")
    result = ac.calibrate_target("test-review", dirs, floors, quarantined, pass_rate_fn, routing_path, ladder_path)

    # fx1 excluded -> only fx2 counted -> 100% pass rate at every band.
    assert result["quarantined"] == ["fx1::test-review"]
    assert result["band_results"]["low"]["total"] == 1
    assert result["band_results"]["low"]["rate"] == 1.0

    report = ac.render_report([result], "2026-01-01T00-00-00Z")
    assert "fx1::test-review" in report


def test_load_quarantine_reads_eval_variance_shape(tmp_path: Path) -> None:
    path = tmp_path / "eval-variance.json"
    path.write_text(json.dumps({
        "schema": "eval-variance/v1",
        "quarantine": ["fx1::test-review", "fx2::other-agent"],
    }))
    assert ac.load_quarantine(path) == {"fx1::test-review", "fx2::other-agent"}


def test_load_quarantine_missing_file_is_empty(tmp_path: Path) -> None:
    assert ac.load_quarantine(tmp_path / "nope.json") == set()


# ---------------------------------------------------------------------------
# Cost preflight arithmetic.
# ---------------------------------------------------------------------------

def test_worst_case_dispatch_count() -> None:
    assert ac.worst_case_dispatch_count(4) == 12  # 4 fixtures x 3 bands
    assert ac.worst_case_dispatch_count(0) == 0


def test_cost_preflight_subtracts_cache_hits(corpus: Path) -> None:
    _write_agent(corpus, "test-review", "medium")
    _write_fixture(corpus, "fx1", "test-review")
    dirs = _dirs(corpus)
    routing_path, ladder_path = _routing_paths(corpus)
    cache_path = corpus / "evals" / ".eval-cache.json"

    pairs = ac.fixtures_for_target("test-review", dirs)
    worst_case, hits, net = ac.cost_preflight(pairs, dirs, cache_path, routing_path, ladder_path)
    # No cache populated yet -> zero hits, net == worst case.
    assert worst_case == 3  # 1 fixture x 3 bands
    assert hits == 0
    assert net == 3

    # Populate the cache for the "low" band model with a passing entry.
    from eval_cache import cache_put, compute_fingerprint, save_cache, load_cache
    cache = load_cache(cache_path)
    sha, _ = compute_fingerprint("fx1::test-review", dirs, "model-low")
    cache_put(cache, "fx1::test-review", sha, {"status": "fail", "issues": [], "summary": ""}, "model-low")
    save_cache(cache_path, cache)

    worst_case2, hits2, net2 = ac.cost_preflight(pairs, dirs, cache_path, routing_path, ladder_path)
    assert hits2 == 1
    assert net2 == worst_case2 - 1


# ---------------------------------------------------------------------------
# Calibration-record routing hash.
# ---------------------------------------------------------------------------

def test_routing_hash_changes_with_routing_content(corpus: Path) -> None:
    routing_path, ladder_path = _routing_paths(corpus)
    h1 = ac.routing_hash(routing_path, None)
    routing_path.write_text(json.dumps({"low": "different-model", "medium": "m", "high": "h"}))
    h2 = ac.routing_hash(routing_path, None)
    assert h1 != h2


def test_routing_hash_changes_with_ladder_presence(corpus: Path) -> None:
    routing_path, ladder_path = _routing_paths(corpus)
    h_no_ladder = ac.routing_hash(routing_path, None)
    ladder_path.write_text(json.dumps(["model-a", "model-b"]))
    h_with_ladder = ac.routing_hash(routing_path, ladder_path)
    assert h_no_ladder != h_with_ladder


# ---------------------------------------------------------------------------
# Records persistence never touches agent/skill files.
# ---------------------------------------------------------------------------

def test_calibration_record_written_and_agents_untouched(corpus: Path) -> None:
    _write_agent(corpus, "test-review", "medium")
    _write_fixture(corpus, "fx1", "test-review")
    _write_floors(corpus, {"test-review": {"riskClass": "standard", "floor": 0.9}})

    agents_dir = corpus / "plugins" / "dev-team" / "agents"
    skills_dir = corpus / "plugins" / "dev-team" / "skills"
    before = {p: p.read_bytes() for p in agents_dir.rglob("*") if p.is_file()}

    dirs = _dirs(corpus)
    routing_path, ladder_path = _routing_paths(corpus)

    def dispatch_fn(pair: str, model: str) -> bool:
        return True

    pass_rate_fn = ac.make_pass_rate_fn(dispatch_fn)
    floors = ac.load_floors(corpus / "plugins" / "dev-team" / "knowledge" / "calibration-floors.json")
    result = ac.calibrate_target("test-review", dirs, floors, set(), pass_rate_fn, routing_path, ladder_path)

    rhash = ac.routing_hash(routing_path, None)
    record = ac.build_record(result, rhash, now="2026-01-01T00:00:00Z")
    records_path = corpus / ".claude" / "evals" / "calibration-records.json"
    records = ac.load_records(records_path)
    records[result["target"]] = record
    ac.save_records(records_path, records)

    saved = json.loads(records_path.read_text())
    assert saved["test-review"]["declared_band"] == "medium"
    assert saved["test-review"]["calibrated_band"] == "low"
    assert saved["test-review"]["routing_hash"] == rhash

    after = {p: p.read_bytes() for p in agents_dir.rglob("*") if p.is_file()}
    assert before == after
    assert not skills_dir.exists() or not any(skills_dir.rglob("*"))
