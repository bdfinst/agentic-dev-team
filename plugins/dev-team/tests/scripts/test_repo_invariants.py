"""Unit tests for skills/code-review/scripts/repo_invariants.py (#1608).

Covers the deterministic "every X has a Y" pre-pass: findings are only raised
for genuinely undocumented modules, and the check currently passes clean
against the real repo (regressions here are real doc-completeness gaps, not
test noise).
"""

from __future__ import annotations

import sys

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(
    0,
    str(_REPO_ROOT / "plugins" / "dev-team" / "skills" / "code-review" / "scripts"),
)

import repo_invariants


class TestMutationKillScriptsDocumented:
    def test_real_repo_has_no_undocumented_mutation_kill_scripts(self):
        # Every script currently shipped under skills/mutation-testing/scripts/
        # is named somewhere in that skill's own docs. A finding here means a
        # newly-added script module was never documented.
        findings = repo_invariants.check_mutation_kill_scripts_documented()
        assert findings == []

    def test_flags_a_script_absent_from_the_doc_set(self, tmp_path, monkeypatch):
        plugin_root = tmp_path / "plugin"
        scripts_dir = plugin_root / "skills" / "mutation-testing" / "scripts"
        scripts_dir.mkdir(parents=True)
        (scripts_dir / "mutation_report.py").write_text("# documented\n")
        (scripts_dir / "new_undocumented_module.py").write_text("# new\n")

        agent_dir = plugin_root / "agents"
        agent_dir.mkdir(parents=True)
        (agent_dir / "mutation-kill.md").write_text(
            "Invoke `mutation_report.py` to score the run.\n"
        )
        (plugin_root / "skills" / "mutation-testing" / "SKILL.md").write_text(
            "See the agent for details.\n"
        )

        monkeypatch.setattr(repo_invariants, "_PLUGIN_ROOT", plugin_root)

        findings = repo_invariants.check_mutation_kill_scripts_documented()

        assert len(findings) == 1
        finding = findings[0]
        assert finding["invariant"] == "mutation-kill-scripts-documented"
        assert finding["file"].endswith("new_undocumented_module.py")
        assert "new_undocumented_module.py" in finding["message"]

    def test_no_scripts_dir_yields_no_findings(self, tmp_path, monkeypatch):
        monkeypatch.setattr(repo_invariants, "_PLUGIN_ROOT", tmp_path / "empty")
        assert repo_invariants.check_mutation_kill_scripts_documented() == []

    def test_flags_a_non_python_script_absent_from_the_doc_set(self, tmp_path, monkeypatch):
        # The check is not Python-specific: it must catch an undocumented
        # module regardless of extension, not just `.py` files.
        plugin_root = tmp_path / "plugin"
        scripts_dir = plugin_root / "skills" / "mutation-testing" / "scripts"
        scripts_dir.mkdir(parents=True)
        (scripts_dir / "documented.sh").write_text("# documented\n")
        (scripts_dir / "undocumented_wrapper.ts").write_text("// new\n")

        agent_dir = plugin_root / "agents"
        agent_dir.mkdir(parents=True)
        (agent_dir / "mutation-kill.md").write_text(
            "Invoke `documented.sh` to score the run.\n"
        )
        (plugin_root / "skills" / "mutation-testing" / "SKILL.md").write_text(
            "See the agent for details.\n"
        )

        monkeypatch.setattr(repo_invariants, "_PLUGIN_ROOT", plugin_root)

        findings = repo_invariants.check_mutation_kill_scripts_documented()

        assert len(findings) == 1
        assert findings[0]["file"].endswith("undocumented_wrapper.ts")

    def test_ignores_pycache_and_init(self, tmp_path, monkeypatch):
        plugin_root = tmp_path / "plugin"
        scripts_dir = plugin_root / "skills" / "mutation-testing" / "scripts"
        (scripts_dir / "__pycache__").mkdir(parents=True)
        (scripts_dir / "__pycache__" / "mutation_report.cpython-311.pyc").write_text("x")
        (scripts_dir / "__init__.py").write_text("")

        agent_dir = plugin_root / "agents"
        agent_dir.mkdir(parents=True)
        (agent_dir / "mutation-kill.md").write_text("nothing relevant here\n")
        (plugin_root / "skills" / "mutation-testing" / "SKILL.md").write_text("n/a\n")

        monkeypatch.setattr(repo_invariants, "_PLUGIN_ROOT", plugin_root)

        assert repo_invariants.check_mutation_kill_scripts_documented() == []


class TestRunAll:
    def test_run_all_aggregates_every_registered_check(self):
        findings = repo_invariants.run_all()
        assert isinstance(findings, list)

    def test_main_prints_json_findings_object(self, capsys):
        exit_code = repo_invariants.main([])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert '"findings"' in captured.out
