"""Unit tests for skills/code-review/scripts/dispatch_reconcile.py (#1761).

Covers the deterministic dispatched-vs-returned reconciliation: which agents
in a dispatched roster never appeared in the set of contract-valid returns.
Order-preserving and de-duplicating on the dispatched side; an unexpected
extra name on the returned side is ignored rather than raised as an error.
"""

from __future__ import annotations

import json
import subprocess
import sys

from _repo_root import REPO_ROOT as _REPO_ROOT

_SCRIPTS_DIR = _REPO_ROOT / "plugins" / "dev-team" / "skills" / "code-review" / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

import dispatch_reconcile

_SCRIPT_PATH = _SCRIPTS_DIR / "dispatch_reconcile.py"


class TestReconcileDispatch:
    def test_all_dispatched_agents_returned_yields_empty_missing_list(self):
        dispatched = ["correctness-review", "structure-review", "security-review"]
        returned = {"correctness-review", "structure-review", "security-review"}
        assert dispatch_reconcile.reconcile_dispatch(dispatched, returned) == []

    def test_some_missing_preserves_roster_order(self):
        dispatched = ["correctness-review", "structure-review", "security-review"]
        returned = {"correctness-review", "security-review"}
        assert dispatch_reconcile.reconcile_dispatch(dispatched, returned) == ["structure-review"]

    def test_empty_dispatched_roster_yields_empty_missing_list(self):
        assert dispatch_reconcile.reconcile_dispatch([], {"correctness-review"}) == []

    def test_nothing_returned_reports_every_dispatched_agent(self):
        dispatched = ["correctness-review", "structure-review"]
        assert dispatch_reconcile.reconcile_dispatch(dispatched, set()) == dispatched

    def test_duplicate_names_in_roster_reported_once_at_first_seen_order(self):
        dispatched = ["correctness-review", "correctness-review", "security-review"]
        assert dispatch_reconcile.reconcile_dispatch(dispatched, set()) == [
            "correctness-review",
            "security-review",
        ]

    def test_unexpected_returned_name_outside_roster_is_ignored(self):
        dispatched = ["correctness-review"]
        returned = {"correctness-review", "some-other-agent"}
        assert dispatch_reconcile.reconcile_dispatch(dispatched, returned) == []


class TestCli:
    def test_cli_reports_missing_agent_as_json(self):
        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "--dispatched",
                "correctness-review,structure-review,security-review",
                "--returned",
                "correctness-review,security-review",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        assert json.loads(result.stdout) == {"missing": ["structure-review"]}

    def test_cli_empty_roster_reports_empty_missing_list(self):
        result = subprocess.run(
            [sys.executable, str(_SCRIPT_PATH), "--dispatched", "", "--returned", ""],
            capture_output=True,
            text=True,
            check=True,
        )
        assert json.loads(result.stdout) == {"missing": []}
