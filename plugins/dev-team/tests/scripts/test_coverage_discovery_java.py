"""Tests for scripts/coverage_discovery_java.py (issue #1765).

Pure filesystem + build-file parsing — no JVM, no `mvn`, and no `gradlew` is
invoked, so these tests need no Java toolchain installed. Mirrors the
.NET (Slice 2) and JS/TS (Slice 3) discovery test suites of #1759.
"""

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import coverage_discovery_java as cdjava
from coverage_config import DISCOVERY_NOT_APPLICABLE, TestClassification
from coverage_flow_shared import write

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def aggregator_pom(modules) -> str:
    entries = "\n".join(f"    <module>{m}</module>" for m in modules)
    return (
        '<project xmlns="http://maven.apache.org/POM/4.0.0">\n'
        "  <modules>\n"
        f"{entries}\n"
        "  </modules>\n"
        "</project>\n"
    )


def leaf_pom(*, with_test_dep: bool, framework: str = "junit-jupiter") -> str:
    deps = ""
    if with_test_dep:
        deps = (
            "  <dependencies>\n"
            "    <dependency>\n"
            "      <groupId>org.junit.jupiter</groupId>\n"
            f"      <artifactId>{framework}</artifactId>\n"
            "      <scope>test</scope>\n"
            "    </dependency>\n"
            "  </dependencies>\n"
        )
    return (
        '<project xmlns="http://maven.apache.org/POM/4.0.0">\n'
        "  <artifactId>leaf</artifactId>\n"
        f"{deps}"
        "</project>\n"
    )


def make_module(
    root: Path,
    rel: str,
    *,
    test_dir: str | None = "src/test/java",
    test_dep: bool = True,
    build_file: str = "pom.xml",
) -> None:
    """Create a module directory with an optional test-source dir and an
    optional test-framework dependency in its own build file."""
    mod = root / rel
    if build_file == "pom.xml":
        write(mod / "pom.xml", leaf_pom(with_test_dep=test_dep))
    elif build_file == "build.gradle":
        body = "dependencies {\n"
        if test_dep:
            body += "  testImplementation 'org.junit.jupiter:junit-jupiter:5.10.0'\n"
        else:
            body += "  implementation 'com.google.guava:guava:33.0.0-jre'\n"
        body += "}\n"
        write(mod / "build.gradle", body)
    elif build_file == "build.gradle.kts":
        body = "dependencies {\n"
        if test_dep:
            body += '  testImplementation("org.junit.jupiter:junit-jupiter:5.10.0")\n'
        else:
            body += '  implementation("com.google.guava:guava:33.0.0-jre")\n'
        body += "}\n"
        write(mod / "build.gradle.kts", body)
    if test_dir:
        (mod / test_dir).mkdir(parents=True, exist_ok=True)


def paths_of(result) -> list:
    return [entry["path"] for entry in result]


def classification_of(result, path):
    for entry in result:
        if entry["path"] == path:
            return entry["classification"]
    raise AssertionError(f"{path!r} not in result: {paths_of(result)}")


# ---------------------------------------------------------------------------
# Slice 1 — Maven module discovery
# ---------------------------------------------------------------------------


def test_aggregator_pom_yields_one_entry_per_module_with_classifications(tmp_path):
    write(tmp_path / "pom.xml", aggregator_pom(["core", "api", "it-tests"]))
    make_module(tmp_path, "core", test_dir="src/test/java", test_dep=True)
    make_module(tmp_path, "api", test_dir=None, test_dep=False)
    make_module(tmp_path, "it-tests", test_dir="src/test/java", test_dep=False)

    result = cdjava.discover_java_modules(tmp_path)

    assert paths_of(result) == ["api", "core", "it-tests"]
    assert classification_of(result, "core") is TestClassification.TEST
    assert classification_of(result, "api") is TestClassification.NOT_TEST
    assert classification_of(result, "it-tests") is TestClassification.AMBIGUOUS


