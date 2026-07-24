"""Unit tests for hooks/lib/minimal_yaml.py (#732).

This module replaces `import yaml` (third-party PyYAML) in three shipped
scripts, per ADR 0014 / ADR 0015 (stdlib-only). Coverage here targets the
exact shapes those three call sites parse:

  - build_skills_index.py: SKILL.md frontmatter (name/description/
    user-invocable, folded `>-` block scalars, block sequences with
    trailing comments) + skill_categories.yaml (block sequence of
    two-key mappings with a multi-line flow list value).
  - agent-readiness/scanner.py: scorecard.yaml-shaped config (nested block
    mappings, inline flow mappings/lists, multi-line flow collections,
    quoted strings, ints/floats/bools).
  - security-review-adapter.py: security-review-rule-map.yaml-shaped
    mapping file (flat string->string `mappings`, plus a `classes` section
    mixing block and inline-flow mapping values) and its malformed-input
    failure mode.
"""

from __future__ import annotations

import sys

import pytest

from _repo_root import REPO_ROOT as _REPO_ROOT

sys.path.insert(0, str(_REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib"))

from minimal_yaml import (
    FrontmatterError,
    YamlError,
    extract_frontmatter_block,
    parse_yaml,
)


def test_yaml_import_is_not_used_by_this_module():
    """The whole point: no third-party import anywhere in the module."""
    src = (
        _REPO_ROOT / "plugins" / "dev-team" / "hooks" / "lib" / "minimal_yaml.py"
    ).read_text(encoding="utf-8")
    assert not any(
        line.strip() in ("import yaml", "from yaml import *")
        for line in src.splitlines()
    )
    assert not any(line.strip().startswith("from yaml ") for line in src.splitlines())


# ---------------------------------------------------------------------------
# extract_frontmatter_block
# ---------------------------------------------------------------------------


def test_extract_frontmatter_block_returns_text_between_markers():
    text = "---\nname: foo\n---\n\n# Body\n"
    assert extract_frontmatter_block(text) == "\nname: foo"


def test_extract_frontmatter_block_missing_leading_marker_raises():
    with pytest.raises(FrontmatterError):
        extract_frontmatter_block("name: foo\n---\n")


def test_extract_frontmatter_block_unterminated_raises():
    with pytest.raises(FrontmatterError):
        extract_frontmatter_block("---\nname: foo\n")


# ---------------------------------------------------------------------------
# SKILL.md frontmatter shapes (build_skills_index.py's _frontmatter)
# ---------------------------------------------------------------------------


def test_frontmatter_simple_key_values():
    block = extract_frontmatter_block(
        "---\n"
        "name: agent-audit\n"
        "description: Audit code-review agents, skills, and hooks.\n"
        "user-invocable: true\n"
        "---\n"
    )
    data = parse_yaml(block)
    assert data == {
        "name": "agent-audit",
        "description": "Audit code-review agents, skills, and hooks.",
        "user-invocable": True,
    }


def test_frontmatter_folded_block_scalar_description():
    block = extract_frontmatter_block(
        "---\n"
        "name: agent-readiness\n"
        "description: >-\n"
        "  Score how ready the current repository is for AI-assisted development against\n"
        '  the Agent-Readiness Scorecard. Use when the user asks "how agent-ready is this\n'
        '  repo".\n'
        'argument-hint: "[repo-path] [--json <file>]"\n'
        "user-invocable: true\n"
        "---\n"
    )
    data = parse_yaml(block)
    assert data["name"] == "agent-readiness"
    assert data["description"] == (
        "Score how ready the current repository is for AI-assisted development against "
        'the Agent-Readiness Scorecard. Use when the user asks "how agent-ready is this '
        'repo".'
    )
    assert data["argument-hint"] == "[repo-path] [--json <file>]"
    assert data["user-invocable"] is True


def test_frontmatter_block_scalar_ignores_hash_as_literal_not_comment():
    """Inside a `>-` body, `#` is literal text, never a comment (a real skill
    description can legitimately contain 'C#')."""
    block = extract_frontmatter_block(
        "---\n"
        "name: setup\n"
        "description: >-\n"
        "  prompts for language selection (JS/TS, Java, C#) to install the matching\n"
        "  tool.\n"
        "---\n"
    )
    data = parse_yaml(block)
    assert "C#)" in data["description"]


def test_frontmatter_block_sequence_with_trailing_comment():
    """Matches static-analysis-integration/SKILL.md's `maintainers:` list,
    including a `# TODO: ...` trailing comment on one item."""
    block = extract_frontmatter_block(
        "---\n"
        "name: static-analysis-integration\n"
        "maintainers:\n"
        "  - bdfinst\n"
        "  - unassigned   # TODO: name a second maintainer; bus-factor minimum is 2.\n"
        "required-primitives-contract: ^1.0.0\n"
        "---\n"
    )
    data = parse_yaml(block)
    assert data["maintainers"] == ["bdfinst", "unassigned"]
    assert data["required-primitives-contract"] == "^1.0.0"


def test_frontmatter_unescaped_colon_in_plain_scalar_raises_yamlerror():
    """A bare (unquoted, non-`>-`) description containing ': ' is ambiguous
    with a nested mapping key in real YAML and must be rejected loudly, not
    silently accepted — matches tests/repo/test_skills_index_current.py's
    test_unparseable_frontmatter_fails_the_build_loudly."""
    block = extract_frontmatter_block(
        "---\nname: bad\ndescription: refers to foo: bar inline\nuser-invocable: true\n---\n"
    )
    with pytest.raises(YamlError):
        parse_yaml(block)


def test_frontmatter_missing_description_key_is_just_absent():
    block = extract_frontmatter_block("---\nname: foo\n---\n")
    data = parse_yaml(block)
    assert "description" not in data


def test_frontmatter_malformed_yaml_raises_yamlerror():
    block = extract_frontmatter_block("---\nname: foo: bar: baz\n  nested: oops\n---\n")
    with pytest.raises(YamlError):
        parse_yaml(block)


# ---------------------------------------------------------------------------
# skill_categories.yaml shape (build_skills_index.py's _load_categories)
# ---------------------------------------------------------------------------


def test_skill_categories_shape_sequence_of_two_key_mappings_with_flow_list():
    text = (
        "categories:\n"
        "  - name: Specs & Planning\n"
        "    skills: [specs, plan, design-doc, design-interrogation, design-it-twice,\n"
        "             api-design, gherkin-derive]\n"
        "  - name: Build & Ship\n"
        "    skills: [build, test-driven-development, continue]\n"
    )
    data = parse_yaml(text)
    cats = data["categories"]
    assert cats[0]["name"] == "Specs & Planning"
    assert cats[0]["skills"] == [
        "specs",
        "plan",
        "design-doc",
        "design-interrogation",
        "design-it-twice",
        "api-design",
        "gherkin-derive",
    ]
    assert cats[1] == {
        "name": "Build & Ship",
        "skills": ["build", "test-driven-development", "continue"],
    }


def test_flow_sequence_with_opening_bracket_on_its_own_line():
    # A common auto-formatter output shape: `key:` then `[` alone on the next
    # line, one item per line, rather than `key: [a, b]` with the bracket on
    # the key's own line. The parser must merge and parse this the same way.
    text = (
        "categories:\n"
        "  - name: Specs & Planning\n"
        "    skills:\n"
        "      [\n"
        "        specs,\n"
        "        plan,\n"
        "        design-doc,\n"
        "      ]\n"
    )
    data = parse_yaml(text)
    assert data["categories"][0]["skills"] == ["specs", "plan", "design-doc"]


def test_flow_mapping_with_opening_brace_on_its_own_line():
    # Symmetry with the sequence case above: _parse_node's fix branches on
    # `[` OR `{`, so a flow mapping split the same way must work too.
    text = "k:\n  {\n    a: 1,\n    b: 2,\n  }\n"
    assert parse_yaml(text) == {"k": {"a": 1, "b": 2}}


def test_flow_sequence_tolerates_a_trailing_comma():
    assert parse_yaml("k: [a, b, c,]\n") == {"k": ["a", "b", "c"]}


def test_flow_sequence_tolerates_a_trailing_comma_with_one_element():
    assert parse_yaml("k: [a,]\n") == {"k": ["a"]}


def test_flow_mapping_tolerates_a_trailing_comma():
    assert parse_yaml("k: { a: 1, b: 2, }\n") == {"k": {"a": 1, "b": 2}}


def test_flow_mapping_tolerates_a_trailing_comma_with_one_element():
    assert parse_yaml("k: { a: 1, }\n") == {"k": {"a": 1}}


def test_nested_flow_collection_with_trailing_comma_inside_multiline_sequence():
    # Combines both fixes: bracket-on-its-own-line plus a trailing comma on
    # an inner flow collection.
    text = "k:\n  [\n    a,\n    { x: 1, },\n  ]\n"
    assert parse_yaml(text) == {"k": ["a", {"x": 1}]}


def test_unterminated_multiline_flow_sequence_raises_yaml_error():
    # The merge-continuation path (_next_line) must still surface an
    # unterminated flow collection as an error, not silently truncate it.
    text = "k:\n  [\n    a,\n    b,\n"
    with pytest.raises(YamlError):
        parse_yaml(text)


# ---------------------------------------------------------------------------
# scorecard.yaml shape (agent-readiness/scanner.py)
# ---------------------------------------------------------------------------


def test_scorecard_shape_nested_mappings_flow_collections_and_types():
    text = (
        'version: "1.0-mvp"\n'
        "\n"
        "weights:\n"
        "  test_infrastructure: 0.25\n"
        "  build_env: 0.20\n"
        "\n"
        "tiers:\n"
        "  agent_ready: 75\n"
        "  agent_assisted: 50\n"
        "\n"
        "criteria:\n"
        "  build_env:\n"
        "    B1_single_command_build: { mvp: false }\n"
        "    B2_reproducible_env: { mvp: true }\n"
        "  code_quality:\n"
        "    C3_architecture: { mvp: false, manual_review: true }\n"
        "\n"
        "thresholds:\n"
        "  file_size_p90_small: 300   # source-file p90 line count\n"
        "  readme_min_words: 200\n"
        "\n"
        'source_extensions: [".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java",\n'
        '                    ".cs", ".rb"]\n'
        'exclude_dirs: [".git", "node_modules"]\n'
    )
    data = parse_yaml(text)
    assert data["version"] == "1.0-mvp"
    assert data["weights"] == {"test_infrastructure": 0.25, "build_env": 0.20}
    assert data["tiers"] == {"agent_ready": 75, "agent_assisted": 50}
    assert data["criteria"]["build_env"]["B1_single_command_build"] == {"mvp": False}
    assert data["criteria"]["build_env"]["B2_reproducible_env"] == {"mvp": True}
    assert data["criteria"]["code_quality"]["C3_architecture"] == {
        "mvp": False,
        "manual_review": True,
    }
    assert data["thresholds"]["file_size_p90_small"] == 300
    assert data["thresholds"]["readme_min_words"] == 200
    assert data["source_extensions"] == [
        ".py",
        ".js",
        ".ts",
        ".jsx",
        ".tsx",
        ".go",
        ".rs",
        ".java",
        ".cs",
        ".rb",
    ]
    assert data["exclude_dirs"] == [".git", "node_modules"]


def test_scorecard_inline_test_config_shape():
    """Matches tests/repo/test_agent_readiness.py's inline custom config —
    single-line flow mappings, including one split across two lines."""
    text = (
        'version: "test"\n'
        "weights: { documentation: 1.0 }\n"
        "tiers: { agent_ready: 0, agent_assisted: 0, agent_limited: 0 }\n"
        "criteria:\n"
        "  documentation:\n"
        "    D1_readme: { mvp: true }\n"
        "thresholds: { readme_min_words: 200, ai_instructions_min_words: 100,\n"
        "              file_size_p90_small: 300, file_size_p90_large: 500 }\n"
        'source_extensions: [".py"]\n'
        'exclude_dirs: [".git"]\n'
    )
    data = parse_yaml(text)
    assert data["version"] == "test"
    assert data["weights"] == {"documentation": 1.0}
    assert data["tiers"] == {
        "agent_ready": 0,
        "agent_assisted": 0,
        "agent_limited": 0,
    }
    assert data["criteria"]["documentation"]["D1_readme"] == {"mvp": True}
    assert data["thresholds"] == {
        "readme_min_words": 200,
        "ai_instructions_min_words": 100,
        "file_size_p90_small": 300,
        "file_size_p90_large": 500,
    }
    assert data["source_extensions"] == [".py"]
    assert data["exclude_dirs"] == [".git"]


# ---------------------------------------------------------------------------
# security-review-rule-map.yaml shape (security-review-adapter.py)
# ---------------------------------------------------------------------------


def test_rule_map_shape_flat_mappings_dict():
    text = (
        "version: 1.1.0\n"
        "mappings:\n"
        "  A02.weak-hashing-md5: semgrep.generic.weak-hash-md5\n"
        "  A01.idor: security-review.a01.idor\n"
        "\n"
        "classes:\n"
        "  A02.weak-hashing-md5:\n"
        "    surface: rule\n"
        "    fp_rate: 0.0\n"
        "    fixtures: knowledge/rule-fixtures/A02.weak-hashing-md5\n"
        "  A01.idor: { surface: prompt }\n"
    )
    data = parse_yaml(text)
    assert data["mappings"] == {
        "A02.weak-hashing-md5": "semgrep.generic.weak-hash-md5",
        "A01.idor": "security-review.a01.idor",
    }
    assert data["classes"]["A02.weak-hashing-md5"] == {
        "surface": "rule",
        "fp_rate": 0.0,
        "fixtures": "knowledge/rule-fixtures/A02.weak-hashing-md5",
    }
    assert data["classes"]["A01.idor"] == {"surface": "prompt"}


def test_rule_map_malformed_mapping_raises_yamlerror():
    """Matches evals/security-review-adapter/fixtures/malformed-mapping.yaml:
    a scalar value ('this: is') followed by orphaned, more-indented content
    is invalid and must hard-fail, not silently parse."""
    text = "version: 1.0.0\nmappings: this: is\n  not valid\n  [yaml\n"
    with pytest.raises(YamlError):
        parse_yaml(text)


# ---------------------------------------------------------------------------
# Scalar type coercion
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("true", True),
        ("false", False),
        ("null", None),
        ("~", None),
        ("42", 42),
        ("-3", -3),
        ("0.25", 0.25),
        ("2.0.0", "2.0.0"),  # not a valid int/float -> stays a plain string
        ("^1.0.0", "^1.0.0"),
        ('"quoted string"', "quoted string"),
        ("'single quoted'", "single quoted"),
        ("bare string", "bare string"),
    ],
)
def test_parse_scalar_via_top_level_key(raw, expected):
    data = parse_yaml(f"k: {raw}\n")
    assert data["k"] == expected
