"""#2080 — a huge local-transcript token count must not abort extraction.

`_NUM_MAX`/`_safe_number` (session_report.py) were written to guard
the PEER-digest ingestion path (`_read_synced_records` -> `rollup()`). A
second, structurally identical `round(cost * 1e6)` sits on the LOCAL-transcript
extraction path (`_accumulate_token_signals` -> `_cost`), reading
`usage.get("input_tokens")` etc. directly out of a transcript file with no
bound at all.

`_cost`'s `inp / 1e6 * ir` promotes `inp` through Python's int-to-float
conversion for true division; an integer whose magnitude exceeds
`sys.float_info.max` (legal JSON, no wire-size limit) raises `OverflowError`
there, aborting `extract` for the whole file before `round()` is even
reached — a single corrupted transcript denies the whole run, the same
failure class #2079/#2016 closed on the peer-digest path, in a different
trust domain (a transcript this script does not author, per
`_iter_records`'s own comment).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from _repo_root import REPO_ROOT

EXTRACT = REPO_ROOT / "plugins" / "dev-team" / "scripts" / "session_report.py"
PLUGIN = REPO_ROOT / "plugins" / "dev-team"
SESSION_ID = "22222222-3333-4444-5555-666666666666"

# Larger in magnitude than sys.float_info.max (~1.8e308) -- legal JSON, no
# wire-size limit, but int-to-float conversion overflows on it.
_HUGE_TOKEN_COUNT = 10**400


def _assistant(usage: dict) -> dict:
    return {
        "type": "assistant",
        "sessionId": SESSION_ID,
        "cwd": "/tmp/fixture/project",
        "timestamp": "2026-08-27T12:00:00Z",
        "isSidechain": False,
        "message": {
            "role": "assistant",
            "model": "claude-sonnet-5",
            "content": [{"type": "text", "text": "hi"}],
            "usage": usage,
        },
    }


def _run(transcript: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(EXTRACT), "--profile", "maintainer",
            "--transcript",
            str(transcript),
            "--plugin-root",
            str(PLUGIN),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def _write(path: Path, records: list[dict]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


def test_oversized_input_tokens_does_not_abort_extraction(tmp_path: Path) -> None:
    transcript = tmp_path / f"{SESSION_ID}.jsonl"
    _write(
        transcript,
        [
            _assistant(
                {
                    "input_tokens": _HUGE_TOKEN_COUNT,
                    "output_tokens": 20,
                    "cache_creation_input_tokens": 30,
                    "cache_read_input_tokens": 40,
                }
            )
        ],
    )
    result = _run(transcript)
    assert result.returncode == 0, result.stdout + result.stderr
    digest = json.loads(result.stdout)
    # Clamped to 0, not left at the hostile magnitude and not aborting.
    assert digest["token"]["totals"]["input_tokens"] == 0
    assert digest["token"]["totals"]["output_tokens"] == 20


def test_negative_token_count_does_not_corrupt_the_running_total(
    tmp_path: Path,
) -> None:
    """Two records in one transcript: the second's negative count must not
    subtract from the first's genuine total -- same corruption class as
    #2079, single-host here rather than cross-host."""
    transcript = tmp_path / f"{SESSION_ID}.jsonl"
    _write(
        transcript,
        [
            _assistant(
                {
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "cache_creation_input_tokens": 30,
                    "cache_read_input_tokens": 40,
                }
            ),
            _assistant(
                {
                    "input_tokens": -500,
                    "output_tokens": 20,
                    "cache_creation_input_tokens": 30,
                    "cache_read_input_tokens": 40,
                }
            ),
        ],
    )
    result = _run(transcript)
    assert result.returncode == 0, result.stdout + result.stderr
    digest = json.loads(result.stdout)
    assert digest["token"]["totals"]["input_tokens"] == 100