def test_kotlin_test_source_dir_counts_as_a_test_source_directory(tmp_path):
    write(tmp_path / "pom.xml", aggregator_pom(["core"]))
    make_module(tmp_path, "core", test_dir="src/test/kotlin", test_dep=True)

    result = cdjava.discover_java_modules(tmp_path)

    assert result == [{"path": "core", "classification": TestClassification.TEST}]


def test_testng_dependency_is_recognized(tmp_path):
    write(tmp_path / "pom.xml", aggregator_pom(["core"]))
    mod = tmp_path / "core"
    write(
        mod / "pom.xml",
        '<project xmlns="http://maven.apache.org/POM/4.0.0">\n'
        "  <dependencies><dependency>\n"
        "    <groupId>org.testng</groupId><artifactId>testng</artifactId>\n"
        "  </dependency></dependencies>\n"
        "</project>\n",
    )
    (mod / "src" / "test" / "java").mkdir(parents=True)

    result = cdjava.discover_java_modules(tmp_path)

    assert classification_of(result, "core") is TestClassification.TEST


def test_nested_aggregator_modules_are_discovered_recursively(tmp_path):
    write(tmp_path / "pom.xml", aggregator_pom(["group"]))
    write(tmp_path / "group" / "pom.xml", aggregator_pom(["alpha", "beta"]))
    make_module(tmp_path, "group/alpha", test_dep=True)
    make_module(tmp_path, "group/beta", test_dep=True)

    result = cdjava.discover_java_modules(tmp_path)

    assert "group/alpha" in paths_of(result)
    assert "group/beta" in paths_of(result)


def test_self_referential_module_graph_terminates_without_duplicates(tmp_path):
    write(tmp_path / "pom.xml", aggregator_pom(["group"]))
    # group's own pom re-declares itself relative to the root, forming a cycle.
    write(tmp_path / "group" / "pom.xml", aggregator_pom(["../group"]))

    result = cdjava.discover_java_modules(tmp_path)

    assert paths_of(result).count("group") == 1


def test_maven_module_directory_without_a_pom_is_a_discovery_error(tmp_path):
    """A declared Maven <module> whose directory exists but has no pom.xml is
    the same domain fact as a missing directory — `mvn` itself fails on it — so
    it gets the same hard error. Classifying it would land it on NOT_TEST and
    drop it from coverage accounting silently."""
    write(tmp_path / "pom.xml", aggregator_pom(["ghost"]))
    (tmp_path / "ghost").mkdir()

    result = cdjava.discover_java_modules(tmp_path)

    assert result.get("signal") == "error"
    assert "ghost" in result["message"]


def test_gradle_subproject_without_a_build_file_is_classified_not_errored(tmp_path):
    """Deliberately NOT symmetrical with Maven: a Gradle subproject directory
    with no build file is legitimate (a container project), so it stays on the
    lenient classification path rather than becoming an error."""
    write(tmp_path / "settings.gradle", "include ':container'\n")
    (tmp_path / "container").mkdir()

    result = cdjava.discover_java_modules(tmp_path)

    assert result == [
        {"path": "container", "classification": TestClassification.NOT_TEST}
    ]


def test_declared_module_with_no_directory_on_disk_is_a_discovery_error(tmp_path):
    """A <module> naming a directory that does not exist is a broken build
    graph. It must NOT classify NOT_TEST — that makes needs_accounting() false,
    so the entry would never need to appear in included/excluded and would
    vanish from operator accounting. Mirrors coverage_discovery_dotnet.py's
    missing-project error."""
    write(tmp_path / "pom.xml", aggregator_pom(["absent"]))

    result = cdjava.discover_java_modules(tmp_path)

    assert result.get("signal") == "error"
    assert "absent" in result["message"]


def test_gradle_include_with_no_directory_on_disk_is_a_discovery_error(tmp_path):
    write(tmp_path / "settings.gradle", "include ':absent'\n")

    result = cdjava.discover_java_modules(tmp_path)

    assert result.get("signal") == "error"
    assert "absent" in result["message"]


