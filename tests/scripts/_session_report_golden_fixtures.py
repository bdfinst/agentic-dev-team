"""Shared golden-harness fixtures for `test_session_report_golden.py`.

Split out of that file back when it also golden-tested the two now-retired
predecessor extractors (issue #2046's `test_session_report_profiles_golden.py`
sibling; both merged back into one file in #2048 once the predecessors —
and the floor-incompatibility that motivated the split — were deleted).
Kept as its own module rather than folded back into the test file because
`_regenerate()`'s CLI entry point and the pytest test functions both need
these same constants/helpers.
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
# tests/fixtures/session_log/projects/) that must never surface in either
# profile's output.
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
