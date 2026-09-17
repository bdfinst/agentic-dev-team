"""Unit tests for scripts/measure_rereview_duplication.py (#2165, slice 0
of epic #2164, Step 1.1: shared imports + the theoretical leg's core
cross-checkpoint dedup algorithm).

Uses a real git repo built in `tmp_path` via subprocess `git init`/`commit`
(not a mock) — the thing under test is the interaction between git's own
`diff --name-status`/`show` semantics and `select_lenses.applicable_lenses`,
which a mocked git would only beg the question of.

One shared commit history (`_seed_repo`) covers scenarios (a)-(c) and (e);
the added-only lens drop-out case (d) uses two commits appended to the same
history (`review_me.py`'s add-then-revert), so this file stays to one
fixture repo rather than several throwaway ones.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import subprocess

import pytest

from _repo_root import REPO_ROOT

_SCRIPT = REPO_ROOT / "scripts" / "measure_rereview_duplication.py"

#: Hermetic git env (see tests/scripts/test_churn_coupling_report.py's own
#: `_HERMETIC_GIT_ENV`): strips the host's global/system git config so a
#: developer's `~/.gitconfig` can't alter this fixture repo's behavior.
_HERMETIC_GIT_ENV = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}


def _load():
    spec = importlib.util.spec_from_file_location("measure_rereview_duplication", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mrd = _load()


# ---------------------------------------------------------------------------
# Fixture repo plumbing
# ---------------------------------------------------------------------------


def _git(repo, *args):
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        check=True,
        capture_output=True,
        text=True,
        env=_HERMETIC_GIT_ENV,
    )


def _write(repo, rel, text):
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _commit(repo, message):
    _git(repo, "commit", "-q", "-m", message)


def _head_sha(repo):
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        env=_HERMETIC_GIT_ENV,
    )
    return result.stdout.strip()


def _seed_repo(root):
    """A commit sequence covering (a)/(b)/(c)/(d)/(e) in one history:

    c0: seed foo.py=F1, qux.py=Q1
    c1: foo.py F1->F2 (foo's LAST-EVER change)
    c2: qux.py Q1->Q2 (qux's first change)
    c3: qux.py Q2->Q3 (qux's second change)
    c4: review_me.py newly ADDED, content matches the added-only lens's glob
    c5: review_me.py modified — a pure revert of c4's addition

    Returns `{"c0": sha, "c1": sha, ...}`.
    """
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q", "-b", "main")
    shas = {}

    _write(root, "foo.py", "F1\n")
    _write(root, "qux.py", "Q1\n")
    _git(root, "add", "-A")
    _commit(root, "c0: seed foo+qux")
    shas["c0"] = _head_sha(root)

    _write(root, "foo.py", "F2\n")
    _git(root, "add", "-A")
    _commit(root, "c1: foo's last change")
    shas["c1"] = _head_sha(root)

    _write(root, "qux.py", "Q2\n")
    _git(root, "add", "-A")
    _commit(root, "c2: qux first change")
    shas["c2"] = _head_sha(root)

    _write(root, "qux.py", "Q3\n")
    _git(root, "add", "-A")
    _commit(root, "c3: qux second change")
    shas["c3"] = _head_sha(root)

    _write(root, "review_me.py", "MATCH\n")
    _git(root, "add", "-A")
    _commit(root, "c4: review_me.py added")
    shas["c4"] = _head_sha(root)

    _write(root, "review_me.py", "reverted\n")
    _git(root, "add", "-A")
    _commit(root, "c5: review_me.py pure revert")
    shas["c5"] = _head_sha(root)

    return shas


#: A plain glob-scoped lens (applies to any changed .py file) plus an
#: added-only lens (applies only to a newly-added .py file within a given
#: checkpoint's range) — shared by every test below so no test builds its
#: own throwaway roster.
_NORMAL_LENS = ("normal-review", ["**/*.py"], False)
_ADDED_ONLY_LENS = (
    "added-only-review",
    (mrd.select_lenses.SCOPE_ADDED_ONLY, ["**/*.py"]),
    False,
)
_ROSTER = [_NORMAL_LENS, _ADDED_ONLY_LENS]


# ---------------------------------------------------------------------------
# parse_checkpoint_spec
# ---------------------------------------------------------------------------


class TestParseCheckpointSpec:
    def test_baseline_and_head_only_defaults_the_label(self):
        cp = mrd.parse_checkpoint_spec("abc123:def456")
        assert cp.baseline == "abc123"
        assert cp.head == "def456"
        assert cp.label == "abc123..def456"

    def test_explicit_label_is_used_verbatim(self):
        cp = mrd.parse_checkpoint_spec("abc123:def456:slice1")
        assert cp.label == "slice1"

    def test_trailing_empty_label_falls_back_to_the_default(self):
        cp = mrd.parse_checkpoint_spec("abc123:def456:")
        assert cp.label == "abc123..def456"

    def test_missing_head_raises(self):
        with pytest.raises(ValueError):
            mrd.parse_checkpoint_spec("abc123")


# ---------------------------------------------------------------------------
# Scenario (a) + (b): cumulative visibility, and a full duplicate
# ---------------------------------------------------------------------------


class TestCumulativeVisibilityAndDuplication:
    def test_file_untouched_by_the_later_checkpoints_own_commits_is_still_seen(self, tmp_path):
        repo = tmp_path / "repo"
        shas = _seed_repo(repo)
        early = mrd.Checkpoint(baseline=shas["c0"], head=shas["c1"], label="early")
        # `late`'s own new commit only touches qux.py (c1->c2), but its
        # baseline is shared with `early`'s (c0) -- exactly the
        # `backstop-full` real-world case: a checkpoint whose baseline
        # predates a file's last change sees that file even though no
        # commit strictly "belonging to" this checkpoint re-touched it.
        late = mrd.Checkpoint(baseline=shas["c0"], head=shas["c2"], label="late")

        result = mrd.find_theoretical_duplicates([early, late], repo, _ROSTER)

        late_row = next(row for row in result["checkpoints"] if row["label"] == "late")
        assert "foo.py" in late_row["file_set"]

    def test_repeated_lens_file_hash_pair_across_checkpoints_is_a_duplicate(self, tmp_path):
        repo = tmp_path / "repo"
        shas = _seed_repo(repo)
        early = mrd.Checkpoint(baseline=shas["c0"], head=shas["c1"], label="early")
        late = mrd.Checkpoint(baseline=shas["c0"], head=shas["c2"], label="late")

        result = mrd.find_theoretical_duplicates([early, late], repo, _ROSTER)

        foo_hash = hashlib.sha256(b"F2\n").hexdigest()
        dup = next(
            d
            for d in result["duplicates"]
            if d["lens"] == "normal-review" and d["file"] == "foo.py"
        )
        assert dup["file_hash"] == foo_hash
        assert dup["first_seen_at"] == "early"
        assert dup["duplicate_at"] == "late"
        # Only the occurrence AFTER the first counts toward the estimate.
        assert dup["avoidable_tokens_estimate"] == mrd.mfd.estimate_tokens(len(b"F2\n"))
        assert result["avoidable_tokens_estimate"] == dup["avoidable_tokens_estimate"]


# ---------------------------------------------------------------------------
# Scenario (c): a real edit between checkpoints is not a duplicate
# ---------------------------------------------------------------------------


class TestEditedFileIsNotADuplicate:
    def test_differing_hashes_across_checkpoints_are_not_reported(self, tmp_path):
        repo = tmp_path / "repo"
        shas = _seed_repo(repo)
        late = mrd.Checkpoint(baseline=shas["c0"], head=shas["c2"], label="late")
        third = mrd.Checkpoint(baseline=shas["c2"], head=shas["c3"], label="third")

        result = mrd.find_theoretical_duplicates([late, third], repo, _ROSTER)

        # qux.py is reviewed at both checkpoints (Q2 at `late`, Q3 at
        # `third`) but its content differs each time, so it must never be
        # reported as a duplicate at either occurrence.
        assert not any(d["file"] == "qux.py" for d in result["duplicates"])
        late_row = next(row for row in result["checkpoints"] if row["label"] == "late")
        third_row = next(row for row in result["checkpoints"] if row["label"] == "third")
        assert "qux.py" in late_row["file_set"]
        assert "qux.py" in third_row["file_set"]


# ---------------------------------------------------------------------------
# Scenario (d): an added-only lens drops out cleanly after a pure revert
# ---------------------------------------------------------------------------


class TestAddedOnlyLensDropsOutCleanly:
    def test_pure_revert_makes_the_added_only_lens_not_reapply(self, tmp_path):
        repo = tmp_path / "repo"
        shas = _seed_repo(repo)
        d1 = mrd.Checkpoint(baseline=shas["c3"], head=shas["c4"], label="d1")
        d2 = mrd.Checkpoint(baseline=shas["c4"], head=shas["c5"], label="d2")

        result = mrd.find_theoretical_duplicates([d1, d2], repo, _ROSTER)

        d1_row = next(row for row in result["checkpoints"] if row["label"] == "d1")
        d2_row = next(row for row in result["checkpoints"] if row["label"] == "d2")
        # review_me.py is genuinely ADDED within d1's range (status 'A') --
        # the added-only lens applies there. Within d2's range it is only
        # MODIFIED (status 'M', a pure revert of the addition), so the
        # lens is not in d2's applicable set at all -- no special case, a
        # structural consequence of `added_files` being computed fresh per
        # checkpoint.
        assert "added-only-review" in d1_row["lenses"]
        assert "added-only-review" not in d2_row["lenses"]
        assert not any(d["lens"] == "added-only-review" for d in result["duplicates"])


# ---------------------------------------------------------------------------
# Scenario (e): no recurring pairs reports zero cleanly
# ---------------------------------------------------------------------------


class TestNoRecurringPairsReportsZeroCleanly:
    def test_single_checkpoint_has_no_duplicates_and_a_zero_estimate(self, tmp_path):
        repo = tmp_path / "repo"
        shas = _seed_repo(repo)
        early = mrd.Checkpoint(baseline=shas["c0"], head=shas["c1"], label="early")

        result = mrd.find_theoretical_duplicates([early], repo, _ROSTER)

        assert result["duplicates"] == []
        assert result["avoidable_tokens_estimate"] == 0

    def test_disjoint_checkpoints_have_no_duplicates(self, tmp_path):
        repo = tmp_path / "repo"
        shas = _seed_repo(repo)
        early = mrd.Checkpoint(baseline=shas["c0"], head=shas["c1"], label="early")
        third = mrd.Checkpoint(baseline=shas["c2"], head=shas["c3"], label="third")

        result = mrd.find_theoretical_duplicates([early, third], repo, _ROSTER)

        assert result["duplicates"] == []
        assert result["avoidable_tokens_estimate"] == 0


# ---------------------------------------------------------------------------
# Unresolvable sha: hard failure for the whole invocation
# ---------------------------------------------------------------------------


class TestUnresolvableShaFailsTheWholeInvocation:
    def test_bad_baseline_sha_names_the_sha_and_checkpoint(self, tmp_path):
        repo = tmp_path / "repo"
        shas = _seed_repo(repo)
        bogus = mrd.Checkpoint(baseline="deadbeef" * 5, head=shas["c1"], label="bogus")

        with pytest.raises(mrd.CheckpointResolutionError) as exc_info:
            mrd.find_theoretical_duplicates([bogus], repo, _ROSTER)

        message = str(exc_info.value)
        assert "deadbeef" in message
        assert "bogus" in message

    def test_bad_head_sha_names_the_sha_and_checkpoint(self, tmp_path):
        repo = tmp_path / "repo"
        shas = _seed_repo(repo)
        bogus = mrd.Checkpoint(baseline=shas["c0"], head="0123456789abcdef" * 2, label="bogus-head")

        with pytest.raises(mrd.CheckpointResolutionError) as exc_info:
            mrd.find_theoretical_duplicates([bogus], repo, _ROSTER)

        message = str(exc_info.value)
        assert "0123456789abcdef" in message
        assert "bogus-head" in message

    def test_no_partial_result_is_returned_before_the_raise(self, tmp_path):
        """A resolvable checkpoint followed by an unresolvable one must not
        leak the first checkpoint's rows anywhere a caller can observe --
        the function raises instead of returning, so there is nothing
        partial to inspect. Asserted by construction: `pytest.raises`
        proves no return value was ever produced."""
        repo = tmp_path / "repo"
        shas = _seed_repo(repo)
        good = mrd.Checkpoint(baseline=shas["c0"], head=shas["c1"], label="good")
        bad = mrd.Checkpoint(baseline=shas["c1"], head="f" * 40, label="bad")

        with pytest.raises(mrd.CheckpointResolutionError):
            mrd.find_theoretical_duplicates([good, bad], repo, _ROSTER)


# ---------------------------------------------------------------------------
# measure_full_file_duplication.py's public/underscored aliases (#2165)
# ---------------------------------------------------------------------------


class TestPublicAliasesAreSameObject:
    """The new public names must be the SAME object as their existing
    underscored counterparts (`is`, not just equal output) so the two names
    can never silently drift apart — accessed via `mrd.mfd`, the module
    `measure_rereview_duplication.py` itself imports."""

    def test_parse_iso_alias_identity(self):
        assert mrd.mfd.parse_iso is mrd.mfd._parse_iso

    def test_filter_since_alias_identity(self):
        assert mrd.mfd.filter_since is mrd.mfd._filter_since

    def test_percentile_distribution_alias_identity(self):
        assert mrd.mfd.percentile_distribution is mrd.mfd._percentile_distribution
