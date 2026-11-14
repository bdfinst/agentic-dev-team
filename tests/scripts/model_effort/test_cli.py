"""The CLI's argument handling, default dependencies and pre-run refusals (scripts/model_effort_ab.py)."""

from __future__ import annotations

import io
import re
import shutil
import subprocess
import sys
from types import SimpleNamespace

import model_effort_ab
import pytest
from ab_constants import SCOUT_HAIKU_ARGS
from ab_inputs import make_file_fixture, write_agent_file, write_expected
from ab_stub_claude import StubClaude
from ab_world import assert_nothing_ran, cli, passing_stub
from model_effort import external, paths, runner


class TestReadGitHeadSha:
    @pytest.mark.parametrize(
        "error",
        [OSError("git missing"), subprocess.CalledProcessError(128, "git")],
        ids=["git-not-installed", "not-a-repository"],
    )
    def test_a_failing_git_yields_none(self, monkeypatch, error):
        def failing_run(*_args, **_kwargs):
            raise error

        monkeypatch.setattr(model_effort_ab.subprocess, "run", failing_run)

        assert model_effort_ab._read_git_head_sha() is None

    @pytest.mark.skipif(
        shutil.which("git") is None or not (paths.REPO_ROOT / ".git").exists(),
        reason="needs git and a checkout with a .git entry",
    )
    def test_the_real_repository_yields_a_full_commit_hash(self):
        sha = model_effort_ab._read_git_head_sha()

        assert sha is not None and re.fullmatch(r"[0-9a-f]{40}", sha)


class TestEntryPoint:
    def test_the_script_runs_in_isolated_mode_from_another_directory(self, tmp_path):
        script = paths.REPO_ROOT / "scripts" / "model_effort_ab.py"

        completed = subprocess.run(
            [sys.executable, "-I", str(script), "--help"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )

        assert completed.returncode == 0, completed.stderr
        assert "usage:" in completed.stdout


class TestDepsDefaults:
    def test_default_deps_use_the_shipped_directories_and_collaborators(self):
        deps = model_effort_ab.Deps()

        assert deps.eval_paths == paths.EvalPaths.default()
        assert deps.run_trial is runner.run_trial
        assert deps.read_git_sha is model_effort_ab._read_git_head_sha

    def test_default_stdin_is_the_process_stdin(self, monkeypatch):
        stream = io.StringIO()
        monkeypatch.setattr(sys, "stdin", stream)

        assert model_effort_ab.Deps().stdin is stream

    @pytest.mark.parametrize("is_tty", [True, False])
    def test_default_tty_check_follows_the_process_stdin(self, monkeypatch, is_tty):
        monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: is_tty))

        assert model_effort_ab.Deps().stdin_is_tty() is is_tty

    def test_default_clock_reads_a_timezone_aware_time(self):
        assert model_effort_ab.Deps().clock().tzinfo is not None

    def test_each_default_deps_has_its_own_random_generator(self):
        assert model_effort_ab.Deps().rng is not model_effort_ab.Deps().rng

    def test_default_pricing_table_is_the_shipped_one(self):
        assert model_effort_ab.Deps().pricing_table == external.pricing().load_pricing(
            paths.PRICING_PATH
        )