def test_nested_aggregator_with_empty_modules_is_a_discovery_error(tmp_path):
    """The declared-but-empty <modules> rule applies one level down too — the
    root-only version of this check let a nested aggregator pass silently."""
    write(tmp_path / "pom.xml", aggregator_pom(["group"]))
    write(
        tmp_path / "group" / "pom.xml",
        '<project xmlns="http://maven.apache.org/POM/4.0.0">\n'
        "  <modules>\n  </modules>\n"
        "</project>\n",
    )

    result = cdjava.discover_java_modules(tmp_path)

    assert result.get("signal") == "error"
    assert "group" in result["message"]


# ---------------------------------------------------------------------------
# Maven classification is scoped to the module's own <dependencies>
# ---------------------------------------------------------------------------


def _pom_with(body: str) -> str:
    return (
        '<project xmlns="http://maven.apache.org/POM/4.0.0">\n'
        f"{body}"
        "</project>\n"
    )


@pytest.mark.parametrize(
    "body,label",
    [
        ("  <artifactId>junit-extensions</artifactId>\n", "own artifactId"),
        (
            (
                "  <dependencyManagement><dependencies><dependency>\n"
                "    <groupId>org.junit</groupId>"
                "<artifactId>junit-bom</artifactId>\n"
                "  </dependency></dependencies></dependencyManagement>\n"
            ),
            "dependencyManagement BOM",
        ),
        (
            (
                "  <build><plugins><plugin>\n"
                "    <artifactId>junit-platform-maven-plugin</artifactId>\n"
                "  </plugin></plugins></build>\n"
            ),
            "build plugin coordinate",
        ),
        (
            (
                "  <profiles><profile><dependencies><dependency>\n"
                "    <artifactId>junit-jupiter</artifactId>\n"
                "  </dependency></dependencies></profile></profiles>\n"
            ),
            "profile-scoped dependency",
        ),
    ],
)
def test_non_local_junit_mention_classifies_ambiguous_not_test(tmp_path, body, label):
    """Only the module's own top-level <dependencies> count as a locally
    declared test framework. A module merely NAMED junit-*, a BOM version
    declaration, a plugin coordinate, and a conditional profile-scoped
    dependency must each leave the module AMBIGUOUS — preserving the signal
    drift_check uses to force an operator decision."""
    write(tmp_path / "pom.xml", aggregator_pom(["mod"]))
    write(tmp_path / "mod" / "pom.xml", _pom_with(body))
    (tmp_path / "mod" / "src" / "test" / "java").mkdir(parents=True)

    result = cdjava.discover_java_modules(tmp_path)

    assert classification_of(result, "mod") is TestClassification.AMBIGUOUS, label


def test_single_module_pom_is_not_applicable(tmp_path):
    write(
        tmp_path / "pom.xml",
        '<project xmlns="http://maven.apache.org/POM/4.0.0">\n'
        "  <artifactId>solo</artifactId>\n"
        "</project>\n",
    )

    assert cdjava.discover_java_modules(tmp_path) is DISCOVERY_NOT_APPLICABLE


def test_no_java_build_files_at_all_is_not_applicable(tmp_path):
    (tmp_path / "src").mkdir()

    assert cdjava.discover_java_modules(tmp_path) is DISCOVERY_NOT_APPLICABLE


def test_malformed_root_pom_is_a_discovery_error(tmp_path):
    write(tmp_path / "pom.xml", "<project><modules><module>a</module>")

    result = cdjava.discover_java_modules(tmp_path)

    assert result.get("signal") == "error"
    assert "pom.xml" in result["message"]


def test_malformed_nested_module_pom_is_a_discovery_error(tmp_path):
    write(tmp_path / "pom.xml", aggregator_pom(["broken"]))
    write(tmp_path / "broken" / "pom.xml", "<project><dependencies>")

    result = cdjava.discover_java_modules(tmp_path)

    assert result.get("signal") == "error"
    assert "broken" in result["message"]


