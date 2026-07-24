"""Unit tests for skills/code-review/scripts/activation.py.

Covers should_slice precedence (no-slice override, explicit --slice, auto-engage,
exact-threshold boundary, non-full-repo suppression, invalid --slice) and the
advisory slice-count ceiling guard.
"""

from __future__ import annotations

import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(
    0,
    str(_REPO_ROOT / "plugins" / "dev-team" / "skills" / "code-review" / "scripts"),
)

import activation


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


def test_no_slice_wins_before_slice_validation():
    # Precedence contract: --no-slice must short-circuit BEFORE --slice is
    # validated. An invalid slice_flag alongside no_slice_flag must NOT raise.
    engage, cap = activation.should_slice(
        "full-repo", 1000, slice_flag=0, no_slice_flag=True
    )
    assert engage is False
    assert cap is None


def test_auto_engage_uses_custom_default_cap():
    # The default_cap parameter (used on auto-engage) is honored, not ignored.
    engage, cap = activation.should_slice(
        "full-repo", 900, threshold=500, default_cap=25
    )
    assert engage is True
    assert cap == 25
