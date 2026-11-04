"""progress_guardian.parse_plan reads its steps from the feature record (#2275).

Import style: `parse_plan` is called on plan files and compared item by item
with a frozen copy of the loop it used before it read the record. The import
order of `feature_record` and `progress_guardian` is checked in a fresh
interpreter per order.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

_SCRIPTS = _REPO_ROOT / "plugins" / "dev-team" / "scripts"
sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(_SCRIPTS / "lib"))

import feature_record
import progress_guardian

# ---------------------------------------------------------------------------
# The oracle: the checkbox loop of `progress_guardian.parse_plan` as of
# 8aec4d4 (before it read the record), copied literally with its regex. It must
# not follow the live guardian, so it shares no code with it.
# ---------------------------------------------------------------------------

_OLD_STEP_PATTERN = re.compile(r"^-\s+\[( |x|X)\]\s+(?:Step\s+[\d.]+:\s+)?(.+)$")


def _old_loop_steps(text: str) -> list[tuple[bool, str]]:
    lines = text.splitlines()
    has_build_progress = any(
        line.rstrip().startswith("## Build Progress") for line in lines
    )

    steps = []
    in_build_progress = not has_build_progress  # legacy plans: scan everything
    in_acceptance = False
    for raw in lines:
        line = raw.rstrip()
        if has_build_progress:
            if line.startswith("## Build Progress"):
                in_build_progress = True
                in_acceptance = False
                continue
            # Any other H2 closes the section.
            if in_build_progress and line.startswith("## "):
                in_build_progress = False
                continue
            if in_build_progress and line.startswith("### Acceptance Criteria"):
                in_acceptance = True
                continue
            # Any other H3 within Build Progress exits the AC subsection.
            if in_acceptance and line.startswith("### "):
                in_acceptance = False
        if not in_build_progress or in_acceptance:
            continue
        m = _OLD_STEP_PATTERN.match(line)
        if m:
            flag, header = m.group(1), m.group(2).strip()
            steps.append((flag.lower() == "x", header))
    return steps


# ---------------------------------------------------------------------------
# Plans: every literal the guardian's own tests write, plus a real-shape plan
# with indented steps nested under each slice.
# ---------------------------------------------------------------------------


def _guardian_fixture_plans() -> list[str]:
    source = (_REPO_ROOT / "tests" / "scripts" / "test_progress_guardian.py").read_text(
        encoding="utf-8"
    )

    def fold(node: ast.AST) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left, right = fold(node.left), fold(node.right)
            return None if left is None or right is None else left + right
        return None

    plans = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        name = getattr(node.func, "attr", getattr(node.func, "id", ""))
        if name == "write_text":
            candidate = fold(node.args[0])
        elif name == "make_plan" and len(node.args) > 1:
            candidate = fold(node.args[1])
        else:
            continue
        if candidate and "- [" in candidate:
            plans.append(candidate)
    return plans


_NESTED_INDENT_REAL_SHAPE = """# Plan: real shape

## Acceptance Criteria

- [ ] AC1 a top-level criterion

## Build Progress

### Slices (grouped by wave)

#### Wave 1
- [ ] Slice 1: Plan parse helpers
  - [x] Step 1.1: nested one
  - [ ] Step 1.2: nested two
- [x] Slice 2: The record
    - [x] Step 2.1: deeper nested

### Acceptance Criteria
- [ ] mirrored criterion

### Notes
- [X] Step 9.9: after the mirror

## Risks
- [ ] outside the section
"""

_PLANS = {
    **{f"guardian-fixture-{n}": p for n, p in enumerate(_guardian_fixture_plans())},
    "nested-indent-real-shape": _NESTED_INDENT_REAL_SHAPE,
}


def _write(tmp_path: Path, text: str) -> Path:
    plan = tmp_path / "plan.md"
    plan.write_text(text, encoding="utf-8")
    return plan


def _as_pairs(steps: list[progress_guardian.Step]) -> list[tuple[bool, str]]:
    return [(s.done, s.header) for s in steps]


def test_the_fixture_extraction_found_the_guardians_plans():
    assert len(_PLANS) > 10
    assert any("## Build Progress" in p for p in _PLANS.values())
    assert any("## Build Progress" not in p for p in _PLANS.values())


@pytest.mark.parametrize("plan_text", list(_PLANS.values()), ids=list(_PLANS))
def test_the_steps_equal_the_old_loops_item_by_item(tmp_path, plan_text):
    steps, errors = progress_guardian.parse_plan(_write(tmp_path, plan_text))

    expected = _old_loop_steps(plan_text)
    assert _as_pairs(steps) == expected
    assert bool(errors) == (not expected)


def test_the_steps_equal_the_records_build_progress_items(tmp_path):
    plan = _write(tmp_path, _NESTED_INDENT_REAL_SHAPE)

    steps, _ = progress_guardian.parse_plan(plan)

    items = feature_record.build_record(_NESTED_INDENT_REAL_SHAPE)["build_progress"][
        "items"
    ]
    assert steps == [progress_guardian.Step(i["done"], i["header"]) for i in items]
    assert [s.header for s in steps] == [
        "Slice 1: Plan parse helpers",
        "Slice 2: The record",
        "after the mirror",
    ]


def test_parse_plan_takes_its_steps_from_the_record_and_does_not_parse_markdown(
    tmp_path, monkeypatch
):
    """The record is the seam: a record that holds an item the Markdown does
    not hold must come out as a step. This fails if `parse_plan` re-reads the
    Markdown itself."""
    sentinel = {
        "kind": "step",
        "id": "7.7",
        "header": "sentinel only the record holds",
        "done": True,
        "commit_backed": None,
    }
    seen = []

    def fake_build_record(text, spec_text=None, *args, **kwargs):
        seen.append(text)
        return {"build_progress": {"legacy": False, "items": [sentinel]}}

    monkeypatch.setattr(
        progress_guardian.feature_record, "build_record", fake_build_record
    )
    plan = _write(tmp_path, _NESTED_INDENT_REAL_SHAPE)

    steps, errors = progress_guardian.parse_plan(plan)

    assert seen == [_NESTED_INDENT_REAL_SHAPE]
    assert steps == [progress_guardian.Step(True, "sentinel only the record holds")]
    assert errors == []


# ---------------------------------------------------------------------------
# Import order: a fresh interpreter per order.
# ---------------------------------------------------------------------------

_IMPORT_PROBE = """
import sys
sys.path.insert(0, {scripts!r})
{first}
{second}
def names(leaf):
    return sorted(k for k in sys.modules if k.split(".")[-1] == leaf)
for leaf in ("plan_parse", "plan_record_parse", "commit_evidence", "feature_record"):
    assert names(leaf) == [leaf], (leaf, names(leaf))
assert progress_guardian.feature_record is sys.modules["feature_record"]
assert progress_guardian.commit_evidence is sys.modules["commit_evidence"]
assert feature_record.plan_parse is sys.modules["plan_parse"]
print("ok")
"""


@pytest.mark.parametrize(
    "first,second",
    [
        ("import feature_record", "import progress_guardian"),
        ("import progress_guardian", "import feature_record"),
    ],
    ids=["feature_record-first", "progress_guardian-first"],
)
def test_the_modules_import_in_either_order_with_one_module_identity(first, second):
    probe = _IMPORT_PROBE.format(scripts=str(_SCRIPTS), first=first, second=second)

    result = subprocess.run(
        [sys.executable, "-I", "-c", probe],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
