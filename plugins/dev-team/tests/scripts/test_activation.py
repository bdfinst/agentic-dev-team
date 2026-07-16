"""Unit tests for skills/code-review/scripts/activation.py.

Covers should_slice precedence (no-slice override, explicit --slice, auto-engage,
exact-threshold boundary, non-full-repo suppression, invalid --slice) and the
advisory slice-count ceiling guard.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(
    0,
    str(_REPO_ROOT / "plugins" / "dev-team" / "skills" / "code-review" / "scripts"),
)

import activation  # noqa: E402


def test_auto_engage_above_threshold_full_repo():
    engage, cap = activation.should_slice("full-repo", 501, threshold=500)
    assert engage is True
    assert cap == activation.DEFAULT_CAP


def test_exact_threshold_does_not_auto_engage():
    engage, cap = activation.should_slice("full-repo", 500, threshold=500)
    assert engage is False
    assert cap is None


def test_below_threshold_does_not_auto_engage():
    engage, _ = activation.should_slice("full-repo", 10, threshold=500)
    assert engage is False


def test_explicit_slice_engages_at_any_size():
    engage, cap = activation.should_slice("full-repo", 3, slice_flag=25)
    assert engage is True
    assert cap == 25


def test_explicit_slice_engages_for_non_full_repo_scope():
    engage, cap = activation.should_slice("path", 3, slice_flag=25)
    assert engage is True
    assert cap == 25


def test_no_slice_overrides_everything():
    # --no-slice wins even when --slice is also given and repo is large.
    engage, cap = activation.should_slice(
        "full-repo", 10_000, slice_flag=25, no_slice_flag=True
    )
    assert engage is False
    assert cap is None


def test_non_full_repo_scope_never_auto_slices():
    for scope in ("path", "since", "uncommitted"):
        engage, _ = activation.should_slice(scope, 10_000, threshold=500)
        assert engage is False, scope


@pytest.mark.parametrize("bad", [0, -1, -100, 1.5, "10", True, object()])
def test_invalid_slice_flag_rejected(bad):
    with pytest.raises(ValueError):
        activation.should_slice("full-repo", 100, slice_flag=bad)


def test_ceiling_guard_fires_above_ceiling():
    msg = activation.check_slice_ceiling(activation.SLICE_COUNT_CEILING + 1)
    assert msg is not None
    assert "--slice" in msg


def test_ceiling_guard_silent_at_or_below_ceiling():
    assert activation.check_slice_ceiling(activation.SLICE_COUNT_CEILING) is None
    assert activation.check_slice_ceiling(1) is None
