"""Unit tests for hooks/lib/xunit_v3_operator_gate.py (#1791).

The gate is the mechanism that turns "xunit.v3 blocks Stryker" from hook
stdout the agent may paraphrase or skip into a decision the operator has to
make: the question always carries what is blocking plus the four remediation
options, and the guard stays blocked until a choice is *recorded*.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_LIB = _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"
sys.path.insert(0, str(_LIB))

import xunit_v3_operator_gate as ogate

_MODULE = _LIB / "xunit_v3_operator_gate.py"


@pytest.fixture(autouse=True)
def _pin_decision_store(tmp_path, monkeypatch):
    """Pin the store to tmp_path via the env seam.

    Without it, `decision_store_path` resolves through `artifact_paths`, which
    shells out to `git rev-parse --show-toplevel` per call — safe only because
    pytest's temp root happens to sit outside a repo. Pinning it makes these
    unit tests hermetic rather than incidentally-hermetic, and drops a real git
    subprocess per call.
    """
    monkeypatch.setenv(
        "DEV_TEAM_XUNIT3_SHIM_DECISION_FILE", str(tmp_path / "decisions.json")
    )


def _finding(file: str, construct: str, **over) -> dict:
    base = {
        "file": file,
        "line": 12,
        "construct": construct,
        "compile_ability": "no-v2-equivalent",
        "coverage_impact": "bearing",
        "snippet": "[AutoData]",
    }
    base.update(over)
    return base


# --- the four options are the gate's contract -------------------------------


def test_exactly_the_four_documented_remediation_options():
    assert [o.id for o in ogate.REMEDIATION_OPTIONS] == [
        "port",
        "exclude",
        "skip",
        "degrade",
    ]


def test_every_option_carries_a_tradeoff_not_just_a_label():
    for option in ogate.REMEDIATION_OPTIONS:
        assert option.label.strip()
        assert option.tradeoff.strip(), f"{option.id} has no tradeoff stated"
        assert option.label != option.tradeoff


def test_valid_choices_matches_the_option_ids():
    # Literal, not derived from REMEDIATION_OPTIONS: a constant built from a
    # wrong-but-internally-consistent source would satisfy a circular oracle.
    assert ogate.VALID_CHOICES == ("port", "exclude", "skip", "degrade")


# --- build_question: what is blocking ---------------------------------------


def test_question_headline_names_construct_and_file_count():
    q = ogate.build_question(
        "Acme.Tests",
        [_finding("A.cs", "autofixture-auto-data"), _finding("B.cs", "autofixture-auto-data")],
    )
    assert "2 test file" in q.headline
    assert "autofixture-auto-data" in q.headline
    assert "Acme.Tests" in q.headline


def test_question_carries_per_construct_breakdown_with_coverage_impact():
    q = ogate.build_question(
        "Acme.Tests",
        [
            _finding("A.cs", "autofixture-auto-data"),
            _finding("A.cs", "assert-skip", coverage_impact="bearing"),
            _finding(
                "B.cs",
                "fact-explicit",
                coverage_impact="neutral",
                compile_ability="no-v2-equivalent",
            ),
        ],
    )
    by_construct = {b.construct: b for b in q.breakdown}
    assert set(by_construct) == {
        "autofixture-auto-data",
        "assert-skip",
        "fact-explicit",
    }
    assert by_construct["fact-explicit"].coverage_impact == "neutral"
    assert by_construct["autofixture-auto-data"].files == ("A.cs",)
    assert q.bearing_count == 2
    assert q.neutral_count == 1


def test_question_lists_candidate_exclusion_files_deduped_in_first_seen_order():
    q = ogate.build_question(
        "T",
        [
            _finding("B.cs", "assert-skip"),
            _finding("A.cs", "test-context"),
            _finding("B.cs", "autofixture-auto-data"),
        ],
    )
    assert q.files == ("B.cs", "A.cs")


def test_unclassified_files_are_reported_separately_not_silently_dropped():
    # The guard's own token scan is broader than the detector's classified
    # construct set; a file it flags that the detector cannot classify must
    # still reach the operator, labelled as needing manual triage.
    q = ogate.build_question("T", [], unclassified_files=["Legacy.cs"])
    assert q.unclassified_files == ("Legacy.cs",)
    assert q.blocking
    assert "Legacy.cs" in "\n".join(ogate.render_question(q))


def test_no_blockers_means_no_question_to_ask():
    q = ogate.build_question("T", [])
    assert not q.blocking


def test_the_detectors_own_dataclass_is_accepted_identically_to_a_dict():
    # The documented input shape is "the detector's dataclass OR its --json dict
    # form". Only the dict half was exercised, leaving the getattr branch — and
    # therefore the direct in-process wiring — unproven.
    sys.path.insert(
        0,
        str(
            _REPO_ROOT / "plugins" / "dev-team" / "skills" / "mutation-testing"
            / "scripts"
        ),
    )
    import xunit_v3_feature_detector as det

    real = det.scan_text("A.cs", "[Theory, AutoData]")
    assert real, "fixture line no longer produces a detector finding"

    from_objects = ogate.build_question("T", real)
    from_dicts = ogate.build_question(
        "T",
        [
            {
                "file": f.file,
                "line": f.line,
                "construct": f.construct,
                "compile_ability": f.compile_ability,
                "coverage_impact": f.coverage_impact,
                "snippet": f.snippet,
            }
            for f in real
        ],
    )
    assert from_objects.blockers == from_dicts.blockers
    assert from_objects.fingerprint == from_dicts.fingerprint


def test_a_non_numeric_line_degrades_to_zero_rather_than_raising():
    # A malformed detector entry must not take the gate down — a crashed gate is
    # a gate that does not ask.
    q = ogate.build_question("T", [_finding("A.cs", "assert-skip", line="nope")])
    assert q.blockers[0].line == 0


# --- render_question: the operator-facing payload ---------------------------


def test_render_includes_headline_all_four_options_and_their_tradeoffs():
    q = ogate.build_question("Acme.Tests", [_finding("A.cs", "autofixture-auto-data")])
    text = "\n".join(ogate.render_question(q))
    assert q.headline in text
    for option in ogate.REMEDIATION_OPTIONS:
        assert option.id in text
        assert option.tradeoff[:40] in text


def test_render_names_the_files_and_lines_the_operator_must_decide_about():
    q = ogate.build_question(
        "T", [_finding("Widgets/AutoTests.cs", "autofixture-auto-data", line=42)]
    )
    text = "\n".join(ogate.render_question(q))
    assert "Widgets/AutoTests.cs" in text
    assert "42" in text


def test_render_includes_the_record_command_so_the_choice_can_be_persisted():
    q = ogate.build_question("T", [_finding("A.cs", "assert-skip")])
    text = "\n".join(ogate.render_question(q, record_command="RECORD-HERE"))
    assert "RECORD-HERE" in text


def test_render_states_that_the_operator_chooses_not_the_agent():
    q = ogate.build_question("T", [_finding("A.cs", "assert-skip")])
    text = "\n".join(ogate.render_question(q)).lower()
    assert "operator" in text or "ask the user" in text
    assert "do not" in text or "don't" in text


# --- fingerprint: a decision covers the blockers it was made about ---------


def test_fingerprint_is_stable_across_finding_order():
    a = ogate.build_question("T", [_finding("A.cs", "x"), _finding("B.cs", "y")])
    b = ogate.build_question("T", [_finding("B.cs", "y"), _finding("A.cs", "x")])
    assert a.fingerprint == b.fingerprint


def test_fingerprint_changes_when_a_new_blocking_file_appears():
    a = ogate.build_question("T", [_finding("A.cs", "x")])
    b = ogate.build_question("T", [_finding("A.cs", "x"), _finding("B.cs", "x")])
    assert a.fingerprint != b.fingerprint


def test_fingerprint_ignores_line_numbers_so_unrelated_edits_do_not_reask():
    a = ogate.build_question("T", [_finding("A.cs", "x", line=1)])
    b = ogate.build_question("T", [_finding("A.cs", "x", line=900)])
    assert a.fingerprint == b.fingerprint


# --- decision record --------------------------------------------------------


def test_record_then_read_round_trips(tmp_path):
    q = ogate.build_question("Acme.Tests", [_finding("A.cs", "assert-skip")])
    ogate.record_decision(
        "Acme.Tests", "exclude", cwd=tmp_path, fingerprint=q.fingerprint, files=["A.cs"]
    )
    decision = ogate.decision_for(q, cwd=tmp_path)
    assert decision is not None
    assert decision["choice"] == "exclude"
    assert decision["files"] == ["A.cs"]


def test_absent_decision_reads_as_none(tmp_path):
    q = ogate.build_question("T", [_finding("A.cs", "assert-skip")])
    assert ogate.decision_for(q, cwd=tmp_path) is None


def test_decision_for_a_different_project_does_not_apply(tmp_path):
    q = ogate.build_question("Acme.Tests", [_finding("A.cs", "assert-skip")])
    ogate.record_decision("Other.Tests", "degrade", cwd=tmp_path, fingerprint=q.fingerprint)
    assert ogate.decision_for(q, cwd=tmp_path) is None


def test_stale_decision_is_reasked_when_the_blocker_set_changed(tmp_path):
    first = ogate.build_question("T", [_finding("A.cs", "assert-skip")])
    ogate.record_decision("T", "exclude", cwd=tmp_path, fingerprint=first.fingerprint)
    widened = ogate.build_question(
        "T", [_finding("A.cs", "assert-skip"), _finding("New.cs", "test-context")]
    )
    assert ogate.decision_for(widened, cwd=tmp_path) is None, (
        "a decision made about a smaller blocker set must not silently cover "
        "newly-appeared blockers"
    )
    # The earlier question is still covered.
    assert ogate.decision_for(first, cwd=tmp_path) is not None


def test_recording_a_second_project_keeps_the_first(tmp_path):
    qa = ogate.build_question("A.Tests", [_finding("A.cs", "assert-skip")])
    qb = ogate.build_question("B.Tests", [_finding("B.cs", "assert-skip")])
    ogate.record_decision("A.Tests", "port", cwd=tmp_path, fingerprint=qa.fingerprint)
    ogate.record_decision("B.Tests", "degrade", cwd=tmp_path, fingerprint=qb.fingerprint)
    assert ogate.decision_for(qa, cwd=tmp_path)["choice"] == "port"
    assert ogate.decision_for(qb, cwd=tmp_path)["choice"] == "degrade"


def test_re_recording_the_same_project_replaces_the_choice(tmp_path):
    q = ogate.build_question("T", [_finding("A.cs", "assert-skip")])
    ogate.record_decision("T", "exclude", cwd=tmp_path, fingerprint=q.fingerprint)
    ogate.record_decision("T", "degrade", cwd=tmp_path, fingerprint=q.fingerprint)
    assert ogate.decision_for(q, cwd=tmp_path)["choice"] == "degrade"


def test_a_fingerprintless_entry_does_not_cover_anything(tmp_path):
    # Fail closed. `if recorded and recorded != fingerprint` let a blanket entry
    # cover every future blocker set forever, which is the opposite of the
    # guarantee this module exists for — a coverage-bearing file added later
    # would be excluded from the shim without the operator ever seeing it.
    q = ogate.build_question("T", [_finding("A.cs", "assert-skip")])
    store = ogate.decision_store_path(tmp_path)
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text(
        json.dumps({"T": {"project": "T", "choice": "exclude", "files": []}}),
        encoding="utf-8",
    )
    assert ogate.read_decision("T", tmp_path) is not None  # the entry is there
    assert ogate.decision_for(q, cwd=tmp_path) is None  # but covers nothing


def test_a_stored_choice_outside_the_four_is_reasked_not_coerced(tmp_path):
    # record_decision rejects these on the write side, so reaching this needs a
    # hand-edited or externally-produced store. The read side is exactly where
    # the "never coerced into one of the four" guarantee has to hold.
    q = ogate.build_question("T", [_finding("A.cs", "assert-skip")])
    store = ogate.decision_store_path(tmp_path)
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text(
        json.dumps(
            {"T": {"project": "T", "choice": "whatever", "fingerprint": q.fingerprint}}
        ),
        encoding="utf-8",
    )
    assert ogate.decision_for(q, cwd=tmp_path) is None


def test_a_stored_entry_with_no_choice_key_is_reasked(tmp_path):
    q = ogate.build_question("T", [_finding("A.cs", "assert-skip")])
    store = ogate.decision_store_path(tmp_path)
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text(
        json.dumps({"T": {"project": "T", "fingerprint": q.fingerprint}}),
        encoding="utf-8",
    )
    assert ogate.decision_for(q, cwd=tmp_path) is None


def test_unknown_choice_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="choice"):
        ogate.record_decision("T", "whatever", cwd=tmp_path, fingerprint="abc")


@pytest.mark.parametrize("blank", ["", None])
def test_recording_without_a_fingerprint_is_rejected(tmp_path, blank):
    # A record that covers nothing is worse than no record: the operator thinks
    # they answered and the gate keeps asking. Reject at write time, loudly.
    with pytest.raises(ValueError, match="fingerprint"):
        ogate.record_decision("T", "exclude", cwd=tmp_path, fingerprint=blank)


def test_corrupt_store_reads_as_no_decision_rather_than_raising(tmp_path):
    q = ogate.build_question("T", [_finding("A.cs", "assert-skip")])
    ogate.decision_store_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    ogate.decision_store_path(tmp_path).write_text("not json{{{", encoding="utf-8")
    assert ogate.decision_for(q, cwd=tmp_path) is None


def test_decision_records_a_timestamp_for_the_audit_trail(tmp_path):
    q = ogate.build_question("T", [_finding("A.cs", "assert-skip")])
    entry = ogate.record_decision("T", "port", cwd=tmp_path, fingerprint=q.fingerprint)
    assert entry["recorded_at"].endswith("Z")


def test_env_seam_overrides_the_store_location(tmp_path, monkeypatch):
    target = tmp_path / "elsewhere" / "decisions.json"
    monkeypatch.setenv("DEV_TEAM_XUNIT3_SHIM_DECISION_FILE", str(target))
    ogate.record_decision("T", "port", cwd=tmp_path, fingerprint="abc")
    assert target.is_file()


# --- CLI --------------------------------------------------------------------


def _cli(args: list[str], cwd) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_MODULE), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_record_and_check_round_trip(tmp_path):
    rec = _cli(
        ["record", "--project", "Acme.Tests", "--choice", "exclude", "--file", "A.cs",
         "--fingerprint", "deadbeefdeadbeef"],
        tmp_path,
    )
    assert rec.returncode == 0, rec.stderr
    chk = _cli(["check", "--project", "Acme.Tests"], tmp_path)
    assert chk.returncode == 0
    payload = json.loads(chk.stdout)
    assert payload["choice"] == "exclude"
    assert payload["files"] == ["A.cs"]


def test_cli_check_without_a_decision_exits_nonzero(tmp_path):
    chk = _cli(["check", "--project", "Nope"], tmp_path)
    assert chk.returncode == 1
    assert chk.stdout.strip() == "" or json.loads(chk.stdout) is None


def test_cli_record_rejects_an_unknown_choice(tmp_path):
    rec = _cli(
        ["record", "--project", "T", "--choice", "nonsense",
         "--fingerprint", "abc"],
        tmp_path,
    )
    assert rec.returncode != 0


def test_cli_record_requires_a_fingerprint(tmp_path):
    rec = _cli(["record", "--project", "T", "--choice", "exclude"], tmp_path)
    assert rec.returncode != 0
    assert "fingerprint" in rec.stderr


def test_cli_options_lists_the_four_choices(tmp_path):
    out = _cli(["options"], tmp_path)
    assert out.returncode == 0
    for option in ogate.REMEDIATION_OPTIONS:
        assert option.id in out.stdout
