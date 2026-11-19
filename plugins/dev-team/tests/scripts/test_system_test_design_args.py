"""Unit tests for scripts/system_test_design_args.py.

The argument errors must stop the run before any file is written, name the
offending argument, and exit non-zero; success prints the resolved run as
JSON. The error cases are the fail-on-purpose half of the gate.
"""

from __future__ import annotations

import json
import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "scripts"))

import system_test_design_args as args_mod


def _repo(tmp_path, name):
    repo = tmp_path / name
    (repo / ".git").mkdir(parents=True)
    return str(repo)


def _run(argv, capsys):
    code = args_mod.main(argv)
    out = capsys.readouterr()
    return code, out.out, out.err


def test_resolves_three_named_repos_with_default_mode_and_report_path(tmp_path, capsys):
    a, b, c = (_repo(tmp_path, n) for n in ("entry", "svc-b", "svc-c"))
    code, out, err = _run([a, b, c], capsys)
    run = json.loads(out)
    assert code == 0 and err == ""
    assert run["entry"] == "entry"
    assert [r["name"] for r in run["repos"]] == ["entry", "svc-b", "svc-c"]
    assert run["mode"] == "full"
    assert run["report_path"] == ".dev-team-reports/system-test-design-entry.md"


@pytest.mark.parametrize(
    ("flags", "mode"),
    [(["--e2e-only"], "e2e-only"), (["--overlap-only"], "overlap-only"), ([], "full")],
)
def test_mode_flags(tmp_path, capsys, flags, mode):
    code, out, _ = _run([_repo(tmp_path, "entry"), *flags], capsys)
    assert code == 0 and json.loads(out)["mode"] == mode


def test_coverage_and_mutation_pairs_are_keyed_by_repo_basename(tmp_path, capsys):
    a, b = _repo(tmp_path, "entry"), _repo(tmp_path, "svc-b")
    code, out, _ = _run(
        [a, b, "--coverage", "entry=cov.json", "--mutation", "svc-b=mut.json"], capsys
    )
    run = json.loads(out)
    assert code == 0
    assert run["coverage"] == {"entry": "cov.json"}
    assert run["mutation"] == {"svc-b": "mut.json"}


def test_missing_repo_path_is_an_argument_error_naming_it(tmp_path, capsys):
    gone = str(tmp_path / "gone")
    code, out, err = _run([gone], capsys)
    assert code == 2 and out == ""
    assert gone in err and "argument error" in err


def test_directory_that_is_not_a_git_checkout_is_an_argument_error(tmp_path, capsys):
    plain = tmp_path / "plain"
    plain.mkdir()
    code, out, err = _run([str(plain)], capsys)
    assert code == 2 and out == "" and "not a git checkout" in err


def test_both_mode_flags_together_is_an_argument_error(tmp_path, capsys):
    code, out, err = _run([_repo(tmp_path, "entry"), "--e2e-only", "--overlap-only"], capsys)
    assert code == 2 and out == ""
    assert "--e2e-only" in err and "--overlap-only" in err


def test_coverage_value_naming_a_repo_not_in_scope_is_an_argument_error(tmp_path, capsys):
    code, out, err = _run([_repo(tmp_path, "entry"), "--coverage", "other=cov.json"], capsys)
    assert code == 2 and out == ""
    assert "--coverage" in err and "'other'" in err


@pytest.mark.parametrize("value", ["nopath", "=cov.json", "entry="])
def test_malformed_repo_path_pair_is_an_argument_error(tmp_path, capsys, value):
    code, _, err = _run([_repo(tmp_path, "entry"), "--mutation", value], capsys)
    assert code == 2 and "--mutation" in err


def test_no_entry_repo_is_an_argument_error(capsys):
    code, _, err = _run([], capsys)
    assert code == 2 and "entry-repo" in err


def test_unknown_flag_and_missing_option_value_exit_2_without_usage_dump(tmp_path, capsys):
    entry = _repo(tmp_path, "entry")
    assert _run([entry, "--bogus"], capsys)[0] == 2
    assert _run([entry, "--aliases"], capsys)[0] == 2


def test_duplicate_basenames_are_an_argument_error(tmp_path, capsys):
    a = _repo(tmp_path / "x", "svc")
    b = _repo(tmp_path / "y", "svc")
    code, _, err = _run([a, b], capsys)
    assert code == 2 and "unique" in err


def test_aliases_must_be_an_existing_json_object_of_strings(tmp_path, capsys):
    entry = _repo(tmp_path, "entry")
    good = tmp_path / "good.json"
    good.write_text('{"billing": "payments"}')
    bad_shape = tmp_path / "shape.json"
    bad_shape.write_text('{"billing": 1}')
    broken = tmp_path / "broken.json"
    broken.write_text("{")

    assert _run([entry, "--aliases", str(good)], capsys)[0] == 0
    for bad in (bad_shape, broken, tmp_path / "gone.json"):
        code, out, err = _run([entry, "--aliases", str(bad)], capsys)
        assert code == 2 and out == "" and "--aliases" in err


def test_argument_error_writes_no_report_file(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _run([str(tmp_path / "gone")], capsys)
    assert not (tmp_path / ".dev-team-reports").exists()
