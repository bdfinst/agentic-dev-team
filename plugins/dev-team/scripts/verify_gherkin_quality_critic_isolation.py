#!/usr/bin/env python3
"""verify_gherkin_quality_critic_isolation.py — runtime isolation check for
the two-instance `gherkin-quality-critic` dispatch (issue #1465).

`/gherkin-derive` and `/gherkin-public` both dispatch **two independent
instances** of the `gherkin-quality-critic` agent in parallel — the whole
point being ensemble/self-consistency corroboration on the same judgment
call (see `knowledge/gherkin-quality-review-dispatch.md`). That mutual
blindness — "one message, two calls, read neither result until both are
issued" — is currently asserted only in prose and in content-guards that
check the markdown *says* the right thing. Nothing runs two real dispatches
and checks the isolation property held at runtime; a future refactor could
accidentally thread one instance's output into the other's prompt and
nothing would catch it.

This script closes that gap with a cross-contamination canary: each
instance's `.feature` fixture carries a distinct, randomly-generated marker
string embedded in its own context (mirroring how a real dispatch's cited
source text could carry incidental detail). Two fully independent `claude
-p` subprocess calls dispatch the real `gherkin-quality-critic` agent (via
the `/review-agent` skill) against each fixture — no shared mutable state, no
piping one call's output into the other's input. If either transcript
contains the *other* instance's canary, isolation was broken somewhere in the
dispatch path and the script fails loudly.

This intentionally diverges from production's "identical input to both
instances" property (see the dispatch doc) — seeding a distinct marker per
instance is what makes contamination observable at all. It does not change
what the two instances are asked to review (the fixture's Gherkin content is
otherwise identical); only the throwaway canary comment differs.

**Opt-in, paid, fail-open.** Mirrors `evals/README.md`'s "CI gate (issue
#99)" live-gate convention: this script dispatches the real `claude` CLI, so
it costs tokens and must never block anyone without eval credentials. When
the `claude` CLI is missing or `ANTHROPIC_API_KEY` is unset, it prints a
skip message and exits 0 — never a failure. It is not wired into any CI
workflow by this change; see `knowledge/gherkin-quality-review-dispatch.md`
for how to run it locally (or gate it into CI the same way the existing live
eval gate is: a label + `ANTHROPIC_API_KEY`).

Stdlib only. (ADR 0014/0015).

Usage:
    python3 verify_gherkin_quality_critic_isolation.py
    python3 verify_gherkin_quality_critic_isolation.py --model <model-id> --timeout 300
"""

from __future__ import annotations

import argparse
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

_DEFAULT_TIMEOUT_SECONDS = 300.0


def _default_timeout() -> float:
    """Per-dispatch subprocess timeout, overridable for local tuning."""
    raw = os.environ.get("VERIFY_GHERKIN_ISOLATION_TIMEOUT")
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return _DEFAULT_TIMEOUT_SECONDS


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        default=None,
        help="model id passed to `claude -p --model` (default: omitted, so "
        "`claude -p` uses its own configured default model — this script "
        "does not pin a snapshot; see ADR 0026)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=_default_timeout(),
        help="per-dispatch subprocess timeout in seconds "
        "(default: $VERIFY_GHERKIN_ISOLATION_TIMEOUT or 300)",
    )
    return parser.parse_args(argv)


def check_prerequisites() -> list[str]:
    """Return missing-prerequisite messages (empty == ready to dispatch)."""
    missing: list[str] = []
    if shutil.which("claude") is None:
        missing.append(
            "the `claude` CLI (npm install -g @anthropic-ai/claude-code)"
        )
    if not os.environ.get("ANTHROPIC_API_KEY"):
        missing.append("ANTHROPIC_API_KEY (required to dispatch a live agent call)")
    return missing


def build_fixture(canary: str) -> str:
    """A minimal `.feature` file with one deliberate, known finding: two
    success-path variants and no failure path at all — the exact
    "unbalanced coverage" / "missing failure path" case
    `gherkin-quality-critic` is documented to flag. `canary` is embedded as
    a throwaway leading comment, not part of the scenario content."""
    return textwrap.dedent(
        f"""\
        # isolation-canary: {canary}
        Feature: Widget creation
          As a user
          I want to create a widget
          So that I can use it later

          Scenario: Create a widget with a valid name
            Given I am authenticated
            When I create a widget named "Anvil"
            Then the widget is created successfully

          Scenario: Create a widget with a valid name and a description
            Given I am authenticated
            When I create a widget named "Anvil" with description "Heavy"
            Then the widget is created successfully
        """
    )