def test_empty_modules_element_is_a_discovery_error(tmp_path):
    """An explicit but empty <modules> is a declared-yet-unusable shape — it
    must not silently degrade to NOT_APPLICABLE (this issue's own failure
    mode: a silently empty module list)."""
    write(
        tmp_path / "pom.xml",
        '<project xmlns="http://maven.apache.org/POM/4.0.0">\n'
        "  <modules>\n  </modules>\n"
        "</project>\n",
    )

    result = cdjava.discover_java_modules(tmp_path)

    assert result.get("signal") == "error"


# ---------------------------------------------------------------------------
# Slice 2 — Gradle module discovery
# ---------------------------------------------------------------------------


def test_groovy_dsl_include_declarations_yield_subprojects(tmp_path):
    write(tmp_path / "settings.gradle", "include ':core', ':services:api'\n")
    make_module(tmp_path, "core", test_dep=True, build_file="build.gradle")
    make_module(tmp_path, "services/api", test_dep=True, build_file="build.gradle")

    result = cdjava.discover_java_modules(tmp_path)

    # Full expected shape, matching the .NET/JS sibling suites' convention.
    assert result == [
        {"path": "core", "classification": TestClassification.TEST},
        {"path": "services/api", "classification": TestClassification.TEST},
    ]


def test_gradle_module_with_no_test_source_dir_is_not_test(tmp_path):
    write(tmp_path / "settings.gradle", "include ':helper'\n")
    make_module(
        tmp_path, "helper", test_dir=None, test_dep=False, build_file="build.gradle"
    )

    result = cdjava.discover_java_modules(tmp_path)

    assert result == [
        {"path": "helper", "classification": TestClassification.NOT_TEST}
    ]


def test_gradle_build_file_declaration_is_used_when_the_pom_does_not_declare(tmp_path):
    """A module carrying BOTH a pom.xml and a Gradle build file falls through
    to the Gradle file when the POM declares no test framework — this
    fallthrough is otherwise unexercised."""
    write(tmp_path / "settings.gradle", "include ':mixed'\n")
    mod = tmp_path / "mixed"
    write(mod / "pom.xml", leaf_pom(with_test_dep=False))
    write(
        mod / "build.gradle",
        "dependencies {\n"
        "  testImplementation 'org.junit.jupiter:junit-jupiter:5.10.0'\n"
        "}\n",
    )
    (mod / "src" / "test" / "java").mkdir(parents=True)

    result = cdjava.discover_java_modules(tmp_path)

    assert classification_of(result, "mixed") is TestClassification.TEST


def test_kotlin_dsl_include_forms_are_recognized(tmp_path):
    write(tmp_path / "settings.gradle.kts", 'include("core", "services:api")\n')
    make_module(tmp_path, "core", test_dep=True, build_file="build.gradle.kts")
    make_module(tmp_path, "services/api", test_dep=True, build_file="build.gradle.kts")

    result = cdjava.discover_java_modules(tmp_path)

    assert paths_of(result) == ["core", "services/api"]


def test_commented_out_include_is_ignored(tmp_path):
    write(
        tmp_path / "settings.gradle",
        "include ':core'\n// include ':legacy'\n",
    )
    make_module(tmp_path, "core", test_dep=True, build_file="build.gradle")
    make_module(tmp_path, "legacy", test_dep=True, build_file="build.gradle")

    result = cdjava.discover_java_modules(tmp_path)

    assert paths_of(result) == ["core"]


def test_settings_file_with_no_recognizable_include_is_a_discovery_error(tmp_path):
    write(tmp_path / "settings.gradle", "rootProject.name = 'thing'\n")

    result = cdjava.discover_java_modules(tmp_path)

    assert result.get("signal") == "error"
    assert result is not DISCOVERY_NOT_APPLICABLE
    assert "settings.gradle" in result["message"]


def test_gradle_classification_reads_the_modules_own_build_file(tmp_path):
    write(tmp_path / "settings.gradle.kts", 'include(":tested", ":inherited")\n')
    make_module(
        tmp_path, "tested", test_dir="src/test/kotlin", test_dep=True,
        build_file="build.gradle.kts",
    )
    make_module(
        tmp_path, "inherited", test_dir="src/test/java", test_dep=False,
        build_file="build.gradle.kts",
    )

    result = cdjava.discover_java_modules(tmp_path)

    assert classification_of(result, "tested") is TestClassification.TEST
    assert classification_of(result, "inherited") is TestClassification.AMBIGUOUS


