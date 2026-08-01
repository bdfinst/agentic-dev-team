#!/usr/bin/env python3
"""Import every shipped plugin module under the current interpreter.

Run by the "Python 3.10 floor" job in `.github/workflows/plugin-tests.yml`.
That job's gate is this probe, plus a byte-compile pass over the shipped
tree, plus (since issue #1650) actually running the test slice covering the
five shipped agent scripts under the floor interpreter via `uv run
--python` — not the plugin's entire suite (that would double this gate's
wall-clock re-running everything under a second interpreter), but enough to
catch a runtime-only API used inside a function body, which byte-compiling
and importing alone cannot (see `chk_python_floor` in `scripts/ci-local.sh`).

Byte-compiling proves a file *parses*. It does not prove it *imports*, and the
gap between those two is exactly where the shipped tree had drifted: PEP 585
generics in a module-level type alias
(`Generator = Callable[[str, list[dict]], str]`) compile on every Python ever
released and raise `TypeError: 'type' object is not subscriptable` the moment
the module is loaded on the floor interpreter. Five shipped scripts were in that state.

Like the suite, this asks the interpreter rather than pattern-matching source:
whatever the floor interpreter refuses to import is a failure here, with no list of known-bad
APIs to keep current.

That principle had one gap of its own (#1681): a blanket `except ImportError:
pass` swallowed every `ImportError`, including the exact shape a genuinely
missing stdlib symbol produces (`from datetime import UTC` on pre-3.11 —
`ImportError: cannot import name 'UTC' from 'datetime'`). `_is_version_error`
now distinguishes that case from the sibling-path/harness artifacts the
exclusion was meant for — see its own docstring.

Executing module top-level code is safe here because every shipped entry point
guards its side effects behind `if __name__ == "__main__":` — a convention
this probe therefore also enforces, since a script that runs its work on
import will surface as a failure.
"""

from __future__ import annotations

import importlib.util
import sys
import traceback
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SHIPPED = REPO_ROOT / "plugins" / "dev-team"

#: Not importable modules. `rule-fixtures` holds deliberately broken semgrep
#: positives and negatives; `templates` holds scaffolding copied into user
#: projects, not executed here.
EXCLUDED = ("/tests/", "node_modules", "rule-fixtures", "/templates/")

#: Failures that indicate a real version-floor problem.
VERSION_ERRORS = (SyntaxError, TypeError, AttributeError, NameError, ValueError)


def _is_version_error(exc: BaseException) -> bool:
    """True for a failure that indicates a real version-floor problem.

    `ImportError` needs its own test rather than a blanket exclusion or a
    blanket inclusion (#1681): it covers structurally different failures, and
    a first attempt at this fix (`type(exc) is ImportError`, excluding only
    `ModuleNotFoundError`) proved too broad against this repo's own shipped
    tree — see below.

    - `ModuleNotFoundError` (a subclass) — the whole module could not be
      located. Shipped scripts import siblings via `sys.path` manipulation,
      and a miss there is a path artifact of this probe's harness rather than
      something a user would hit running the script normally. Excluded.
    - Plain `ImportError` (not the subclass) for a name that failed to
      resolve INSIDE an already-found STDLIB module — e.g. `from datetime
      import UTC` (3.11+) on the 3.10 floor. For `from X import Y`, Python
      only raises this exact shape once `X` has resolved successfully, and a
      standard-library module's contents are fixed by the interpreter, not by
      anything this probe's harness does — so this is never a probe artifact.
      Included.
    - Plain `ImportError` for a name that resolved to a PROJECT-LOCAL module.
      Verified against this repo's own shipped tree: `codebase_recon.py`'s
      `from lib import deterministic_recon` failed with `e.name == "lib"`
      (not `None`) — but "lib" here had resolved to
      `hooks/mutation_adapters/lib.py`, a same-named sibling this probe's
      shared sys.path (accumulated across every file it loads in one process,
      never reset between them) put ahead of the real `scripts/lib/` package.
      That collision is an artifact of running every shipped file's imports
      in one shared process, not a version signal — `e.name` alone is not
      enough to tell the two plain-`ImportError` cases apart; excluded unless
      the resolved name is an actual standard-library module.

    `type(exc) is ImportError`, not `isinstance`: `isinstance` would also
    match the `ModuleNotFoundError` subclass, collapsing the first
    distinction above. `sys.stdlib_module_names` requires 3.10+, which this
    probe already assumes — it's the CI job's own floor interpreter.
    """
    if isinstance(exc, VERSION_ERRORS):
        return True
    if type(exc) is ImportError:
        return exc.name is not None and exc.name in sys.stdlib_module_names
    return False


def _candidate_paths(path: Path):
    """Directories a shipped module may expect on `sys.path`.

    Mirrors the `sys.path.insert(0, ...)` idiom the hooks and skill scripts use
    to reach siblings and the shared `lib/` trees without being installed as
    packages.
    """
    return [
        path.parent,
        SHIPPED / "hooks" / "lib",
        SHIPPED / "scripts" / "lib",
        SHIPPED / "hooks",
        SHIPPED / "scripts",
    ]


def main() -> int:
    files = sorted(
        p
        for p in SHIPPED.rglob("*.py")
        if not any(fragment in str(p) for fragment in EXCLUDED)
    )

    failures = []
    for index, path in enumerate(files):
        for candidate in _candidate_paths(path):
            entry = str(candidate)
            if candidate.is_dir() and entry not in sys.path:
                sys.path.insert(0, entry)

        # A unique name per file, registered before execution: a module that
        # looks itself up via sys.modules[__name__] during import would
        # otherwise fail on a technicality of this probe rather than on
        # anything to do with the interpreter version.
        name = "_probe_{}_{}".format(index, path.stem.replace("-", "_"))
        try:
            spec = importlib.util.spec_from_file_location(name, path)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
        except Exception as exc:  # noqa: BLE001 — dispatched by _is_version_error below
            if _is_version_error(exc):
                failures.append((path, traceback.format_exc()))
            # Anything else (ModuleNotFoundError for an unresolvable sibling,
            # an OSError from a module probing its environment) is not
            # evidence about the interpreter version — see _is_version_error.
        finally:
            sys.modules.pop(name, None)

    print(
        "import probe: {} shipped modules on Python {}.{}.{}".format(
            len(files), *sys.version_info[:3]
        )
    )
    if failures:
        print(f"\n{len(failures)} module(s) failed to import:\n", file=sys.stderr)
        for path, tb in failures:
            print(f"=== {path.relative_to(REPO_ROOT)} ===", file=sys.stderr)
            print(tb, file=sys.stderr)
        print(
            "ADR 0014 sets the shipped floor at Python 3.10. See "
            "tests/repo/test_python_floor.py.",
            file=sys.stderr,
        )
        return 1

    print("all shipped modules import cleanly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
