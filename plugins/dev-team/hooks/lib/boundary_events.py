"""boundary_events.py — shared boundary-level telemetry emit helper (#859).

Records the decision process of the plugin's guard hooks (policy-gateway
events, per *Code as Agent Harness* §3.5.1): which hook, on which tool,
decided what, because of which rule. Complements `telemetry.py`
(command/skill/gate invocation counts) and `cost_meter.py` (per-agent
token/cost) as the third, boundary-level channel.

ALWAYS-ON: unlike `telemetry.py`, this stream is not gated by
`DEV_TEAM_TELEMETRY` consent — it is a local-only, rule-IDs-only safety /
accountability record (Ambiguity Log, issue #859). Never write free text:
command text, prompt text, file paths, or reasons must never appear in a
`matched_rule` value — only rule IDs from closed vocabularies.

Fail-open: every exception is swallowed. A full disk, read-only
`.claude/metrics/`, or malformed state must never change the calling
hook's stdout, stderr, or exit code.

Stdlib only. See ADR 0014 / ADR 0015.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import artifact_paths

_LOG_NAME = "boundary-events.jsonl"


# The single source of truth for this stream's `ts` format (#1461 structure
# review). `hooks/lib/review_gate_corroboration.py` imports this directly
# rather than re-declaring its own literal — its lexical since/until
# comparison over `ts` strings is only correct because every emitter uses
# this exact format, so a format change must move both modules in lockstep,
# not by convention/comment alone.
TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _isoformat_utc() -> str:
    return datetime.now(timezone.utc).strftime(TS_FORMAT)


def _load_plugin_version() -> str:
    # hooks/lib/boundary_events.py -> hooks/lib -> hooks -> plugin root
    manifest = Path(__file__).resolve().parents[2] / ".claude-plugin" / "plugin.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        version = data.get("version")
        if isinstance(version, str) and version:
            return version
    except (OSError, ValueError):
        pass
    return "unknown"


def emit_boundary_event(
    cwd,
    hook: str,
    tool: str,
    decision: str,
    matched_rule: str,
    session_id: str | None = None,
    subject_hash: str | None = None,
    subject_hash_normalized: str | None = None,
) -> None:
    """Append one compact JSON line to
    `<cwd>/.claude/metrics/boundary-events.jsonl`.

    Fail-open: any error (bad `cwd`, unwritable `.claude/metrics/`, disk
    full, etc.) is swallowed silently — this must never affect the
    caller's exit code, stdout, or stderr.

    Args:
        cwd: Directory whose `.claude/metrics/` subdirectory receives the
            event. Accepts `str` or `Path`.
        hook: Emitting hook's module name (e.g. "destructive_guard").
        tool: Hooked tool / event name (e.g. "Bash", "UserPromptSubmit").
        decision: One of "block", "warn", "bypass", "intervention", "revert",
            "record", "dispatch-failure". "record" (#1461) is a non-verdict,
            observational entry — it does not block/warn/bypass/intervene/
            revert anything, it merely notes that a genuine, registered
            review-agent dispatch occurred (emitted by
            `agent_dispatch_ledger.py`). "dispatch-failure" (#1763) is also
            non-verdict-counted, observational — it notes that a dispatched
            review agent failed to return a contract-valid result even after
            one retry. Unlike "record" it is designed to be consumed ONLY as
            NEGATIVE evidence, by a gate veto in
            `hooks/lib/review_gate_corroboration.py` (a later slice of the
            same #1763 epic this event's write side landed in — until that
            read path exists, this event is write-only telemetry with no
            consumer), so a forged event can only ever narrow corroboration,
            never widen it. Exclude both from verdict counts; see
            `knowledge/telemetry-schema.md`.
        matched_rule: A rule ID from a closed vocabulary — never free
            text (no command text, prompt text, file paths, or reasons).
        session_id: Optional opaque session ID from the hook payload,
            enabling per-session joins with session-digest.jsonl.
        subject_hash: Optional `review_gate_hash()` value (#1461) binding
            this event to the specific staged-content hash it corroborates
            — not free text (a hex digest carries no path/prompt/reason
            information), but a derived value naming what was reviewed.
            `hooks/lib/review_gate_corroboration.py` requires this to match
            the gate's current hash before treating a "record" or exemption
            event as corroborating evidence, so a genuine dispatch/exemption
            for one diff can't satisfy the gate for a different, unrelated
            one.
        subject_hash_normalized: Optional `normalized_gate_hash()` value
            (#1627) — the same binding, computed over the staged patch after
            doc-hunk and indentation normalization. Lets the gate carry
            corroboration forward across a re-stage that provably changed no
            behavior, without a fresh dispatch whose only purpose is to feed
            the ledger. Like `subject_hash`, a derived digest carrying no
            path/prompt/reason information. Events written before this field
            existed simply never match on the normalized path — the same
            backward-compat posture `subject_hash` itself has.
    """
    try:
        base = Path(cwd) if cwd else Path.cwd()
        log = artifact_paths.resolve_file("metrics", _LOG_NAME, base)
        log.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "ts": _isoformat_utc(),
            "hook": hook,
            "tool": tool,
            "decision": decision,
            "matched_rule": matched_rule,
            "plugin_version": _load_plugin_version(),
        }
        if session_id:
            payload["session_id"] = session_id
        if subject_hash:
            payload["subject_hash"] = subject_hash
        if subject_hash_normalized:
            payload["subject_hash_normalized"] = subject_hash_normalized

        with open(log, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, separators=(",", ":")) + "\n")
    except Exception:  # noqa: BLE001, S110 — fail-open by design, see module docstring
        pass


# Fixed (hook, tool, decision, matched_rule) tuples the CLI may emit — see
# `_main()`'s docstring. This is a closed set, not a free-form pass-through:
# a skill invoking this CLI picks one of these named events, it can never
# supply its own hook/tool/decision/matched_rule. In particular, "record"
# (the decision `agent_dispatch_ledger.py` uses) is not reachable from this
# CLI at all — only the real PreToolUse hook can emit it — closing a
# ledger-forgery vector security review found in an earlier draft (#1461):
# an unrestricted CLI writer could otherwise fabricate arbitrary dispatch
# evidence, including fake "record" rows for unregistered agent names,
# byte-identical to genuine hook output.
#
# Bounded exception (#1763): `--event dispatch-failure` (below, handled by
# its own branch in `_main()`, via `_CLI_AGENT_EVENTS`, not this dict) is
# deliberately NOT a fixed tuple — it carries one piece of caller-supplied,
# per-invocation data (the failed agent's name) as `matched_rule`, which a
# static tuple can't express. This is still safe BY DESIGN, independent of
# whether the read side has landed yet: the decision value it writes
# ("dispatch-failure") is intended to be consumed ONLY as negative evidence,
# by a gate veto in `hooks/lib/review_gate_corroboration.py` — never as
# corroborating evidence for a `.review-passed` write — so a forged/hand-run
# invocation can only ever narrow corroboration (cause a false block on a
# gate that would otherwise pass), never widen it (cause a false pass), once
# that veto exists. Until the veto's read path lands (a later slice of this
# same epic), this event is inert write-only telemetry — no code path
# consumes it yet, so it can neither cause a false block nor prevent one;
# the safety property above describes the design's intended end state, not
# a claim that enforcement is already wired up. The opposite forgery
# direction from "record" either way. The agent name is still validated at
# write time against the registered review-agent set
# (`review_agent_registry.registered_review_agent_names`, with the same
# plugin-prefix normalization `agent_dispatch_ledger.py` applies), matching
# that hook's own posture: an unregistered name is silently NOT recorded,
# never written even as a rejected/flagged entry.
_CLI_EVENTS = {
    "doc-only": ("code-review", "Skill", "bypass", "doc-only-review-exempt"),
    "single-agent": ("code-review", "Skill", "bypass", "single-agent-review-exempt"),
}

# (hook, tool, decision) for events whose `matched_rule` is supplied
# per-invocation via `--agent` rather than fixed in the tuple — a second,
# small registry alongside `_CLI_EVENTS` (not folded into it, since those
# tuples carry a fixed `matched_rule` and this one doesn't) so the set of
# CLI-constructible events stays declarable in one place per event shape.
# See the comment above `_CLI_EVENTS` for why a dynamic `matched_rule` here
# is still a bounded, safe exception to the closed-tuple design.
_CLI_AGENT_EVENTS = {
    "dispatch-failure": ("code-review", "Skill", "dispatch-failure"),
}


def _main() -> int:
    """CLI entry point (#1461): lets a *skill's* bash-block prose emit one of
    a small, fixed set of exemption events, the same way
    `hooks/lib/iteration_journal_gate.py` and `hooks/lib/review_gate_hash.py`
    are invoked from skill markdown — hooks read a stdin JSON payload, but a
    skill step has no such payload to hand this module, only CLI-style
    arguments. Used today by `skills/code-review/SKILL.md`'s doc-only
    short-circuit (`--event doc-only`) and its `--agent <name>` single-agent
    review path (`--event single-agent`), each recording their exemption
    event contemporaneously with the `.review-passed` gate write, bound via
    `--subject-hash` to that write's own `review_gate_hash()` value so the
    exemption can't be replayed for a different, unrelated diff.

    Deliberately NOT a generic `--hook/--tool/--decision/--matched-rule`
    pass-through (see `_CLI_EVENTS`) — `--event` selects one of two fixed
    tuples, or (#1763) `dispatch-failure` (see `_CLI_AGENT_EVENTS`), whose
    `matched_rule` comes from `--agent` and is validated against the
    registered review-agent set before being written; nothing else is
    constructible from the command line.

    `--event dispatch-failure --agent <name> --subject-hash <hash>`
    (#1763): used by `SKILL.md` Step 4 when a dispatched review agent still
    fails to return a contract-valid result after its single retry,
    recording that fact as negative evidence intended for
    `hooks/lib/review_gate_corroboration.py`'s gate veto (landing in the
    same epic, #1763's later slice — this event is write-only telemetry
    until that read path exists; do not assume a `.review-passed` write is
    blocked by it before that lands). `<name>` must be a registered
    `agents/*-review.md` stem — an unregistered name is silently NOT
    recorded, matching `agent_dispatch_ledger.py`'s own validation posture
    (including the same plugin-prefix normalization, `strip_plugin_prefix`).

    Fail-open, same posture as `emit_boundary_event` itself: the emit path
    never raises — a missing `--agent`, a broken registry read, or an
    unregistered name all degrade to a silent no-op (return 0), never an
    exception or a nonzero exit. (Argument-parsing usage errors from
    `argparse` itself — e.g. an unrecognized `--event` value — still exit
    nonzero via `parser.error`, as for any CLI; that is a caller-code bug,
    not a runtime condition this fail-open contract covers.)
    """
    import argparse

    parser = argparse.ArgumentParser(description=_main.__doc__)
    parser.add_argument("--cwd", default=None)
    parser.add_argument(
        "--event",
        required=True,
        choices=sorted({*_CLI_EVENTS, *_CLI_AGENT_EVENTS}),
    )
    parser.add_argument("--subject-hash", required=True, dest="subject_hash")
    parser.add_argument("--session-id", default=None, dest="session_id")
    parser.add_argument("--agent", default=None, dest="agent")
    args = parser.parse_args()

    if args.event in _CLI_AGENT_EVENTS:
        if not args.agent:
            # Fail-open: a caller that forgot --agent gets a silent no-op,
            # not a nonzero exit from a telemetry emitter — matches this
            # function's own "always exits 0" contract for the emit path.
            return 0
        try:
            # Local import: only this branch needs this sibling module, so
            # callers that merely import `emit_boundary_event` (every guard
            # hook) never pay for it, and copy-into-tmp-dir test harnesses
            # that stage only boundary_events.py + artifact_paths.py
            # alongside the hook under test (see
            # test_contract_version_guard.py::_run_hook_from) keep working
            # unmodified. Inside the try/except below so an ImportError from
            # a partial install degrades the same way a broken registry
            # read does, rather than raising.
            import review_agent_registry

            agents_dir = Path(__file__).resolve().parents[2] / "agents"
            registered = review_agent_registry.registered_review_agent_names(agents_dir)
        except Exception:  # noqa: BLE001 - fail-open: a broken registry read never records
            return 0
        # Normalize the plugin-qualified form ("dev-team:security-review")
        # to the bare stem the registry's closed set uses, matching
        # agent_dispatch_ledger.py's own normalization exactly — otherwise
        # the plugin's normal, installed invocation form would be silently
        # dropped as "unregistered".
        agent = review_agent_registry.strip_plugin_prefix(args.agent)
        if agent not in registered:
            # Unregistered name -> silently NOT recorded (matches
            # agent_dispatch_ledger.py's own posture; see module comment).
            return 0
        hook, tool, decision = _CLI_AGENT_EVENTS[args.event]
        emit_boundary_event(
            args.cwd,
            hook,
            tool,
            decision,
            agent,
            args.session_id,
            subject_hash=args.subject_hash,
        )
        return 0

    hook, tool, decision, matched_rule = _CLI_EVENTS[args.event]
    emit_boundary_event(
        args.cwd,
        hook,
        tool,
        decision,
        matched_rule,
        args.session_id,
        subject_hash=args.subject_hash,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
