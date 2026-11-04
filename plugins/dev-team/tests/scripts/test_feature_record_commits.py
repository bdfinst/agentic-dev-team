"""The commit invariant of scripts/feature_record.py (#2275).

Library cases take a fake evidence callback; no git is involved. The CLI
cases against real temporary repositories are further down.
"""

from __future__ import annotations

import json
import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_SCRIPTS = _REPO_ROOT / "plugins" / "dev-team" / "scripts"
sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(_SCRIPTS / "lib"))

import feature_record

# Unindented items, as the guardian reads them: a slice and two steps.
PLAN = """# Plan: sample

## Build Progress

- [x] Slice 1: Parse
- [x] Step 1.1: Parse a line
- [x] Add the builder
- [ ] Step 2.1: Build a file
"""


def _backed(by_id: dict[str, bool | None]):
    """A callback answering by item id; records every item it is asked about."""
    asked: list[dict] = []

    def callback(item):
        asked.append(item)
        return by_id[item["id"]]

    callback.asked = asked
    return callback


def _commit_backed(record) -> dict[str, bool | None]:
    return {i["id"]: i["commit_backed"] for i in record["build_progress"]["items"]}


def _ids(found) -> list[str]:
    return [v["subject"] for v in found if v["id"] == "tick-without-commit"]


def test_without_a_callback_every_item_is_null_and_not_evaluated():
    record = feature_record.build_record(PLAN)
    assert set(_commit_backed(record).values()) == {None}
    assert record["applicability"]["commit_evidence"] == "not-evaluated"
    assert feature_record.unverifiable(record) == []
    assert _ids(feature_record.violations(record)) == []


def test_a_callback_marks_the_record_evaluated():
    record = feature_record.build_record(PLAN, commit_evidence=lambda item: True)
    assert record["applicability"]["commit_evidence"] == "evaluated"


def test_the_callback_answers_land_on_the_ticked_items_of_either_kind():
    callback = _backed({"1": True, "1.1": False, "Add the builder": None})
    record = feature_record.build_record(PLAN, commit_evidence=callback)
    assert _commit_backed(record) == {
        "1": True,
        "1.1": False,
        "Add the builder": None,
        "2.1": None,
    }


def test_an_unticked_item_is_never_asked_and_stays_null():
    callback = _backed({"1": True, "1.1": True, "Add the builder": True})
    record = feature_record.build_record(PLAN, commit_evidence=callback)
    assert [i["id"] for i in callback.asked] == ["1", "1.1", "Add the builder"]
    assert _commit_backed(record)["2.1"] is None


def test_the_callback_is_given_the_item_it_is_asked_about():
    callback = _backed({"1": True, "1.1": True, "Add the builder": True})
    feature_record.build_record(PLAN, commit_evidence=callback)
    assert callback.asked[0]["kind"] == "slice"
    assert callback.asked[0]["header"] == "Slice 1: Parse"
    assert callback.asked[1]["kind"] == "step"


def test_a_callback_that_mutates_its_item_does_not_change_the_record():
    def callback(item):
        item["header"] = "tampered"
        item["done"] = False
        return True

    record = feature_record.build_record(PLAN, commit_evidence=callback)
    first = record["build_progress"]["items"][0]
    assert first["header"] == "Slice 1: Parse"
    assert first["done"] is True


def test_only_a_bool_counts_as_an_answer():
    record = feature_record.build_record(PLAN, commit_evidence=lambda item: "yes")
    assert set(_commit_backed(record).values()) == {None}
    record = feature_record.build_record(PLAN, commit_evidence=lambda item: 1)
    assert set(_commit_backed(record).values()) == {None}


def test_a_callback_that_raises_leaves_the_item_unverifiable():
    def callback(item):
        raise RuntimeError("git exploded")

    record = feature_record.build_record(PLAN, commit_evidence=callback)
    assert _commit_backed(record) == {
        "1": None,
        "1.1": None,
        "Add the builder": None,
        "2.1": None,
    }
    assert feature_record.unverifiable(record) == ["1", "1.1", "Add the builder"]


def test_an_unbacked_ticked_item_is_a_violation_naming_it():
    callback = _backed({"1": True, "1.1": False, "Add the builder": True})
    found = feature_record.violations(
        feature_record.build_record(PLAN, commit_evidence=callback)
    )
    assert _ids(found) == ["Step 1.1"]
    violation = found[0]
    assert violation["what"] == (
        "Step 1.1 is ticked done and no commit on this branch backs it. "
        "[tick-without-commit]"
    )
    assert (
        violation["why"]
        == "A tick with no commit claims work the history does not show."
    )
    assert violation["how"] == (
        "Commit the step (touching <declared files>), or untick it "
        "under ## Build Progress."
    )


def test_an_unbacked_slice_item_is_named_as_the_slice():
    callback = _backed({"1": False, "1.1": True, "Add the builder": True})
    found = feature_record.violations(
        feature_record.build_record(PLAN, commit_evidence=callback)
    )
    assert _ids(found) == ["Slice 1"]


def test_declared_files_on_an_item_fill_the_how_text():
    record = feature_record.build_record(
        PLAN,
        commit_evidence=_backed({"1": False, "1.1": True, "Add the builder": True}),
    )
    record["build_progress"]["items"][0]["declared_files"] = ["docs/b.md", "docs/c.md"]
    (found,) = feature_record.violations(record)
    assert "touching docs/b.md, docs/c.md" in found["how"]


def test_a_backed_or_unverifiable_item_is_not_a_violation():
    callback = _backed({"1": True, "1.1": None, "Add the builder": True})
    record = feature_record.build_record(PLAN, commit_evidence=callback)
    assert _ids(feature_record.violations(record)) == []
    assert feature_record.unverifiable(record) == ["1.1"]


def test_an_unticked_item_with_false_evidence_is_not_a_violation():
    record = feature_record.build_record(PLAN)
    record["applicability"]["commit_evidence"] = "evaluated"
    record["build_progress"]["items"][3]["commit_backed"] = False  # "- [ ] Step 2.1"
    assert _ids(feature_record.violations(record)) == []


def test_the_commit_violation_comes_after_the_structural_ones():
    plan = (
        "### Slice 1: Parse\n\n"
        + PLAN
        + "\n## Plan Review Summary\n\n**Open blocker**: Slice 1 - not done\n"
    )
    record = feature_record.build_record(
        plan,
        commit_evidence=_backed({"1": False, "1.1": True, "Add the builder": True}),
    )
    assert [v["id"] for v in feature_record.violations(record)] == [
        "closed-slice-open-blocker",
        "tick-without-commit",
    ]


def test_the_record_with_evidence_is_json_serialisable():
    record = feature_record.build_record(
        PLAN,
        commit_evidence=_backed({"1": True, "1.1": False, "Add the builder": None}),
    )
    assert json.loads(json.dumps(record)) == record


@pytest.mark.parametrize("text", ["", "x", "- [x] a\n" * 3, "\x00\x01- [x] b"])
def test_build_record_with_a_callback_is_total(text):
    record = feature_record.build_record(text, commit_evidence=lambda item: False)
    feature_record.violations(record)
