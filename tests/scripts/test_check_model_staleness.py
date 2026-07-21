"""Tests for scripts/check_model_staleness.py (#1271).

Covers the pure logic (pinned-ID extraction, family derivation, latest-by-
created_at selection, bump planning, formatting-preserving text rewrite, and
deterministic branch naming), plus the main() control flow with the network
(`fetch_live_models`) and GitHub (`open_bump_pr` / `create_issue` / the dedup
lookups) boundaries monkeypatched. No network, no `gh`.
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


def test_pinned_ids_dedupe_and_skip_non_models() -> None:
    routing = {
        "low": "claude-haiku-4-5",
        "medium": "claude-sonnet-5",
        "high": "claude-opus-4-8",
        "opus": "claude-opus-4-8",  # legacy alias — collapses
        "rounding": "round_half_up",  # not a model
    }
    assert mod.pinned_model_ids(routing) == [
        "claude-haiku-4-5",
        "claude-opus-4-8",
        "claude-sonnet-5",
    ]


# --- family_of -------------------------------------------------------------


def test_family_of_new_scheme() -> None:
    assert mod.family_of("claude-opus-4-8") == "opus"
    assert mod.family_of("claude-sonnet-5") == "sonnet"
    assert mod.family_of("claude-haiku-4-5") == "haiku"


def test_family_of_old_scheme_number_first() -> None:
    # Old naming puts the version first; family word must still be extracted.
    assert mod.family_of("claude-3-7-sonnet-20250219") == "sonnet"
    assert mod.family_of("claude-3-haiku-20240307") == "haiku"


# --- latest_in_family (ranks by created_at, not digits) --------------------


def _live():
    return [
        {"id": "claude-opus-4-8", "created_at": "2026-05-01T00:00:00Z"},
        {"id": "claude-opus-4-7", "created_at": "2026-02-01T00:00:00Z"},
        {"id": "claude-sonnet-5", "created_at": "2026-01-01T00:00:00Z"},
        # Old naming, huge digits, but OLDER by created_at — must NOT win.
        {"id": "claude-3-haiku-20240307", "created_at": "2024-03-07T00:00:00Z"},
        {"id": "claude-haiku-4-5", "created_at": "2025-10-01T00:00:00Z"},
    ]


def test_latest_prefers_created_at_over_digits() -> None:
    # 20240307 digits dwarf 4-5, but created_at makes claude-haiku-4-5 newest.
    assert mod.latest_in_family("haiku", _live())["id"] == "claude-haiku-4-5"
    assert mod.latest_in_family("opus", _live())["id"] == "claude-opus-4-8"


def test_latest_empty_when_family_absent() -> None:
    assert mod.latest_in_family("fable", _live()) == {}


# --- plan_bumps ------------------------------------------------------------


def test_plan_bumps_flags_only_superseded() -> None:
    pinned = ["claude-haiku-4-5", "claude-opus-4-7", "claude-sonnet-5"]
    bumps, gone = mod.plan_bumps(pinned, _live())
    assert bumps == {"claude-opus-4-7": "claude-opus-4-8"}  # 4-7 -> 4-8
    assert gone == []


def test_plan_bumps_reports_family_with_no_successor() -> None:
    pinned = ["claude-opus-4-8", "claude-fable-5"]
    bumps, gone = mod.plan_bumps(pinned, _live())
    assert bumps == {}
    assert gone == ["claude-fable-5"]


# --- rewrite_routing_text (formatting-preserving) --------------------------


def test_rewrite_preserves_formatting_and_only_changes_ids() -> None:
    raw = (
        "{\n"
        '  "low": "claude-haiku-4-5",\n'
        "\n"
        '  "high": "claude-opus-4-7",\n'
        '  "rounding": "round_half_up"\n'
        "}\n"
    )
    out = mod.rewrite_routing_text(raw, {"claude-opus-4-7": "claude-opus-4-8"})
    assert '"high": "claude-opus-4-8"' in out
    assert '"low": "claude-haiku-4-5"' in out  # untouched
    assert "\n\n" in out  # blank line preserved
    assert "claude-opus-4-7" not in out


def test_rewrite_quoted_match_avoids_substring_bleed() -> None:
    raw = '{"a": "claude-opus-4-8", "b": "claude-opus-4-8-fast"}'
    out = mod.rewrite_routing_text(raw, {"claude-opus-4-8": "claude-opus-5"})
    assert '"claude-opus-5"' in out
    assert "claude-opus-4-8-fast" in out  # longer ID untouched


# --- branch_name -----------------------------------------------------------


def test_branch_name_is_deterministic_and_prefixed() -> None:
    a = mod.branch_name({"claude-opus-4-7": "claude-opus-4-8"})
    b = mod.branch_name({"claude-opus-4-7": "claude-opus-4-8"})
    c = mod.branch_name({"claude-sonnet-4-6": "claude-sonnet-5"})
    assert a == b
    assert a != c
    assert a.startswith(mod.BRANCH_PREFIX)


# --- main() flow (boundaries monkeypatched) --------------------------------


def _write_routing(tmp_path: Path) -> Path:
    p = tmp_path / "model-routing.json"
    p.write_text(
        json.dumps(
            {
                "low": "claude-haiku-4-5",
                "medium": "claude-sonnet-5",
                "high": "claude-opus-4-7",
                "rounding": "round_half_up",
            }
        ),
        encoding="utf-8",
    )
    return p


def _stub_gh(monkeypatch, opened, issued, open_pr=0, open_issue=0):
    monkeypatch.setattr(mod, "fetch_live_models", lambda base, key: _live())
    monkeypatch.setattr(mod, "open_pr_for_branch", lambda repo, branch: open_pr)
    monkeypatch.setattr(mod, "find_open_issue", lambda repo, title: open_issue)
    monkeypatch.setattr(mod, "close_superseded_bump_prs", lambda repo, keep: None)
    monkeypatch.setattr(
        mod,
        "open_bump_pr",
        lambda repo, base, branch, path, content, title, body: opened.update(
            branch=branch, content=content
        ),
    )
    monkeypatch.setattr(
        mod,
        "create_issue",
        lambda repo, title, body: issued.update(title=title, body=body),
    )


def test_main_no_api_key_returns_2(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    routing = _write_routing(tmp_path)
    assert mod.main(["--repo", "o/r", "--routing", str(routing)]) == 2


def test_main_opens_pr_for_superseded_pin(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    opened, issued = {}, {}
    _stub_gh(monkeypatch, opened, issued)
    routing = _write_routing(tmp_path)
    assert mod.main(["--repo", "o/r", "--routing", str(routing)]) == 0
    assert "claude-opus-4-8" in opened["content"]  # bumped 4-7 -> 4-8
    assert "claude-opus-4-7" not in opened["content"]
    assert not issued  # nothing gone


def test_main_skips_when_bump_pr_already_open(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    opened, issued = {}, {}
    _stub_gh(monkeypatch, opened, issued, open_pr=99)
    routing = _write_routing(tmp_path)
    assert mod.main(["--repo", "o/r", "--routing", str(routing)]) == 0
    assert not opened  # deduped


def test_main_dry_run_opens_nothing(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    opened, issued = {}, {}
    _stub_gh(monkeypatch, opened, issued)
    routing = _write_routing(tmp_path)
    assert mod.main(["--repo", "o/r", "--routing", str(routing), "--dry-run"]) == 0
    assert not opened and not issued


def test_main_files_issue_when_family_gone(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    opened, issued = {}, {}
    _stub_gh(monkeypatch, opened, issued)
    # A pin whose family has no live member at all.
    p = tmp_path / "model-routing.json"
    p.write_text(json.dumps({"high": "claude-fable-5"}), encoding="utf-8")
    assert mod.main(["--repo", "o/r", "--routing", str(p)]) == 0
    assert "claude-fable-5" in issued["body"]
    assert not opened


def test_main_all_latest_does_nothing(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    opened, issued = {}, {}
    _stub_gh(monkeypatch, opened, issued)
    p = tmp_path / "model-routing.json"
    p.write_text(
        json.dumps({"high": "claude-opus-4-8", "medium": "claude-sonnet-5"}),
        encoding="utf-8",
    )
    assert mod.main(["--repo", "o/r", "--routing", str(p)]) == 0
    assert not opened and not issued
