"""The convention / accessibility / performance probes (#1979).

Two extra invocations of tools already in the tiers — `ruff --select
N,PLR2004` and oxlint with its jsx-a11y/react-perf plugins — hand review
agents deterministic findings where `naming-review`, `a11y-review`, and
`performance-review` would otherwise re-derive them by inference.

Where the tool is guaranteed present in CI (ruff is a declared dev
dependency) these are **behavioral** tests that run it: a documented claim
about a tool's behavior is worth only as much as the run that confirms it,
and the calibration claims here — that `PLR2004` ignores `0`/`1`, that
`--select` does not duplicate the main lane — are exactly the kind that rot
silently. oxlint is not installed in CI, so its probes are skip-guarded and
the documentation contract is asserted instead.
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from _repo_root import REPO_ROOT

_SAI = REPO_ROOT / "plugins/dev-team/skills/static-analysis-integration"
SKILL = _SAI / "SKILL.md"
CONFIGS = _SAI / "references" / "tool-configs.md"
PARSER = _SAI / "references" / "sarif-parser.md"
AGENTS = REPO_ROOT / "plugins/dev-team/agents"

RUFF_PROBE = "ruff check --select N,PLR2004 --output-format sarif ."
OXLINT_PROBE = (
    "npx oxlint --jsx-a11y-plugin --react-plugin --react-perf-plugin "
    "-D perf --format sarif ."
)


def _ruff_sarif(target_dir) -> list[dict]:
    """Run the documented convention probe and return its SARIF results.

    Also asserts the driver name, because that string is the key
    `TOOL_TIER_MAP` is looked up by: if ruff ever renamed itself, every
    finding would silently fall back to the `generic` tier — the exact defect
    #1979 fixed — with the rule-id unit tests still green, since they pass the
    driver name in by hand.
    """
    proc = subprocess.run(
        ["python3", "-m", "ruff", "check", "--select", "N,PLR2004",
         "--output-format", "sarif", "."],
        cwd=str(target_dir), capture_output=True, text=True, timeout=120, check=False,
    )
    doc = json.loads(proc.stdout)
    assert doc["runs"][0]["tool"]["driver"]["name"] == "ruff"
    return doc["runs"][0]["results"]


def _rule_ids(results) -> set:
    return {r["ruleId"] for r in results}


# --------------------------------------------------------------------------
# ruff convention probe — behavioral (ruff is a declared dev dependency)
# --------------------------------------------------------------------------
def test_convention_probe_reports_naming_and_magic_values(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[tool.ruff.lint]\nselect = ["E", "F"]\n')
    (tmp_path / "svc.py").write_text(
        "def BadlyNamedFunction(X):\n"
        "    if X > 1000:\n"
        "        return X\n"
        "    return 0\n"
    )
    rules = _rule_ids(_ruff_sarif(tmp_path))
    assert "N802" in rules, "PEP 8 function-name convention not reported"
    assert "N803" in rules, "PEP 8 argument-name convention not reported"
    assert "PLR2004" in rules, "magic value in comparison not reported"


def test_convention_probe_finds_rules_the_project_has_not_enabled(tmp_path):
    """The whole point: a project whose own config selects only E/F still
    yields naming and magic-value context for the agents. If this stopped
    holding, the lane would be displacing nothing."""
    (tmp_path / "pyproject.toml").write_text('[tool.ruff.lint]\nselect = ["E", "F"]\n')
    (tmp_path / "svc.py").write_text("def BadName(x):\n    return x > 1000\n")
    project_run = subprocess.run(
        ["python3", "-m", "ruff", "check", "--output-format", "sarif", "."],
        cwd=str(tmp_path), capture_output=True, text=True, timeout=120, check=False,
    )
    assert _rule_ids(json.loads(project_run.stdout)["runs"][0]["results"]) == set()
    assert _rule_ids(_ruff_sarif(tmp_path))


def test_magic_value_rule_ignores_trivial_literals(tmp_path):
    """The calibration claim in tool-configs: PLR2004's defaults exclude 0, 1
    and -1, which is why this probe runs unconditionally while the JS/TS
    equivalent is a project opt-in. Ruff changing that default would flood the
    injection, so it is pinned rather than trusted."""
    (tmp_path / "svc.py").write_text(
        "def f(xs):\n"
        "    if len(xs) == 0:\n"
        "        return 1\n"
        "    if len(xs) == -1:\n"
        "        return 0\n"
        "    return len(xs) > 1000\n"
    )
    results = _ruff_sarif(tmp_path)
    messages = [r["message"]["text"] for r in results if r["ruleId"] == "PLR2004"]
    assert any("1000" in m for m in messages), "the real magic value was missed"
    for trivial in ("`0`", "`1`", "`-1`"):
        assert not any(trivial in m for m in messages), f"{trivial} should be ignored"


def test_select_does_not_re_report_what_the_main_lane_already_covers(tmp_path):
    """`--select` (not `--extend-select`) is what keeps the probe's output
    disjoint from the main lane's, so the two invocations do not each pay to
    report the project's own configured rules."""
    (tmp_path / "pyproject.toml").write_text('[tool.ruff.lint]\nselect = ["F"]\n')
    (tmp_path / "svc.py").write_text("import os\n\n\ndef Bad(x):\n    return x > 1000\n")
    rules = _rule_ids(_ruff_sarif(tmp_path))
    assert "F401" not in rules, "probe re-reported a main-lane rule (unused import)"
    assert rules <= {"N801", "N802", "N803", "N806", "N815", "PLR2004"}


