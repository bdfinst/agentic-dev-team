"""The shared-classifier modules must be imported, never re-implemented (#1968).

`change_shape.py` and `select_lenses.py` each used to carry a hand-written
`except ImportError` fallback duplicating a `hooks/lib/` classifier. Two things
were wrong with that:

1. **It could drift silently, and did.** The `is_test_file` fallback added in
   #1964 shipped folding all four indicator families into one `re.IGNORECASE`
   pattern, while `test_file_classify` compiles its step-definition regex
   case-sensitively — so `backsteps.py` read as a step definition and an
   ordinary source file could pass as a test.
2. **The guard that claimed to catch drift could not fail.** When the import
   succeeds — always, in this repo — `test_is_functional_config_matches_
   doc_classification_module` compared the canonical implementation against
   itself. Sabotaging the fallback to `return False` left the whole suite
   green. `CLAUDE.md`: "A gate that cannot fail is worse than no gate."

`hooks/lib/` ships inside the same plugin as its consumers, so an unreachable
one is a broken install, not a supported degraded mode. The fallbacks are gone
and the import now fails loudly. These tests keep it that way: a reintroduced
fallback is a structural regression, not a style choice.
"""

from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
import textwrap

import pytest

from _repo_root import REPO_ROOT

_PLUGIN = REPO_ROOT / "plugins" / "dev-team"

#: Consumer modules that import a shared classifier across the hooks/lib
#: boundary, and the shared module names each one requires.
CONSUMERS = {
    _PLUGIN / "skills" / "code-review" / "scripts" / "change_shape.py": (
        "doc_classification",
        "test_file_classify",
    ),
    # select_lenses.py gained `test_file_classify` with the `test-files`
    # scope sentinel (#1978) — the same no-fallback rule applies to it.
    _PLUGIN / "scripts" / "select_lenses.py": (
        "doc_classification",
        "test_file_classify",
    ),
}

#: Names the deleted fallbacks defined. Any of these reappearing in a consumer
#: means a local re-implementation came back.
FORBIDDEN_FALLBACK_NAMES = (
    "_FALLBACK_FUNCTIONAL_CONFIG_NAMES",
    "_FALLBACK_FUNCTIONAL_CONFIG_SEGMENTS",
    "_FALLBACK_TEST_NAME_RE",
    "_FALLBACK_STEP_DEF_RE",
)


def _import_handlers(tree: ast.AST, shared: tuple[str, ...]) -> list[ast.ExceptHandler]:
    """Every `except ImportError` handler guarding an import of `shared`."""
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        imported = {
            n.module
            for stmt in node.body
            for n in ast.walk(stmt)
            if isinstance(n, ast.ImportFrom) and n.module
        } | {
            alias.name
            for stmt in node.body
            for n in ast.walk(stmt)
            if isinstance(n, ast.Import)
            for alias in n.names
        }
        if imported & set(shared):
            found.extend(node.handlers)
    return found


@pytest.mark.parametrize("path,shared", CONSUMERS.items(), ids=lambda v: getattr(v, "name", v))
def test_shared_import_has_no_fallback_body(path, shared):
    """The handler may only re-raise — never define a stand-in."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    handlers = _import_handlers(tree, shared)
    assert handlers, f"{path.name}: no guarded import of {shared} found"
    for handler in handlers:
        for stmt in handler.body:
            assert isinstance(stmt, ast.Raise), (
                f"{path.name}: the ImportError handler for {shared} contains a "
                f"{type(stmt).__name__} — it must only re-raise. A fallback "
                f"implementation here is a second copy of the classifier that "
                f"can drift from its source (#1968)."
            )


@pytest.mark.parametrize("path,shared", CONSUMERS.items(), ids=lambda v: getattr(v, "name", v))
def test_no_local_reimplementation_of_shared_classifiers(path, shared):
    src = path.read_text(encoding="utf-8")
    for name in FORBIDDEN_FALLBACK_NAMES:
        assert name not in src, (
            f"{path.name} defines {name!r} — a local re-implementation of a "
            f"hooks/lib classifier. Import it instead (#1968)."
        )


@pytest.mark.parametrize("path,shared", CONSUMERS.items(), ids=lambda v: getattr(v, "name", v))
def test_import_failure_is_loud_and_names_the_searched_path(path, shared, tmp_path):
    """Run the module in a subprocess with hooks/lib unreachable and assert it
    dies with a diagnostic — not a bare ModuleNotFoundError, and never a
    silent degrade. This is the behavior the deleted fallbacks suppressed."""
    probe = textwrap.dedent(f"""
        import importlib.util, sys
        for _n in {list(shared)!r}:
            sys.modules[_n] = None          # force ImportError on import
        spec = importlib.util.spec_from_file_location("probe_mod", {str(path)!r})
        m = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(m)
        except ImportError as exc:
            print("RAISED", exc)
            sys.exit(0)
        print("NO_RAISE")
        sys.exit(1)
    """)
    script = tmp_path / "probe.py"
    script.write_text(probe)
    res = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert res.returncode == 0, (
        f"{path.name} did not raise on an unreachable shared module: "
        f"{res.stdout}{res.stderr}"
    )
    out = res.stdout
    assert "RAISED" in out
    # The diagnostic must name the path it searched — the parent-count in the
    # sys.path setup is the fragile part when a file moves, and a bare
    # "No module named X" leaves that to be reverse-engineered.
    assert "hooks/lib" in out or "hooks\\lib" in out, f"no searched path in: {out}"
    assert "#1968" in out, f"diagnostic does not point at the rationale: {out}"


def test_consumers_still_import_and_classify_normally():
    """The happy path is unaffected: with hooks/lib reachable (the real case),
    both modules import and classify as before."""
    for path in CONSUMERS:
        spec = importlib.util.spec_from_file_location(f"ok_{path.stem}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert module.is_functional_config("plugins/dev-team/agents/foo.md") is True
        assert module.is_functional_config("docs/x.md") is False
