"""Tests for scripts/check_model_staleness.py (#1271).

Covers the pure comparison logic (pinned-ID extraction, staleness diff, issue
body) against fixtures, plus the main() control flow with the network
(`fetch_live_model_ids`) and GitHub (`find_open_issue`/`create_issue`)
boundaries monkeypatched. No network, no `gh`.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_model_staleness.py"

_spec = importlib.util.spec_from_file_location("check_model_staleness", SCRIPT)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


# --- pinned_model_ids ------------------------------------------------------


def test_pinned_ids_current_shape() -> None:
    routing = {
        "low": "claude-haiku-4-5",
        "medium": "claude-sonnet-5",
        "high": "claude-opus-4-8",
        "rounding": "round_half_up",
    }
    assert mod.pinned_model_ids(routing) == [
        "claude-haiku-4-5",
        "claude-opus-4-8",
        "claude-sonnet-5",
    ]


def test_pinned_ids_dedupes_legacy_alias_keys() -> None:
    # Pre-#1269 shape: the same three IDs listed under bands AND aliases.
    routing = {
        "low": "claude-haiku-4-5",
        "medium": "claude-sonnet-5",
        "high": "claude-opus-4-8",
        "haiku": "claude-haiku-4-5",
        "sonnet": "claude-sonnet-5",
        "opus": "claude-opus-4-8",
        "rounding": "round_half_up",
    }
    assert mod.pinned_model_ids(routing) == [
        "claude-haiku-4-5",
        "claude-opus-4-8",
        "claude-sonnet-5",
    ]


def test_pinned_ids_skips_non_model_values() -> None:
    assert mod.pinned_model_ids({"rounding": "round_half_up"}) == []


# --- stale_models ----------------------------------------------------------


def test_stale_none_when_all_served() -> None:
    pinned = ["claude-haiku-4-5", "claude-opus-4-8"]
    live = ["claude-haiku-4-5", "claude-opus-4-8", "claude-sonnet-5"]
    assert mod.stale_models(pinned, live) == []


def test_stale_flags_missing_and_preserves_order() -> None:
    pinned = ["claude-haiku-4-5", "claude-opus-4-8", "claude-sonnet-5"]
    live = ["claude-sonnet-5"]
    assert mod.stale_models(pinned, live) == [
        "claude-haiku-4-5",
        "claude-opus-4-8",
    ]


# --- issue_body ------------------------------------------------------------


def test_issue_body_lists_stale_ids() -> None:
    body = mod.issue_body(["claude-opus-4-8"], ["claude-sonnet-5", "gpt-ignored"])
    assert "`claude-opus-4-8`" in body
    assert "no longer" in body.lower()
    # Only claude-* live models are echoed under "currently served".
    assert "gpt-ignored" not in body


# --- main() flow (boundaries monkeypatched) --------------------------------


def _write_routing(tmp_path: Path) -> Path:
    p = tmp_path / "model-routing.json"
    p.write_text(
        json.dumps(
            {
                "low": "claude-haiku-4-5",
                "medium": "claude-sonnet-5",
                "high": "claude-opus-4-8",
                "rounding": "round_half_up",
            }
        ),
        encoding="utf-8",
    )
    return p


def test_main_no_api_key_returns_2(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    routing = _write_routing(tmp_path)
    assert mod.main(["--repo", "o/r", "--routing", str(routing)]) == 2


def test_main_all_served_does_not_file_issue(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(
        mod,
        "fetch_live_model_ids",
        lambda base, key: ["claude-haiku-4-5", "claude-sonnet-5", "claude-opus-4-8"],
    )
    called = {"create": 0}
    monkeypatch.setattr(
        mod, "create_issue", lambda *a, **k: called.__setitem__("create", 1)
    )
    routing = _write_routing(tmp_path)
    assert mod.main(["--repo", "o/r", "--routing", str(routing)]) == 0
    assert called["create"] == 0


def test_main_stale_files_issue_when_none_open(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(
        mod, "fetch_live_model_ids", lambda base, key: ["claude-sonnet-5"]
    )
    monkeypatch.setattr(mod, "find_open_issue", lambda repo, title: 0)
    created = {}
    monkeypatch.setattr(
        mod,
        "create_issue",
        lambda repo, title, body: created.update(title=title, body=body),
    )
    routing = _write_routing(tmp_path)
    assert mod.main(["--repo", "o/r", "--routing", str(routing)]) == 0
    assert "claude-haiku-4-5" in created["body"]
    assert "claude-opus-4-8" in created["body"]


def test_main_stale_skips_when_issue_already_open(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(
        mod, "fetch_live_model_ids", lambda base, key: ["claude-sonnet-5"]
    )
    monkeypatch.setattr(mod, "find_open_issue", lambda repo, title: 42)
    called = {"create": 0}
    monkeypatch.setattr(
        mod, "create_issue", lambda *a, **k: called.__setitem__("create", 1)
    )
    routing = _write_routing(tmp_path)
    assert mod.main(["--repo", "o/r", "--routing", str(routing)]) == 0
    assert called["create"] == 0


def test_main_dry_run_never_files(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(
        mod, "fetch_live_model_ids", lambda base, key: ["claude-sonnet-5"]
    )
    called = {"create": 0}
    monkeypatch.setattr(
        mod, "create_issue", lambda *a, **k: called.__setitem__("create", 1)
    )
    routing = _write_routing(tmp_path)
    assert mod.main(["--repo", "o/r", "--routing", str(routing), "--dry-run"]) == 0
    assert called["create"] == 0
