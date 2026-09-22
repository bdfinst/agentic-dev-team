"""Hypothesis property-test scaffold for a single target Python function (#2190).

This module's own analysis is stdlib-only (`ast`), per ADR 0014 — no
third-party imports here. The *generated* test file it writes imports the
third-party `hypothesis` library; that import lives only in the emitted
file, never in this script.

Narrow, explicit heuristic (do not extend without updating this docstring):

1. Round-trip: the target module defines a function literally named
   `encode` and a function literally named `decode` — either both at module
   level, or both as methods of the same class — and the requested function
   is one of that pair. Generates a test asserting
   `decode(encode(x)) == x`.
2. Invariant: the target function's docstring contains a recognized
   postcondition phrase (see `INVARIANT_PHRASES`) and the function carries
   at least one type annotation (parameter or return) — the "near a type
   hint" signal. Generates a test asserting that invariant.
3. Neither matches: no file is written; the exact negative message is
   printed to stdout.

This is deliberately narrow — it is not a general contract-inference
engine. Extending the phrase list or the type-annotation proximity check is
in scope; inferring arbitrary contracts from prose is not.
"""

from __future__ import annotations

import argparse
import ast
import os
from dataclasses import dataclass

# Postcondition phrase -> human label used only for readability; the phrase
# itself is the literal substring matched (case-insensitively) against the
# target function's docstring.
INVARIANT_PHRASES = ("returns sorted", "is idempotent")

NO_PROPERTY_MESSAGE = (
    "No property derived for {function} — no round-trip pair or documented "
    "invariant found nearby. Add a docstring postcondition (e.g. a 'returns "
    "sorted'/'is idempotent'-style phrase) to make one derivable."
)

# Narrow annotation -> Hypothesis strategy expression map. Anything not
# listed here falls back to st.text() — this is not general type inference.
_STRATEGY_BY_ANNOTATION = {
    "str": "st.text()",
    "int": "st.integers()",
    "float": "st.floats(allow_nan=False, allow_infinity=False)",
    "bool": "st.booleans()",
    "list[int]": "st.lists(st.integers())",
    "List[int]": "st.lists(st.integers())",
}


@dataclass
class RoundTripProperty:
    encode_name: str
    decode_name: str
    class_name: str | None = None


@dataclass
class InvariantProperty:
    function_name: str
    phrase: str


def _module_name(module_path: str) -> str:
    """Derive the importable module name a generated test's `from {module}
    import ...` line will use.

    Raises `ValueError` when the basename isn't a valid Python identifier —
    this value is interpolated unescaped into a generated test file's import
    statement (`_render_roundtrip_test`/`_render_invariant_test`), so a
    filename engineered to contain e.g. a newline could otherwise inject
    arbitrary statements into a file pytest later collects and executes
    (security-review finding). Every other interpolated value on that path
    is already constrained to a safe shape: `encode`/`decode` are literals,
    `class_name`/`function_name` are `ast.FunctionDef`/`ClassDef.name`
    values (valid identifiers by construction), and `module_dir` is
    `repr()`-escaped at render time.
    """
    base = os.path.basename(module_path)
    name = base.removesuffix(".py")
    if not name.isidentifier():
        raise ValueError(
            f"unsupported module filename {module_path!r}: {name!r} is not a "
            "valid Python identifier, so it can't be used in a generated "
            "test's import statement"
        )
    return name


def _parse_module(module_path: str) -> ast.Module:
    with open(module_path, "r", encoding="utf-8") as handle:
        source = handle.read()
    return ast.parse(source, filename=module_path)


def _find_function(tree: ast.Module, name: str) -> ast.FunctionDef | None:
    """Module-level functions only — deliberately not `ast.walk`, which
    would also match a same-named method inside a class body. The invariant
    render path assumes a module-level import (`from {module} import
    {function_name}`), which is wrong for a method (no `self`/receiver, no
    class import/instantiation) — see `find_roundtrip_pair` for the
    separate, already class-aware handling the round-trip path has."""
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def find_roundtrip_pair(tree: ast.Module) -> RoundTripProperty | None:
    """Locate a literal `encode`/`decode` pair at module level or as methods
    of one class. Returns None when no such pair exists."""
    module_level = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    if "encode" in module_level and "decode" in module_level:
        return RoundTripProperty(encode_name="encode", decode_name="decode")

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            methods = {n.name for n in node.body if isinstance(n, ast.FunctionDef)}
            if "encode" in methods and "decode" in methods:
                return RoundTripProperty(
                    encode_name="encode", decode_name="decode", class_name=node.name
                )
    return None


def _has_nearby_type_hint(func: ast.FunctionDef) -> bool:
    """Narrow proximity check: the function carries at least one type
    annotation (a parameter or its return type)."""
    if func.returns is not None:
        return True
    return any(arg.annotation is not None for arg in func.args.args)


