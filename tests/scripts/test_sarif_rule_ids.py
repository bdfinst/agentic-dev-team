"""Rule-id construction in the shared SARIF parser (#1979).

`build_rule_id` implements `references/sarif-parser.md`'s prefix conventions
and is what every static-analysis lane's findings are keyed by — dedup, the
ACCEPTED-RISKS suppression rules, and the agent-facing injection all read it.
It had no test at all, and two defects were living in that gap: `ruff` and
`oxlint` were missing from `TOOL_TIER_MAP`, so their findings were emitted
under a `generic` tier that contradicts the ids their own tool-configs entries
advertise; and oxlint's `plugin(rule)` id shape was hyphen-flattened, losing
the plugin namespace that tells an accessibility finding from a performance
one.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import textwrap

import pytest

from _repo_root import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "evals" / "static-analysis-tools"))
import validate

SCHEMA = json.loads(
    (
        REPO_ROOT
        / "plugins/dev-team/knowledge/schemas/unified-finding-v1.json"
    ).read_text()
)
#: The envelope's own `rule_id` constraint — the oracle here, not a restatement.
RULE_ID_PATTERN = re.compile(SCHEMA["properties"]["rule_id"]["pattern"])


@pytest.mark.parametrize(
    "driver,raw,expected",
    [
        # oxlint's `plugin(rule)` shape: the plugin becomes the tier segment.
        ("oxlint", "jsx-a11y(alt-text)", "oxlint.jsx-a11y.alt-text"),
        ("oxlint", "eslint(no-magic-numbers)", "oxlint.eslint.no-magic-numbers"),
        ("oxlint", "eslint(no-await-in-loop)", "oxlint.eslint.no-await-in-loop"),
        ("oxlint", "oxc(no-map-spread)", "oxlint.oxc.no-map-spread"),
        # Flat ids still take the tool's tier from TOOL_TIER_MAP.
        ("oxlint", "some-flat-rule", "oxlint.js.some-flat-rule"),
        ("ruff", "N802", "ruff.python.n802"),
        ("ruff", "PLR2004", "ruff.python.plr2004"),
        # Pre-existing conventions must be untouched by the new branch.
        (
            "semgrep",
            "python.django.audit.sql-injection",
            "semgrep.python.django.audit.sql-injection",
        ),
        ("gitleaks", "aws-access-key", "gitleaks.secrets.aws-access-key"),
        ("hadolint", "DL3008", "hadolint.dockerfile.dl3008"),
    ],
)
def test_rule_id_construction(driver, raw, expected):
    assert validate.build_rule_id(driver, raw) == expected


@pytest.mark.parametrize(
    "driver,raw",
    [
        ("oxlint", "jsx-a11y(alt-text)"),
        ("oxlint", "eslint(no-magic-numbers)"),
        ("oxlint", "weird((nested))"),      # unmatched shape must still be valid
        ("oxlint", "trailing()"),           # empty rule half
        ("ruff", "N802"),
        ("ruff", "ANN101"),
        ("semgrep", "python.lang.security.audit.eval-detected"),
        ("trivy", "CVE-2024-1234"),
        ("unknown-tool", "SOME_RULE"),
        # Degenerate inputs. Each produced a schema-INVALID id before #1979:
        # a driver name with a space landed a space in the first segment, and
        # a rule id that kebabs to nothing left an empty trailing segment.
        ("ox lint", "a(b)"),
        ("Semgrep OSS", "py.rule"),
        ("oxlint", ""),
        ("oxlint", "()"),
        ("oxlint", "日本語"),
        ("oxlint", "---"),
        ("日本語", "N802"),          # driver that kebabs to nothing
        ("   ", "a(b)"),
    ],
)
def test_every_rule_id_satisfies_the_envelope_pattern(driver, raw):
    """The schema is the oracle: a rule_id that fails this pattern makes the
    whole finding invalid, and the parser is required to emit only valid
    findings."""
    rule_id = validate.build_rule_id(driver, raw)
    assert RULE_ID_PATTERN.match(rule_id), f"{raw!r} -> {rule_id!r}"


def test_ruff_and_oxlint_are_not_emitted_under_the_generic_tier():
    """Regression: both were absent from TOOL_TIER_MAP, so every finding from
    the two language linters carried a `generic` segment while their
    tool-configs entries documented `python`/`js`."""
    assert validate.TOOL_TIER_MAP["ruff"] == "python"
    assert validate.TOOL_TIER_MAP["oxlint"] == "js"
    assert "generic" not in validate.build_rule_id("ruff", "N802")
    assert "generic" not in validate.build_rule_id("oxlint", "no-debugger")


def test_a_rule_id_that_kebabs_to_nothing_is_named_rather_than_left_empty():
    """`oxlint.js.` — a trailing dot with an empty segment — fails the
    envelope pattern, so the whole finding would be dropped by the validating
    parser even though its file, line, and message are perfectly usable."""
    assert validate.build_rule_id("oxlint", "") == "oxlint.js.unknown"
    assert validate.build_rule_id("oxlint", "()") == "oxlint.js.unknown"


def test_a_driver_name_is_kebab_cased_into_the_first_segment():
    """A tool reporting itself as `Semgrep OSS` must not put a space in the
    rule id. No-op for every tool actually wired up."""
    assert validate.build_rule_id("Semgrep OSS", "py.rule") == "semgrep-oss.py.rule"
    assert validate.build_rule_id("semgrep", "py.rule") == "semgrep.py.rule"


def test_the_plugin_segment_makes_oxlint_findings_selectable_by_prefix():
    """What preserving `plugin(rule)` actually buys: the plugin-scoped lanes
    are addressable by prefix. Asserted as a prefix match rather than
    "not a11y" — the weaker form was satisfied by the hyphen-flattened id
    this branch exists to replace, so it could not have failed."""
    assert validate.build_rule_id("oxlint", "jsx-a11y(alt-text)").startswith(
        "oxlint.jsx-a11y."
    )
    assert validate.build_rule_id(
        "oxlint", "react-perf(jsx-no-new-object-as-prop)"
    ).startswith("oxlint.react-perf.")


def test_the_eslint_plugin_segment_does_not_separate_concerns():
    """The honest limit of the branch, pinned so the rationale cannot drift
    into overclaiming: oxlint files both a performance rule and a correctness
    rule under its `eslint` plugin, so those two are distinguished by leaf
    name, not by prefix."""
    perf = validate.build_rule_id("oxlint", "eslint(no-await-in-loop)")
    correctness = validate.build_rule_id("oxlint", "eslint(no-unused-vars)")
    assert perf.rsplit(".", 1)[0] == correctness.rsplit(".", 1)[0] == "oxlint.eslint"
    assert perf != correctness


def test_a_driver_name_that_kebabs_to_nothing_is_named_too():
    """The driver is the one segment with no empty guard until #1979, and
    `parse_sarif` rejects only a falsy driver name — whitespace or a
    non-Latin name reaches the builder and would emit a leading dot."""
    for driver in ("日本語", "   ", "---"):
        rule_id = validate.build_rule_id(driver, "N802")
        assert rule_id.startswith("unknown-tool."), rule_id
        assert RULE_ID_PATTERN.match(rule_id)


def test_the_module_imports_without_the_jsonschema_dependency():
    """Regression: `validate.py` imported `jsonschema`/`referencing` at module
    scope, so importing it purely for `build_rule_id` required a dependency
    the validation path alone needs. That broke this very file's collection in
    the `Plugin content & hooks` CI job, which installs pytest and nothing
    else — a green local run (where the dep is present) could not catch it.
    Run in a subprocess with the modules forced unimportable."""
    probe = textwrap.dedent(
        """
        import sys
        for mod in ("jsonschema", "referencing", "referencing.jsonschema"):
            sys.modules[mod] = None
        sys.path.insert(0, %r)
        import validate
        assert validate.build_rule_id("ruff", "N802") == "ruff.python.n802"
        print("OK")
        """
    ) % str(REPO_ROOT / "evals" / "static-analysis-tools")
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, timeout=60,
        check=False,
    )
    assert result.returncode == 0, f"{result.stdout}{result.stderr}"
    assert "OK" in result.stdout


def test_normalize_findings_shares_this_parser_rather_than_copying_it():
    """`scripts/lib/normalize_findings.py` imports the same builder, so the
    conventions cannot drift between the eval validator and the pre-pass."""
    path = REPO_ROOT / "scripts" / "lib" / "normalize_findings.py"
    source = path.read_text(encoding="utf-8")
    assert "from validate import" in source
    spec = importlib.util.spec_from_file_location("normalize_findings_probe", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.TOOL_TIER_MAP["oxlint"] == "js"
