"""Unit tests for skills/code-review/scripts/repo_invariants.py (#1608).

Covers the deterministic "every X has a Y" pre-pass: findings are only raised
for genuinely undocumented modules, and the check currently passes clean
against the real repo (regressions here are real doc-completeness gaps, not
test noise).
"""

from __future__ import annotations

import json
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


# --- #1629: churn-generator checks ---------------------------------------


class TestChangesetScoping:
    """All three #1629 checks are scoped to the changeset, because each
    enforces a convention that is required going forward but explicitly not
    retrofitted. With no changeset they must stay silent rather than dumping
    the ~150 pre-existing findings into every review panel."""

    def test_pre_pass_with_no_changeset_is_silent(self):
        assert repo_invariants.check_eval_calibration_blocks(None) == []
        assert repo_invariants.check_must_not_mention_terms_appear_in_fixture(None) == []
        assert repo_invariants.check_scope_glob_matches_skip_prose(None) == []

    def test_every_registered_check_accepts_the_changed_files_argument(self):
        for check in repo_invariants.CHECKS:
            assert check(None) is not None
            assert check([]) is not None

    def test_run_all_is_clean_against_the_real_repo_with_no_changeset(self):
        assert repo_invariants.run_all(None) == []


class TestEvalCalibrationBlocks:
    def _write(self, tmp_path, monkeypatch, name, spec):
        expected = tmp_path / "evals" / "expected"
        expected.mkdir(parents=True, exist_ok=True)
        (expected / name).write_text(json.dumps(spec), encoding="utf-8")
        monkeypatch.setattr(repo_invariants, "_REPO_ROOT", tmp_path)
        return f"evals/expected/{name}"

    def test_bounded_expectation_without_calibration_is_flagged(self, tmp_path, monkeypatch):
        rel = self._write(
            tmp_path,
            monkeypatch,
            "new-fixture.json",
            {
                "fixture": "new-fixture.ts",
                "agents": {"structure-review": {"issueCount": {"min": 1, "max": 3}}},
            },
        )
        findings = repo_invariants.check_eval_calibration_blocks([rel])
        assert len(findings) == 1
        assert findings[0]["invariant"] == "eval-calibration-block-required"
        assert "structure-review" in findings[0]["message"]

    def test_bounded_expectation_with_calibration_passes(self, tmp_path, monkeypatch):
        rel = self._write(
            tmp_path,
            monkeypatch,
            "new-fixture.json",
            {
                "fixture": "new-fixture.ts",
                "agents": {
                    "structure-review": {
                        "issueCount": {"min": 1, "max": 3},
                        "_calibration": {"source": "measured", "note": "3 runs at HEAD"},
                    }
                },
            },
        )
        assert repo_invariants.check_eval_calibration_blocks([rel]) == []

    def test_severity_bounds_alone_also_require_calibration(self, tmp_path, monkeypatch):
        rel = self._write(
            tmp_path,
            monkeypatch,
            "sev.json",
            {
                "fixture": "sev.ts",
                "agents": {"doc-review": {"severities": {"warning": {"min": 1, "max": 2}}}},
            },
        )
        assert len(repo_invariants.check_eval_calibration_blocks([rel])) == 1

    def test_expectation_without_bounds_needs_no_calibration(self, tmp_path, monkeypatch):
        rel = self._write(
            tmp_path,
            monkeypatch,
            "plain.json",
            {"fixture": "plain.ts", "agents": {"doc-review": {"expectedStatus": "pass"}}},
        )
        assert repo_invariants.check_eval_calibration_blocks([rel]) == []

    def test_unchanged_legacy_fixtures_are_never_flagged(self, tmp_path, monkeypatch):
        """The 'do not retrofit' rule, enforced: a bounded fixture that isn't
        in the changeset produces nothing."""
        self._write(
            tmp_path,
            monkeypatch,
            "legacy.json",
            {"fixture": "legacy.ts", "agents": {"doc-review": {"issueCount": {"min": 1}}}},
        )
        assert repo_invariants.check_eval_calibration_blocks(["src/unrelated.ts"]) == []


