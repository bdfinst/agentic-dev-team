#!/usr/bin/env python3
"""Detect a plain src/-layout Python project and emit the mypy flags it needs.

mypy fails outright on a common, unremarkable layout — a ``src/`` directory
holding modules with no ``__init__.py``, and no project-level mypy
package-base configuration (``mypy_path`` / ``explicit_package_bases`` / a
``pyproject.toml`` ``[tool.mypy]`` section). The moment any other checked
file imports one of those modules via its dotted ``src.`` path (a root-level
entry point, a test, ...), mypy resolves the same file two different ways
and refuses to proceed:

    Source file found twice under different module names: "calc" and "src.calc"

mypy >= 0.990 accepts ``--explicit-package-bases`` to resolve this without
requiring ``__init__.py`` files or hand-written config. This script detects
the layout and prints the extra flag(s) to pass (empty when not applicable)
so the caller can splice them into the mypy invocation documented in
``../references/tool-configs.md``:

    mypy $(python3 adapters/mypy-src-layout.py .) --output json .

Detection deliberately never overrides a project that already owns its mypy
config — "bind, don't replace" (see static-self-heal.md's provider-binding
rule): if any recognized mypy config file/section is present, this reports
no src-layout regardless of what src/ contains.
"""

from __future__ import annotations

import sys
from pathlib import Path

# name -> marker string that must appear in the file for it to count as a
# mypy package-base config; None means the file's mere presence counts.
_CONFIG_MARKERS = {
    "mypy.ini": None,
    ".mypy.ini": None,
    "setup.cfg": "[mypy]",
    "tox.ini": "[mypy]",
    "pyproject.toml": "[tool.mypy]",
}


def _has_mypy_config(root: Path) -> bool:
    for name, marker in _CONFIG_MARKERS.items():
        path = root / name
        if not path.is_file():
            continue
        if marker is None:
            return True
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if marker in text:
            return True
    return False


def _src_has_modules_without_init(src: Path) -> bool:
    has_module = False
    for path in src.rglob("*.py"):
        if path.name == "__init__.py":
            return False
        has_module = True
    return has_module


def is_src_layout(root: Path) -> bool:
    """True when `root` needs `--explicit-package-bases` to resolve mypy's
    src/-layout module-naming ambiguity, and nothing in the project already
    tells mypy how to resolve it."""
    src = root / "src"
    if not src.is_dir():
        return False
    if not _src_has_modules_without_init(src):
        return False
    return not _has_mypy_config(root)


def extra_args(root: Path) -> list:
    return ["--explicit-package-bases"] if is_src_layout(root) else []


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    root = Path(argv[0]) if argv else Path(".")
    print(" ".join(extra_args(root)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