def find_invariant(func: ast.FunctionDef) -> InvariantProperty | None:
    docstring = ast.get_docstring(func) or ""
    if not docstring or not _has_nearby_type_hint(func):
        return None
    lowered = docstring.lower()
    for phrase in INVARIANT_PHRASES:
        if phrase in lowered:
            return InvariantProperty(function_name=func.name, phrase=phrase)
    return None


def _first_arg_strategy(func: ast.FunctionDef) -> str:
    args = func.args.args
    if not args or args[0].annotation is None:
        return "st.text()"
    annotation_text = ast.unparse(args[0].annotation)
    return _STRATEGY_BY_ANNOTATION.get(annotation_text, "st.text()")


def _render_roundtrip_test(
    prop: RoundTripProperty, module_path: str, module_name: str
) -> str:
    module_dir = os.path.dirname(os.path.abspath(module_path))
    if prop.class_name:
        import_line = f"from {module_name} import {prop.class_name}"
        setup = f"    obj = {prop.class_name}()\n"
        call_encode = f"obj.{prop.encode_name}(x)"
        call_decode = "obj.{}({})".format(prop.decode_name, "encoded")
    else:
        import_line = f"from {module_name} import {prop.encode_name}, {prop.decode_name}"
        setup = ""
        call_encode = f"{prop.encode_name}(x)"
        call_decode = f"{prop.decode_name}(encoded)"

    return (
        f'"""Generated by hypothesis_scaffold.py — round-trip property test\n'
        f"for {prop.encode_name}/{prop.decode_name}. Do not hand-edit;\n"
        f'regenerate via /property-based-testing if the source module changes.\n"""\n\n'
        "import os\n"
        "import sys\n\n"
        f"sys.path.insert(0, {module_dir!r})\n\n"
        "from hypothesis import given\n"
        "from hypothesis import strategies as st\n\n"
        f"{import_line}\n\n\n"
        "@given(st.text())\n"
        f"def test_{prop.encode_name}_{prop.decode_name}_roundtrip(x):\n"
        f"{setup}"
        f"    encoded = {call_encode}\n"
        f"    assert {call_decode} == x\n"
    )


def _render_invariant_test(
    prop: InvariantProperty, func: ast.FunctionDef, module_path: str, module_name: str
) -> str:
    module_dir = os.path.dirname(os.path.abspath(module_path))
    strategy_expr = _first_arg_strategy(func)
    if prop.phrase == "returns sorted":
        assertion = (
            f"    result = {prop.function_name}(value)\n"
            "    assert result == sorted(result)\n"
        )
    elif prop.phrase == "is idempotent":
        assertion = (
            f"    once = {prop.function_name}(value)\n"
            f"    twice = {prop.function_name}(once)\n"
            "    assert twice == once\n"
        )
    else:  # pragma: no cover - defensive, INVARIANT_PHRASES is exhaustive above
        assertion = f"    {prop.function_name}(value)\n"

    return (
        f'"""Generated by hypothesis_scaffold.py — invariant property test\n'
        f'for {prop.function_name} ("{prop.phrase}"). Do not hand-edit;\n'
        f'regenerate via /property-based-testing if the source module changes.\n"""\n\n'
        "import sys\n\n"
        f"sys.path.insert(0, {module_dir!r})\n\n"
        "from hypothesis import given\n"
        "from hypothesis import strategies as st\n\n"
        f"from {module_name} import {prop.function_name}\n\n\n"
        f"@given({strategy_expr})\n"
        f"def test_{prop.function_name}_invariant(value):\n"
        f"{assertion}"
    )


def scaffold(module_path: str, function_name: str, out_dir: str) -> str | None:
    """Analyze `module_path` for a property involving `function_name`.

    On a match, writes `test_<function_name>_properties.py` into `out_dir`
    and returns its path. On no match, prints the exact negative message to
    stdout and returns None without writing any file.
    """
    tree = _parse_module(module_path)
    module_name = _module_name(module_path)

    roundtrip = find_roundtrip_pair(tree)
    if roundtrip and function_name in (roundtrip.encode_name, roundtrip.decode_name):
        content = _render_roundtrip_test(roundtrip, module_path, module_name)
    else:
        func = _find_function(tree, function_name)
        invariant = find_invariant(func) if func is not None else None
        if func is not None and invariant:
            content = _render_invariant_test(invariant, func, module_path, module_name)
        else:
            print(NO_PROPERTY_MESSAGE.format(function=function_name))
            return None

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"test_{function_name}_properties.py")
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return out_path


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scaffold a Hypothesis property test for a Python function."
    )
    parser.add_argument("module_path", help="path to the target module")
    parser.add_argument("function_name", help="name of the function to target")
    parser.add_argument(
        "--out-dir",
        default=None,
        help="directory to write the generated test into (default: module's directory)",
    )
    args = parser.parse_args(argv)
    out_dir = args.out_dir or os.path.dirname(os.path.abspath(args.module_path))
    result = scaffold(args.module_path, args.function_name, out_dir)
    if result:
        print(f"Wrote {result}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