class TestPreRunRefusals:
    def test_existing_artifact_path_exits_2_before_any_trial_and_stays_unchanged(
        self, world
    ):
        stub = StubClaude(world.stub_dir)
        world.artifact_path.write_text("sentinel", encoding="utf-8")

        code = cli(world, stub, *SCOUT_HAIKU_ARGS)

        assert code == 2
        assert stub.calls == []
        assert world.artifact_path.read_text(encoding="utf-8") == "sentinel"

    def test_collision_message_says_what_is_wrong_and_how_to_fix_it(
        self, world, capsys
    ):
        stub = StubClaude(world.stub_dir)
        world.artifact_path.write_text("x", encoding="utf-8")

        cli(world, stub, *SCOUT_HAIKU_ARGS)

        stderr = capsys.readouterr().err
        assert "already exists" in stderr and "rerun" in stderr

    def test_unknown_agent_exits_2_listing_valid_agents_and_writes_nothing(
        self, world, capsys
    ):
        stub = StubClaude(world.stub_dir)

        code = cli(world, stub, "no-such-agent")

        stderr = capsys.readouterr().err
        assert code == 2
        assert "no-such-agent" in stderr
        assert "scout" in stderr and "lonely" in stderr
        assert_nothing_ran(stub, world)

    def test_unknown_fixture_exits_2_naming_it_and_listing_valid_stems(
        self, world, capsys
    ):
        stub = StubClaude(world.stub_dir)

        code = cli(world, stub, "scout", "--fixtures", "clean-form,nope")

        stderr = capsys.readouterr().err
        assert code == 2
        assert "nope" in stderr
        assert "clean-form" in stderr and "layered-svc" in stderr
        assert_nothing_ran(stub, world)

    def test_a_fixtures_list_with_no_stems_exits_2_and_runs_nothing(
        self, world, capsys
    ):
        stub = StubClaude(world.stub_dir)

        code = cli(world, stub, "scout", "--fixtures", ",")

        assert code == 2
        assert "named no stems" in capsys.readouterr().err
        assert_nothing_ran(stub, world)

    def test_fixture_whose_expected_entry_names_another_agent_exits_2(
        self, world, capsys
    ):
        stub = StubClaude(world.stub_dir)

        code = cli(world, stub, "scout", "--fixtures", "other-only")

        assert code == 2
        assert "other-only" in capsys.readouterr().err
        assert_nothing_ran(stub, world)

    def test_agent_with_no_expected_entries_exits_2_stating_no_fixtures_found(
        self, world, capsys
    ):
        stub = StubClaude(world.stub_dir)

        code = cli(world, stub, "lonely")

        assert code == 2
        assert "no fixtures were found" in capsys.readouterr().err
        assert_nothing_ran(stub, world)

    def test_write_capable_agent_exits_2_before_any_trial(self, world, capsys):
        stub = StubClaude(world.stub_dir)

        code = cli(world, stub, "write-capable")

        err = capsys.readouterr().err
        assert code == 2
        assert "marks it `sandbox: true`" in err
        assert (
            "Choose an agent whose tools are limited to Read, Grep and Glob, "
            "or mark it `sandbox: true` in evals/model-effort/graders.json."
        ) in err
        assert_nothing_ran(stub, world)

    def test_missing_runs_directory_exits_2_before_any_trial(self, world, capsys):
        stub = StubClaude(world.stub_dir)
        world.runs_dir.rmdir()

        code = cli(world, stub, *SCOUT_HAIKU_ARGS)

        assert code == 2
        assert "runs directory" in capsys.readouterr().err
        assert stub.calls == []

    def test_malformed_expected_json_exits_2_naming_the_file(self, world, capsys):
        stub = StubClaude(world.stub_dir)
        broken = world.expected_dir / "broken.json"
        broken.write_text("{not json", encoding="utf-8")

        code = cli(world, stub, "scout")

        assert code == 2
        assert str(broken) in capsys.readouterr().err
        assert_nothing_ran(stub, world)

    def test_misspelled_candidate_effort_exits_2_before_any_trial(self, world, capsys):
        stub = StubClaude(world.stub_dir)

        code = cli(world, stub, "scout", "--effort", "hgih")

        stderr = capsys.readouterr().err
        assert code == 2
        assert "hgih" in stderr and "high" in stderr
        assert_nothing_ran(stub, world)

    def test_candidate_model_with_path_characters_exits_2_before_any_trial(
        self, world, capsys
    ):
        stub = StubClaude(world.stub_dir)

        code = cli(world, stub, "scout", "--model", "../../etc")

        assert code == 2
        assert "--model" in capsys.readouterr().err
        assert_nothing_ran(stub, world)


