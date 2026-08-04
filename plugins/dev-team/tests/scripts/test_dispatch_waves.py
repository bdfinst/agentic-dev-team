"""Unit tests for skills/code-review/scripts/dispatch_waves.py (#1752).

Covers the deterministic wave-chunking gate: an eligible agent roster splits
into ordered waves of at most `max_parallel` agents each, so a single
`/code-review` message never dispatches more concurrent `Agent` calls than
the harness has shown it can reliably fulfill. Fail-safe on both the env
override and an explicit `--max-parallel`: unset, empty, oversized,
non-integer, or non-positive values all fall back to the default rather than
silently collapsing concurrency to something unintended — via one shared
resolution rule (`resolve_max_parallel`'s `override` parameter), not two
independently-maintained fallbacks.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_SCRIPTS_DIR = _REPO_ROOT / "plugins" / "dev-team" / "skills" / "code-review" / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

import dispatch_waves

_SCRIPT_PATH = _SCRIPTS_DIR / "dispatch_waves.py"


class TestResolveMaxParallel:
    def test_unset_env_defaults_to_ten(self):
        assert dispatch_waves.resolve_max_parallel({}) == 10

    def test_valid_override_is_honored(self):
        assert dispatch_waves.resolve_max_parallel({dispatch_waves.MAX_PARALLEL_ENV_VAR: "4"}) == 4

    def test_empty_string_falls_back_to_default(self):
        assert dispatch_waves.resolve_max_parallel({dispatch_waves.MAX_PARALLEL_ENV_VAR: ""}) == 10

    def test_non_numeric_falls_back_to_default(self):
        assert dispatch_waves.resolve_max_parallel({dispatch_waves.MAX_PARALLEL_ENV_VAR: "abc"}) == 10

    def test_non_ascii_digit_falls_back_to_default(self):
        # Full-width '5' (U+FF15) passes a bare isdigit() but must not reach
        # int() as if it were ASCII "5" — assert the premise itself so this
        # test fails loudly, not silently, if that library behavior changes.
        assert "５".isdigit() and not "５".isascii()
        assert dispatch_waves.resolve_max_parallel({dispatch_waves.MAX_PARALLEL_ENV_VAR: "５"}) == 10

    def test_surrounding_whitespace_is_tolerated(self):
        assert dispatch_waves.resolve_max_parallel({dispatch_waves.MAX_PARALLEL_ENV_VAR: " 4 "}) == 4

    def test_zero_falls_back_to_default(self):
        assert dispatch_waves.resolve_max_parallel({dispatch_waves.MAX_PARALLEL_ENV_VAR: "0"}) == 10

    def test_negative_falls_back_to_default(self):
        assert dispatch_waves.resolve_max_parallel({dispatch_waves.MAX_PARALLEL_ENV_VAR: "-2"}) == 10

    def test_oversized_digit_string_falls_back_to_default(self):
        # Guards CPython's int-string conversion limit (default 4300 digits
        # on 3.11+, CVE-2020-10735) — must fall back, never raise.
        huge = "9" * 5000
        assert dispatch_waves.resolve_max_parallel({dispatch_waves.MAX_PARALLEL_ENV_VAR: huge}) == 10

    def test_default_reads_from_os_environ_when_no_dict_given(self, monkeypatch):
        monkeypatch.setenv(dispatch_waves.MAX_PARALLEL_ENV_VAR, "3")
        assert dispatch_waves.resolve_max_parallel() == 3

    def test_valid_override_param_wins_over_env(self):
        env = {dispatch_waves.MAX_PARALLEL_ENV_VAR: "4"}
        assert dispatch_waves.resolve_max_parallel(env, override=7) == 7

    def test_non_positive_override_falls_back_to_default(self):
        assert dispatch_waves.resolve_max_parallel({}, override=0) == 10
        assert dispatch_waves.resolve_max_parallel({}, override=-3) == 10

    def test_bool_override_falls_back_to_default(self):
        # bool is a subclass of int — True must not slip through as 1.
        assert dispatch_waves.resolve_max_parallel({}, override=True) == 10

    def test_invalid_override_does_not_fall_through_to_env(self):
        # An explicit (even malformed) override always wins over env — it is
        # never treated as absent just because it failed validation.
        env = {dispatch_waves.MAX_PARALLEL_ENV_VAR: "4"}
        assert dispatch_waves.resolve_max_parallel(env, override=0) == 10


class TestFormDispatchWaves:
    def test_empty_roster_yields_no_waves(self):
        assert dispatch_waves.form_dispatch_waves([], 10) == []

    def test_roster_under_max_is_a_single_wave(self):
        agents = ["a", "b", "c"]
        assert dispatch_waves.form_dispatch_waves(agents, 10) == [["a", "b", "c"]]

    def test_roster_exactly_at_max_is_a_single_wave(self):
        agents = [str(i) for i in range(10)]
        assert dispatch_waves.form_dispatch_waves(agents, 10) == [agents]

    def test_sixteen_agents_at_max_ten_splits_ten_and_six(self):
        # The exact shape of the incident that opened #1752.
        agents = [f"agent-{i}" for i in range(16)]
        waves = dispatch_waves.form_dispatch_waves(agents, 10)
        assert [len(w) for w in waves] == [10, 6]
        assert waves[0] + waves[1] == agents

    def test_order_is_preserved_within_and_across_waves(self):
        agents = ["z", "a", "m"]
        waves = dispatch_waves.form_dispatch_waves(agents, 1)
        assert waves == [["z"], ["a"], ["m"]]

    def test_non_positive_max_parallel_raises(self):
        with pytest.raises(ValueError):
            dispatch_waves.form_dispatch_waves(["a"], 0)

    def test_bool_max_parallel_raises(self):
        # bool is a subclass of int in Python — guard against a stray True/False.
        with pytest.raises(ValueError):
            dispatch_waves.form_dispatch_waves(["a"], True)


class TestCli:
    def test_cli_prints_waves_as_json(self):
        agents = ",".join(f"agent-{i}" for i in range(16))
        result = subprocess.run(
            [sys.executable, str(_SCRIPT_PATH), "--agents", agents, "--max-parallel", "10"],
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(result.stdout)
        assert payload["maxParallel"] == 10
        assert [len(w) for w in payload["waves"]] == [10, 6]

    def test_cli_strips_whitespace_around_agent_names(self):
        result = subprocess.run(
            [sys.executable, str(_SCRIPT_PATH), "--agents", "a, b , c", "--max-parallel", "10"],
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(result.stdout)
        assert payload["waves"] == [["a", "b", "c"]]

    def test_cli_defaults_max_parallel_from_env(self):
        result = subprocess.run(
            [sys.executable, str(_SCRIPT_PATH), "--agents", "a,b,c,d,e,f"],
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, dispatch_waves.MAX_PARALLEL_ENV_VAR: "5"},
        )
        payload = json.loads(result.stdout)
        assert payload["maxParallel"] == 5
        assert [len(w) for w in payload["waves"]] == [5, 1]

    def test_cli_invalid_explicit_max_parallel_falls_back_to_default(self):
        # The CLI's own --max-parallel path must route through the same
        # resolution rule as the env path, not a second ad hoc clamp.
        result = subprocess.run(
            [sys.executable, str(_SCRIPT_PATH), "--agents", "a,b,c", "--max-parallel", "0"],
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(result.stdout)
        assert payload["maxParallel"] == 10
