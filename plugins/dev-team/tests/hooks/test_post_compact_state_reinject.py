"""Tests for hooks/post_compact_state_reinject.py (#2177 slice 4, AC 7)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_HOOKS = _REPO_ROOT / "plugins" / "dev-team" / "hooks"
_HOOK = _HOOKS / "post_compact_state_reinject.py"
sys.path.insert(0, str(_HOOKS))

import post_compact_state_reinject as hook

PLAN = """# Plan

## Goal
- [ ] not a build item

## Build Progress

- [x] 1.1
- [ ] 2.3
  - [ ] 2.4

## Risks
- [ ] also not a build item
"""

HEAD = "Restored after compaction: phase=p step=1 plan=plans/a.md"
_LIMIT = hook.MAX_CONTEXT_CHARS


@pytest.fixture
def proj(tmp_path):
    p = tmp_path / "proj"
    (p / "plans").mkdir(parents=True)
    return p


def _state(proj, **over):
    rec = {
        "phase": "refactor",
        "step": "2.3",
        "written_at": datetime.now(timezone.utc).isoformat(),
        "test_files_staged": [],
        "plan_path": "plans/foo.md",
    }
    rec.update(over)
    path = proj / ".claude" / "memory" / "build-phase.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec), encoding="utf-8")
    return path


def _run(proj, stdin, extra_env=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE_", "DEV_TEAM_"))}
    env["CLAUDE_PROJECT_DIR"] = str(proj)
    env.update(extra_env or {})
    return subprocess.run(
        [sys.executable, str(_HOOK)],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(proj),
        check=False,
    )


def _compact():
    return json.dumps({"hook_event_name": "SessionStart", "source": "compact"})


def _context(result):
    return json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]


def test_with_state_injects_context_and_visible_message(proj):
    (proj / "plans" / "foo.md").write_text(PLAN, encoding="utf-8")
    _state(proj)
    r = _run(proj, _compact())
    assert (r.returncode, r.stderr) == (0, "")
    out = json.loads(r.stdout)
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert out["hookSpecificOutput"]["additionalContext"] == (
        "Restored after compaction: phase=refactor step=2.3 plan=plans/foo.md. "
        "Unchecked: 2.3, 2.4."
    )
    assert out["systemMessage"] == "dev-team: restored build state (step 2.3) after compaction"


def test_no_state_emits_nothing(proj):
    r = _run(proj, _compact())
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")


@pytest.mark.parametrize("content", ["", "{}", "[]"])
def test_cleared_state_emits_nothing(proj, content):
    path = _state(proj)
    path.write_text(content, encoding="utf-8")
    assert _run(proj, _compact()).stdout == ""


def test_stale_state_emits_nothing(proj):
    _state(proj, written_at="2020-01-01T00:00:00Z")
    assert _run(proj, _compact()).stdout == ""


def test_plan_path_missing_injects_phase_step_only(proj):
    _state(proj, plan_path="plans/missing.md")
    assert _context(_run(proj, _compact())) == "Restored after compaction: phase=refactor step=2.3"


def test_real_plan_file_outside_repo_is_omitted(tmp_path, proj):
    (tmp_path / "secret.md").write_text(PLAN, encoding="utf-8")  # sibling of proj/
    _state(proj, plan_path="../secret.md")
    assert _context(_run(proj, _compact())) == "Restored after compaction: phase=refactor step=2.3"


def test_plan_without_build_progress_degrades_to_phase_step(proj):
    (proj / "plans" / "foo.md").write_text("# Plan\n\n## Goal\n- [ ] x\n", encoding="utf-8")
    _state(proj)
    assert _context(_run(proj, _compact())) == (
        "Restored after compaction: phase=refactor step=2.3 plan=plans/foo.md"
    )


@pytest.mark.parametrize(
    "stdin",
    [json.dumps({"source": "startup"}), json.dumps({"source": "resume"}), json.dumps({})],
)
def test_only_compact_source_fires(proj, stdin):
    _state(proj)
    assert _run(proj, stdin).stdout == ""


@pytest.mark.parametrize("stdin", ["", "   ", "\x00{{", "[1]", "null"])
def test_fail_open_on_bad_stdin(proj, stdin):
    _state(proj)
    r = _run(proj, stdin)
    assert r.returncode == 0 and "Traceback" not in r.stderr and r.stdout == ""


def test_main_swallows_an_internal_error(monkeypatch, capsys):
    def boom(_payload):
        raise RuntimeError("boom")

    monkeypatch.setattr(hook, "build_output", boom)
    monkeypatch.setattr(hook, "read_stdin_json", lambda: {"source": "compact"})
    assert hook.main() == 0
    captured = capsys.readouterr()
    assert captured.out == ""


def test_state_path_that_is_a_directory_is_fail_open(proj):
    (proj / ".claude" / "memory" / "build-phase.json").mkdir(parents=True)
    r = _run(proj, _compact())
    assert (r.returncode, r.stdout) == (0, "")


def test_binary_plan_file_is_fail_open(proj):
    (proj / "plans" / "foo.md").write_bytes(b"\xff\xfe\x00\x01binary")
    _state(proj)
    r = _run(proj, _compact())
    assert r.returncode == 0
    assert _context(r).startswith("Restored after compaction: phase=refactor step=2.3")


def test_control_characters_in_state_are_stripped(proj):
    _state(proj, phase="re\nfactor\x1b[31m", step="2.3")
    ctx = _context(_run(proj, _compact()))
    assert "\n" not in ctx and "\x1b" not in ctx


# --- boundaries: pure assemble() over characters --------------------------


def _items_for_total(total: int, filler: str = "x") -> list[str]:
    """Items whose fully rendered text is exactly `total` characters."""

    def rendered(items: list[str]) -> int:
        return len(hook.assemble("p", "1", "plans/a.md", items, limit=10**9))

    items: list[str] = []
    while rendered([*items, filler * 100]) + len(", ") + 1 <= total:
        items.append(filler * 100)
    last = total - rendered(items) - len(", ")
    items.append(filler * last)
    assert rendered(items) == total
    return items


@pytest.mark.parametrize("filler", ["x", "é"])
@pytest.mark.parametrize("total", [9_999, 10_000])
def test_at_or_below_limit_is_kept_whole(total, filler):
    items = _items_for_total(total, filler)
    full = hook.assemble("p", "1", "plans/a.md", items, limit=10**9)
    assert len(full) == total
    out = hook.assemble("p", "1", "plans/a.md", items)
    assert out == full
    assert hook.TRUNCATION_MARKER not in out


@pytest.mark.parametrize("filler", ["x", "é", "日", "😀"])
def test_one_over_the_limit_is_truncated_to_the_maximal_prefix(filler):
    items = _items_for_total(10_001, filler)
    out = hook.assemble("p", "1", "plans/a.md", items)
    k = len(out.split("Unchecked: ")[1].removesuffix(hook.TRUNCATION_MARKER).split(", "))
    expected = HEAD + ". Unchecked: " + ", ".join(items[:k]) + "." + hook.TRUNCATION_MARKER
    assert out == expected
    assert len(out) <= _LIMIT
    # maximal: one more item would not fit
    longer = HEAD + ". Unchecked: " + ", ".join(items[: k + 1]) + "." + hook.TRUNCATION_MARKER
    assert len(longer) > _LIMIT


def test_items_are_dropped_last_first_with_exact_output():
    items = [f"item-{i:03d}-" + "x" * 90 for i in range(200)]
    out = hook.assemble("p", "1", "plans/a.md", items)
    body = out.split("Unchecked: ")[1].removesuffix(hook.TRUNCATION_MARKER).removesuffix(".")
    kept = body.split(", ")
    assert kept == items[: len(kept)]
    assert 0 < len(kept) < len(items)
    assert out == HEAD + ". Unchecked: " + ", ".join(kept) + "." + hook.TRUNCATION_MARKER
    assert len(out) <= _LIMIT


def test_limit_without_room_for_any_item_returns_head_plus_marker():
    assert hook.assemble("p", "1", "plans/a.md", ["y" * 200], limit=90) == (
        HEAD + hook.TRUNCATION_MARKER
    )


@pytest.mark.parametrize("limit", [70, 45])
def test_tight_limits_cut_plan_path_before_phase_and_step(limit):
    out = hook.assemble("p", "1", "plans/a.md", ["y" * 200], limit=limit)
    assert out == (HEAD + hook.TRUNCATION_MARKER)[:limit]
    assert out.startswith("Restored after compaction: phase=p step=1")


def test_unchecked_items_only_from_build_progress_section():
    assert hook.unchecked_items(PLAN) == ["2.3", "2.4"]


def test_assembling_100k_items_is_linear_not_quadratic():
    items = [f"item-{i:06d}" for i in range(100_000)]
    start = time.perf_counter()
    out = hook.assemble("p", "1", "plans/a.md", items)
    assert time.perf_counter() - start < 2.0
    assert len(out) <= _LIMIT
    assert out.endswith(hook.TRUNCATION_MARKER)
    body = out.split("Unchecked: ")[1].removesuffix(hook.TRUNCATION_MARKER).removesuffix(".")
    kept = body.split(", ")
    assert kept == items[: len(kept)]
