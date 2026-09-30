"""Tests for hooks/post_compact_state_reinject.py (#2177 slice 4, AC 7)."""

from __future__ import annotations

import json
import os
import subprocess
import sys

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


@pytest.fixture
def proj(tmp_path):
    p = tmp_path / "proj"
    (p / "plans").mkdir(parents=True)
    return p


def _state(proj, **over):
    rec = {"phase": "refactor", "step": "2.3", "written_at": "t", "test_files_staged": []}
    rec["plan_path"] = "plans/foo.md"
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


def test_plan_path_missing_injects_phase_step_only(proj):
    _state(proj, plan_path="plans/missing.md")
    ctx = json.loads(_run(proj, _compact()).stdout)["hookSpecificOutput"]["additionalContext"]
    assert ctx == "Restored after compaction: phase=refactor step=2.3"


def test_plan_path_outside_repo_is_omitted(proj):
    _state(proj, plan_path="../../etc/passwd")
    ctx = json.loads(_run(proj, _compact()).stdout)["hookSpecificOutput"]["additionalContext"]
    assert ctx == "Restored after compaction: phase=refactor step=2.3"


def test_plan_without_build_progress_degrades_to_phase_step(proj):
    (proj / "plans" / "foo.md").write_text("# Plan\n\n## Goal\n- [ ] x\n", encoding="utf-8")
    _state(proj)
    ctx = json.loads(_run(proj, _compact()).stdout)["hookSpecificOutput"]["additionalContext"]
    assert ctx == "Restored after compaction: phase=refactor step=2.3 plan=plans/foo.md"


@pytest.mark.parametrize("stdin", [
    json.dumps({"source": "startup"}),
    json.dumps({"source": "resume"}),
    json.dumps({}),
])
def test_only_compact_source_fires(proj, stdin):
    _state(proj)
    assert _run(proj, stdin).stdout == ""


@pytest.mark.parametrize("stdin", ["", "   ", "\x00{{", "[1]", "null"])
def test_fail_open_on_bad_stdin(proj, stdin):
    _state(proj)
    r = _run(proj, stdin)
    assert r.returncode == 0 and "Traceback" not in r.stderr and r.stdout == ""


@pytest.mark.skipif(
    os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="chmod 000 is not enforced for root / Windows",
)
def test_unreadable_state_file_is_fail_open(proj):
    path = _state(proj)
    path.chmod(0)
    try:
        r = _run(proj, _compact())
        assert (r.returncode, r.stdout) == (0, "")
    finally:
        path.chmod(0o644)


def test_binary_plan_file_is_fail_open(proj):
    (proj / "plans" / "foo.md").write_bytes(b"\xff\xfe\x00\x01binary")
    _state(proj)
    r = _run(proj, _compact())
    assert r.returncode == 0
    ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
    assert ctx.startswith("Restored after compaction: phase=refactor step=2.3")


def test_control_characters_in_state_are_stripped(proj):
    _state(proj, phase="re\nfactor\x1b[31m", step="2.3")
    ctx = json.loads(_run(proj, _compact()).stdout)["hookSpecificOutput"]["additionalContext"]
    assert "\n" not in ctx and "\x1b" not in ctx


# --- boundaries: pure assemble() over characters --------------------------

_LIMIT = hook.MAX_CONTEXT_CHARS


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


@pytest.mark.parametrize("total", [9_999, 10_000])
def test_at_or_below_limit_is_kept_whole(total):
    items = _items_for_total(total)
    full = hook.assemble("p", "1", "plans/a.md", items, limit=10**9)
    assert len(full) == total
    assert hook.assemble("p", "1", "plans/a.md", items) == full


def test_one_over_the_limit_is_truncated_with_marker():
    items = _items_for_total(10_001)
    full = hook.assemble("p", "1", "plans/a.md", items, limit=10**9)
    assert len(full) == 10_001
    out = hook.assemble("p", "1", "plans/a.md", items)
    assert len(out) <= _LIMIT
    assert out.endswith(hook.TRUNCATION_MARKER)
    assert out.startswith("Restored after compaction: phase=p step=1 plan=plans/a.md")


def test_items_are_dropped_last_first():
    items = [f"item-{i:03d}-" + "x" * 90 for i in range(200)]
    out = hook.assemble("p", "1", "plans/a.md", items)
    kept = out.split("Unchecked: ")[1].removesuffix(hook.TRUNCATION_MARKER).removesuffix(".").split(", ")
    assert kept == items[: len(kept)]
    assert 0 < len(kept) < len(items)
    assert len(out) <= _LIMIT


@pytest.mark.parametrize("filler", ["é", "日", "😀"])
def test_multibyte_counts_characters_not_bytes(filler):
    items = _items_for_total(10_001, filler=filler)
    out = hook.assemble("p", "1", "plans/a.md", items)
    assert len(out) <= _LIMIT
    out.encode("utf-8")  # never split mid-codepoint: encodes cleanly
    assert out.endswith(hook.TRUNCATION_MARKER)
    # a byte-counting implementation would have cut far earlier
    assert len(out) > _LIMIT - 400


def test_priority_phase_step_and_plan_survive_even_when_no_item_fits():
    out = hook.assemble("p", "1", "plans/a.md", ["y" * 200], limit=90)
    assert out.startswith("Restored after compaction: phase=p step=1")
    assert len(out) <= 90


def test_unchecked_items_only_from_build_progress_section():
    assert hook.unchecked_items(PLAN) == ["2.3", "2.4"]
