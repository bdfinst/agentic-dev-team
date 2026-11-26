#!/usr/bin/env python3
"""bash_regulator.py — role-aware allow / ask / deny decisions for Bash calls.

PreToolUse hook. Opt in with `DEV_TEAM_REGULATOR=on`; off (the default) it
does nothing. `DEV_TEAM_REGULATOR_MODE` picks `advisory` (default: log the
decision to `.claude/metrics/regulator-decisions.jsonl`, change nothing) or
`enforce` (emit `permissionDecision`).

Per call: split the command into segments (`hooks/lib/bash_segments.py`),
evaluate the ordered rules in `hooks/regulator_rules.json` per segment (first
match wins), merge deny > ask > allow. A segment no rule matches falls through
to normal permissions, so the call is only allowed when every segment is.
An unparseable command is denied with a rewrite hint.

Destructive patterns come from `hooks/destructive-commands.json` (shared with
`destructive_guard.py`): `ask`, or `deny` while `/careful` is active. The
guard stays registered for its default-branch escalations.

`bypassPermissions`: the user opted out of prompts, so only `deny` decisions
are emitted there.

Subagent calls carry `agent_type`; rules with `applies_to` fire only for a
matching agent, and `subagents_only` rules never fire in the main session. A
plugin prefix (`dev-team:`) is stripped before matching.

Debug: `bash_regulator.py --explain '<command>' [--agent-type NAME]` prints
the deciding rule per segment.

Needs Claude Code >= 2.1.330 (PreToolUse `permission_mode`, `agent_type`,
`permissionDecision`).
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_LIB_DIR = _SCRIPT_DIR / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import artifact_paths
import bash_segments
import destructive_guard as _guard
import instrument_log
from stdin_json import read_stdin_json

_RULES_FILE = _SCRIPT_DIR / "regulator_rules.json"
_SEVERITY = {"allow": 0, "ask": 1, "deny": 2}
_PLUGIN_PREFIX = re.compile(r"^[\w-]+:")
# Only flags that cannot change what git runs or where it runs are stripped;
# any other option before the subcommand (`-c`, `-C`, `--git-dir`, ...) makes
# the segment untrusted for allow rules.
_GIT_GLOBAL_FLAGS = {"--no-pager", "--paginate", "-P", "--no-optional-locks"}
# Global options whose next word is a value, skipped when finding the subcommand.
_GIT_VALUE_OPTIONS = {
    "-c",
    "-C",
    "--git-dir",
    "--work-tree",
    "--namespace",
    "--exec-path",
    "--super-prefix",
    "--config-env",
}
# `sed` is auto-allowed only for a print/delete/quit address or one s///
# substitution whose flags cannot write or execute, with only these options.
_SED_SAFE_OPTIONS = re.compile(
    r"-[nEr]+|--(quiet|silent|regexp-extended|null-data|posix|sandbox)"
)
_SED_ADDRESS = r"(?:\d+|\$|/[^/\n]*/)"
_SED_SAFE_SCRIPT = re.compile(
    rf"(?:{_SED_ADDRESS})?(?:,{_SED_ADDRESS})?!?[pdq=]|"
    r"s(.)(?:(?!\1)[^\n])*\1(?:(?!\1)[^\n])*\1[gpIiM0-9]*"
)
_GIT_BRANCH_LIST_FLAGS = {
    "-a",
    "-r",
    "-v",
    "-vv",
    "--list",
    "-l",
    "--show-current",
    "--merged",
    "--no-merged",
    "--contains",
    "--no-contains",
    "--all",
    "--remotes",
    "--verbose",
}
_GIT_BRANCH_OPERAND_FLAGS = {"--merged", "--no-merged", "--contains", "--no-contains"}
_REWRITE_HINT = (
    "Command could not be parsed safely ({why}). Rewrite it as plain commands "
    "joined with && or run one command per call."
)


# --- normalization -----------------------------------------------------------


def normalize_agent_type(agent_type) -> str:
    if not isinstance(agent_type, str):
        return ""
    return _PLUGIN_PREFIX.sub("", agent_type.strip())


def _strip_git_globals(argv: list[str]) -> list[str]:
    out, i = [argv[0]], 1
    while i < len(argv) and argv[i] in _GIT_GLOBAL_FLAGS:
        i += 1
    return out + argv[i:]


def _normalized_argv(segment: bash_segments.Segment) -> list[str]:
    argv = [segment.cmd, *segment.argv[1:]]
    return _strip_git_globals(argv) if segment.cmd == "git" else argv


def _subcommand(argv: list[str]) -> str:
    skip = False
    for word in argv[1:]:
        if skip:
            skip = False
        elif argv[0] == "git" and word in _GIT_VALUE_OPTIONS:
            skip = True
        elif not word.startswith("-"):
            return word
    return ""


# --- named predicates (the Python escape hatch) -------------------------------


def _writes_file(segment, argv) -> bool:
    """An output redirect to anything but /dev/null (input redirects read)."""
    for redirect in segment.redirects:
        operator = redirect.split(" ", 1)[0]
        target = redirect.split(" ", 1)[1] if " " in redirect else ""
        if ">" in operator and target != "/dev/null":
            return True
    return False


def _sed_is_safe_print_or_substitute(segment, argv) -> bool:
    """Only safe options, then one script that cannot write or execute."""
    words = argv[1:]
    while words and words[0].startswith("-"):
        if not _SED_SAFE_OPTIONS.fullmatch(words[0]):
            return False
        words = words[1:]
    return bool(words) and _SED_SAFE_SCRIPT.fullmatch(words[0]) is not None


def _git_branch_only_lists(segment, argv) -> bool:
    args, i, lists = argv[2:], 0, any(w in ("--list", "-l") for w in argv[2:])
    while i < len(args):
        word = args[i]
        if word in _GIT_BRANCH_OPERAND_FLAGS:
            i += 2
            continue
        if word not in _GIT_BRANCH_LIST_FLAGS and (word.startswith("-") or not lists):
            return False
        i += 1
    return True


CHECKS = {
    "writes_file": _writes_file,
    "sed_is_safe": _sed_is_safe_print_or_substitute,
    "git_branch_only_lists": _git_branch_only_lists,
}


# --- rules -------------------------------------------------------------------


def load_rules(path: Path = _RULES_FILE) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [r for r in data.get("rules", []) if isinstance(r, dict) and r.get("id")]


def _as_list(value) -> list:
    return value if isinstance(value, list) else [value]


def _applies(rule: dict, agent_type: str) -> bool:
    if rule.get("subagents_only") and not agent_type:
        return False
    patterns = rule.get("applies_to")
    if patterns is None:
        return True
    return bool(agent_type) and any(
        fnmatch.fnmatchcase(agent_type, p) for p in patterns
    )


def _options_match(pattern: str, argv: list[str]) -> bool:
    """Every option word (one starting with `-`) fully matches `pattern`.

    An allowlist of options: an abbreviation, a new flag, or an unknown spelling
    fails, so a write or exec option cannot slip past a denylist.
    """
    return all(re.fullmatch(pattern, w) for w in argv[1:] if w.startswith("-"))


def _matches(rule: dict, segment, argv: list[str]) -> bool:
    if "cmd" in rule and argv[0] not in _as_list(rule["cmd"]):
        return False
    if "sub" in rule and _subcommand(argv) not in _as_list(rule["sub"]):
        return False
    if "args_any" in rule and not set(argv[1:]) & set(rule["args_any"]):
        return False
    if "args_none" in rule and set(argv[1:]) & set(rule["args_none"]):
        return False
    if "opts_re" in rule and not _options_match(rule["opts_re"], argv):
        return False
    if "regex" in rule and not re.search(rule["regex"], " ".join(argv)):
        return False
    if "check" in rule and not CHECKS[rule["check"]](segment, argv):
        return False
    return not (rule["decision"] == "allow" and _writes_file(segment, argv))


def _without_git_globals(argv: list[str]) -> list[str]:
    """`git` plus its subcommand and arguments, global options (and values) dropped."""
    if argv[0] != "git":
        return argv
    skip, i = False, 1
    while i < len(argv):
        word = argv[i]
        if skip:
            skip = False
        elif word in _GIT_VALUE_OPTIONS:
            skip = True
        elif not word.startswith("-"):
            break
        i += 1
    return [argv[0], *argv[i:]]


def _destructive_rule(argv: list[str], careful: bool) -> dict | None:
    text = " ".join(_without_git_globals(argv)).lower()
    file_p, db_p, git_p, proc_p, perm_p, safe_p = _guard._load_patterns()
    if _guard._matches_any(text, safe_p) is not None:
        return None
    hit = _guard._first_match(
        text,
        [
            (file_p, "File destruction"),
            (db_p, "Database destruction"),
            (git_p, "Git destruction"),
            (proc_p, "Process destruction"),
            (perm_p, "Permission escalation"),
        ],
    )
    if hit is None:
        return None
    return {
        "id": "destructive-pattern",
        "decision": "deny" if careful else "ask",
        "reason": f"Destructive command ({hit})."
        + (" Careful mode is active." if careful else ""),
    }


def _redirect_only_rule(segment, rules, agent_type: str) -> dict | None:
    """A subshell or bare redirect: only non-allow rules (e.g. read-only roles) apply."""
    if not _writes_file(segment, [""]):
        return None
    for rule in rules:
        if (
            rule["decision"] != "allow"
            and _applies(rule, agent_type)
            and _matches(rule, segment, [""])
        ):
            return rule
    return None


def evaluate_segment(segment, rules, agent_type: str, careful: bool) -> dict | None:
    """The deciding rule for one segment, or None to fall through."""
    if not segment.argv:
        return _redirect_only_rule(segment, rules, agent_type)
    if segment.opaque_reason:
        return {
            "id": "opaque-command",
            "decision": "ask",
            "reason": segment.opaque_reason,
        }
    argv = _normalized_argv(segment)
    untrusted = bool(segment.untrusted_reason) or "/" in segment.argv[0]
    if segment.cmd == "git" and len(argv) > 1 and argv[1].startswith("-"):
        untrusted = True
    destructive = _destructive_rule(argv, careful)
    matched = None
    for rule in rules:
        if rule["decision"] == "allow" and untrusted:
            continue
        if _applies(rule, agent_type) and _matches(rule, segment, argv):
            matched = rule
            break
    # A role deny outranks the generic destructive ask; the destructive rule
    # still wins when it also denies (careful mode) or no rule matched.
    if matched and matched["decision"] == "deny":
        return matched
    return destructive or matched


def decide(
    command: str, agent_type: str = "", careful: bool = False, rules=None
) -> dict:
    """{decision: allow|ask|deny|None, reason, segments: [{argv, rule, decision}]}."""
    rules = load_rules() if rules is None else rules
    try:
        segments = bash_segments.parse(command)
    except bash_segments.Unparseable as exc:
        return {
            "decision": "deny",
            "reason": _REWRITE_HINT.format(why=exc),
            "segments": [{"argv": [], "rule": "unparseable", "decision": "deny"}],
        }
    rows, merged, unmatched = [], None, False
    for segment in segments:
        rule = evaluate_segment(segment, rules, agent_type, careful)
        if rule is None:
            unmatched = True
            rows.append({"argv": segment.argv, "rule": None, "decision": None})
            continue
        rows.append(
            {
                "argv": segment.argv,
                "rule": rule["id"],
                "decision": rule["decision"],
                "reason": rule.get("reason", ""),
            }
        )
        if (
            merged is None
            or _SEVERITY[rule["decision"]] > _SEVERITY[merged["decision"]]
        ):
            merged = rule
    if merged is None or (merged["decision"] == "allow" and unmatched):
        return {"decision": None, "reason": "", "segments": rows}
    return {
        "decision": merged["decision"],
        "reason": merged.get("reason", ""),
        "segments": rows,
    }


# --- hook entry ----------------------------------------------------------------


def _enabled() -> bool:
    return os.environ.get("DEV_TEAM_REGULATOR", "").strip().lower() in {
        "on",
        "1",
        "true",
    }


def _enforcing() -> bool:
    return (
        os.environ.get("DEV_TEAM_REGULATOR_MODE", "advisory").strip().lower()
        == "enforce"
    )


def main() -> int:
    if not _enabled():
        return 0
    try:
        payload = read_stdin_json() or {}
        tool_input = payload.get("tool_input")
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        if not isinstance(command, str) or not command.strip():
            return 0
        raw_cwd = payload.get("cwd")
        cwd = (
            raw_cwd
            if isinstance(raw_cwd, str) and raw_cwd and "\0" not in raw_cwd
            else "."
        )
        agent_type = normalize_agent_type(payload.get("agent_type"))
        careful_path = artifact_paths.resolve_file(
            "hooks", "careful-state.json", root=cwd, migrate=False
        )
        result = decide(command, agent_type, _guard._careful_active(careful_path))
        permission_mode = payload.get("permission_mode")
        enforcing = _enforcing()
        instrument_log.append_row(
            "regulator-decisions",
            {
                "mode": "enforce" if enforcing else "advisory",
                "decision": result["decision"] or "fall-through",
                "rules": sorted({s["rule"] for s in result["segments"] if s["rule"]}),
                "agent_type": agent_type or "main",
                "permission_mode": permission_mode
                if isinstance(permission_mode, str)
                else "",
            },
            cwd=cwd,
            session_id=payload.get("session_id"),
        )
        decision = result["decision"]
        if not enforcing or decision is None:
            return 0
        if permission_mode == "bypassPermissions" and decision != "deny":
            return 0
        sys.stdout.write(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": decision,
                        "permissionDecisionReason": result["reason"]
                        or f"regulator: {decision}",
                    }
                }
            )
            + "\n"
        )
    except Exception:  # noqa: BLE001 — fail open: a regulator fault never blocks a call
        return 0
    return 0


def _explain(argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="bash_regulator.py")
    parser.add_argument("--explain", required=True, metavar="COMMAND")
    parser.add_argument("--agent-type", default="")
    parser.add_argument("--careful", action="store_true")
    args = parser.parse_args(argv)
    result = decide(args.explain, normalize_agent_type(args.agent_type), args.careful)
    for row in result["segments"]:
        print(
            f"{row['decision'] or 'fall-through':<12} {row['rule'] or '-':<26} {' '.join(row['argv'])}"
        )
    print(
        f"=> {result['decision'] or 'fall-through'}"
        + (f"  ({result['reason']})" if result["reason"] else "")
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_explain(sys.argv[1:]) if "--explain" in sys.argv[1:] else main())
