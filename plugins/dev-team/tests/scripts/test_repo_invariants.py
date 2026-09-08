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


class TestSkillScriptsDocumented:
    """#1981: the check that created this module covered one skill. A second
    report of the same class — `review_value_coverage.py` landing in
    `skills/code-review/scripts/` undocumented — made it a registry rather
    than a copied function."""

    def test_every_registered_skill_is_clean_in_the_real_repo(self):
        """Corpus-wide, not changeset-scoped: an undocumented script is a
        standing gap whether or not this changeset touched it."""
        assert repo_invariants.check_skill_scripts_documented() == []

    def test_code_review_scripts_are_covered_not_just_mutation_testing(self):
        """The regression this slice exists for. If the registry silently
        loses the code-review entry, the class it was added for goes
        undetected again and this test is the only thing that notices."""
        skills = [entry[0] for entry in repo_invariants._DOCUMENTED_SCRIPT_SKILLS]
        assert "code-review" in skills
        assert "mutation-testing" in skills

    def test_each_skill_keeps_its_own_invariant_id(self):
        """Findings are keyed by invariant id downstream. Collapsing two
        skills onto one id would make a code-review gap indistinguishable
        from a mutation-testing one in any report that groups by it."""
        ids = {entry[2] for entry in repo_invariants._DOCUMENTED_SCRIPT_SKILLS}
        assert ids == {"mutation-kill-scripts-documented", "code-review-scripts-documented"}


class TestMutationKillScriptsDocumented:
    def test_real_repo_has_no_undocumented_mutation_kill_scripts(self):
        # Every script currently shipped under skills/mutation-testing/scripts/
        # is named somewhere in that skill's own docs. A finding here means a
        # newly-added script module was never documented.
        findings = repo_invariants.check_skill_scripts_documented()
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

        findings = repo_invariants.check_skill_scripts_documented()

        assert len(findings) == 1
        finding = findings[0]
        assert finding["invariant"] == "mutation-kill-scripts-documented"
        assert finding["file"].endswith("new_undocumented_module.py")
        assert "new_undocumented_module.py" in finding["message"]

    def test_no_scripts_dir_yields_no_findings(self, tmp_path, monkeypatch):
        monkeypatch.setattr(repo_invariants, "_PLUGIN_ROOT", tmp_path / "empty")
        assert repo_invariants.check_skill_scripts_documented() == []

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

        findings = repo_invariants.check_skill_scripts_documented()

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

        assert repo_invariants.check_skill_scripts_documented() == []


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
        # check_scope_glob_matches_skip_prose resolves its agents dir via the
        # shared registry helper (#1904 item 3), not `_PLUGIN_ROOT` directly —
        # patch it too so the fixture agent this helper wrote is what gets globbed.
        monkeypatch.setattr(repo_invariants, "default_agents_dir", lambda: agents)
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
    """`--all` is the triage escape hatch: it runs the changeset-scoped checks
    across the whole corpus so a maintainer can see the pre-existing findings
    each convention chose not to retrofit.

    These tests deliberately assert **shape, not census**. An earlier draft
    pinned `js-fp-review` as the known `.mjs`/`.cjs` drift case; PR #1632 then
    fixed it upstream and the test went red for a good outcome. A backlog test
    that fails when the backlog shrinks is measuring the wrong thing — the
    detector's correctness is pinned by the synthetic fixtures above, which
    cannot be invalidated by someone fixing the corpus.
    """

    def test_sweep_all_runs_against_the_real_corpus_without_error(self):
        findings = repo_invariants._sweep_all()
        assert isinstance(findings, list)

    def test_every_sweep_finding_is_well_formed(self):
        for finding in repo_invariants._sweep_all():
            assert set(finding) == {"invariant", "file", "message"}
            assert finding["invariant"] in {
                "mutation-kill-scripts-documented",
                "eval-calibration-block-required",
                "must-not-mention-term-absent-from-fixture",
                "scope-glob-skip-prose-extension-drift",
            }
            assert finding["file"] and finding["message"]

    def test_sweep_finds_strictly_more_than_the_silent_pre_pass(self):
        """The whole point of the flag: the pre-pass stays silent on legacy
        findings, `--all` surfaces them. If these ever agreed, the scoping
        would be doing nothing."""
        assert len(repo_invariants._sweep_all()) > len(repo_invariants.run_all(None))


