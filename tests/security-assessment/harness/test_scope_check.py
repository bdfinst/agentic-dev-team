"""scope_check.py's is_self_owned() duplicated the CIDR-match loop twice —
once for a literal IP host, once per resolved IP for a hostname. Both should
share one helper. These tests lock the existing accept/reject behavior and
then assert the duplication is gone.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = (
    REPO_ROOT
    / "plugins"
    / "security-assessment"
    / "harness"
    / "redteam"
    / "lib"
    / "scope_check.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("scope_check", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["scope_check"] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


scope_check = _load_module()


@pytest.mark.parametrize(
    "target",
    [
        "http://127.0.0.1:8080",
        "http://10.1.2.3",
        "http://172.16.0.5",
        "http://192.168.1.1",
        "http://[::1]",
        "http://[fc00::1]",
    ],
)
def test_self_owned_literal_ips_are_accepted(target: str) -> None:
    accepted, _reason = scope_check.is_self_owned(target)
    assert accepted is True


@pytest.mark.parametrize(
    "target",
    [
        "http://8.8.8.8",
        "http://1.1.1.1",
        "http://[2001:4860:4860::8888]",
    ],
)
def test_public_literal_ips_are_rejected(target: str) -> None:
    accepted, reason = scope_check.is_self_owned(target)
    assert accepted is False
    assert "not in self-owned CIDRs" in reason


def test_localhost_hostname_resolves_and_is_accepted() -> None:
    accepted, _reason = scope_check.is_self_owned("http://localhost")
    assert accepted is True


def test_unresolvable_hostname_is_refused_by_default() -> None:
    accepted, reason = scope_check.is_self_owned(
        "http://this-host-should-not-resolve.invalid"
    )
    assert accepted is False
    assert "Could not resolve host" in reason


def test_no_duplicated_cidr_match_loop() -> None:
    src = MODULE_PATH.read_text(encoding="utf-8")
    occurrences = src.count("for net in ALLOWED_CIDRS_V4")
    assert occurrences <= 1, (
        "the CIDR-match loop over ALLOWED_CIDRS_V4 appears more than once; "
        "extract a shared helper"
    )
