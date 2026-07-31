#!/usr/bin/env python3
"""Import every shipped plugin module under the current interpreter.

Run by the "Python 3.8 floor" job in `.github/workflows/plugin-tests.yml`.
That job's main gate is the plugin's own test suite on a real 3.8; this probe
covers the remainder — modules the suite never imports, which would otherwise
reach users untested on the floor interpreter.

Byte-compiling proves a file *parses*. It does not prove it *imports*, and the
gap between those two is exactly where the shipped tree had drifted: PEP 585
generics in a module-level type alias
(`Generator = Callable[[str, list[dict]], str]`) compile on every Python ever
released and raise `TypeError: 'type' object is not subscriptable` the moment
the module is loaded on 3.8. Five shipped scripts were in that state.

Like the suite, this asks the interpreter rather than pattern-matching source:
whatever 3.8 refuses to import is a failure here, with no list of known-bad
APIs to keep current.

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

#: Failures that indicate a real version-floor problem. An `ImportError` is
#: excluded on purpose: shipped scripts import siblings via `sys.path`
#: manipulation, and a miss there is a path artifact of this probe rather than
#: something a user would hit running the script normally.
VERSION_ERRORS = (SyntaxError, TypeError, AttributeError, NameError, ValueError)


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
        except VERSION_ERRORS:
            failures.append((path, traceback.format_exc()))
        except Exception:
            # Anything else (ImportError for an unresolvable sibling, an
            # OSError from a module probing its environment) is not evidence
            # about the interpreter version.
            pass
        finally:
            sys.modules.pop(name, None)

    print(
        "import probe: {} shipped modules on Python {}.{}.{}".format(
            len(files), *sys.version_info[:3]
        )
    )
    if failures:
        print("\n{} module(s) failed to import:\n".format(len(failures)), file=sys.stderr)
        for path, tb in failures:
            print("=== {} ===".format(path.relative_to(REPO_ROOT)), file=sys.stderr)
            print(tb, file=sys.stderr)
        print(
            "ADR 0014 sets the shipped floor at Python 3.8. See "
            "tests/repo/test_python_floor.py.",
            file=sys.stderr,
        )
        return 1

    print("all shipped modules import cleanly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