def test_include_with_nested_colon_path_translates_to_directories(tmp_path):
    write(tmp_path / "settings.gradle", "include ':a:b:c'\n")
    make_module(tmp_path, "a/b/c", test_dep=True, build_file="build.gradle")

    result = cdjava.discover_java_modules(tmp_path)

    assert paths_of(result) == ["a/b/c"]


def test_multiline_groovy_include_list_yields_every_module(tmp_path):
    """A Groovy multi-line argument list is ONE declaration. A line-based
    parser sees ':lib' on a line with no include token and drops it — a
    partial discovery that slips past the no-recognized-include guard because
    specs is non-empty. This is the exact silent-subproject-exclusion failure
    mode multi-project discovery exists to prevent."""
    write(tmp_path / "settings.gradle", "include ':app',\n        ':lib'\n")
    make_module(tmp_path, "app", test_dep=True, build_file="build.gradle")
    make_module(tmp_path, "lib", test_dep=True, build_file="build.gradle")

    result = cdjava.discover_java_modules(tmp_path)

    assert paths_of(result) == ["app", "lib"]


def test_multiline_kotlin_include_call_yields_every_module(tmp_path):
    write(
        tmp_path / "settings.gradle.kts",
        'include(\n    ":app",\n    ":lib",\n)\n',
    )
    make_module(tmp_path, "app", test_dep=True, build_file="build.gradle.kts")
    make_module(tmp_path, "lib", test_dep=True, build_file="build.gradle.kts")

    result = cdjava.discover_java_modules(tmp_path)

    assert paths_of(result) == ["app", "lib"]


def test_block_commented_include_is_ignored(tmp_path):
    """Commenting a subproject out with /* ... */ is an ordinary Gradle idiom;
    treating it as live would invent a phantom module."""
    write(
        tmp_path / "settings.gradle",
        "include ':core'\n/* include ':legacy' */\n",
    )
    make_module(tmp_path, "core", test_dep=True, build_file="build.gradle")
    make_module(tmp_path, "legacy", test_dep=True, build_file="build.gradle")

    result = cdjava.discover_java_modules(tmp_path)

    assert paths_of(result) == ["core"]


def test_multiline_block_comment_spanning_includes_is_ignored(tmp_path):
    write(
        tmp_path / "settings.gradle",
        "include ':core'\n/*\ninclude ':a'\ninclude ':b'\n*/\n",
    )
    make_module(tmp_path, "core", test_dep=True, build_file="build.gradle")

    result = cdjava.discover_java_modules(tmp_path)

    assert paths_of(result) == ["core"]


def test_includeflat_is_not_treated_as_a_subproject(tmp_path):
    """includeFlat means ../sibling — a different base directory, so matching
    it as include would resolve the spec against the wrong root."""
    write(
        tmp_path / "settings.gradle",
        "includeFlat 'sibling'\ninclude ':core'\n",
    )
    make_module(tmp_path, "core", test_dep=True, build_file="build.gradle")

    result = cdjava.discover_java_modules(tmp_path)

    assert paths_of(result) == ["core"]


def test_second_statement_on_the_same_line_does_not_bleed_into_include(tmp_path):
    write(
        tmp_path / "settings.gradle",
        "include ':core'; includeBuild '../other-build'\n",
    )
    make_module(tmp_path, "core", test_dep=True, build_file="build.gradle")

    result = cdjava.discover_java_modules(tmp_path)

    assert paths_of(result) == ["core"]


def test_a_url_in_a_quoted_string_is_not_read_as_a_line_comment(tmp_path):
    """// inside a quoted string is not a comment marker."""
    write(
        tmp_path / "settings.gradle",
        "sourceControl { gitRepository('https://example.test/x.git') }\n"
        "include ':core'\n",
    )
    make_module(tmp_path, "core", test_dep=True, build_file="build.gradle")

    result = cdjava.discover_java_modules(tmp_path)

    assert paths_of(result) == ["core"]


