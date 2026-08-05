"""Guard `plugins/security-assessment/harness/**` against `datetime.UTC`
(issue #1805).

That plugin's own `CLAUDE.md` states "Python >= 3.10 available (red-team
harness requires it)" (checked by `install.sh`) — a real floor, separate from
ADR 0031's `plugins/dev-team/**` one, because this harness also runs on an end
user's interpreter, not just a maintainer's/CI's. `datetime.UTC` is a 3.11+
stdlib alias (PEP 631's `datetime.UTC`, added in 3.11) that raises
`ImportError` on 3.10 — exactly what happened in `probe_08_report_generator.py`
before this fix.

`ruff.toml`'s `[per-file-target-version]` now pins this path to `py310`
(alongside `plugins/dev-team/**`), which stops ruff's own autofixer from
*reintroducing* `datetime.UTC` here — but nothing short of an interpreter
proves the floor, and this harness has no `chk_python_floor`-equivalent
byte-compile+import gate the way `plugins/dev-team/**` does. This grep-based
check is a cheaper, narrower backstop for the one specific regression this
issue exists to close, not a substitute for that stronger gate — a future
pass adding byte-compile+import coverage for this harness (mirroring
`chk_python_floor`) would fully subsume it.

Deliberately NOT applied to `scripts/**` or `tests/**` (repo-root dev
tooling): ADR 0031 explicitly states those run on a maintainer's/CI's
interpreter and are outside the shipped floor — "Repo-root scripts may now
use `datetime.UTC` and other 3.11-only stdlib surface; shipped code may not."
`plugins/dev-team/**` needs no separate check here either: `chk_python_floor`
already byte-compiles and imports every module there under a real 3.10
interpreter, which would raise `ImportError` on `datetime.UTC` directly —
a stronger signal than a regex could ever be, per this repo's own
"deterministic tools over inference" rule.
"""

from __future__ import annotations

import re

from _repo_root import REPO_ROOT

HARNESS_DIR = REPO_ROOT / "plugins" / "security-assessment" / "harness"

# Matches a real usage: `from datetime import UTC` (optionally alongside other
# names) or `datetime.UTC` as an attribute access. Deliberately anchored so it
# doesn't match `UTC` appearing as a plain identifier/string/comment elsewhere
# (e.g. a timestamp format string, or prose mentioning "UTC").
_IMPORT_UTC_RE = re.compile(r"^\s*from\s+datetime\s+import\s+.*\bUTC\b", re.MULTILINE)
_ATTR_UTC_RE = re.compile(r"\bdatetime\.UTC\b")


def _real_usages(text: str) -> list[str]:
    """Real `datetime.UTC` usages in `text`, skipping comment-only lines."""
    hits = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        code = line.split("#", 1)[0]
        if _IMPORT_UTC_RE.match(code) or _ATTR_UTC_RE.search(code):
            hits.append(f"line {lineno}: {line.strip()}")
    return hits


def test_real_usages_flags_an_import_and_an_attribute_access() -> None:
    """Proves the detector can actually fire — not just stay quiet on a clean tree."""
    src = (
        "from datetime import UTC\n"
        "import datetime\n"
        "now = datetime.datetime.now(datetime.UTC)\n"
    )
    hits = _real_usages(src)
    assert len(hits) == 2
    assert "line 1" in hits[0]
    assert "line 3" in hits[1]


def test_real_usages_ignores_comment_only_mentions() -> None:
    src = (
        "# from datetime import UTC -- do not do this\n"
        "# datetime.UTC needs 3.11+\n"
        "from datetime import timezone\n"
        "now = datetime.datetime.now(timezone.utc)  # not datetime.UTC\n"
    )
    assert _real_usages(src) == []


def test_no_datetime_utc_in_security_assessment_harness() -> None:
    """`datetime.UTC` requires Python 3.11+; this harness's floor is 3.10."""
    assert HARNESS_DIR.is_dir(), f"expected harness dir at {HARNESS_DIR}"

    offenders: dict[str, list[str]] = {}
    for path in sorted(HARNESS_DIR.rglob("*.py")):
        hits = _real_usages(path.read_text(encoding="utf-8"))
        if hits:
            offenders[str(path.relative_to(REPO_ROOT))] = hits

    assert not offenders, (
        "datetime.UTC (Python 3.11+) used in plugins/security-assessment/harness, "
        "which declares a Python >= 3.10 floor in its own CLAUDE.md. Use "
        "`from datetime import timezone` + `timezone.utc` instead "
        f"(available since Python 3.2):\n{offenders}"
    )