class TestInvalidArgumentsAreRefusedBeforeTheEstimate:
    def _assert_refused(self, world, stub, capsys, code, fix_hint):
        err = capsys.readouterr().err
        assert code == 2
        assert fix_hint in err
        assert "Estimate" not in err
        assert_nothing_ran(stub, world)

    @pytest.mark.parametrize("trials", ["0", "-1", "abc", "2.5"])
    def test_non_positive_or_non_integer_trials_name_the_fix(
        self, world, capsys, trials
    ):
        stub = StubClaude(world.stub_dir)

        with pytest.raises(SystemExit) as excinfo:
            cli(world, stub, *SCOUT_HAIKU_ARGS, "--trials", trials)

        self._assert_refused(
            world, stub, capsys, excinfo.value.code, "a whole number of 1 or more"
        )

    @pytest.mark.parametrize(
        "write_agent",
        [
            pytest.param(
                lambda agents_dir: write_agent_file(
                    agents_dir, "odd", "Read", model="sonnet"
                ),
                id="no-effort",
            ),
            pytest.param(
                lambda agents_dir: (agents_dir / "odd.md").write_text(
                    "No frontmatter here.\n", encoding="utf-8"
                ),
                id="no-frontmatter",
            ),
        ],
    )
    def test_an_agent_file_without_usable_frontmatter_is_refused_naming_the_fix(
        self, world, capsys, write_agent
    ):
        write_agent(world.deps.eval_paths.agents_dir)
        stub = StubClaude(world.stub_dir)

        code = cli(world, stub, "odd", "--model", "haiku", "--effort", "low")

        self._assert_refused(
            world,
            stub,
            capsys,
            code,
            "Fix the agent file's frontmatter; the baseline arm needs `model:` and `effort:`.",
        )

    @pytest.mark.parametrize("seconds", ["0", "-1", "abc", "1.5"])
    def test_non_positive_or_non_integer_trial_timeout_names_the_fix(
        self, world, capsys, seconds
    ):
        stub = StubClaude(world.stub_dir)

        with pytest.raises(SystemExit) as excinfo:
            cli(world, stub, *SCOUT_HAIKU_ARGS, "--trial-timeout", seconds)

        self._assert_refused(
            world, stub, capsys, excinfo.value.code, "a whole number of 1 or more"
        )

    @pytest.mark.parametrize(
        "overrides",
        [
            [],
            ["--model", "sonnet", "--effort", "high"],
            ["--model", "sonnet"],
            ["--effort", "high"],
        ],
        ids=["no-overrides", "both-equal", "model-only-equal", "effort-only-equal"],
    )
    def test_candidate_equal_to_frontmatter_names_the_fix(
        self, world, capsys, overrides
    ):
        stub = StubClaude(world.stub_dir)

        code = cli(world, stub, "scout", *overrides)

        self._assert_refused(
            world, stub, capsys, code, "pass a different --model or --effort"
        )

    @pytest.mark.parametrize(
        ("model", "effort", "named_key", "bad_value"),
        [
            ("../evil", "high", "model", "../evil"),
            ("sonnet", "hgih", "effort", "hgih"),
        ],
        ids=["model", "effort"],
    )
    def test_malformed_frontmatter_value_is_refused_naming_the_key_and_value(
        self, world, capsys, model, effort, named_key, bad_value
    ):
        write_agent_file(
            world.deps.eval_paths.agents_dir, "odd", "Read", model=model, effort=effort
        )
        write_expected(world.expected_dir, "odd-case", "odd", "pass")
        make_file_fixture(world.deps.eval_paths.fixtures_dir, "odd-case.txt")
        stub = StubClaude(world.stub_dir)

        code = cli(world, stub, "odd", "--model", "haiku", "--effort", "low")

        err = capsys.readouterr().err
        assert code == 2
        assert f"frontmatter `{named_key}:`" in err
        assert repr(bad_value) in err
        assert "Estimate" not in err
        assert_nothing_ran(stub, world)

    def test_a_partial_override_that_changes_one_value_is_accepted(self, world):
        stub = passing_stub(world)

        code = cli(world, stub, "scout", "--effort", "low", "--trials", "1")

        assert code == 0
