"""#822 — project-init detects the project's stack from cheap filesystem
signals, inventories the existing toolchain per capability slot, asks the
user when detection is inconclusive, and keeps the old JS trigger phrases
alongside the new generic ones. Documentation gate over the skill prose.
"""

from __future__ import annotations

from skill_doc_helpers import PLUGIN_ROOT, frontmatter, grep, section

SKILL = PLUGIN_ROOT / "skills" / "project-init" / "SKILL.md"


def _text() -> str:
    return SKILL.read_text()


def _frontmatter() -> str:
    return frontmatter(_text())


def _detection_section() -> str:
    return section(_text(), r"^### Step 1: Detect the stack")


def _inventory_section() -> str:
    return section(_text(), r"^### Step 2: Inventory the existing toolchain")


# --- rename: frontmatter identity -------------------------------------------


def test_frontmatter_names_the_skill_project_init():
    assert grep(r"^name: project-init$", _frontmatter())


def test_skill_stays_user_invocable():
    assert grep(r"^user-invocable: true$", _frontmatter())


def test_description_keeps_the_previous_js_trigger_phrases():
    fm = _frontmatter()
    for phrase in (
        "init a new project",
        "set up a JS project",
        "create a new node app",
        "start a new frontend project",
        "bootstrap a new package",
    ):
        assert phrase in fm, f"missing JS trigger phrase: {phrase}"


def test_description_adds_the_generic_toolchain_trigger_phrases():
    fm = _frontmatter()
    for phrase in (
        "set up my project's toolchain",
        "install the linters for this repo",
        "get this repo ready for the plugin",
    ):
        assert phrase in fm, f"missing generic trigger phrase: {phrase}"


# --- stack detection signals -------------------------------------------------


def test_detection_uses_only_cheap_filesystem_signals():
    assert grep(r"no builds, no network", _detection_section())


def test_detection_signals_for_js_ts():
    s = _detection_section()
    for sig in ("package.json", "tsconfig.json"):
        assert sig in s, f"missing JS/TS signal: {sig}"


def test_detection_signals_for_python():
    s = _detection_section()
    for sig in ("pyproject.toml", "requirements", "setup.py"):
        assert sig in s, f"missing Python signal: {sig}"


def test_detection_signals_for_csharp():
    s = _detection_section()
    for sig in (".sln", ".csproj", "global.json"):
        assert sig in s, f"missing C# signal: {sig}"


def test_detection_signals_for_java():
    s = _detection_section()
    for sig in ("pom.xml", "build.gradle"):
        assert sig in s, f"missing Java signal: {sig}"


def test_multiple_detected_stacks_set_up_every_matched_language():
    assert grep(r"multiple stacks", _detection_section(), ignore_case=True)
    assert grep(r"every matched\s+language", _detection_section(), ignore_case=True)


def test_inconclusive_detection_asks_the_user_with_a_something_else_option():
    s = _detection_section()
    assert grep(r"ask the\s+\**user", s, ignore_case=True)
    assert grep(r"something else", s, ignore_case=True)


def test_something_else_exits_gracefully_with_no_writes():
    s = _detection_section()
    assert grep(r"no\s+files written", s, ignore_case=True)
    assert grep(r"nothing installed", s, ignore_case=True)


# --- toolchain inventory (brownfield second pass) ----------------------------


def test_inventory_reads_config_file_signals():
    s = _inventory_section()
    for sig in (
        "eslint.config.js",
        "biome.json",
        "[tool.ruff]",
        ".flake8",
        ".pylintrc",
        "checkstyle.xml",
    ):
        assert sig in s, f"missing config-file signal: {sig}"


def test_inventory_reads_dependency_signals():
    s = _inventory_section()
    for sig in ("devDependencies", "requirements-dev.txt", "dev group"):
        assert sig in s, f"missing dependency signal: {sig}"


def test_inventory_runs_registry_probes_down_each_slots_ordered_provider_list():
    s = _inventory_section()
    assert grep(r"ordered provider list", s)
    assert grep(r"probe", s, ignore_case=True)


def test_binding_follows_bind_dont_replace():
    assert "bind-don't-replace" in _inventory_section()
