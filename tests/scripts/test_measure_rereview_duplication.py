"""Unit tests for scripts/measure_rereview_duplication.py (#2165, slice 0
of epic #2164): Step 1.1 (shared imports + the theoretical leg's core
cross-checkpoint dedup algorithm), Step 1.2 (the `theoretical` and
`empirical` CLI subcommands), and Step 1.3 (the `report`/`rollup`
subcommands and their combining logic).

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
import json
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
    """A commit sequence covering (a)/(b)/(c)/(d)/(e), plus the review
    findings' extra scenarios (9)-(11) below, in one history:

    c0: seed foo.py=F1, qux.py=Q1
    c1: foo.py F1->F2 (foo's LAST-EVER change)
    c2: qux.py Q1->Q2 (qux's first change)
    c3: qux.py Q2->Q3 (qux's second change)
    c4: review_me.py newly ADDED, content matches the added-only lens's glob
    c5: review_me.py modified — a pure revert of c4's addition
    c6: rare_a.py and rare_b.py both newly ADDED in this SAME commit, with
        byte-identical content ("RARE\\n") — two different files, one
        checkpoint, for the same-checkpoint-is-not-a-duplicate case.
    c7: rare_c.py newly ADDED, also with content "RARE\\n" — a THIRD,
        different file with the same content, in a LATER commit — for the
        cross-checkpoint dedup-by-hash-not-path case.
    c8: review_me.py renamed (git mv) to renamed_review_me.py, content
        unchanged — for the rename-is-not-an-add case.

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

    _write(root, "rare_a.py", "RARE\n")
    _write(root, "rare_b.py", "RARE\n")
    _git(root, "add", "-A")
    _commit(root, "c6: rare_a.py + rare_b.py added, identical content, same commit")
    shas["c6"] = _head_sha(root)

    _write(root, "rare_c.py", "RARE\n")
    _git(root, "add", "-A")
    _commit(root, "c7: rare_c.py added, same content as c6's pair, later commit")
    shas["c7"] = _head_sha(root)

    _git(root, "mv", "review_me.py", "renamed_review_me.py")
    _commit(root, "c8: review_me.py renamed to renamed_review_me.py")
    shas["c8"] = _head_sha(root)

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
        # Exact equality, not membership: `late`'s cumulative diff (c0..c2)
        # must be precisely {foo.py, qux.py} -- foo.py via cumulative
        # visibility (this test's own point) and qux.py via `late`'s own
        # c1->c2 commit, nothing else and nothing missing.
        assert late_row["file_set"] == ["foo.py", "qux.py"]

    def test_repeated_lens_file_hash_pair_across_checkpoints_is_a_duplicate(self, tmp_path):
        repo = tmp_path / "repo"
        shas = _seed_repo(repo)
        early = mrd.Checkpoint(baseline=shas["c0"], head=shas["c1"], label="early")
        late = mrd.Checkpoint(baseline=shas["c0"], head=shas["c2"], label="late")

        result = mrd.find_theoretical_duplicates([early, late], repo, _ROSTER)

        assert len(result["duplicates"]) == 1
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
# Review finding: dedup key is (lens, file_hash), not (lens, file_path,
# file_hash) -- two different files with byte-identical content, in
# DIFFERENT checkpoints, are the same duplicate pair.
# ---------------------------------------------------------------------------


class TestDedupKeyIsLensAndHashNotPath:
    def test_different_file_same_content_across_checkpoints_is_a_duplicate(self, tmp_path):
        repo = tmp_path / "repo"
        shas = _seed_repo(repo)
        # c6 adds rare_a.py + rare_b.py (identical content) in one commit;
        # c7 adds a THIRD, differently-named file (rare_c.py) with the same
        # content in a later commit/checkpoint.
        first = mrd.Checkpoint(baseline=shas["c5"], head=shas["c6"], label="first")
        second = mrd.Checkpoint(baseline=shas["c6"], head=shas["c7"], label="second")

        result = mrd.find_theoretical_duplicates([first, second], repo, _ROSTER)

        rare_hash = hashlib.sha256(b"RARE\n").hexdigest()
        matches = [
            d for d in result["duplicates"] if d["lens"] == "normal-review" and d["file_hash"] == rare_hash
        ]
        assert len(matches) == 1
        dup = matches[0]
        # The duplicate is rare_c.py (a file NEVER seen before) matched
        # against a pair first recorded under a DIFFERENT file's name at
        # `first` -- proving the key is (lens, hash), not (lens, path, hash).
        assert dup["file"] == "rare_c.py"
        assert dup["first_seen_at"] == "first"
        assert dup["duplicate_at"] == "second"


# ---------------------------------------------------------------------------
# Review finding: two different files with identical content added WITHIN
# THE SAME checkpoint must not be reported as a duplicate of each other.
# ---------------------------------------------------------------------------


class TestSameCheckpointIdenticalContentIsNotADuplicate:
    def test_two_files_added_in_the_same_checkpoint_with_identical_content_are_not_duplicates(
        self, tmp_path
    ):
        repo = tmp_path / "repo"
        shas = _seed_repo(repo)
        # c6 adds BOTH rare_a.py and rare_b.py, identical content, in one
        # commit -- so a single checkpoint spanning only c5..c6 sees both
        # files for the first time together.
        only = mrd.Checkpoint(baseline=shas["c5"], head=shas["c6"], label="only")

        result = mrd.find_theoretical_duplicates([only], repo, _ROSTER)

        assert result["duplicates"] == []
        assert result["avoidable_tokens_estimate"] == 0


# ---------------------------------------------------------------------------
# Review finding: `first_seen_at` stays pinned to the FIRST checkpoint a
# (lens, hash) pair appeared at across 3+ checkpoints, not the
# second-most-recent one.
# ---------------------------------------------------------------------------


class TestFirstSeenAtStaysPinnedAcrossThreeOrMoreCheckpoints:
    def test_first_seen_at_is_the_earliest_checkpoint_not_the_prior_one(self, tmp_path):
        repo = tmp_path / "repo"
        shas = _seed_repo(repo)
        # All three checkpoints share baseline c0 (cumulative visibility),
        # so each one's file set includes foo.py at its final content (F2,
        # foo's last-ever change was at c1) -- the same (lens, hash) pair
        # recurs at every checkpoint after the first.
        first = mrd.Checkpoint(baseline=shas["c0"], head=shas["c1"], label="first")
        second = mrd.Checkpoint(baseline=shas["c0"], head=shas["c2"], label="second")
        third = mrd.Checkpoint(baseline=shas["c0"], head=shas["c3"], label="third")

        result = mrd.find_theoretical_duplicates([first, second, third], repo, _ROSTER)

        foo_dups = [d for d in result["duplicates"] if d["file"] == "foo.py"]
        assert len(foo_dups) == 2
        assert {d["duplicate_at"] for d in foo_dups} == {"second", "third"}
        # Load-bearing: BOTH later occurrences point back to the very first
        # checkpoint, not to the checkpoint immediately before them.
        assert all(d["first_seen_at"] == "first" for d in foo_dups)


# ---------------------------------------------------------------------------
# Review finding: a rename (status `R...`, not `A`) must not spuriously
# satisfy an added-only lens.
# ---------------------------------------------------------------------------


class TestRenameDoesNotSatisfyAddedOnlyLens:
    def test_git_mv_rename_does_not_trigger_the_added_only_lens(self, tmp_path):
        repo = tmp_path / "repo"
        shas = _seed_repo(repo)
        # c8 renames review_me.py -> renamed_review_me.py (git mv, content
        # unchanged) -- a rename status code (e.g. `R100`) does not start
        # with "A", so `added_files` must not include the renamed path.
        # Baseline is c7 (not c5) so this checkpoint's range contains ONLY
        # the rename -- c6/c7's genuinely-added rare_*.py files would
        # otherwise also satisfy the added-only lens and mask the point.
        renamed = mrd.Checkpoint(baseline=shas["c7"], head=shas["c8"], label="renamed")

        result = mrd.find_theoretical_duplicates([renamed], repo, _ROSTER)

        renamed_row = next(row for row in result["checkpoints"] if row["label"] == "renamed")
        assert "renamed_review_me.py" in renamed_row["file_set"]
        assert "added-only-review" not in renamed_row["lenses"]


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


# ---------------------------------------------------------------------------
# Step 1.2: `theoretical` CLI subcommand
# ---------------------------------------------------------------------------

_NORMAL_AGENT_MD = """\
---
name: normal-review
model: sonnet
---

Scope:
- **/*.py
"""

_ADDED_ONLY_AGENT_MD = """\
---
name: added-only-review
model: sonnet
---

Scope: added-only
- **/*.py
"""

_CLI_REGISTRY_TEXT = """\
## Review Agents

| Name | File | Purpose |
| --- | --- | --- |
| normal-review | `agents/normal-review.md` | test lens |
| added-only-review | `agents/added-only-review.md` | test added-only lens |
"""


def _write_cli_roster(tmp_path):
    """A real on-disk agents-dir + registry (unlike `_ROSTER` above, which
    the pure-algorithm tests hand `find_theoretical_duplicates` directly) --
    the CLI resolves its roster via `select_lenses.build_review_roster`,
    exactly as `measure_full_file_duplication.py`'s own `cmd_theoretical`
    does, so this exercises that same disk-reading path."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "normal-review.md").write_text(_NORMAL_AGENT_MD, encoding="utf-8")
    (agents_dir / "added-only-review.md").write_text(_ADDED_ONLY_AGENT_MD, encoding="utf-8")
    registry_path = tmp_path / "agent-registry.md"
    registry_path.write_text(_CLI_REGISTRY_TEXT, encoding="utf-8")
    return agents_dir, registry_path


class TestTheoreticalCli:
    def test_output_shape_and_duplicate_reported(self, tmp_path, capsys):
        repo = tmp_path / "repo"
        shas = _seed_repo(repo)
        agents_dir, registry_path = _write_cli_roster(tmp_path)

        rc = mrd.main(
            [
                "theoretical",
                "--checkpoint",
                f"{shas['c0']}:{shas['c1']}:early",
                "--checkpoint",
                f"{shas['c0']}:{shas['c2']}:late",
                "--agents-dir",
                str(agents_dir),
                "--registry",
                str(registry_path),
                "--repo-root",
                str(repo),
            ]
        )

        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert set(out) == {
            "checkpoints",
            "duplicates",
            "avoidable_tokens_estimate",
            "roster_warnings",
        }
        assert out["roster_warnings"] == []
        assert len(out["duplicates"]) == 1
        dup = out["duplicates"][0]
        assert dup["lens"] == "normal-review"
        assert dup["file"] == "foo.py"
        assert dup["first_seen_at"] == "early"
        assert dup["duplicate_at"] == "late"
        assert dup["file_hash"] == hashlib.sha256(b"F2\n").hexdigest()
        assert out["avoidable_tokens_estimate"] == dup["avoidable_tokens_estimate"]


class TestTheoreticalCliUnresolvableShaFails:
    def test_bad_sha_exits_nonzero_names_it_and_prints_no_partial_output(
        self, tmp_path, capsys
    ):
        repo = tmp_path / "repo"
        shas = _seed_repo(repo)
        agents_dir, registry_path = _write_cli_roster(tmp_path)
        bogus = "deadbeef" * 5

        rc = mrd.main(
            [
                "theoretical",
                "--checkpoint",
                f"{bogus}:{shas['c1']}:bogus",
                "--agents-dir",
                str(agents_dir),
                "--registry",
                str(registry_path),
                "--repo-root",
                str(repo),
            ]
        )

        assert rc != 0
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "deadbeef" in captured.err
        assert "bogus" in captured.err


class TestTheoreticalCliMalformedCheckpointSpecFails:
    def test_malformed_checkpoint_spec_is_a_clean_refusal_not_a_traceback(
        self, tmp_path, capsys
    ):
        agents_dir, registry_path = _write_cli_roster(tmp_path)

        rc = mrd.main(
            [
                "theoretical",
                "--checkpoint",
                "only-one-field",
                "--agents-dir",
                str(agents_dir),
                "--registry",
                str(registry_path),
                "--repo-root",
                str(tmp_path),
            ]
        )

        assert rc != 0
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.startswith("error:")


# ---------------------------------------------------------------------------
# Step 1.2: `empirical` CLI subcommand
# ---------------------------------------------------------------------------


def _write_agent_dispatch(subagents_dir, agent_id, agent_type, ts, input_tokens):
    """One `agent-<id>.jsonl` + `.meta.json` sibling pair — the same
    sibling-subagent-file layout `measure_full_file_duplication.py`'s own
    tests build (`_write_sibling_agent`), reproduced locally here rather
    than imported cross-test-module."""
    (subagents_dir / f"agent-{agent_id}.meta.json").write_text(
        json.dumps({"agentType": agent_type}), encoding="utf-8"
    )
    record = {
        "timestamp": ts,
        "message": {"usage": {"input_tokens": input_tokens, "output_tokens": 1}},
    }
    (subagents_dir / f"agent-{agent_id}.jsonl").write_text(
        json.dumps(record), encoding="utf-8"
    )


def _empirical_fixture(tmp_path):
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("", encoding="utf-8")
    subagents_dir = tmp_path / "session" / "subagents"
    subagents_dir.mkdir(parents=True)
    return transcript, subagents_dir


class TestEmpiricalCli:
    def test_reports_real_spend_grouped_by_agent_type(self, tmp_path, capsys):
        transcript, subagents_dir = _empirical_fixture(tmp_path)
        # Agent type A: two dispatches, 100 + 150 = 250 total input tokens.
        _write_agent_dispatch(
            subagents_dir, "a1", "dev-team:type-a", "2026-08-01T19:00:00.000Z", 100
        )
        _write_agent_dispatch(
            subagents_dir, "a2", "dev-team:type-a", "2026-08-01T19:00:05.000Z", 150
        )
        # Agent type B: one dispatch, 200 total input tokens.
        _write_agent_dispatch(
            subagents_dir, "b1", "dev-team:type-b", "2026-08-01T19:00:10.000Z", 200
        )

        rc = mrd.main(["empirical", "--transcript", str(transcript)])

        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["spend_by_agent_type"]["dev-team:type-a"] == {
            "total_input_tokens": 250,
            "n_dispatches": 2,
        }
        assert out["spend_by_agent_type"]["dev-team:type-b"] == {
            "total_input_tokens": 200,
            "n_dispatches": 1,
        }


class TestEmpiricalMissingTranscriptIsRefused:
    def test_nonexistent_transcript_path_exits_nonzero(self, tmp_path, capsys):
        missing = tmp_path / "does-not-exist.jsonl"

        rc = mrd.main(["empirical", "--transcript", str(missing)])

        assert rc != 0
        captured = capsys.readouterr()
        assert captured.out == ""
        assert str(missing) in captured.err


# ---------------------------------------------------------------------------
# Review finding: `measured_avg_by_lens` normalizes BEFORE grouping, not
# after -- a plugin-qualified and a bare spelling of the SAME lens must be
# merged, not last-wins-collapsed; and a bucket with dispatches but zero
# recorded spend must not be treated as "measured".
# ---------------------------------------------------------------------------


class TestMeasuredAvgByLensNormalizesBeforeGrouping:
    def test_qualified_and_bare_spellings_of_the_same_lens_are_merged(self):
        spend_by_agent_type = {
            "dev-team:correctness-review": {"total_input_tokens": 100, "n_dispatches": 1},
            "correctness-review": {"total_input_tokens": 50, "n_dispatches": 1},
        }

        avg = mrd.measured_avg_by_lens(spend_by_agent_type)

        # (100 + 50) / (1 + 1) -- neither spelling's dispatches silently
        # dropped by a last-wins dict collapse.
        assert avg == {"correctness-review": 75.0}

    def test_zero_recorded_spend_bucket_is_not_treated_as_measured(self):
        spend_by_agent_type = {
            "dev-team:correctness-review": {"total_input_tokens": 0, "n_dispatches": 1},
        }

        avg = mrd.measured_avg_by_lens(spend_by_agent_type)

        assert avg == {}


# ---------------------------------------------------------------------------
# Step 1.3: `report`'s combining logic (`build_report`) -- spend_source
# correctness and the zero-duplicates edge case
# ---------------------------------------------------------------------------


class TestBuildReportSpendSource:
    def test_covered_lens_uses_measured_average_not_byte_estimate(self, tmp_path):
        repo = tmp_path / "repo"
        shas = _seed_repo(repo)
        early = mrd.Checkpoint(baseline=shas["c0"], head=shas["c1"], label="early")
        late = mrd.Checkpoint(baseline=shas["c0"], head=shas["c2"], label="late")
        # "normal-review" IS the lens that produces the one real duplicate
        # (foo.py, early->late) -- 300 total tokens over 3 dispatches, a
        # transcript that plainly covers this lens under its plugin-qualified
        # form.
        spend_by_agent_type = {
            "dev-team:normal-review": {"total_input_tokens": 300, "n_dispatches": 3}
        }

        result = mrd.build_report([early, late], repo, _ROSTER, spend_by_agent_type)

        assert len(result["duplicates"]) == 1
        dup = result["duplicates"][0]
        assert dup["lens"] == "normal-review"
        assert dup["spend_source"] == "measured"
        assert dup["avoidable_tokens_estimate"] == 100.0
        assert result["avoidable_tokens_estimate"] == 100.0
        # total_tokens_estimate: early has 1 (lens, file) occurrence
        # (normal-review x foo.py) and late has 2 (normal-review x foo.py,
        # normal-review x qux.py) -- 3 occurrences, all measured at 100.0
        # each (flat per-lens average, size-invariant within the lens).
        assert result["total_tokens_estimate"] == 300.0
        assert result["avoidable_pct_of_total"] == 33.33
        assert result["spend_source_assumption"] == mrd._SPEND_SOURCE_ASSUMPTION

    def test_uncovered_lens_falls_back_to_the_byte_estimate(self, tmp_path):
        repo = tmp_path / "repo"
        shas = _seed_repo(repo)
        early = mrd.Checkpoint(baseline=shas["c0"], head=shas["c1"], label="early")
        late = mrd.Checkpoint(baseline=shas["c0"], head=shas["c2"], label="late")

        result = mrd.build_report([early, late], repo, _ROSTER, None)

        assert len(result["duplicates"]) == 1
        dup = result["duplicates"][0]
        assert dup["spend_source"] == "estimated"
        foo_bytes_estimate = mrd.mfd.estimate_tokens(len(b"F2\n"))
        assert dup["avoidable_tokens_estimate"] == foo_bytes_estimate
        assert result["avoidable_tokens_estimate"] == foo_bytes_estimate
        # 3 occurrences (as above), all byte-estimated at 1 token each
        # (`estimate_tokens(3) == 1`).
        assert result["total_tokens_estimate"] == 3 * foo_bytes_estimate
        assert result["avoidable_pct_of_total"] == 33.33

    def test_empty_spend_by_agent_type_dict_also_falls_back_to_estimated(self, tmp_path):
        repo = tmp_path / "repo"
        shas = _seed_repo(repo)
        early = mrd.Checkpoint(baseline=shas["c0"], head=shas["c1"], label="early")
        late = mrd.Checkpoint(baseline=shas["c0"], head=shas["c2"], label="late")

        result = mrd.build_report([early, late], repo, _ROSTER, {})

        assert result["duplicates"][0]["spend_source"] == "estimated"

    def test_dispatched_but_zero_spend_lens_falls_back_to_estimated_not_a_confident_zero(
        self, tmp_path
    ):
        repo = tmp_path / "repo"
        shas = _seed_repo(repo)
        early = mrd.Checkpoint(baseline=shas["c0"], head=shas["c1"], label="early")
        late = mrd.Checkpoint(baseline=shas["c0"], head=shas["c2"], label="late")
        # A bucket exists (a dispatch happened) but recorded zero real
        # spend -- must NOT be reported as "measured" with a confident-
        # looking 0.0 avoidable_tokens_estimate.
        spend_by_agent_type = {
            "dev-team:normal-review": {"total_input_tokens": 0, "n_dispatches": 1}
        }

        result = mrd.build_report([early, late], repo, _ROSTER, spend_by_agent_type)

        dup = result["duplicates"][0]
        assert dup["spend_source"] == "estimated"
        foo_bytes_estimate = mrd.mfd.estimate_tokens(len(b"F2\n"))
        assert dup["avoidable_tokens_estimate"] == foo_bytes_estimate


class TestBuildReportZeroDuplicatesCleanly:
    def test_zero_duplicates_reports_zero_pct_not_an_error(self, tmp_path):
        repo = tmp_path / "repo"
        shas = _seed_repo(repo)
        early = mrd.Checkpoint(baseline=shas["c0"], head=shas["c1"], label="early")

        result = mrd.build_report([early], repo, _ROSTER, None)

        assert result["duplicates"] == []
        assert result["avoidable_tokens_estimate"] == 0.0
        assert result["avoidable_pct_of_total"] == 0.0

    def test_zero_total_tokens_never_raises_zero_division(self, tmp_path):
        repo = tmp_path / "repo"
        shas = _seed_repo(repo)
        # baseline == head: an empty diff, so no lenses apply and no files
        # are resolved -- total_tokens_estimate is genuinely 0, the literal
        # division-by-zero risk `avoidable_pct_of_total`'s formula guards
        # against, not just the "numerator is zero" case above.
        empty = mrd.Checkpoint(baseline=shas["c0"], head=shas["c0"], label="empty")

        result = mrd.build_report([empty], repo, _ROSTER, None)

        assert result["total_tokens_estimate"] == 0.0
        assert result["avoidable_pct_of_total"] == 0.0


# ---------------------------------------------------------------------------
# Step 1.3: `report` CLI subcommand
# ---------------------------------------------------------------------------


class TestReportCli:
    def test_output_shape_falls_back_to_estimated_without_a_transcript(
        self, tmp_path, capsys
    ):
        repo = tmp_path / "repo"
        shas = _seed_repo(repo)
        agents_dir, registry_path = _write_cli_roster(tmp_path)

        rc = mrd.main(
            [
                "report",
                "--checkpoint",
                f"{shas['c0']}:{shas['c1']}:early",
                "--checkpoint",
                f"{shas['c0']}:{shas['c2']}:late",
                "--agents-dir",
                str(agents_dir),
                "--registry",
                str(registry_path),
                "--repo-root",
                str(repo),
            ]
        )

        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert set(out) == {
            "checkpoints",
            "duplicates",
            "avoidable_tokens_estimate",
            "total_tokens_estimate",
            "avoidable_pct_of_total",
            "spend_source_assumption",
            "roster_warnings",
        }
        assert out["duplicates"][0]["spend_source"] == "estimated"

    def test_missing_transcript_path_is_refused(self, tmp_path, capsys):
        repo = tmp_path / "repo"
        shas = _seed_repo(repo)
        agents_dir, registry_path = _write_cli_roster(tmp_path)
        missing = tmp_path / "does-not-exist.jsonl"

        rc = mrd.main(
            [
                "report",
                "--checkpoint",
                f"{shas['c0']}:{shas['c1']}:early",
                "--transcript",
                str(missing),
                "--agents-dir",
                str(agents_dir),
                "--registry",
                str(registry_path),
                "--repo-root",
                str(repo),
            ]
        )

        assert rc != 0
        captured = capsys.readouterr()
        assert captured.out == ""
        assert str(missing) in captured.err

    def test_malformed_checkpoint_spec_is_a_clean_refusal_not_a_traceback(
        self, tmp_path, capsys
    ):
        agents_dir, registry_path = _write_cli_roster(tmp_path)

        rc = mrd.main(
            [
                "report",
                "--checkpoint",
                "only-one-field",
                "--agents-dir",
                str(agents_dir),
                "--registry",
                str(registry_path),
                "--repo-root",
                str(tmp_path),
            ]
        )

        assert rc != 0
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.startswith("error:")


# ---------------------------------------------------------------------------
# Step 1.3: `rollup` subcommand
# ---------------------------------------------------------------------------


def _write_report(path, avoidable_pct_of_total):
    path.write_text(
        json.dumps({"avoidable_pct_of_total": avoidable_pct_of_total}), encoding="utf-8"
    )


class TestRollupDistribution:
    def test_three_reports_reproduce_hand_computed_min_median_max(self, tmp_path, capsys):
        r1, r2, r3 = tmp_path / "r1.json", tmp_path / "r2.json", tmp_path / "r3.json"
        _write_report(r1, 10.0)
        _write_report(r2, 20.0)
        _write_report(r3, 30.0)

        rc = mrd.main(["rollup", "--reports", str(r1), str(r2), str(r3)])

        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["distribution"]["min_pct"] == 10.0
        assert out["distribution"]["median_pct"] == 20.0
        assert out["distribution"]["max_pct"] == 30.0
        assert out["distribution"]["n_rounds_sampled"] == 3

    def test_exactly_one_report_has_a_well_defined_median(self, tmp_path, capsys):
        r1 = tmp_path / "r1.json"
        _write_report(r1, 42.0)

        rc = mrd.main(["rollup", "--reports", str(r1)])

        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["distribution"]["min_pct"] == 42.0
        assert out["distribution"]["median_pct"] == 42.0
        assert out["distribution"]["max_pct"] == 42.0

    def test_exactly_two_reports_has_a_well_defined_median(self, tmp_path, capsys):
        r1, r2 = tmp_path / "r1.json", tmp_path / "r2.json"
        _write_report(r1, 10.0)
        _write_report(r2, 20.0)

        rc = mrd.main(["rollup", "--reports", str(r1), str(r2)])

        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["distribution"]["median_pct"] == 15.0


class TestRollupRefusesMalformedReport:
    def test_invalid_json_path_fails_the_whole_call(self, tmp_path, capsys):
        good = tmp_path / "good.json"
        bad = tmp_path / "bad.json"
        _write_report(good, 10.0)
        bad.write_text("not valid json{", encoding="utf-8")

        rc = mrd.main(["rollup", "--reports", str(good), str(bad)])

        assert rc != 0
        captured = capsys.readouterr()
        # No partial min/median/max computed over just the valid file.
        assert captured.out == ""
        assert str(bad) in captured.err

    def test_well_formed_dict_missing_the_key_is_refused(self, tmp_path, capsys):
        good = tmp_path / "good.json"
        missing_key = tmp_path / "missing_key.json"
        _write_report(good, 10.0)
        # Valid JSON, valid dict -- just lacking the one key `rollup` reads.
        missing_key.write_text(json.dumps({"some_other_field": 1}), encoding="utf-8")

        rc = mrd.main(["rollup", "--reports", str(good), str(missing_key)])

        assert rc != 0
        captured = capsys.readouterr()
        assert captured.out == ""
        assert str(missing_key) in captured.err

    def test_non_dict_json_is_refused_not_a_raw_traceback(self, tmp_path, capsys):
        good = tmp_path / "good.json"
        non_dict = tmp_path / "non_dict.json"
        _write_report(good, 10.0)
        # Valid JSON, but not a dict -- a bare number, which `"key" not in
        # data`-style checks (or a plain `data["avoidable_pct_of_total"]`
        # lookup) would raise a `TypeError` on rather than cleanly refuse.
        non_dict.write_text("5", encoding="utf-8")

        rc = mrd.main(["rollup", "--reports", str(good), str(non_dict)])

        assert rc != 0
        captured = capsys.readouterr()
        assert captured.out == ""
        assert str(non_dict) in captured.err

    def test_non_numeric_value_is_refused(self, tmp_path, capsys):
        good = tmp_path / "good.json"
        bad_value = tmp_path / "bad_value.json"
        _write_report(good, 10.0)
        # A well-formed dict carrying the right key, but a string value --
        # `median()` over a mixed str/float list would raise, not cleanly
        # refuse.
        bad_value.write_text(
            json.dumps({"avoidable_pct_of_total": "not-a-number"}), encoding="utf-8"
        )

        rc = mrd.main(["rollup", "--reports", str(good), str(bad_value)])

        assert rc != 0
        captured = capsys.readouterr()
        assert captured.out == ""
        assert str(bad_value) in captured.err


class TestRollupRecommendationBoundary:
    def test_median_exactly_5_0_recommends_proceed(self, tmp_path, capsys):
        r1, r2, r3 = tmp_path / "r1.json", tmp_path / "r2.json", tmp_path / "r3.json"
        _write_report(r1, 4.0)
        _write_report(r2, 5.0)
        _write_report(r3, 6.0)

        rc = mrd.main(["rollup", "--reports", str(r1), str(r2), str(r3)])

        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["distribution"]["median_pct"] == 5.0
        assert out["recommendation"] == "proceed"

    def test_median_4_99_recommends_do_not_proceed(self, tmp_path, capsys):
        # Same shape as the 5.0 case above (a symmetric triple), shifted
        # down by 0.01 so the median itself lands just under the threshold.
        r1, r2, r3 = tmp_path / "r1.json", tmp_path / "r2.json", tmp_path / "r3.json"
        _write_report(r1, 3.99)
        _write_report(r2, 4.99)
        _write_report(r3, 5.99)

        rc = mrd.main(["rollup", "--reports", str(r1), str(r2), str(r3)])

        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["distribution"]["median_pct"] == 4.99
        assert out["recommendation"] == "do-not-proceed"


class TestPrivacyBoundaryCli:
    def test_sentinel_prompt_text_never_appears_in_empirical_stdout(
        self, tmp_path, capsys
    ):
        # Ports measure_full_file_duplication.py's own TestPrivacyBoundary
        # pattern: a transcript fixture carrying a distinctive string in a
        # field this script must never read (message.content), asserting
        # that string never appears in the CLI's stdout. `empirical` is the
        # only subcommand this step adds that reads a transcript at all.
        transcript, subagents_dir = _empirical_fixture(tmp_path)
        sentinel = "SENTINEL-PROMPT-TEXT-SHOULD-NEVER-SURFACE"
        (subagents_dir / "agent-abc.meta.json").write_text(
            json.dumps({"agentType": "dev-team:correctness-review"}), encoding="utf-8"
        )
        record = {
            "timestamp": "2026-08-01T19:00:00.000Z",
            "message": {
                "content": [{"type": "text", "text": sentinel}],
                "usage": {"input_tokens": 1},
            },
        }
        (subagents_dir / "agent-abc.jsonl").write_text(
            json.dumps(record), encoding="utf-8"
        )

        rc = mrd.main(["empirical", "--transcript", str(transcript)])

        assert rc == 0
        assert sentinel not in capsys.readouterr().out
