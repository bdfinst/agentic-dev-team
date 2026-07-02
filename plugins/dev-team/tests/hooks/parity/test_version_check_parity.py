"""Parity fixtures for hooks/version-check (#609 / #572 Phase 3).

The hook consults `/tmp/adt-version-check-<today>` as a daily cache, then
compares HEAD to origin/<default-branch> via `git fetch`. Both sides use the
same literal `/tmp` path, so we cannot fixture the cache via the parity
sandbox's initial_tree — it lives outside the sandbox by design.

Instead, we pre-populate `/tmp/adt-version-check-<today>` with the fixture
content before dispatching either implementation. That short-circuits both
past the network-dependent path, giving byte-parity we can actually check.

Fixture cases:
  - cache_hit_with_message → cache has a notice line → both echo it, exit 0
  - cache_hit_empty        → cache exists but empty  → both silent-pass
  - malformed_stdin        → stdin is broken JSON, cache empty → silent-pass
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable

import pytest

from parity import Fixture, assert_parity  # type: ignore[import-not-found]


_REPO_ROOT = Path(__file__).resolve().parents[5]
_HOOK_SH = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "version-check.sh"
_HOOK_PY = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "version_check.py"


def _cache_path() -> Path:
    today = datetime.now().strftime("%Y-%m-%d")
    return Path("/tmp") / f"adt-version-check-{today}"


@pytest.fixture
def restore_cache_file():
    """Save whatever /tmp/adt-version-check-<today> currently is, restore it
    after the test — so real user cache is never clobbered."""
    cache = _cache_path()
    original: bytes | None = None
    if cache.is_file():
        original = cache.read_bytes()
    try:
        yield cache
    finally:
        if original is None:
            if cache.is_file():
                cache.unlink()
        else:
            cache.write_bytes(original)


CASES = [
    (
        "cache_hit_with_message",
        b"\xf0\x9f\x93\xa6 dev-team@bfinster: 3 update(s) available. "
        b"Run /upgrade to update.\n",
        b'{"tool_name":"Read"}',
    ),
    ("cache_hit_empty", b"", b'{"tool_name":"Read"}'),
    ("malformed_stdin", b"", b'{"broken'),
]


@pytest.mark.skipif(
    not _HOOK_SH.is_file() or not _HOOK_PY.is_file(),
    reason="both .sh and .py implementations required",
)
@pytest.mark.parametrize("name, cache_content, stdin", CASES, ids=[c[0] for c in CASES])
def test_parity(
    restore_cache_file: Path, name: str, cache_content: bytes, stdin: bytes
) -> None:
    restore_cache_file.write_bytes(cache_content)
    fixture = Fixture(name=name, stdin=stdin, argv=[], env={}, initial_tree={})
    assert_parity(
        sh_argv=["bash", str(_HOOK_SH)],
        py_argv=["python3", str(_HOOK_PY)],
        fixture=fixture,
    )