def test_includebuild_is_not_treated_as_a_subproject(tmp_path):
    write(
        tmp_path / "settings.gradle",
        "includeBuild '../other-build'\ninclude ':core'\n",
    )
    make_module(tmp_path, "core", test_dep=True, build_file="build.gradle")

    result = cdjava.discover_java_modules(tmp_path)

    assert paths_of(result) == ["core"]


@pytest.mark.parametrize(
    "body,label",
    [
        (
            (
                "dependencies {\n"
                "  testImplementation platform('org.junit:junit-bom:5.10.0')\n"
                "}\n"
            ),
            "platform BOM version pin",
        ),
        (
            (
                "dependencies {\n"
                "  testImplementation enforcedPlatform("
                "'org.junit:junit-bom:5.10')\n"
                "}\n"
            ),
            "enforcedPlatform BOM version pin",
        ),
        (
            "plugins {\n  id 'org.junit.platform.gradle.plugin'\n}\n",
            "plugin id",
        ),
        (
            "archivesBaseName = 'junit-helpers'\n",
            "project property containing junit",
        ),
        (
            (
                "dependencies {\n"
                "  implementation 'org.junit.jupiter:junit-jupiter:5.10.0'\n"
                "}\n"
            ),
            "non-test configuration",
        ),
    ],
)
def test_gradle_non_test_junit_mention_classifies_ambiguous(tmp_path, body, label):
    """The Gradle branch is scoped exactly as tightly as the POM branch. A
    whole-file substring scan resolved each of these to a confident TEST,
    spending the AMBIGUOUS signal drift_check needs to force an operator
    decision."""
    write(tmp_path / "settings.gradle", "include ':mod'\n")
    mod = tmp_path / "mod"
    write(mod / "build.gradle", body)
    (mod / "src" / "test" / "java").mkdir(parents=True)

    result = cdjava.discover_java_modules(tmp_path)

    assert classification_of(result, "mod") is TestClassification.AMBIGUOUS, label


@pytest.mark.parametrize(
    "body,label",
    [
        ("test { useJUnitPlatform() }\n", "Test task configuration block"),
        ("testng { suites 'suites.xml' }\n", "TestNG plugin extension block"),
        ("testngVersion = '7.8.0'\n", "ext property assignment"),
        ("testFixtures { }\n", "testFixtures block"),
    ],
)
def test_gradle_test_task_and_extension_blocks_are_not_dependencies(
    tmp_path, body, label
):
    """A `test { … }` task block or `testng { … }` extension block configures a
    task, it does not declare a dependency — so a module whose JUnit dependency
    is only inherited must stay AMBIGUOUS. The `testng`/`testngVersion` cases
    specifically guard the regex against backtracking into a PREFIX of a longer
    identifier (`test` + the `n` of `ng` looking like an argument)."""
    write(tmp_path / "settings.gradle", "include ':mod'\n")
    mod = tmp_path / "mod"
    write(mod / "build.gradle", body)
    (mod / "src" / "test" / "java").mkdir(parents=True)

    result = cdjava.discover_java_modules(tmp_path)

    assert classification_of(result, "mod") is TestClassification.AMBIGUOUS, label


@pytest.mark.parametrize(
    "body,label",
    [
        (
            'dependencies { testImplementation "junit:junit:4.13" }\n',
            "one-line dependencies block",
        ),
        (
            (
                "dependencies {\n  testImplementation(\n"
                '    "org.junit.jupiter:junit-jupiter"\n  )\n}\n'
            ),
            "declaration split across lines",
        ),
        (
            "dependencies {\n  testImplementation(libs.junit.jupiter)\n}\n",
            "version-catalog accessor, no quoted coordinate",
        ),
    ],
)
def test_gradle_declaration_forms_are_recognized(tmp_path, body, label):
    """Forms an earlier, start-of-line-anchored matcher missed — each declares
    the dependency locally, so each must classify TEST, not AMBIGUOUS."""
    write(tmp_path / "settings.gradle", "include ':mod'\n")
    mod = tmp_path / "mod"
    write(mod / "build.gradle", body)
    (mod / "src" / "test" / "java").mkdir(parents=True)

    result = cdjava.discover_java_modules(tmp_path)

    assert classification_of(result, "mod") is TestClassification.TEST, label


