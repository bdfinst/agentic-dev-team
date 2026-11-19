#!/usr/bin/env python3
"""system_test_design_args.py — validate `/system-test-design` arguments.

Runs before the skill writes anything. On any argument error it prints one
line naming the offending argument to stderr, prints nothing to stdout, and
exits 2, so the skill stops with no report file created. On success it prints
the resolved run as JSON and exits 0.

Argument contract (see skills/system-test-design/SKILL.md):

    <entry-repo> [related-repo...]
    [--coverage <repo>=<path>]... [--mutation <repo>=<path>]...
    [--aliases <path>] [--e2e-only] [--overlap-only]

Errors: a repo path that does not exist or is not a git checkout; a
`<repo>=` value in `--coverage`/`--mutation` that names no repo in scope
(`<repo>` is a repo basename); an `--aliases` file that is missing or not a
JSON object of strings; both mode flags together; no entry repo.
Evidence paths are not checked here: a missing, unrecognised, or malformed
evidence path is `static-judgment` input handled by the skill, not an error.

Stdlib only (ADR 0014/0015).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_ARGUMENT_ERROR = 2
REPORT_DIR = ".dev-team-reports"


class ArgumentProblem(Exception):
    """An argument the skill must reject before writing anything."""


class _Parser(argparse.ArgumentParser):
    """Raises instead of printing usage and exiting, so every parse error
    reaches the one `argument error:` line and exit code in `main`."""

    def error(self, message: str):  # type: ignore[override]
        raise ArgumentProblem(message)


def _is_git_checkout(path: Path) -> bool:
    return path.is_dir() and (path / ".git").exists()


def _parse_repo_path_pairs(option: str, values: list[str], scope: set[str]) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for value in values:
        repo, sep, evidence = value.partition("=")
        if not sep or not repo or not evidence:
            raise ArgumentProblem(f"{option} {value!r}: expected <repo>=<path>")
        if repo not in scope:
            raise ArgumentProblem(
                f"{option} {value!r}: repo {repo!r} is not in scope "
                f"(named repos: {', '.join(sorted(scope))})"
            )
        pairs[repo] = evidence
    return pairs


def _check_aliases(path: str) -> None:
    file = Path(path)
    if not file.is_file():
        raise ArgumentProblem(f"--aliases {path!r}: file does not exist")
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArgumentProblem(f"--aliases {path!r}: not valid JSON ({exc})") from exc
    if not isinstance(data, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in data.items()
    ):
        raise ArgumentProblem(f"--aliases {path!r}: must be a JSON object of string to string")


def resolve(argv: list[str]) -> dict:
    """Return the resolved run, or raise ArgumentProblem."""
    parser = _Parser(add_help=False)
    parser.add_argument("repos", nargs="*")
    parser.add_argument("--coverage", action="append", default=[])
    parser.add_argument("--mutation", action="append", default=[])
    parser.add_argument("--aliases")
    parser.add_argument("--e2e-only", action="store_true")
    parser.add_argument("--overlap-only", action="store_true")
    args = parser.parse_args(argv)

    if args.e2e_only and args.overlap_only:
        raise ArgumentProblem("--e2e-only and --overlap-only cannot be used together")
    if not args.repos:
        raise ArgumentProblem("missing <entry-repo>")

    for repo in args.repos:
        if not _is_git_checkout(Path(repo)):
            raise ArgumentProblem(f"repo path {repo!r} does not exist or is not a git checkout")

    names = [Path(r).resolve().name for r in args.repos]
    if len(set(names)) != len(names):
        raise ArgumentProblem("repo basenames must be unique: " + ", ".join(names))
    scope = set(names)

    coverage = _parse_repo_path_pairs("--coverage", args.coverage, scope)
    mutation = _parse_repo_path_pairs("--mutation", args.mutation, scope)
    if args.aliases is not None:
        _check_aliases(args.aliases)

    mode = "e2e-only" if args.e2e_only else "overlap-only" if args.overlap_only else "full"
    return {
        "entry": names[0],
        "repos": [{"path": r, "name": n} for r, n in zip(args.repos, names, strict=True)],
        "coverage": coverage,
        "mutation": mutation,
        "aliases": args.aliases,
        "mode": mode,
        "report_path": f"{REPORT_DIR}/system-test-design-{names[0]}.md",
    }


def main(argv: list[str] | None = None) -> int:
    try:
        run = resolve(sys.argv[1:] if argv is None else argv)
    except ArgumentProblem as exc:
        print(f"system-test-design: argument error: {exc}", file=sys.stderr)
        return EXIT_ARGUMENT_ERROR
    print(json.dumps(run, indent=2))
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