class TestContractFailureShapesDocumented:
    """#1998: two independent review agents (doc-review, domain-review)
    rediscovered the same drift — SKILL.md's prose enumeration of loggable
    `contract-failures.jsonl` shapes disagreeing with the module's actual
    behavior. This check pins `telemetry-schema.md`'s table row to
    `validate_review_output.FAILURE_SHAPES` instead."""

    def test_clean_against_the_real_repo(self):
        assert repo_invariants.check_contract_failure_shapes_documented(None) == []

    def test_flags_a_mismatched_table_row(self, tmp_path, monkeypatch):
        plugin_root = tmp_path / "plugin"
        knowledge = plugin_root / "knowledge"
        knowledge.mkdir(parents=True)
        (knowledge / "telemetry-schema.md").write_text(
            "| `shape` | string enum | `empty` \\| `truncated` \\| `not-json` — stale text |\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(repo_invariants, "_PLUGIN_ROOT", plugin_root)

        findings = repo_invariants.check_contract_failure_shapes_documented(None)

        assert len(findings) == 1
        assert findings[0]["invariant"] == "contract-failure-shapes-documented"
        assert "malformed-json" in findings[0]["message"]

    def test_flags_a_missing_table_row(self, tmp_path, monkeypatch):
        plugin_root = tmp_path / "plugin"
        knowledge = plugin_root / "knowledge"
        knowledge.mkdir(parents=True)
        (knowledge / "telemetry-schema.md").write_text("no such row here\n", encoding="utf-8")
        monkeypatch.setattr(repo_invariants, "_PLUGIN_ROOT", plugin_root)

        findings = repo_invariants.check_contract_failure_shapes_documented(None)

        assert len(findings) == 1
        assert findings[0]["invariant"] == "contract-failure-shapes-documented"


class TestTranscriptParsingConfinedToSessionLog:
    """#2048: ADR 0036 records that both structure-review and arch-review
    independently raised the same duplication while reviewing #1991 -- the
    second report this repo's ratchet rule converts into a check. Without
    it, nothing stops a third independent transcript parser from growing
    back once the two the epic unified are gone."""

    def test_clean_against_the_real_repo(self):
        """The real repo, as of #2048, has no undocumented (unallowlisted)
        transcript parser outside session_log/. A finding here means either
        a real third implementation appeared, or a legitimate new
        usage-dict consumer needs an allowlist entry with a reason."""
        assert repo_invariants.check_transcript_parsing_confined_to_session_log() == []

    def test_flags_a_new_transcript_parser_outside_session_log(self, tmp_path, monkeypatch):
        """Proves the check can actually fail (CLAUDE.md: 'make it fail on
        purpose once before you trust it') -- a throwaway module parsing
        isSidechain/attributionAgent outside session_log/, not on the
        allowlist, must be flagged."""
        repo_root = tmp_path / "repo"
        scripts_dir = repo_root / "plugins" / "dev-team" / "scripts"
        scripts_dir.mkdir(parents=True)
        rogue = scripts_dir / "rogue_parser.py"
        rogue.write_text(
            'def parse(rec):\n    return rec.get("isSidechain"), rec.get("attributionAgent")\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(repo_invariants, "_REPO_ROOT", repo_root)

        findings = repo_invariants.check_transcript_parsing_confined_to_session_log()

        assert len(findings) == 1
        assert findings[0]["invariant"] == "transcript-parsing-confined-to-session-log"
        assert findings[0]["file"] == "plugins/dev-team/scripts/rogue_parser.py"

    def test_ignores_a_matching_file_inside_session_log(self, tmp_path, monkeypatch):
        repo_root = tmp_path / "repo"
        session_log_dir = (
            repo_root / "plugins" / "dev-team" / "scripts" / "lib" / "session_log"
        )
        session_log_dir.mkdir(parents=True)
        (session_log_dir / "records.py").write_text(
            'def usage_of(rec):\n    return rec.get("isSidechain")\n', encoding="utf-8"
        )
        monkeypatch.setattr(repo_invariants, "_REPO_ROOT", repo_root)

        assert repo_invariants.check_transcript_parsing_confined_to_session_log() == []

    def test_ignores_test_files(self, tmp_path, monkeypatch):
        repo_root = tmp_path / "repo"
        tests_dir = repo_root / "plugins" / "dev-team" / "tests" / "scripts"
        tests_dir.mkdir(parents=True)
        (tests_dir / "test_something.py").write_text(
            'USAGE = {"cache_creation_input_tokens": 1, "isSidechain": True}\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(repo_invariants, "_REPO_ROOT", repo_root)

        assert repo_invariants.check_transcript_parsing_confined_to_session_log() == []

    def test_allowlist_entries_all_carry_a_real_reason(self):
        empty = [
            path
            for path, reason in repo_invariants._TRANSCRIPT_PARSING_ALLOWLIST.items()
            if not reason.strip()
        ]
        assert not empty, f"_TRANSCRIPT_PARSING_ALLOWLIST entries with no reason: {empty}"

    def test_allowlist_is_ignored_regardless_of_changed_files(self):
        """Corpus-wide by design, like check_skill_scripts_documented: a
        stray transcript parser is a standing gap whether or not this
        changeset touched it."""
        assert (
            repo_invariants.check_transcript_parsing_confined_to_session_log(["some/file.py"])
            == repo_invariants.check_transcript_parsing_confined_to_session_log(None)
        )


class TestNormativeContentSingleSourced:
    """#2126: "cite, don't restate" for internal-collaborator-doubling.md
    (#2124) needs a mechanism, not just review discipline -- a check that
    can fail on a verbatim restatement outside its home file."""

    def _make_tree(self, tmp_path):
        repo_root = tmp_path / "repo"
        plugin_root = repo_root / "plugins" / "dev-team"
        home = plugin_root / "knowledge" / "internal-collaborator-doubling.md"
        home.parent.mkdir(parents=True)
        home.write_text(
            "Out-of-process handle\nProhibitive real cost\n"
            "the project's own first-party source stays real\n"
            '"It\'s an injected interface" — and the type\'s name\n',
            encoding="utf-8",
        )
        return repo_root, plugin_root

    def test_clean_against_the_real_repo(self):
        """The real repo, as of #2124/#2125, has no file restating the
        rule's content outside its home file."""
        assert repo_invariants.check_normative_content_single_sourced() == []

    def test_flags_a_new_file_restating_a_blocker_row(self, tmp_path, monkeypatch):
        """Proves the check can fail (CLAUDE.md: 'make a new gate fail on
        purpose once before trusting it')."""
        repo_root, plugin_root = self._make_tree(tmp_path)
        offender = plugin_root / "knowledge" / "some-other-file.md"
        offender.write_text(
            "Doubling is fine except for Out-of-process handle cases.\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(repo_invariants, "_REPO_ROOT", repo_root)
        monkeypatch.setattr(repo_invariants, "_PLUGIN_ROOT", plugin_root)

        findings = repo_invariants.check_normative_content_single_sourced()

        assert len(findings) == 1
        assert findings[0]["invariant"] == "normative-content-single-sourced"
        assert findings[0]["file"] == "plugins/dev-team/knowledge/some-other-file.md"

    def test_flags_two_distinct_fragments_as_two_findings(self, tmp_path, monkeypatch):
        repo_root, plugin_root = self._make_tree(tmp_path)
        offender = plugin_root / "agents" / "some-agent.md"
        offender.parent.mkdir(parents=True)
        offender.write_text(
            "See Prohibitive real cost and Out-of-process handle cases.\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(repo_invariants, "_REPO_ROOT", repo_root)
        monkeypatch.setattr(repo_invariants, "_PLUGIN_ROOT", plugin_root)

        findings = repo_invariants.check_normative_content_single_sourced()

        assert len(findings) == 2
        assert any("Prohibitive real cost" in f["message"] for f in findings)
        assert any("Out-of-process handle" in f["message"] for f in findings)

    def test_ignores_the_home_file_itself(self, tmp_path, monkeypatch):
        repo_root, plugin_root = self._make_tree(tmp_path)
        monkeypatch.setattr(repo_invariants, "_REPO_ROOT", repo_root)
        monkeypatch.setattr(repo_invariants, "_PLUGIN_ROOT", plugin_root)

        assert repo_invariants.check_normative_content_single_sourced() == []

    def test_ignores_a_bare_citation(self, tmp_path, monkeypatch):
        repo_root, plugin_root = self._make_tree(tmp_path)
        citing = plugin_root / "knowledge" / "test-pyramid.md"
        citing.write_text(
            "See internal-collaborator-doubling.md for the full rule.\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(repo_invariants, "_REPO_ROOT", repo_root)
        monkeypatch.setattr(repo_invariants, "_PLUGIN_ROOT", plugin_root)

        assert repo_invariants.check_normative_content_single_sourced() == []

    def test_flags_an_attributed_verbatim_quote_anyway(self, tmp_path, monkeypatch):
        """Attribution doesn't exempt a match -- the point is preventing a
        second copy that can drift, not policing citation etiquette."""
        repo_root, plugin_root = self._make_tree(tmp_path)
        citing = plugin_root / "knowledge" / "test-pyramid.md"
        citing.write_text(
            "Per internal-collaborator-doubling.md, \"Out-of-process handle\" is a blocker.\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(repo_invariants, "_REPO_ROOT", repo_root)
        monkeypatch.setattr(repo_invariants, "_PLUGIN_ROOT", plugin_root)

        findings = repo_invariants.check_normative_content_single_sourced()

        assert len(findings) == 1

    def test_ignores_files_outside_the_three_scan_roots(self, tmp_path, monkeypatch):
        repo_root, plugin_root = self._make_tree(tmp_path)
        outside = plugin_root / "docs" / "some-doc.md"
        outside.parent.mkdir(parents=True)
        outside.write_text("Out-of-process handle\n", encoding="utf-8")
        monkeypatch.setattr(repo_invariants, "_REPO_ROOT", repo_root)
        monkeypatch.setattr(repo_invariants, "_PLUGIN_ROOT", plugin_root)

        assert repo_invariants.check_normative_content_single_sourced() == []

    def test_corpus_wide_regardless_of_changed_files(self):
        assert (
            repo_invariants.check_normative_content_single_sourced(["some/file.py"])
            == repo_invariants.check_normative_content_single_sourced(None)
        )

    def test_ignores_non_markdown_files(self, tmp_path, monkeypatch):
        repo_root, plugin_root = self._make_tree(tmp_path)
        non_md = plugin_root / "knowledge" / "some-script.py"
        non_md.write_text("# Out-of-process handle\n", encoding="utf-8")
        monkeypatch.setattr(repo_invariants, "_REPO_ROOT", repo_root)
        monkeypatch.setattr(repo_invariants, "_PLUGIN_ROOT", plugin_root)

        assert repo_invariants.check_normative_content_single_sourced() == []

    def test_handles_an_empty_file_without_error(self, tmp_path, monkeypatch):
        repo_root, plugin_root = self._make_tree(tmp_path)
        empty = plugin_root / "knowledge" / "empty.md"
        empty.write_text("", encoding="utf-8")
        monkeypatch.setattr(repo_invariants, "_REPO_ROOT", repo_root)
        monkeypatch.setattr(repo_invariants, "_PLUGIN_ROOT", plugin_root)

        assert repo_invariants.check_normative_content_single_sourced() == []

    def test_every_fragment_is_still_present_in_the_home_file(self):
        """Design-review staleness guard: if the home file is reworded and a
        fragment silently stops matching, this test fails loudly instead of
        the fragment becoming a permanent no-op."""
        home = (
            _REPO_ROOT
            / "plugins"
            / "dev-team"
            / "knowledge"
            / "internal-collaborator-doubling.md"
        )
        text = home.read_text(encoding="utf-8")
        stale = [f for f in repo_invariants._NORMATIVE_CONTENT_FRAGMENTS if f not in text]
        assert not stale, f"Fragment(s) no longer found in the home file: {stale}"


class TestChurnReportWindowKeySafeAccess:
    """#2108: the same report["window"] bare-index bug recurred twice across
    two structurally-parallel renderers (#2085 review round 2, then round
    3) -- the ratchet rule's textbook "reported twice" trigger."""

    def test_clean_against_the_real_repo(self):
        """The real repo, post-#2085, already fixed both occurrences. A
        finding here means a regression back to a bare index."""
        assert repo_invariants.check_churn_report_window_key_safe_access() == []

    def test_flags_a_bare_index_regression(self, tmp_path, monkeypatch):
        """Proves the check can actually fail (CLAUDE.md: 'make it fail on
        purpose once before you trust it')."""
        repo_root = tmp_path / "repo"
        (repo_root / "scripts" / "lib").mkdir(parents=True)
        (repo_root / "scripts" / "lib" / "churn_recurrence.py").write_text(
            'def render_text(report, top):\n'
            '    window = report["window"]\n'
            '    return window\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(repo_invariants, "_REPO_ROOT", repo_root)

        findings = repo_invariants.check_churn_report_window_key_safe_access()

        assert len(findings) == 1
        assert findings[0]["invariant"] == "churn-report-window-key-safe-access"
        assert findings[0]["file"] == "scripts/lib/churn_recurrence.py"

    def test_ignores_the_assignment_site(self, tmp_path, monkeypatch):
        """report["window"] = ... (the CLI caller's own injection site) is a
        write, not the read bug this check targets."""
        repo_root = tmp_path / "repo"
        (repo_root / "scripts").mkdir(parents=True)
        (repo_root / "scripts" / "churn_coupling_report.py").write_text(
            'report["window"] = f"{args.since} days"\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(repo_invariants, "_REPO_ROOT", repo_root)

        assert repo_invariants.check_churn_report_window_key_safe_access() == []

    def test_ignores_an_already_safe_get_access(self, tmp_path, monkeypatch):
        repo_root = tmp_path / "repo"
        (repo_root / "scripts" / "lib").mkdir(parents=True)
        (repo_root / "scripts" / "lib" / "churn_recurrence.py").write_text(
            'def render_text(report, top):\n'
            '    window = report.get("window", "unknown")\n'
            '    return window\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(repo_invariants, "_REPO_ROOT", repo_root)

        assert repo_invariants.check_churn_report_window_key_safe_access() == []

    def test_ignores_files_outside_the_two_named_paths(self, tmp_path, monkeypatch):
        repo_root = tmp_path / "repo"
        (repo_root / "scripts").mkdir(parents=True)
        (repo_root / "scripts" / "unrelated.py").write_text(
            'window = report["window"]\n', encoding="utf-8"
        )
        monkeypatch.setattr(repo_invariants, "_REPO_ROOT", repo_root)

        assert repo_invariants.check_churn_report_window_key_safe_access() == []

    def test_corpus_wide_regardless_of_changed_files(self):
        """Corpus-wide by design: a regression on either file is a standing
        gap whether or not this changeset touched it."""
        assert (
            repo_invariants.check_churn_report_window_key_safe_access(["some/file.py"])
            == repo_invariants.check_churn_report_window_key_safe_access(None)
        )