def test_project_scoping_survives_the_probe(tmp_path):
    """A project's excludes and per-file-ignores must still apply — the probe
    adds rules, it does not take over config resolution."""
    (tmp_path / "pyproject.toml").write_text(
        '[tool.ruff.lint]\nselect = ["E"]\n'
        'per-file-ignores = {"legacy.py" = ["N"]}\n'
        "\n[tool.ruff]\nexclude = [\"vendored\"]\n"
    )
    (tmp_path / "vendored").mkdir()
    body = "def BadName(X):\n    return X\n"
    (tmp_path / "vendored" / "v.py").write_text(body)
    (tmp_path / "legacy.py").write_text(body)
    (tmp_path / "current.py").write_text(body)
    files = {
        r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
        for r in _ruff_sarif(tmp_path)
    }
    assert any("current.py" in f for f in files)
    assert not any("vendored" in f for f in files), "project exclude was overridden"
    assert not any("legacy.py" in f for f in files), "per-file-ignores was overridden"


def test_inline_noqa_still_suppresses_a_probe_finding(tmp_path):
    """The per-site escape hatch a developer reaches for first."""
    (tmp_path / "svc.py").write_text("def ExemptedName(x):  # noqa: N802\n    return x\n")
    assert "N802" not in _rule_ids(_ruff_sarif(tmp_path))


# --------------------------------------------------------------------------
# oxlint frontend probe — behavioral where available, contract otherwise
# --------------------------------------------------------------------------
def _oxlint_binary() -> str | None:
    """oxlint is documented as a project-local devDependency, so a bare PATH
    probe is not sufficient on its own — tool-configs' own Detection bullet
    says exactly that. Check the repo-local bin first, then PATH."""
    local = REPO_ROOT / "node_modules" / ".bin" / "oxlint"
    if local.is_file():
        return str(local)
    return shutil.which("oxlint")


oxlint_required = pytest.mark.skipif(
    _oxlint_binary() is None,
    reason="oxlint is a project-local devDependency, not present in this environment",
)


def _oxlint_sarif(target_dir) -> list[dict]:
    proc = subprocess.run(
        [_oxlint_binary(), "--jsx-a11y-plugin", "--react-plugin", "--react-perf-plugin",
         "-D", "perf", "--format", "sarif", "."],
        cwd=str(target_dir), capture_output=True, text=True, timeout=120, check=False,
    )
    doc = json.loads(proc.stdout)
    # Same reason as the ruff probe: this is the TOOL_TIER_MAP lookup key.
    assert doc["runs"][0]["tool"]["driver"]["name"] == "oxlint"
    return doc["runs"][0]["results"]


