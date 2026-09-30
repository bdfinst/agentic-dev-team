"""ship_review_gate: skip only when the ledger clears every lens at current content."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ship_review_gate as gate

AGENTS = ROOT / "agents"
REGISTRY = ROOT / "knowledge" / "agent-registry.md"


def test_no_files_never_skips(tmp_path):
    r = gate.decide([], tmp_path, AGENTS, REGISTRY)
    assert r["skip"] is False


def test_empty_ledger_never_skips(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    r = gate.decide(["a.py"], tmp_path, AGENTS, REGISTRY)
    assert r["skip"] is False and r["reason"] == "uncleared-lens-files"


def test_fully_cleared_ledger_skips(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("x = 1\n")
    monkeypatch.setattr(
        gate.verdict_scope, "resolve_for_root",
        lambda lens_files, root: {
            "toDispatch": {}, "skipped": {}, "fullySkippedLenses": sorted(lens_files)},
    )
    r = gate.decide(["a.py"], tmp_path, AGENTS, REGISTRY)
    assert r["skip"] is True and r["lenses"]
