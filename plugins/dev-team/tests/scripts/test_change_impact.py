"""Unit tests for skills/code-review/scripts/change_impact.py.

The gate must drop `arch-review` only when it can PROVE the diff moved no
boundary — and must keep it on every input it cannot classify. A false skip
is a silent coverage hole; a false keep only costs a dispatch.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_PLUGIN_ROOT = _REPO_ROOT / "plugins" / "dev-team"
_SCRIPTS_DIR = _PLUGIN_ROOT / "skills" / "code-review" / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

import change_impact


def _diff(path, added=(), removed=(), header_extra=()):
    lines = [f"diff --git a/{path} b/{path}"]
    lines += list(header_extra)
    lines += [f"--- a/{path}", f"+++ b/{path}", "@@ -1,4 +1,5 @@", " context"]
    lines += [f"-{ln}" for ln in removed]
    lines += [f"+{ln}" for ln in added]
    return "\n".join(lines) + "\n"


BODY_ONLY = _diff(
    "src/pricing.js",
    added=["  if (total < 0) throw new RangeError('negative total')"],
)


class TestNoArchitecturalImpact:
    def test_a_guard_clause_added_inside_a_function_skips_arch_review(self):
        result = change_impact.evaluate(BODY_ONLY)
        assert result["skipLenses"] == ["arch-review"]
        assert result["hasArchitecturalImpact"] is False

    def test_a_pure_value_change_skips_arch_review(self):
        result = change_impact.evaluate(
            _diff("src/config.js", removed=["  const RETRIES = 3"], added=["  const RETRIES = 5"])
        )
        assert result["skipLenses"] == ["arch-review"]

    def test_a_comment_only_change_skips_arch_review(self):
        result = change_impact.evaluate(_diff("src/a.js", added=["  // clarify intent"]))
        assert result["skipLenses"] == ["arch-review"]


class TestArchitecturalSignals:
    @pytest.mark.parametrize(
        "line",
        [
            "import { Repo } from '../infra/repo'",
            "from app.infra.db import Session",
            "using System.Data.SqlClient;",
            "#include <vector>",
            "use crate::infra::db;",
            "const db = require('./db')",
            "export { thing } from './other'",
        ],
    )
    def test_an_added_import_is_a_dependency_signal(self, line):
        result = change_impact.evaluate(_diff("src/domain/order.ts", added=[line]))
        assert "dependency" in result["signals"]
        assert result["skipLenses"] == []

    def test_a_removed_import_also_counts(self):
        result = change_impact.evaluate(_diff("src/a.ts", removed=["import { X } from './x'"]))
        assert "dependency" in result["signals"]

    def test_a_new_file_is_a_structure_signal(self):
        result = change_impact.evaluate(
            _diff("src/new_module.ts", added=["const a = 1"], header_extra=["new file mode 100644"])
        )
        assert "structure" in result["signals"]
        assert result["skipLenses"] == []

    def test_a_deleted_file_is_a_structure_signal(self):
        result = change_impact.evaluate(
            _diff("src/gone.ts", removed=["const a = 1"], header_extra=["deleted file mode 100644"])
        )
        assert "structure" in result["signals"]

    def test_a_rename_is_a_structure_signal(self):
        result = change_impact.evaluate(
            _diff("src/b.ts", header_extra=["rename from src/a.ts", "rename to src/b.ts"])
        )
        assert "structure" in result["signals"]

    @pytest.mark.parametrize(
        "line",
        [
            "export function createOrder() {}",
            "public class OrderService {}",
            "public interface Repo {}",
            "module.exports = { a }",
            "__all__ = ['Order']",
            "class OrderAggregate:",
        ],
    )
    def test_a_public_surface_change_is_an_interface_signal(self, line):
        result = change_impact.evaluate(_diff("src/domain/order.ts", added=[line]))
        assert "interface" in result["signals"]
        assert result["skipLenses"] == []

    @pytest.mark.parametrize(
        "path",
        ["package.json", "pyproject.toml", "go.mod", "pom.xml", "src/App.csproj", "Cargo.toml"],
    )
    def test_a_dependency_manifest_change_is_a_manifest_signal(self, path):
        result = change_impact.evaluate(_diff(path, added=['  "left-pad": "1.0.0"']))
        assert "manifest" in result["signals"]
        assert result["skipLenses"] == []

    @pytest.mark.parametrize(
        "path",
        [
            "Dockerfile",
            "docker-compose.yml",
            "terraform/main.tf",
            "k8s/deploy.yaml",
            ".github/workflows/ci.yml",
            "helm/values.yaml",
        ],
    )
    def test_an_infra_change_is_an_infra_signal(self, path):
        result = change_impact.evaluate(_diff(path, added=["  replicas: 3"]))
        assert "infra" in result["signals"]
        assert result["skipLenses"] == []

    def test_an_adr_change_is_an_adr_signal(self):
        result = change_impact.evaluate(
            _diff("docs/adr/0031-use-outbox.md", added=["We will use the outbox pattern."])
        )
        assert "adr" in result["signals"]
        assert result["skipLenses"] == []


class TestFailSafe:
    def test_unparseable_input_assumes_impact(self):
        result = change_impact.evaluate("this is not a diff")
        assert result["skipLenses"] == []
        assert result["hasArchitecturalImpact"] is True
        assert result["reason"] == "diff-not-parseable-assuming-impact"

    def test_empty_input_assumes_impact(self):
        result = change_impact.evaluate("")
        assert result["skipLenses"] == []
        assert result["hasArchitecturalImpact"] is True

    def test_extra_files_can_supply_a_signal_the_diff_body_lacks(self):
        result = change_impact.evaluate(BODY_ONLY, extra_files=["Dockerfile"])
        assert "infra" in result["signals"]
        assert result["skipLenses"] == []

    def test_a_mixed_diff_keeps_the_lens_when_any_file_carries_signal(self):
        combined = BODY_ONLY + _diff("package.json", added=['  "x": "1"'])
        assert change_impact.evaluate(combined)["skipLenses"] == []


class TestGateComposition:
    def test_only_arch_review_is_gated_in_this_pass(self):
        """domain-review is deliberately NOT gated: business logic placed in a
        controller body is a real violation introduced by a body-only edit."""
        assert set(change_impact.GATED_LENSES) == {"arch-review"}

    def test_the_gate_never_drops_a_change_size_floor_agent(self):
        """change_size.py keeps 4 agents on its narrowest fast path to clear
        the commit gate's >= 2 distinct-dispatch floor. This gate must never
        remove one of them, or the two gates could compose into a blocked
        commit."""
        floor = {"security-review", "correctness-review", "spec-compliance-review", "doc-review"}
        assert not (set(change_impact.GATED_LENSES) & floor)

    def test_the_floor_set_still_matches_change_size(self):
        """Drift guard: if change_size.py's keep-set changes, the assertion
        above must be re-checked against the new set rather than silently
        testing a stale literal."""
        source = (_SCRIPTS_DIR / "change_size.py").read_text(encoding="utf-8")
        for agent in (
            "security-review",
            "correctness-review",
            "spec-compliance-review",
            "doc-review",
        ):
            assert agent in source, f"{agent} no longer named in change_size.py"


class TestCli:
    def test_cli_reads_a_diff_on_stdin(self):
        result = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "change_impact.py")],
            input=BODY_ONLY,
            capture_output=True,
            text=True,
            check=True,
        )
        assert json.loads(result.stdout)["skipLenses"] == ["arch-review"]

    def test_cli_accepts_extra_files(self):
        result = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "change_impact.py"), "--files", "go.mod"],
            input=BODY_ONLY,
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(result.stdout)
        assert "manifest" in payload["signals"]
        assert payload["skipLenses"] == []


class TestAgainstRealRepoDiffs:
    def test_this_prs_own_diff_has_architectural_impact(self):
        """Sanity check against real git output rather than only synthetic
        fixtures: this branch adds new script modules, so the gate must keep
        arch-review."""
        diff = subprocess.run(
            ["git", "diff", "--no-color", "origin/main...HEAD"],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        if diff.returncode != 0 or not diff.stdout.strip():
            pytest.skip("no origin/main..HEAD diff available in this checkout")
        result = change_impact.evaluate(diff.stdout)
        assert result["skipLenses"] == []
        assert "structure" in result["signals"]