class TestMustNotMentionTermsAppearInFixture:
    def _setup(self, tmp_path, monkeypatch, fixture_text, terms):
        (tmp_path / "evals" / "fixtures").mkdir(parents=True, exist_ok=True)
        (tmp_path / "evals" / "expected").mkdir(parents=True, exist_ok=True)
        (tmp_path / "evals" / "fixtures" / "f.ts").write_text(fixture_text, encoding="utf-8")
        (tmp_path / "evals" / "expected" / "f.json").write_text(
            json.dumps(
                {"fixture": "f.ts", "agents": {"doc-review": {"mustNotMention": terms}}}
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(repo_invariants, "_REPO_ROOT", tmp_path)
        return ["evals/expected/f.json"]

    def test_term_absent_from_the_fixture_is_flagged_as_vacuous(self, tmp_path, monkeypatch):
        changed = self._setup(tmp_path, monkeypatch, "const a = 1\n", ["useMemo"])
        findings = repo_invariants.check_must_not_mention_terms_appear_in_fixture(changed)
        assert len(findings) == 1
        assert findings[0]["invariant"] == "must-not-mention-term-absent-from-fixture"

    def test_term_present_in_the_fixture_is_a_meaningful_guard(self, tmp_path, monkeypatch):
        changed = self._setup(tmp_path, monkeypatch, "useMemo(() => 1, [])\n", ["useMemo"])
        assert repo_invariants.check_must_not_mention_terms_appear_in_fixture(changed) == []

    def test_matching_is_case_insensitive(self, tmp_path, monkeypatch):
        changed = self._setup(tmp_path, monkeypatch, "UseMemo()\n", ["usememo"])
        assert repo_invariants.check_must_not_mention_terms_appear_in_fixture(changed) == []

    def test_empty_must_not_mention_produces_nothing(self, tmp_path, monkeypatch):
        changed = self._setup(tmp_path, monkeypatch, "const a = 1\n", [])
        assert repo_invariants.check_must_not_mention_terms_appear_in_fixture(changed) == []


class TestScopeGlobSkipProseDrift:
    def _agent(self, tmp_path, monkeypatch, scope, skip):
        agents = tmp_path / "agents"
        agents.mkdir(parents=True, exist_ok=True)
        (agents / "x-review.md").write_text(
            f"---\nname: x-review\ndescription: d\n---\n\n# X\n\nScope: {scope}\n\n"
            f"## Skip\n\n{skip}\n\n## Detect\n\nstuff\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(repo_invariants, "_PLUGIN_ROOT", tmp_path)
        monkeypatch.setattr(repo_invariants, "_REPO_ROOT", tmp_path)
        return ["agents/x-review.md"]

    def test_the_mjs_cjs_mismatch_class_is_detected(self, tmp_path, monkeypatch):
        """The original #1622 case: Scope routes .mjs/.cjs but the Skip prose
        only names .js/.ts, so the agent self-skips files the resolver sent."""
        changed = self._agent(
            tmp_path, monkeypatch, "**/*.{js,mjs,cjs,ts}", "Skip when no .js or .ts files."
        )
        findings = repo_invariants.check_scope_glob_matches_skip_prose(changed)
        assert len(findings) == 1
        assert ".mjs" in findings[0]["message"]
        assert ".cjs" in findings[0]["message"]

    def test_agreeing_extension_lists_pass(self, tmp_path, monkeypatch):
        changed = self._agent(
            tmp_path,
            monkeypatch,
            "**/*.{js,mjs,cjs,ts}",
            "Skip when no .js, .mjs, .cjs, or .ts files.",
        )
        assert repo_invariants.check_scope_glob_matches_skip_prose(changed) == []

    def test_skip_section_naming_no_extensions_makes_no_claim(self, tmp_path, monkeypatch):
        changed = self._agent(
            tmp_path, monkeypatch, "**/*.{js,ts}", "Skip when the target has no code."
        )
        assert repo_invariants.check_scope_glob_matches_skip_prose(changed) == []

    def test_scope_always_has_no_extension_claim_to_check(self, tmp_path, monkeypatch):
        changed = self._agent(tmp_path, monkeypatch, "always", "Skip when no .md files.")
        assert repo_invariants.check_scope_glob_matches_skip_prose(changed) == []


class TestBacklogSweep:
    def test_sweep_all_surfaces_the_deliberately_unretrofitted_backlog(self):
        """--all is the triage escape hatch. It must find the pre-existing
        findings the pre-pass deliberately stays silent about — otherwise the
        checks would be unverifiable against the real corpus."""
        findings = repo_invariants._sweep_all()
        kinds = {f["invariant"] for f in findings}
        assert "scope-glob-skip-prose-extension-drift" in kinds
        assert "must-not-mention-term-absent-from-fixture" in kinds

    def test_js_fp_review_is_the_known_mjs_cjs_case(self):
        drift = [
            f
            for f in repo_invariants._sweep_all()
            if f["invariant"] == "scope-glob-skip-prose-extension-drift"
        ]
        assert any("js-fp-review" in f["file"] for f in drift)
