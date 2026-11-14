"""Shared table of the entry points that read stdin by default or on a `-` flag value.

Each row names a script (path relative to ``plugins/dev-team``), the argv that
invokes it with its input flag absent, that input flag, a fixed piped fixture,
and the exit status, stdout and stderr fragment the *unmodified* script gave for
that fixture and for ``/dev/null`` (captured before the stdin guard was wired
in, twice, to prove the values are stable). ``orchestrator.py`` has no input
flag and falls back to a default request, so its ``flag`` is ``None``,
``needs_flag`` is False and it has no subprocess goldens (``piped`` and
``devnull`` are ``None``); its stdin handling is covered in-process.

A ``stderr_fragment`` is a literal substring of the expected stderr; ``None``
means the script printed nothing worth pinning, and the row only asserts the
guard's refusal marker is absent. ``json_keys`` limits a stdout golden to the
named keys of its JSON object, for output that embeds unstable values.

``INPUT_FLAGS`` is the single table of every flag that lets a script skip
stdin, including flags that apply only to some ``--mode`` values.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from tests._support.skill_calls import InputFlag


@dataclass(frozen=True)
class Golden:
    exit_status: int
    stdout: str
    stderr_fragment: str | None = None
    json_keys: tuple[str, ...] | None = None


@dataclass(frozen=True)
class StdinFlag(InputFlag):
    """An ``InputFlag`` plus the argv that makes the script read stdin through
    it. Empty for a row's primary flag, whose argv is the row's own."""

    stdin_argvs: tuple[tuple[str, ...], ...] = ()


#: Every flag that lets a script skip stdin. ``--from`` is the input of
#: ``checkpoint_abort.py --mode outcome|merge``; ``--cheap-results-from`` is
#: the input of ``--mode abort`` (the default). ``--name-status-from`` with a
#: file argument means ``--files-from`` is never read.
INPUT_FLAGS: tuple[StdinFlag, ...] = (
    StdinFlag("change_impact.py", "--diff-from"),
    StdinFlag("finding_signature.py", "--findings"),
    StdinFlag("review_context_pack.py", "--files-from"),
    StdinFlag(
        "review_context_pack.py",
        "--name-status-from",
        stdin_argvs=(("--name-status-from", "-"),),
    ),
    StdinFlag("render_tiered_findings.py", "--findings"),
    StdinFlag(
        "checkpoint_abort.py",
        "--cheap-results-from",
        mode_option="--mode",
        modes=("abort",),
        default_mode="abort",
    ),
    StdinFlag(
        "checkpoint_abort.py",
        "--from",
        mode_option="--mode",
        modes=("outcome", "merge"),
        default_mode="abort",
        stdin_argvs=(("--mode", "outcome"), ("--mode", "merge")),
    ),
    StdinFlag("pr_close_keyword_lint.py", "--body-file"),
    StdinFlag("autoship_queue.py", "--input-file"),
    StdinFlag("sql_anti_patterns.py", "--files-from", stdin_only_on_dash=True),
    StdinFlag("sql_review_roster.py", "--files-from", stdin_only_on_dash=True),
    StdinFlag("select_lenses.py", "--files-from", stdin_only_on_dash=True),
    StdinFlag(
        "select_lenses.py",
        "--added-from",
        stdin_only_on_dash=True,
        stdin_argvs=(("--added-from", "-"),),
    ),
    StdinFlag("autoship_proposals.py", "--agent-response-file", stdin_only_on_dash=True),
    StdinFlag("review_round_log.py", "--findings", stdin_only_on_dash=True),
    StdinFlag(
        "review_round_log.py",
        "--fix-diff",
        stdin_only_on_dash=True,
        stdin_argvs=(("--fix-diff", "-"),),
    ),
    StdinFlag("change_size.py", "--numstat-from", stdin_only_on_dash=True),
    StdinFlag("changed_file_list.py", "--name-status-from", stdin_only_on_dash=True),
    StdinFlag("change_shape.py", "--files-from", stdin_only_on_dash=True),
    StdinFlag("validate_review_output.py", "--file", stdin_only_on_dash=True),
    StdinFlag("mutation_feasibility_gate.py", "--v3-findings-json", stdin_only_on_dash=True),
)


@dataclass(frozen=True)
class StdinScript:
    script: str
    argv: tuple[str, ...]
    flag: str | None
    fixture: str
    piped: Golden | None
    devnull: Golden | None
    #: Argv that makes a script read stdin only on an explicit ``-`` (appended
    #: when no input file is given). Empty for a script that reads stdin by default.
    stdin_argv: tuple[str, ...] = ()

    @property
    def needs_flag(self) -> bool:
        return self.flag is not None


_DIFF_FIXTURE = (
    "diff --git a/src/a.py b/src/a.py\n"
    "--- a/src/a.py\n"
    "+++ b/src/a.py\n"
    "@@ -1 +1,2 @@\n"
    " import os\n"
    "+import sys\n"
)

_FINDINGS_FIXTURE = json.dumps(
    [
        {
            "agent": "x",
            "file": "a.py",
            "line": 1,
            "severity": "error",
            "confidence": "high",
            "message": "m",
            "suggestedFix": "f",
        }
    ]
)

_CHEAP_RESULTS_FIXTURE = json.dumps(
    [{"agent": "a", "issues": [{"severity": "error", "confidence": "high"}]}]
)

_GROUPING_FIXTURE = json.dumps(
    {"batches": [], "ungrouped": [{"number": 1, "createdAt": "2026-01-01T00:00:00Z"}]}
)

#: Larger than a pipe buffer (64 KiB): a PR body whose only finding sits after
#: ~72 KB of filler, so a reader that stops early changes the output.
_LARGE_PR_BODY_FIXTURE = "filler line\n" * 6000 + "This does not close #7\n"

#: The stderr line ``orchestrator.py --skip-llm`` prints before it dispatches.
ORCHESTRATOR_RUNS_STDERR = "INFO: dispatching persona codebase-recon\n"

_SELECT_LENSES_OUTPUT = (
    '{"lenses": ["concurrency-review", "doc-review", "naming-review", '
    '"performance-review", "spec-compliance-review", "structure-review", '
    '"test-review", "arch-review", "correctness-review", "domain-review", '
    '"security-review"], "warnings": []}\n'
)

_REVIEW_OUTPUT_FIXTURE = '{"status":"pass","summary":"ok","issues":[]}'
_REVIEW_OUTPUT_VALID = (
    '{"agent": "x", "error": null, "extraction": "clean", "shape": "clean", '
    '"valid": true}\n'
)
_REVIEW_OUTPUT_EMPTY = (
    '{"agent": "x", "error": "output was empty or whitespace-only", '
    '"extraction": null, "shape": "empty", "valid": false}\n'
)

STDIN_SCRIPTS: tuple[StdinScript, ...] = (
    StdinScript(
        "skills/code-review/scripts/change_impact.py",
        ("--files", "a.py"),
        "--diff-from",
        _DIFF_FIXTURE,
        piped=Golden(
            0,
            '{"hasArchitecturalImpact": true, "reason": null, "signals": ["dependency"], '
            '"skipLenses": ["concurrency-review"]}\n',
        ),
        devnull=Golden(
            0,
            '{"hasArchitecturalImpact": true, "reason": "diff-not-parseable-assuming-impact", '
            '"signals": [], "skipLenses": []}\n',
        ),
    ),
    StdinScript(
        "skills/code-review/scripts/finding_signature.py",
        ("--round", "1"),
        "--findings",
        _FINDINGS_FIXTURE,
        piped=Golden(
            0,
            '{"actionable_new": 1, "carried": 0, "ledger_reset": null, "new": 1, '
            '"reason": null, "round": 1, "terminate": false}\n',
        ),
        devnull=Golden(
            0,
            '{"actionable_new": 0, "carried": 0, "ledger_reset": null, "new": 0, '
            '"reason": "converged", "round": 1, "terminate": true}\n',
        ),
    ),
    StdinScript(
        "skills/code-review/scripts/review_context_pack.py",
        (),
        "--files-from",
        "a.py\nb.py\n",
        piped=Golden(
            0,
            json.dumps(
                {
                    "base_ref": "HEAD",
                    "complete": False,
                    "files_omitted": [
                        {
                            "file": "a.py",
                            "reason": "not present in the working tree (deleted or renamed)",
                        },
                        {
                            "file": "b.py",
                            "reason": "not present in the working tree (deleted or renamed)",
                        },
                    ],
                    "files_requested": 2,
                }
            ),
            json_keys=("base_ref", "complete", "files_omitted", "files_requested"),
        ),
        devnull=Golden(1, '{"error": "no files given", "path": null}\n'),
    ),
    StdinScript(
        "skills/code-review/scripts/render_tiered_findings.py",
        (),
        "--findings",
        _FINDINGS_FIXTURE,
        piped=Golden(
            0,
            "a.py:1 [x] error/high — m (x:a.py:1:error)\n"
            "Expand a finding with --expand <finding-id>, or --expand all for every finding.\n",
        ),
        devnull=Golden(0, "Clean pass: 0 findings this round — nothing to expand.\n"),
    ),
    StdinScript(
        "scripts/checkpoint_abort.py",
        (),
        "--cheap-results-from",
        _CHEAP_RESULTS_FIXTURE,
        piped=Golden(
            0,
            '{"aborted": true, "triggeringFinding": {"severity": "error", "confidence": "high"}, '
            '"triggeringAgent": "a", "deferredLenses": []}\n',
        ),
        devnull=Golden(1, "", "cheap-tier results are not valid JSON"),
    ),
    StdinScript(
        "scripts/pr_close_keyword_lint.py",
        (),
        "--body-file",
        _LARGE_PR_BODY_FIXTURE,
        piped=Golden(
            0,
            'warning: issue #7 (negated-closing-keyword): "This does not close #7"\n',
        ),
        devnull=Golden(0, ""),
    ),
    StdinScript(
        "scripts/autoship_queue.py",
        ("--max-issues", "5"),
        "--input-file",
        _GROUPING_FIXTURE,
        piped=Golden(0, '{"queue": [{"type": "solo", "issue": 1}], "deferred": []}\n'),
        devnull=Golden(1, "", "grouping output is not valid JSON"),
    ),
    StdinScript(
        "scripts/sql_anti_patterns.py",
        (),
        "--files-from",
        "a.sql\n",
        piped=Golden(
            2,
            '{"findings": [], "errors": ["cannot read a.sql: No such file or directory"], '
            '"skipped_fragments": {}}\n',
        ),
        devnull=Golden(
            0, '{"findings": [], "errors": [], "skipped_fragments": {}}\n'
        ),
        stdin_argv=("--files-from", "-"),
    ),
    StdinScript(
        "scripts/sql_review_roster.py",
        (),
        "--files-from",
        "a.sql\n",
        piped=Golden(
            0,
            '{"dispatch": true, "status": "ok", "message": "", "hits": [], '
            '"errors": ["cannot read a.sql: No such file or directory"], '
            '"skipped_fragments": {}, "dispatchFailure": null}\n',
        ),
        devnull=Golden(
            0,
            '{"dispatch": false, "status": "ok", "message": "", "hits": [], '
            '"errors": [], "skipped_fragments": {}, "dispatchFailure": null}\n',
        ),
        stdin_argv=("--files-from", "-"),
    ),
    StdinScript(
        "scripts/select_lenses.py",
        ("--files", "x.py"),
        "--files-from",
        "a.py\n",
        piped=Golden(0, _SELECT_LENSES_OUTPUT),
        devnull=Golden(0, _SELECT_LENSES_OUTPUT),
        stdin_argv=("--files-from", "-"),
    ),
    StdinScript(
        "scripts/autoship_proposals.py",
        ("validate-proposals", "--ungrouped-file", "/dev/null"),
        "--agent-response-file",
        "[]",
        piped=Golden(1, "", "'/dev/null' is not valid JSON"),
        devnull=Golden(1, "", "'/dev/null' is not valid JSON"),
        stdin_argv=("--agent-response-file", "-"),
    ),
    StdinScript(
        "skills/code-review/scripts/review_round_log.py",
        (
            "--round",
            "1",
            "--purpose",
            "discovery",
            "--outcome",
            "no-op",
            "--dry-run",
        ),
        "--findings",
        "[]",
        piped=Golden(
            0,
            '{"findings_new": 0, "outcome": "no-op", "round": 1}',
            json_keys=("findings_new", "outcome", "round"),
        ),
        devnull=Golden(
            0,
            '{"findings_new": 0, "outcome": "no-op", "round": 1}',
            json_keys=("findings_new", "outcome", "round"),
        ),
        stdin_argv=("--findings", "-"),
    ),
    StdinScript(
        "skills/code-review/scripts/change_size.py",
        (),
        "--numstat-from",
        "3\t1\ta.py\n",
        piped=Golden(
            0,
            '{"addedLines": 3, "filesChanged": 1, "keepAgents": ["security-review", '
            '"correctness-review", "spec-compliance-review", "doc-review"], '
            '"qualifiesForFastPath": true}\n',
        ),
        devnull=Golden(
            0,
            '{"addedLines": 0, "filesChanged": 0, "keepAgents": [], '
            '"qualifiesForFastPath": false}\n',
        ),
        stdin_argv=("--numstat-from", "-"),
    ),
    StdinScript(
        "skills/code-review/scripts/changed_file_list.py",
        (),
        "--name-status-from",
        "M\ta.py\n",
        piped=Golden(0, '{"added": [], "files": [{"path": "a.py", "status": "M"}]}\n'),
        devnull=Golden(0, '{"added": [], "files": []}\n'),
        stdin_argv=("--name-status-from", "-"),
    ),
    StdinScript(
        "skills/code-review/scripts/change_shape.py",
        (),
        "--files-from",
        "a.py\n",
        piped=Golden(
            0,
            '{"hasRuntimeSurface": true, "isProseOnly": false, "isTestOnly": false, '
            '"skipLenses": []}\n',
        ),
        devnull=Golden(
            0,
            '{"hasRuntimeSurface": false, "isProseOnly": false, "isTestOnly": false, '
            '"skipLenses": []}\n',
        ),
        stdin_argv=("--files-from", "-"),
    ),
    StdinScript(
        "skills/code-review/scripts/validate_review_output.py",
        ("--agent", "x", "--dry-run"),
        "--file",
        _REVIEW_OUTPUT_FIXTURE,
        piped=Golden(0, _REVIEW_OUTPUT_VALID),
        devnull=Golden(1, _REVIEW_OUTPUT_EMPTY),
        stdin_argv=("--file", "-"),
    ),
    StdinScript(
        "skills/mutation-testing/scripts/mutation_feasibility_gate.py",
        (),
        "--v3-findings-json",
        '{"findings": []}',
        piped=Golden(
            0,
            '{\n  "outcome": "enter-loop",\n  "reason": "per-test capture works and the '
            'estimated round 0s is within the 1800s budget",\n  "estimated_round_seconds": 0.0,'
            '\n  "budget_seconds": 1800.0,\n  "question": null,\n  "waiver": null\n}\n',
        ),
        devnull=Golden(2, "", "cannot read --v3-findings-json"),
        stdin_argv=("--v3-findings-json", "-"),
    ),
    StdinScript(
        "scripts/orchestrator.py",
        ("--skip-llm",),
        None,
        "add a login page\n",
        piped=None,
        devnull=None,
    ),
)