@oxlint_required
def test_frontend_probe_reports_accessibility_violations(tmp_path):
    (tmp_path / "Widget.jsx").write_text(
        "export function Widget({ onPick }) {\n"
        "  return (\n"
        "    <div onClick={onPick}>\n"
        '      <img src="/logo.png" />\n'
        "    </div>\n"
        "  )\n"
        "}\n"
    )
    plugins = {r["ruleId"].split("(")[0] for r in _oxlint_sarif(tmp_path)}
    assert "jsx-a11y" in plugins
    assert any("alt-text" in r["ruleId"] for r in _oxlint_sarif(tmp_path))


@oxlint_required
def test_frontend_probe_reports_the_n_plus_one_shape(tmp_path):
    """`no-await-in-loop` is the I/O-in-loop / N+1 pattern the spike names as
    performance-review's mechanical half."""
    (tmp_path / "load.js").write_text(
        "export async function load(ids) {\n"
        "  const out = []\n"
        "  for (const id of ids) {\n"
        "    out.push(await fetch(id))\n"
        "  }\n"
        "  return out\n"
        "}\n"
    )
    assert any("no-await-in-loop" in r["ruleId"] for r in _oxlint_sarif(tmp_path))


# --------------------------------------------------------------------------
# Registration contracts
# --------------------------------------------------------------------------
def test_both_probes_are_registered_in_the_skill_and_the_configs():
    skill, configs = SKILL.read_text(), CONFIGS.read_text()
    assert RUFF_PROBE in skill and RUFF_PROBE in configs
    assert OXLINT_PROBE in skill
    for flag in ("--jsx-a11y-plugin", "--react-perf-plugin", "-D perf"):
        assert flag in configs, f"{flag} not documented in tool-configs"


def test_the_probes_add_no_new_tool_to_the_dedup_chain():
    """Both reuse binaries already in the chain, so the precedence order — and
    the two tests that pin it — are deliberately untouched."""
    chain = (
        "semgrep > gitleaks > trivy > hadolint > actionlint "
        "> ruff > mypy > oxlint > (legacy ESLint > tsc) > lizard > jscpd"
    )
    assert chain in SKILL.read_text()


def test_semgrep_registry_performance_packs_are_explicitly_declined():
    """The spike suggested `p/performance`; resolving a registry pack needs an
    outbound call, which the pre-pass's offline posture forbids. The reason is
    recorded so the option is not silently re-added later."""
    skill = SKILL.read_text()
    assert "p/performance" in skill
    assert "offline" in skill.lower()


def test_parser_documents_the_plugin_rule_shape_and_the_two_tier_rows():
    parser = PARSER.read_text()
    assert "oxlint.jsx-a11y.alt-text" in parser
    assert "| ruff | `python` |" in parser
    assert "| oxlint | `js`" in parser


def test_the_jsts_magic_number_optin_records_the_measurement_behind_it():
    """A project-config opt-in rather than a forced rule, because the
    unconfigured default is mostly trivial values. The number is what makes
    that a decision instead of a preference."""
    configs = CONFIGS.read_text()
    assert "no-magic-numbers" in configs
    assert "35%" in configs
    assert '"ignore": [0, 1, -1]' in configs


@pytest.mark.parametrize(
    "agent,marker",
    [
        ("naming-review", "ruff.python.plr2004"),
        ("a11y-review", "oxlint.jsx-a11y."),
        ("performance-review", "oxlint.eslint.no-await-in-loop"),
    ],
)
def test_each_displaced_lens_is_told_not_to_re_report_the_lane(agent, marker):
    """Acceptance criterion: the charters must not contradict the injection's
    'do not re-report' framing — each names the rule ids that now arrive
    pre-computed, and what judgment remains its own."""
    text = (AGENTS / f"{agent}.md").read_text()
    assert "static-analysis pre-pass" in text
    assert "do not re-report" in text.lower()
    assert marker in text
