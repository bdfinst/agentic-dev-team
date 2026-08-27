"""Shared golden-harness fixtures for the session-report test files.

Split out of `tests/scripts/test_session_report_golden.py` when
`test_session_report_profiles_golden.py` (issue #2046) was added as a
sibling, deliberately NOT a `test_*.py` module (so pytest never collects
it directly) and deliberately importing nothing from either extractor
script at MODULE level — only `_load_module`'s lazy `importlib` load does
that, inside a function body. This matters because
`scripts/session_extract.py` uses `datetime.UTC` (3.11+; that monorepo-only
script isn't subject to the shipped-tree 3.10 floor — see ADR 0031), and
`test_session_report_profiles_golden.py` runs under the floor interpreter
(it tests the newly-shipped `session_report.py`) while
`test_session_report_golden.py` does not. A module-level import of
`session_extract.py`'s own contents here would break that floor run even
though nothing in the profiles file ever calls `_session_extract_digest()`.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

# Under pytest, pytest.ini's `pythonpath = .` already makes `_repo_root`
# importable. The regeneration entry point in test_session_report_golden.py
# runs as a bare `python3 ...py` instead, with no such pythonpath — so make
# the repo root importable here too, before relying on it.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _repo_root import REPO_ROOT

FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "session_log"
CORPUS_ROOT = FIXTURE_ROOT / "projects"

SESSION_EXTRACT_SCRIPT = REPO_ROOT / "scripts" / "session_extract.py"
EXTRACT_SESSION_REPORT_SCRIPT = (
    REPO_ROOT / "plugins" / "dev-team" / "scripts" / "extract_session_report.py"
)
SESSION_REPORT_SCRIPT = REPO_ROOT / "plugins" / "dev-team" / "scripts" / "session_report.py"

SESSION_EXTRACT_GOLDEN = FIXTURE_ROOT / "session_extract.golden.json"
EXTRACT_SESSION_REPORT_GOLDEN = FIXTURE_ROOT / "extract_session_report.golden.json"

# Fixed, literal registry — deliberately NOT the live plugin's agents/skills
# dirs. Names match the corpus's `attributionAgent` values (stripped of
# their `dev-team:` namespace) plus one never-invoked agent/skill each, so
# `never_observed_*` has non-trivial content.
REGISTRY = {
    "skills": ["never-invoked-skill"],
    "agents": ["correctness-review", "doc-review", "never-invoked-agent"],
}

# Maintainer-profile-only: a fixed pricing table so `token.cost_usd` is a
# deterministic function of the corpus, independent of the shipped
# knowledge/model-pricing.json (which changes for reasons unrelated to this
# harness).
PRICING = {
    "models": {"claude-sonnet-5": {"input": 3.0, "output": 15.0}},
    "cache_write_multiplier": 1.25,
    "cache_read_multiplier": 0.1,
}
PLUGIN_VERSION = "0.0.0-golden"

# Sentinel markers embedded in the corpus (see fixture files under
# tests/fixtures/session_log/projects/) that must never surface in any
# extractor's output.
SENTINELS = (
    "SENTINEL_PROMPT_DO_NOT_LEAK",
    "SENTINEL_CODE_DO_NOT_LEAK",
    "SENTINEL_CMD_do_not_leak",
    "SENTINEL_USER",
    # Absolute POSIX path sentinel (issue #2045) — pairs with SENTINEL_USER's
    # Windows-style path above, so the corpus exercises redact()'s
    # from_path=True branch against both path shapes, not Windows only.
    "SENTINEL_POSIX_USER",
)


def load_module(path: Path, name: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
