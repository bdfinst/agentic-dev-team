"""Which CI jobs actually block a merge is pinned, not assumed.

A GitHub status check has two independent halves: the job that produces it
(in `.github/workflows/`, in this tree) and the ruleset entry that makes a
red one block a merge (in repo settings, outside this tree). Nothing ties
them together, and when they disagree the failure is silent in the worst
direction — the check still runs, still reports, still shows a green tick,
and blocks nothing.

Both halves have already drifted here. Four jobs ran on every PR while the
ruleset required none of them: the `Python 3.10 floor` gate (the one ADR
0031 exists for), `Lint (ruff + eslint)`, and both docs jobs. link-check.yml
had gone further and dropped its `paths:` filter *because* its jobs were
"REQUIRED status checks" — paying to run on every PR for a guarantee it
never had.

So this file pins the two halves to `.github/required-status-checks.json`,
the in-tree mirror of the ruleset:

  - Every required context names a real job (a rename can't quietly stop
    blocking), and that job's workflow has no `paths:` filter (a required
    path-filtered check reports nothing on unrelated PRs and deadlocks them
    forever).
  - Every PR-triggered job is either required or carries a written reason
    for not being — the check that would have caught the four above when
    they were added.
  - Where an authenticated `gh` can reach the API, the mirror equals what
    the live ruleset enforces.

The last one is the only assertion that can see the settings half, and it
skips when `gh` is missing, unauthenticated, or the remote isn't this repo.
The first three are hermetic and run everywhere, including CI.

See the "deterministic tools over inference" rule in the repo CLAUDE.md.
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from _repo_root import REPO_ROOT

yaml = pytest.importorskip("yaml")

WORKFLOWS = REPO_ROOT / ".github" / "workflows"
MANIFEST = REPO_ROOT / ".github" / "required-status-checks.json"

#: The live-ruleset assertion only means anything against the repo whose
#: settings the manifest describes. A fork (or a clone with a renamed remote)
#: has its own rules, so it skips rather than failing on someone else's config.
CANONICAL_REMOTE = "bdfinst/agentic-dev-team"
DEFAULT_BRANCH = "main"
GH_TIMEOUT_SECONDS = 20


def _load_workflow(path):
    """A workflow's parsed YAML, with the `on:` key resolved.

    YAML 1.1 reads a bare `on` as the boolean True, so `d["on"]` is a
    KeyError on every workflow in this repo — the trigger block lands under
    `d[True]` instead.
    """
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    triggers = data.get("on", data.get(True)) or {}
    return data, triggers


def _pr_jobs():
    """Every job that a pull_request event can start, as
    (context, workflow_filename, is_path_filtered).

    `context` is the job's `name:` — the string the ruleset matches on —
    falling back to the job id, which is what GitHub reports when a job
    declares no name.
    """
    jobs = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        data, triggers = _load_workflow(path)
        if not isinstance(triggers, dict) or "pull_request" not in triggers:
            continue
        pr = triggers["pull_request"] or {}
        path_filtered = isinstance(pr, dict) and bool(
            pr.get("paths") or pr.get("paths-ignore")
        )
        for job_id, job in (data.get("jobs") or {}).items():
            jobs.append((job.get("name") or job_id, path.name, path_filtered))
    return jobs


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def pr_jobs():
    return _pr_jobs()


class TestTheManifestDescribesRealJobs:
    def test_every_required_context_names_a_pr_triggered_job(self, manifest, pr_jobs):
        """A required context that matches no job never reports, and GitHub
        blocks the PR forever waiting for a status that can't arrive. This is
        also the rename guard: renaming a job without updating the manifest
        (and the ruleset) fails here."""
        contexts = {name for name, _, _ in pr_jobs}
        missing = [c for c in manifest["required"] if c not in contexts]
        assert not missing, (
            f"required status checks naming no PR-triggered job: {missing}. "
            "A required context that never reports blocks every PR "
            "indefinitely — if a job was renamed, update .github/"
            "required-status-checks.json AND the `main` ruleset together"
        )

    def test_no_required_context_comes_from_a_path_filtered_workflow(
        self, manifest, pr_jobs
    ):
        """A path-filtered workflow reports NO status on a PR that doesn't
        match its filter — not a skip, nothing at all — so a required check
        from one deadlocks every unrelated PR. agent-eval.yml and
        link-check.yml both dropped their filters for exactly this reason;
        this is what keeps a future filter from being added back."""
        filtered = {name: wf for name, wf, is_filtered in pr_jobs if is_filtered}
        offenders = {c: filtered[c] for c in manifest["required"] if c in filtered}
        assert not offenders, (
            f"required status checks from path-filtered workflows: {offenders}. "
            "Requiring one deadlocks every PR that doesn't touch its paths — "
            "drop the filter (the job must be cheap enough to always run) or "
            "drop the requirement"
        )

    def test_every_exemption_names_a_real_job(self, manifest, pr_jobs):
        """A stale exemption is a hole with a reason attached: the job it
        described is gone, and the next job to inherit that name inherits
        its pass."""
        contexts = {name for name, _, _ in pr_jobs}
        stale = [c for c in manifest["exempt"] if c not in contexts]
        assert not stale, (
            f"exemptions naming no PR-triggered job: {stale} — delete them, or "
            "correct the name if the job was renamed"
        )

    def test_the_required_list_has_no_duplicates(self, manifest):
        required = manifest["required"]
        assert len(required) == len(set(required)), (
            f"duplicate entries in the required list: {sorted({c for c in required if required.count(c) > 1})}"
        )


class TestEveryPrJobIsRequiredOrExplicitlyNot:
    def test_no_pr_job_is_silently_non_blocking(self, manifest, pr_jobs):
        """The recurrence guard. Four jobs reported on every PR for months
        while blocking nothing, because adding a job to a workflow and adding
        it to the ruleset are unrelated acts and nobody reconciled them. Now
        a new PR-triggered job fails this until it is either required or
        exempted with a stated reason — the decision becomes explicit at the
        moment the job is written, not months later."""
        known = set(manifest["required"]) | set(manifest["exempt"])
        unclassified = sorted(
            {f"{name} ({wf})" for name, wf, _ in pr_jobs if name not in known}
        )
        assert not unclassified, (
            f"PR-triggered jobs that neither block a merge nor say why not: "
            f"{unclassified}. Add each to .github/required-status-checks.json — "
            "to `required` (and to the `main` ruleset), or to `exempt` with the "
            "reason it should report without blocking"
        )

    def test_every_exemption_states_a_reason(self, manifest):
        """An empty reason is an exemption nobody has to defend."""
        blank = sorted(k for k, v in manifest["exempt"].items() if not str(v).strip())
        assert not blank, f"exemptions with no stated reason: {blank}"


def _contexts_from_branch_rules(rules) -> set[str]:
    """The contexts a branch's effective rules require.

    Split out from the API call so both of its branches are reachable
    without a network: an empty result here means every check on every PR is
    advisory, which is the one drift a *present* ruleset can't express.
    """
    contexts: set[str] = set()
    found_rule = False
    for rule in rules:
        if rule.get("type") != "required_status_checks":
            continue
        found_rule = True
        params = rule.get("parameters") or {}
        contexts |= {c["context"] for c in params.get("required_status_checks", [])}

    assert found_rule, (
        f"`{DEFAULT_BRANCH}` enforces no required_status_checks rule at all — "
        "every check on every PR is advisory. Restore the rule in the repo's "
        "ruleset settings"
    )
    return contexts


def _live_required_contexts() -> set[str]:
    """What the `main` branch's rules actually enforce right now.

    Skips — never fails — when the settings half is simply unreachable: no
    `gh`, no auth, no network, a fork's remote. Only a successful API
    response that disagrees with the manifest is a failure, so this can't
    flake a pre-push run into red.
    """
    if shutil.which("gh") is None:
        pytest.skip("gh CLI not installed — cannot read the live ruleset")

    remote = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=GH_TIMEOUT_SECONDS,
    )
    if remote.returncode != 0 or CANONICAL_REMOTE not in remote.stdout:
        pytest.skip(
            f"origin is not {CANONICAL_REMOTE} — a fork's rules are its own business"
        )

    # The effective-rules endpoint, not the ruleset list: it returns what
    # actually applies to the branch, so a second ruleset (or a renamed one)
    # is still accounted for.
    proc = subprocess.run(
        ["gh", "api", f"repos/{{owner}}/{{repo}}/rules/branches/{DEFAULT_BRANCH}"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=GH_TIMEOUT_SECONDS,
    )
    if proc.returncode != 0:
        pytest.skip(f"gh api unavailable ({proc.stderr.strip()[:200]})")

    return _contexts_from_branch_rules(json.loads(proc.stdout))


class TestTheRuleReaderItself:
    """The live assertion is only as good as its reading of the API payload,
    and a payload that says "nothing is required" is exactly the case a
    live-only test can never reach on a healthy repo."""

    def test_it_collects_contexts_across_every_applicable_rule(self):
        rules = [
            {"type": "deletion"},
            {
                "type": "required_status_checks",
                "parameters": {"required_status_checks": [{"context": "A"}]},
            },
            {
                "type": "required_status_checks",
                "parameters": {"required_status_checks": [{"context": "B"}]},
            },
        ]
        assert _contexts_from_branch_rules(rules) == {"A", "B"}

    def test_it_fails_when_the_branch_requires_nothing(self):
        """A ruleset deleted or stripped of its status-check rule leaves
        every check advisory — the loudest possible drift, and silent unless
        something asserts on it."""
        with pytest.raises(AssertionError, match="no required_status_checks rule"):
            _contexts_from_branch_rules([{"type": "deletion"}])

    def test_an_empty_context_list_is_not_a_pass(self):
        """A rule present but emptied of contexts must not read as agreement
        with a non-empty manifest."""
        rules = [
            {
                "type": "required_status_checks",
                "parameters": {"required_status_checks": []},
            }
        ]
        assert _contexts_from_branch_rules(rules) == set()


class TestTheLiveRulesetMatchesTheManifest:
    """The only assertion here that can see repo settings. It answers the
    question the hermetic tests structurally cannot: is the ruleset still
    what this tree says it is?"""

    def test_the_ruleset_requires_exactly_the_manifest_contexts(self, manifest):
        live = _live_required_contexts()
        declared = set(manifest["required"])
        assert live == declared, (
            "the `main` ruleset and .github/required-status-checks.json "
            "disagree.\n"
            f"  required by the ruleset but not declared: {sorted(live - declared)}\n"
            f"  declared but not required by the ruleset: {sorted(declared - live)}\n"
            "The second list is the dangerous one: those checks report on "
            "every PR and block nothing."
        )
