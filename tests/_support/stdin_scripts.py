"""Shared table of the eight entry points that read stdin by default.

Each row names a script (path relative to ``plugins/dev-team``), the argv that
invokes it with its input flag absent, that input flag, a fixed piped fixture,
and the exit status, stdout and stderr fragment the *unmodified* script gave for
that fixture and for ``/dev/null`` (captured before the stdin guard was wired
in, twice, to prove the values are stable). ``orchestrator.py`` has no input
flag and falls back to a default request, so its ``flag`` is ``None`` and
``needs_flag`` is False.

A ``stderr_fragment`` is a literal substring of the expected stderr; ``None``
means the script printed nothing worth pinning, and the row only asserts the
guard's refusal marker is absent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

#: Stands in for the working directory in a stdout golden. The test replaces
#: the real (resolved) directory with this token before comparing, so a golden
#: never embeds a machine-specific path.
CWD_PLACEHOLDER = "<CWD>"


@dataclass(frozen=True)
class Golden:
    exit_status: int
    stdout: str
    stderr_fragment: str | None = None


@dataclass(frozen=True)
class StdinScript:
    script: str
    argv: tuple[str, ...]
    flag: str | None
    fixture: str
    piped: Golden
    devnull: Golden

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

#: The one fixture above 64 KiB: a PR body whose only finding sits after
#: ~72 KB of filler, so a reader that stops early changes the output.
LARGE_FIXTURE_SCRIPT = "scripts/pr_close_keyword_lint.py"
_LARGE_PR_BODY_FIXTURE = "filler line\n" * 6000 + "This does not close #7\n"

_ORCHESTRATOR_RUNS = "INFO: dispatching persona codebase-recon\n"

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
            "{\n"
            '  "base_ref": "HEAD",\n'
            '  "complete": false,\n'
            '  "files_included": [],\n'
            '  "files_omitted": [\n'
            "    {\n"
            '      "file": "a.py",\n'
            '      "reason": "not present in the working tree (deleted or renamed)"\n'
            "    },\n"
            "    {\n"
            '      "file": "b.py",\n'
            '      "reason": "not present in the working tree (deleted or renamed)"\n'
            "    }\n"
            "  ],\n"
            '  "files_requested": 2,\n'
            '  "pack_bytes": 906,\n'
            f'  "path": "{CWD_PLACEHOLDER}/.claude/review-context/pack-088cd6e739f60ee1.md",\n'
            '  "unique_body_bytes": 0\n'
            "}\n",
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
        LARGE_FIXTURE_SCRIPT,
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
        "scripts/orchestrator.py",
        ("--skip-llm",),
        None,
        "add a login page\n",
        piped=Golden(0, "", _ORCHESTRATOR_RUNS),
        devnull=Golden(0, "", _ORCHESTRATOR_RUNS),
    ),
)