@pytest.mark.parametrize(
    "config",
    [
        "testImplementation",
        "testCompileOnly",
        "testRuntimeOnly",
        "androidTestImplementation",
        "integrationTestImplementation",
    ],
)
def test_gradle_test_configurations_are_recognized(tmp_path, config):
    write(tmp_path / "settings.gradle", "include ':mod'\n")
    mod = tmp_path / "mod"
    write(
        mod / "build.gradle",
        f"dependencies {{\n  {config} 'org.junit.jupiter:junit-jupiter:5.10.0'\n}}\n",
    )
    (mod / "src" / "test" / "java").mkdir(parents=True)

    result = cdjava.discover_java_modules(tmp_path)

    assert classification_of(result, "mod") is TestClassification.TEST


def test_commented_out_gradle_test_dependency_does_not_count(tmp_path):
    """A commented-out testImplementation line is not a declared dependency;
    counting it would resolve a genuinely ambiguous module to TEST."""
    write(tmp_path / "settings.gradle", "include ':mod'\n")
    mod = tmp_path / "mod"
    write(
        mod / "build.gradle",
        "dependencies {\n"
        "  // testImplementation 'org.junit.jupiter:junit-jupiter:5.10.0'\n"
        "}\n",
    )
    (mod / "src" / "test" / "java").mkdir(parents=True)

    result = cdjava.discover_java_modules(tmp_path)

    assert classification_of(result, "mod") is TestClassification.AMBIGUOUS


# ---------------------------------------------------------------------------
# Hardening — XML entity expansion, control characters, symlinked test dirs
# ---------------------------------------------------------------------------


def test_root_pom_with_doctype_is_refused(tmp_path):
    """xml.etree.ElementTree is not secure against maliciously constructed
    data, and a pom.xml never legitimately carries a DOCTYPE. Mirrors the
    .NET module's screen, now shared via coverage_config."""
    write(
        tmp_path / "pom.xml",
        '<?xml version="1.0"?>\n'
        '<!DOCTYPE project [<!ENTITY a "boom">]>\n'
        "<project><modules><module>x</module></modules></project>\n",
    )

    result = cdjava.discover_java_modules(tmp_path)

    assert result.get("signal") == "error"
    assert "DOCTYPE" in result["message"]


def test_module_pom_with_entity_declaration_is_refused(tmp_path):
    """The screen covers nested module POMs too, not only the root."""
    write(tmp_path / "pom.xml", aggregator_pom(["mod"]))
    mod = tmp_path / "mod"
    write(
        mod / "pom.xml",
        '<?xml version="1.0"?>\n'
        '<!DOCTYPE project [<!ENTITY a "boom">]>\n'
        "<project/>\n",
    )
    (mod / "src" / "test" / "java").mkdir(parents=True)

    result = cdjava.discover_java_modules(tmp_path)

    assert result.get("signal") == "error"


_SPEC_REJECTED_MESSAGE = "characters this module refuses to build a path from"


@pytest.mark.parametrize(
    "payload,label",
    [
        (b"include ':a\x00b'\n", "NUL"),
        (b"include ':a\tb'\n", "tab"),
        (b"include ':a\rb'\n", "carriage return"),
    ],
)
def test_gradle_spec_with_a_control_character_is_rejected_by_the_allowlist(
    tmp_path, payload, label
):
    """A raw NUL survives errors="replace" decoding (it is not a decode error),
    and `Path.resolve()` raises ValueError — not OSError — on an embedded null,
    which would escape this module's structured-error contract as an unhandled
    traceback. The allowlist rejects it before any path is built, so the
    message assertion below pins THAT path specifically rather than merely
    'some error happened'."""
    (tmp_path / "settings.gradle").write_bytes(payload)

    result = cdjava.discover_java_modules(tmp_path)

    assert result.get("signal") == "error", label
    assert _SPEC_REJECTED_MESSAGE in result["message"], label