def build_prompt(feature_path: Path, canary: str) -> str:
    """Prompt for one dispatch. Asks the CLI to run gherkin-quality-critic
    via the shipped /review-agent skill against exactly one fixture file,
    mirroring how .github/workflows/agent-eval.yml's live gate dispatches a
    named agent through its skill wrapper rather than hand-rolling the Agent
    tool call."""
    return textwrap.dedent(
        f"""
        Use the /review-agent skill to run gherkin-quality-critic against
        exactly this one file: {feature_path}

        Pass --path {feature_path.parent} --json so stdout carries ONLY the
        agent's raw JSON result (per gherkin-quality-critic's documented
        output format in agents/gherkin-quality-critic.md) — no other prose.

        Context marker for this dispatch only: {canary}
        This marker appears in the .feature file's opening comment purely to
        verify this dispatch's isolation from any other concurrent dispatch.
        It is not part of the scenario content to review — do not mention it
        as a finding.
        """
    ).strip()


def dispatch(prompt: str, model: str | None, timeout: float) -> str | None:
    """Run one fully independent `claude -p` subprocess. Returns the raw
    captured stdout (the "transcript"), or None on any infrastructure
    problem (CLI crash, timeout, no output) — callers must treat None as
    fail-open, never as a contamination finding. `model` is only appended to
    the command when explicitly given — omitted, `claude -p` resolves its
    own configured default rather than this script pinning a snapshot."""
    cmd = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "json",
        "--max-turns",
        "30",
        "--allowedTools",
        "Read",
        "Glob",
        "Grep",
        "Skill(review-agent *)",
        "Agent",
    ]
    if model:
        cmd += ["--model", model]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(
            f"SKIP: dispatch could not run ({exc}) — treating as an "
            "infrastructure problem, not a contamination finding.",
            file=sys.stderr,
        )
        return None
    if not proc.stdout.strip():
        print(
            f"SKIP: dispatch produced no output (exit {proc.returncode}); "
            f"stderr: {proc.stderr.strip()[:300]}",
            file=sys.stderr,
        )
        return None
    return proc.stdout


def check_cross_contamination(
    transcript_a: str, transcript_b: str, canary_a: str, canary_b: str
) -> list[str]:
    """Return a list of contamination violations (empty == isolation held).

    A violation is instance A's transcript containing instance B's canary
    (or vice versa) — the marker seeded only into the OTHER instance's
    fixture context. Either direction means output/context leaked across
    the two supposedly-independent dispatches.
    """
    violations: list[str] = []
    if canary_b in transcript_a:
        violations.append(
            f"instance A's transcript contains instance B's canary marker "
            f"({canary_b}) — dispatch isolation broken"
        )
    if canary_a in transcript_b:
        violations.append(
            f"instance B's transcript contains instance A's canary marker "
            f"({canary_a}) — dispatch isolation broken"
        )
    return violations


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    missing = check_prerequisites()
    if missing:
        print(
            "SKIP: gherkin-quality-critic isolation check requires a live "
            "dispatch and cannot run here:"
        )
        for item in missing:
            print(f"  - {item}")
        print(
            "This is an opt-in, paid, live check (mirrors evals/README.md's "
            "CI gate) — skipping, not failing."
        )
        return 0

    canary_a = f"ISOLATION-CANARY-A-{secrets.token_hex(8)}"
    canary_b = f"ISOLATION-CANARY-B-{secrets.token_hex(8)}"

    with tempfile.TemporaryDirectory(prefix="gherkin-isolation-") as tmp:
        tmp_path = Path(tmp)
        dir_a = tmp_path / "instance_a"
        dir_b = tmp_path / "instance_b"
        dir_a.mkdir()
        dir_b.mkdir()
        feature_a = dir_a / "widget_creation.feature"
        feature_b = dir_b / "widget_creation.feature"
        feature_a.write_text(build_fixture(canary_a))
        feature_b.write_text(build_fixture(canary_b))

        prompt_a = build_prompt(feature_a, canary_a)
        prompt_b = build_prompt(feature_b, canary_b)

        # Two fully independent subprocess calls — no shared mutable state,
        # no piping one call's output into the other's prompt.
        transcript_a = dispatch(prompt_a, args.model, args.timeout)
        transcript_b = dispatch(prompt_b, args.model, args.timeout)

    if transcript_a is None or transcript_b is None:
        print(
            "SKIP: one or both dispatches did not produce usable output — "
            "treating as an infrastructure problem, not a contamination "
            "finding."
        )
        return 0

    violations = check_cross_contamination(
        transcript_a, transcript_b, canary_a, canary_b
    )
    if violations:
        print(
            "FAIL: cross-contamination detected between mutually-blind "
            "gherkin-quality-critic dispatches:"
        )
        for v in violations:
            print(f"  - {v}")
        return 1

    print(
        "OK: both gherkin-quality-critic dispatches completed with no "
        "cross-contamination detected."
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
