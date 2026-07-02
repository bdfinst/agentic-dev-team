"""Enforcement: no pinned claude-* snapshot IDs anywhere in the repo outside
the approved files (the single source of truth + its docs).

Ported from tests/repo/no_pinned_snapshots_test.bats (#673).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# The plugin-source files allowed to contain a pinned snapshot ID:
#   knowledge/model-routing.json - single source of truth (the whole point)
#   docs/model-routing.md       - contract doc; illustrative examples
#   docs/model-routing-overrides.md - override guide; worked ladder examples
#   templates/agents/agent-template.md - commented documentation block
#
# Out-of-scope (legitimate references the AC does not police):
#   docs/specs/, plans/, docs/spikes/ - design artifacts that name the
#     values exactly because they describe the migration.
#   evals/ - semgrep fixtures for OTHER plugins' LLM model strings.
#   tests/  - bats + pytest fixtures that depend on the literal values.
#     Includes plugins/dev-team/tests/ (the plugin's own pytest suite) - same
#     exemption reason: fixture-test code legitimately names the literals to
#     assert byte-for-byte against them.
#   knowledge/model-pricing.json - cost meter's pricing table (#102); must key
#     by model snapshot because the transcript usage records emit snapshot
#     IDs.
ALLOWED_PATHS = [
    "plugins/dev-team/knowledge/model-routing.json",
    "plugins/dev-team/docs/model-routing.md",
    "plugins/dev-team/docs/model-routing-overrides.md",
    "plugins/dev-team/templates/agents/agent-template.md",
    "plugins/dev-team/knowledge/model-pricing.json",
]

_SNAPSHOT_RE = re.compile(r"claude-(haiku|sonnet|opus)-[0-9]")


def test_no_pinned_snapshot_ids_in_plugin_source_outside_approved_files() -> None:
    cmd = [
        "git",
        "grep",
        "-nE",
        _SNAPSHOT_RE.pattern,
        "--",
        "plugins/",
    ]
    for allowed in ALLOWED_PATHS:
        cmd.append(f":!{allowed}")
    cmd.append(":!plugins/dev-team/tests/")

    result = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    # git grep exits 1 when no matches are found - that is the success case.
    assert result.returncode in (0, 1), result.stderr
    raw = result.stdout.strip()
    assert not raw, (
        "Pinned snapshot IDs found in non-approved plugin source files:\n" + raw
    )