def test_maven_module_with_a_null_byte_is_rejected_by_the_xml_parser(tmp_path):
    """The Maven `<module>` path has no character allowlist of its own — it
    does not need one: a raw NUL is not well-formed XML, so expat rejects the
    POM before any path is built from the spec. This test pins that as the
    actual mechanism, so the (unreachable-from-Maven) ValueError guard in
    `_contained_dir` is understood as defense in depth rather than as this
    case's live handler."""
    (tmp_path / "pom.xml").write_bytes(
        b"<project><modules><module>a\x00b</module></modules></project>"
    )

    result = cdjava.discover_java_modules(tmp_path)

    assert result.get("signal") == "error"
    assert "not well-formed" in result["message"]


@pytest.mark.skipif(
    not hasattr(Path, "symlink_to"), reason="platform has no symlink support"
)
def test_symlinked_test_source_dir_pointing_outside_the_repo_is_refused(tmp_path):
    """is_dir() follows symlinks, so an unchecked probe would stat outside the
    repo root and let an out-of-root directory decide the classification."""
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    outside.mkdir()
    write(repo / "pom.xml", aggregator_pom(["mod"]))
    mod = repo / "mod"
    write(mod / "pom.xml", leaf_pom(with_test_dep=True))
    (mod / "src" / "test").mkdir(parents=True)
    try:
        (mod / "src" / "test" / "java").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted on this platform")

    result = cdjava.discover_java_modules(repo)

    assert result.get("signal") == "error"


# ---------------------------------------------------------------------------
# Slice 3 — precedence and containment
# ---------------------------------------------------------------------------


def test_maven_wins_when_both_signals_are_present(tmp_path):
    write(tmp_path / "pom.xml", aggregator_pom(["mvn-mod"]))
    make_module(tmp_path, "mvn-mod", test_dep=True)
    write(tmp_path / "settings.gradle", "include ':gradle-mod'\n")
    make_module(tmp_path, "gradle-mod", test_dep=True, build_file="build.gradle")

    result = cdjava.discover_java_modules(tmp_path)

    assert paths_of(result) == ["mvn-mod"]


def test_maven_module_escaping_the_repo_root_is_refused(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (tmp_path / "outside").mkdir()
    write(repo / "pom.xml", aggregator_pom(["../outside"]))

    result = cdjava.discover_java_modules(repo)

    assert result.get("signal") == "error"
    assert "outside" in result["message"]


def test_gradle_include_escaping_the_repo_root_is_refused(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (tmp_path / "outside").mkdir()
    write(repo / "settings.gradle", "include ':..:outside'\n")

    result = cdjava.discover_java_modules(repo)

    assert result.get("signal") == "error"


@pytest.mark.skipif(
    not hasattr(Path, "symlink_to"), reason="platform has no symlink support"
)
def test_symlinked_build_file_pointing_outside_the_repo_is_refused(tmp_path):
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    outside.mkdir()
    write(outside / "pom.xml", leaf_pom(with_test_dep=True))
    write(repo / "pom.xml", aggregator_pom(["mod"]))
    (repo / "mod").mkdir(parents=True)
    try:
        (repo / "mod" / "pom.xml").symlink_to(outside / "pom.xml")
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted on this platform")

    result = cdjava.discover_java_modules(repo)

    assert result.get("signal") == "error"


def test_result_entries_use_repo_relative_posix_paths(tmp_path):
    write(tmp_path / "pom.xml", aggregator_pom(["a/b"]))
    make_module(tmp_path, "a/b", test_dep=True)

    result = cdjava.discover_java_modules(tmp_path)

    assert paths_of(result) == ["a/b"]
    assert "\\" not in paths_of(result)[0]
