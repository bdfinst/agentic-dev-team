"""Drift guard for the shared `_repo_root.REPO_ROOT` constant.

222 test files used to each independently compute their own repo-root
constant via `REPO_ROOT = Path(__file__).resolve().parents[N]` (or
`_REPO_ROOT = ...`), with N depending on that file's own directory depth --
a single-point-of-change risk (test-improve issue-1354, Story 2). They were
migrated to `from _repo_root import REPO_ROOT` instead. This test is what
keeps a *new* file from reintroducing the pattern: without it, nothing stops
the next contributor (human or agent) from writing the same
`REPO_ROOT = Path(__file__).resolve().parents[N]` line again, since a
convention noted only in a doc or skill is easy to miss.

Scope note: this guard matches only the *named* repo-root-constant pattern
(`REPO_ROOT`/`_REPO_ROOT`), not every use of `Path(__file__).resolve()
.parents[N]` in the corpus. ~51 other files use that expression for an
unrelated, file-specific need (e.g. `_SCRIPT_DIR = Path(__file__).resolve()
.parents[2] / "scripts"`, or an inline call with no named constant at all) --
a distinct, differently-shaped finding, out of scope for this guard and this
Story. Broadening the regex to ban the raw expression everywhere would flag
those too, which is not what test-improve issue-1354 fixed.
"""

from __future__ import annotations

import re

from _repo_root import REPO_ROOT

# _repo_root.py itself (the one sanctioned definition site) needs no explicit
# exemption below: it resolves REPO_ROOT via .resolve().parent (no
# .parents[N]), so it can never match _PATTERN, and it also lives outside
# _TEST_DIRS, so _test_files() never yields it anyway.
_PATTERN = re.compile(
    r"^[ \t]*_?REPO_ROOT\s*=\s*Path\(__file__\)\.resolve\(\)\.parents\[\d+\]\s*$",
    re.MULTILINE,
)

_TEST_DIRS = [
    REPO_ROOT / "tests",
    REPO_ROOT / "plugins" / "dev-team" / "tests",
]


def _test_files():
    for base in _TEST_DIRS:
        yield from base.rglob("test_*.py")
        yield from base.rglob("conftest.py")


def test_no_file_reinvents_repo_root_resolution():
    offenders = []
    for path in _test_files():
        text = path.read_text(encoding="utf-8")
        if _PATTERN.search(text):
            offenders.append(str(path.relative_to(REPO_ROOT)))

    assert not offenders, (
        "These files reinvent repo-root resolution instead of importing the "
        "shared constant -- use `from _repo_root import REPO_ROOT` (alias as "
        "needed) instead of `Path(__file__).resolve().parents[N]`:\n  "
        + "\n  ".join(sorted(offenders))
    )
