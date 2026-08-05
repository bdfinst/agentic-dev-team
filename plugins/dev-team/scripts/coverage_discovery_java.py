#!/usr/bin/env python3
"""coverage_discovery_java.py — discover and classify every module in a Java
multi-module build for multi-project coverage discovery (issue #1765).

Generalizes the shape landed for .NET solutions (`coverage_discovery_dotnet.py`)
and JS/TS workspaces (`coverage_discovery_js.py`) in #1759/#1822 to the two
JVM multi-module build graphs:

- **Maven** — the root `pom.xml`'s `<modules><module>` list, resolved
  **recursively** through aggregator modules (a module that itself declares
  `<modules>` contributes its own children), with cycle protection so a
  self- or mutually-referential graph terminates.
- **Gradle** — `settings.gradle` / `settings.gradle.kts` `include(...)`
  declarations, translating Gradle's colon-separated project paths (`:a:b`)
  to directory paths (`a/b`). Both the parenthesized (Kotlin DSL) and bare
  (Groovy) call forms are recognized, including a multi-line argument list —
  `include ':app',\n    ':lib'` is a single declaration and yields BOTH
  modules. `includeBuild` (composite builds) and `includeFlat` (sibling-
  directory projects) are separate build graphs and are deliberately out of
  scope; neither is mistaken for `include`.

**Out of scope, named explicitly.** A Gradle subproject whose directory is
remapped in `settings.gradle` (`project(":api").projectDir = file("custom")`)
is not resolved to its remapped location — this module resolves the default
`:a:b` → `a/b` layout only. Because a declared module whose directory is
absent is a hard `discovery_error` (never a silent `NOT_TEST`), such a
remapping surfaces as a loud, actionable error naming the missing path rather
than silently dropping the subproject from coverage accounting.

**Stack precedence (no cross-merge).** When both a root `pom.xml` declaring
`<modules>` and a `settings.gradle*` declaring `include(...)` are present,
Maven wins and Gradle is not consulted — the same "first present config wins"
rule `coverage_discovery_js.py` applies across `package.json#workspaces` →
`pnpm-workspace.yaml` → `lerna.json`.

**No JVM, no build-tool CLI.** Unlike .NET discovery (which shells out to
`dotnet sln list`), this module is a pure static parse, matching the JS/TS
module's filesystem-only approach. Invoking `mvn`/`gradlew` would require a
JVM and network access for plugin resolution and cost tens of seconds on
every measurement — unacceptable for a per-run re-derivation.

**Identity contract.** A module's "path" is its directory, expressed relative
to `repo_root` in POSIX form (matching both existing discovery modules) — the
exact, unmodified string every caller compares against `included`/`excluded`
entries, per `coverage_config`'s identity contract. The POSIX-relative
rendering is applied once at resolution time, never per comparison.

**Classification.** `TEST` when the module has BOTH a test-source directory
(`src/test/java` or `src/test/kotlin`) AND a JUnit/TestNG dependency declared
in its own build file. `AMBIGUOUS` — never silently `NOT_TEST` — when a
test-source directory is present but the test-framework dependency is not
declared in the module's own build file: it may be inherited from a parent
POM's `<dependencyManagement>`/`<dependencies>` or a Gradle `subprojects {}`
block or convention plugin. This module deliberately never evaluates that
inheritance (mirroring the .NET module's refusal to evaluate MSBuild
`Condition` attributes); it reports the ambiguity and lets
`coverage_config.drift_check` force an operator decision. `NOT_TEST` only
when there is no test-source directory at all.

**Security hardening.** Every resolved module directory, every build file
read, and the test-source-directory probe are verified to stay within the
resolved repository root before they are read or classified — a
`<module>../../etc</module>`, an `include(':..:..')`, a symlinked build file,
or a symlinked `src/test/java` can never cause this module to read or stat
outside the repository. An out-of-root entry is reported as an error, never
silently dropped.

Every XML read routes through `coverage_config.read_and_screen_xml`, the
shared `<!DOCTYPE`/`<!ENTITY` entity-expansion screen the .NET stack
introduced (`xml.etree.ElementTree` is explicitly not secure against
maliciously constructed data, and a `pom.xml` never legitimately carries
either declaration). It reads the bytes once and the caller parses THOSE
bytes via `ET.fromstring`, so no path is ever checked and then re-opened.
Gradle build files are read the same way — one read per contained path, never
a resolve-then-reopen pair.

A parsed Gradle project spec is validated against a conservative character
allowlist before any path is built from it: a raw NUL (reachable because
settings files are decoded with `errors="replace"`, which does not replace
U+0000) would otherwise make `Path.resolve()` raise `ValueError` — not
`OSError` — and escape this module's "every failure is a structured
`discovery_error`" contract as an unhandled traceback.

Stdlib-only (ADR 0014/0015/0031).
"""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import coverage_config
from coverage_config import TestClassification

# Test-source directories that mark a module as carrying tests at all.
_TEST_SOURCE_DIRS = ("src/test/java", "src/test/kotlin")

# Test-framework tokens searched for in a module's own build file. Matched
# case-insensitively against the raw build-file text for Gradle, and against
# declared dependency coordinates for Maven.
_TEST_FRAMEWORK_TOKENS = ("junit", "testng")

_MAVEN_POM_FILE = "pom.xml"
_GRADLE_SETTINGS_FILES = ("settings.gradle", "settings.gradle.kts")
_GRADLE_BUILD_FILES = ("build.gradle", "build.gradle.kts")

# A Gradle line counts as a TEST-framework dependency declaration only when a
# test *configuration* is being invoked with an argument. `test`-prefixed
# covers testImplementation / testCompileOnly / testRuntimeOnly / testApi /
# testAnnotationProcessor; `androidTest`-prefixed covers the Android variants;
# `integrationTest…` and other custom test source sets match the same infix.
#
# The token may follow start-of-line, `{`, or `;` so the one-line
# `dependencies { testImplementation "…" }` form is recognized, and the
# character after it must begin an ARGUMENT — `(`, a quote, or an
# identifier/`$` — never `{`. That last exclusion is load-bearing: `test {
# useJUnitPlatform() }` configures the Test *task*, and `testng { suites … }`
# the TestNG plugin extension; neither declares a dependency, so treating
# either as one would resolve a genuinely inherited-only module to a confident
# `TEST` and spend the `AMBIGUOUS` signal `drift_check` needs.
# The `(?![A-Za-z])` after the identifier is load-bearing: without it the regex
# backtracks into a PREFIX of a longer name, so `testng { suites '…' }` matches
# as `test` followed by the argument-looking `n` of `ng`. The lookahead forces
# the identifier to be complete before the argument check runs.
_GRADLE_TEST_CONFIG_RE = re.compile(
    r"(?:^|[{;])\s*[A-Za-z]*[Tt]est[A-Za-z]*(?![A-Za-z])\s*(?:\(|['\"]|[A-Za-z_$])",
    re.ASCII,
)
# A declaration split across lines (`testImplementation(\n  "…"\n)`) is joined
# before scanning, so the configuration token and its argument are seen
# together. A line ending in `(` or `,` continues into the next.
_GRADLE_CONTINUATION_END = ("(", ",")
# `platform(...)`/`enforcedPlatform(...)` pins a version without declaring a
# dependency — Gradle's analogue of Maven's <dependencyManagement>.
_GRADLE_BOM_RE = re.compile(r"\b(?:enforced)?platform\s*\(", re.ASCII)

# `include`, Groovy or Kotlin DSL — but never `includeBuild`, `includeFlat`, or
# any other `include`-prefixed identifier. The lookahead rejects an identifier
# continuation rather than one specific suffix, so a new Gradle `includeXxx`
# API can never silently start matching as `include`.
_GRADLE_INCLUDE_RE = re.compile(r"\binclude(?![A-Za-z0-9_])")
_GRADLE_QUOTED_RE = re.compile(r"""['"]([^'"]*)['"]""")
# Characters that may separate the quoted project paths of one `include` call.
# Anything else (`;`, a new statement, an identifier) ends the argument list.
_GRADLE_ARG_SEPARATORS = frozenset(" \t\r\n,()")
# Conservative allowlist for a Gradle project spec, applied BEFORE any path is
# built from it. A raw NUL is the motivating case: settings files are decoded
# with errors="replace", which does not replace U+0000, and `Path.resolve()`
# raises ValueError (not OSError) on an embedded null — escaping this module's
# structured-error contract as an unhandled traceback.
_GRADLE_SPEC_ALLOWED_RE = re.compile(r"^[A-Za-z0-9._:\-/ ]+$")

# Maven POMs are namespaced; ElementTree keeps the namespace in the tag, so
# match on the local name instead of hard-coding one namespace URI.
_MAVEN_NS_RE = re.compile(r"^\{[^}]*\}")


def discover_java_modules(repo_root):
    """Discover and classify every module in `repo_root`'s Java multi-module
    build.

    Returns a list of `{"path": <repo-relative POSIX module directory>,
    "classification": TestClassification}` entries on success (sorted by
    path), `coverage_config.DISCOVERY_NOT_APPLICABLE` when no multi-module
    signal is present, or `coverage_config.discovery_error(...)` for a
    parsing or path-containment failure.
    """
    root = Path(repo_root).resolve()

    rel_paths = _maven_module_paths(root)
    if rel_paths is None:
        rel_paths = _gradle_module_paths(root)
    if rel_paths is None:
        return coverage_config.DISCOVERY_NOT_APPLICABLE
    if isinstance(rel_paths, dict):
        return rel_paths  # a discovery_error propagated up

    modules = []
    for rel_path in rel_paths:
        classification = _classify_module(root / rel_path, root)
        if isinstance(classification, dict):
            return classification  # a discovery_error propagated up
        modules.append({"path": rel_path, "classification": classification})
    return modules


# ---------------------------------------------------------------------------
# Maven — recursive <modules> resolution
# ---------------------------------------------------------------------------


def _maven_module_paths(root: Path):
    """Resolve the root `pom.xml`'s `<modules>` list, recursively through
    aggregator modules.

    Returns a sorted list of repo-relative POSIX module directories,
    `None` when this stack does not apply (no root `pom.xml`, or one that
    declares no `<modules>` element at all — a single-module project), or
    `coverage_config.discovery_error(...)` for a parse, containment, or
    empty-declaration failure."""
    root_pom = root / _MAVEN_POM_FILE
    if not root_pom.is_file():
        return None

    declared = _parse_pom_modules(root_pom, root)
    if isinstance(declared, dict):
        return declared  # a discovery_error propagated up
    if declared is None:
        return None  # no <modules> element — single-module project

    if not declared:
        return coverage_config.discovery_error(
            f"'{root_pom}' declares a <modules> element with no <module> "
            "entries. A declared-but-empty module list cannot be "
            "distinguished from a discovery bug, and silently treating it as "
            "an empty project list is the exact silent-exclusion failure "
            "mode multi-project discovery exists to prevent. Remove the "
            "empty <modules> element, or list the real modules."
        )

    resolved: set[str] = set()
    # Each queue item is a (module-spec, declaring-pom-directory) pair, so a
    # nested aggregator's <module> entries resolve relative to that
    # aggregator's own directory, the way Maven itself resolves them.
    queue = [(spec, root) for spec in declared]
    while queue:
        spec, base = queue.pop()
        module_dir = _contained_dir(base / spec, root)
        if isinstance(module_dir, dict):
            return module_dir  # a discovery_error propagated up
        if not module_dir.is_dir():
            return coverage_config.discovery_error(
                f"'{base / 'pom.xml'}' declares <module>{spec}</module> but "
                f"'{module_dir}' is not a directory on disk. A declared "
                "module that does not exist is a broken build graph, not a "
                "non-test module — classifying it NOT_TEST would drop it from "
                "coverage accounting silently."
            )

        rel = module_dir.relative_to(root).as_posix()
        if rel in resolved:
            continue  # cycle, or the same module declared twice
        resolved.add(rel)

        child_pom = module_dir / _MAVEN_POM_FILE
        if not child_pom.is_file():
            # Same domain fact as the missing-directory branch above, so it
            # gets the same treatment: `mvn` itself fails on a <module> with
            # no POM, making this a broken build graph rather than a non-test
            # module. Classifying it would land it on AMBIGUOUS/NOT_TEST and
            # (for NOT_TEST) drop it from accounting silently.
            #
            # Deliberately Maven-only: a Gradle subproject directory with no
            # build file is legitimate (a container project), so the Gradle
            # branch keeps `_classify_module`'s lenient path.
            return coverage_config.discovery_error(
                f"'{base / _MAVEN_POM_FILE}' declares <module>{spec}</module> "
                f"but '{child_pom}' does not exist. A declared Maven module "
                "with no POM is a broken build graph — `mvn` itself fails on "
                "it — not a non-test module."
            )
        child_modules = _parse_pom_modules(child_pom, root)
        if isinstance(child_modules, dict):
            return child_modules  # a discovery_error propagated up
        if child_modules == []:
            # Same rule as the root POM below: a declared-but-empty <modules>
            # is indistinguishable from a discovery bug, so it must never be
            # accepted silently — one level down included.
            return coverage_config.discovery_error(
                f"'{child_pom}' declares a <modules> element with no <module> "
                "entries. A declared-but-empty module list cannot be "
                "distinguished from a discovery bug; remove the empty "
                "<modules> element, or list the real modules."
            )
        for child_spec in child_modules or ():
            queue.append((child_spec, module_dir))

    return sorted(resolved)


def _parse_pom_modules(pom_path: Path, root: Path):
    """Return the list of `<module>` text values declared in `pom_path`'s
    `<modules>` element, `None` when the POM declares no `<modules>` element
    at all, or `coverage_config.discovery_error(...)` when the file cannot be
    read, is not well-formed XML, or resolves outside `root`."""
    root_el = _parse_contained_xml(pom_path, root)
    if isinstance(root_el, dict):
        return root_el  # a discovery_error propagated up

    for child in root_el:
        if _local_name(child.tag) != "modules":
            continue
        specs = []
        for module_el in child:
            if _local_name(module_el.tag) != "module":
                continue
            text = (module_el.text or "").strip()
            if text:
                specs.append(text)
        return specs
    return None


def _local_name(tag) -> str:
    """The namespace-stripped local name of an ElementTree tag."""
    return _MAVEN_NS_RE.sub("", tag if isinstance(tag, str) else "")


# ---------------------------------------------------------------------------
# Gradle — settings.gradle(.kts) include(...) resolution
# ---------------------------------------------------------------------------


def _gradle_module_paths(root: Path):
    """Resolve `include(...)` declarations from `settings.gradle` or
    `settings.gradle.kts`.

    Returns a sorted list of repo-relative POSIX module directories,
    `None` when neither settings file is present (this stack does not
    apply), or `coverage_config.discovery_error(...)` when a settings file is
    present but declares no `include(...)` this parser recognizes, or a
    resolved project escapes `root`."""
    settings_path = None
    for name in _GRADLE_SETTINGS_FILES:
        candidate = root / name
        if candidate.is_file():
            settings_path = candidate
            break
    if settings_path is None:
        return None

    text = _read_contained_text(settings_path, root)
    if isinstance(text, dict):
        return text  # a discovery_error propagated up

    specs = _parse_gradle_includes(text)
    if not specs:
        return coverage_config.discovery_error(
            f"'{settings_path}' is present but declares no include(...) this "
            "parser recognizes (supported: Groovy and Kotlin DSL "
            "include ':a', include(\":a\", \":b\") forms; includeBuild "
            "composite builds are out of scope). Treating it as "
            "single-project would silently exclude every subproject from "
            "coverage — the exact failure mode multi-project discovery "
            "exists to prevent."
        )

    resolved: set[str] = set()
    for spec in specs:
        cleaned = spec.strip().strip(":")
        rel_spec = cleaned.replace(":", "/")
        if not rel_spec:
            continue
        if not _GRADLE_SPEC_ALLOWED_RE.match(rel_spec):
            return coverage_config.discovery_error(
                f"'{settings_path}' includes a project spec containing "
                "characters this module refuses to build a path from "
                f"({cleaned!r}); allowed characters are letters, digits, and "
                "'. _ - / :'. Refusing to resolve it."
            )
        module_dir = _contained_dir(root / rel_spec, root)
        if isinstance(module_dir, dict):
            return module_dir  # a discovery_error propagated up
        if not module_dir.is_dir():
            return coverage_config.discovery_error(
                f"'{settings_path}' includes ':{spec.strip().strip(':')}' but "
                f"'{module_dir}' is not a directory on disk. A declared "
                "subproject that does not exist is a broken build graph, not a "
                "non-test module — classifying it NOT_TEST would drop it from "
                "coverage accounting silently. (A subproject whose directory is "
                "remapped via project(...).projectDir is not resolved by this "
                "module; see the module docstring.)"
            )
        resolved.add(module_dir.relative_to(root).as_posix())
    if not resolved:
        return coverage_config.discovery_error(
            f"'{settings_path}' declares include(...) entries but none "
            "resolved to a subproject path."
        )
    return sorted(resolved)


def _parse_gradle_includes(text: str) -> list:
    """Every quoted project path declared by an `include` call in `text`.

    Scans the **whole comment-stripped document**, not line by line: a Groovy
    multi-line argument list (`include ':app',\\n    ':lib'`) is one
    declaration and must yield both modules. Parsing per line would see
    `':lib'` on a line with no `include` token and silently drop it — a
    partial discovery is the same silent-subproject-exclusion failure mode
    this module exists to prevent, and unlike a zero-spec parse it would slip
    past the "no recognized include" guard because `specs` is non-empty.

    `includeBuild`/`includeFlat` are excluded by the regex's identifier
    lookahead, and each call's argument list is bounded by
    `_collect_quoted_args`, so a second statement on the same line
    (`include ':core'; includeBuild '../other'`) cannot bleed into the
    first call's specs."""
    stripped = _strip_gradle_comments(text)
    specs = []
    for match in _GRADLE_INCLUDE_RE.finditer(stripped):
        specs.extend(_collect_quoted_args(stripped, match.end()))
    return specs


def _collect_quoted_args(text: str, start: int) -> list:
    """The quoted string arguments of one `include` call beginning at `start`.

    Consumes quoted strings separated only by `_GRADLE_ARG_SEPARATORS`
    (whitespace, commas, parentheses), so a multi-line list keeps collecting
    across newlines. Any other character — `;`, a new `include`, an
    identifier, an assignment — ends this call's argument list."""
    args = []
    i = start
    length = len(text)
    while i < length:
        ch = text[i]
        if ch in _GRADLE_ARG_SEPARATORS:
            i += 1
            continue
        if ch in "'\"":
            match = _GRADLE_QUOTED_RE.match(text, i)
            if match is None:
                break  # an unterminated quote ends the argument list
            args.append(match.group(1))
            i = match.end()
            continue
        break
    return args


def _strip_gradle_comments(text: str) -> str:
    """`text` with `//` line comments and `/* ... */` block comments replaced
    by whitespace, ignoring comment markers that appear inside a quoted
    string. Block comments are handled because commenting out a subproject
    with `/* include ':legacy' */` is an ordinary Gradle idiom, and treating
    it as a live declaration would invent a phantom module.

    Comment spans are replaced with spaces rather than removed so that
    positions stay aligned and a block comment can never join two separate
    statements into one."""
    out = []
    i = 0
    length = len(text)
    quote = None
    while i < length:
        ch = text[i]
        if quote:
            out.append(ch)
            if ch == "\\" and i + 1 < length:
                out.append(text[i + 1])  # an escape can't close the string
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "'\"":
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "/" and text[i + 1 : i + 2] == "/":
            while i < length and text[i] != "\n":
                out.append(" ")
                i += 1
            continue
        if ch == "/" and text[i + 1 : i + 2] == "*":
            end = text.find("*/", i + 2)
            stop = length if end == -1 else end + 2
            for j in range(i, stop):
                out.append("\n" if text[j] == "\n" else " ")
            i = stop
            continue
        out.append(ch)
        i += 1
    return "".join(out)


# ---------------------------------------------------------------------------
# Containment helpers
# ---------------------------------------------------------------------------


def _is_within(resolved: Path, root: Path) -> bool:
    return resolved == root or root in resolved.parents


def _contained_dir(candidate: Path, root: Path):
    """`candidate` resolved, once, after confirming it stays inside `root`;
    otherwise `coverage_config.discovery_error(...)`.

    Containment only — this helper deliberately does not require the path to
    exist, because a non-existent path still has to be containment-checked
    before it is named in any message. Existence is the CALLER's check: both
    `_maven_module_paths` and `_gradle_module_paths` reject a declared module
    whose directory is absent as its own `discovery_error`, matching
    `coverage_discovery_dotnet.py`'s missing-project error rather than letting
    it classify `NOT_TEST` and vanish from coverage accounting."""
    try:
        resolved = candidate.resolve()
    except (OSError, ValueError) as exc:
        # ValueError, not just OSError — see `_contained_file` for why.
        return coverage_config.discovery_error(
            f"Could not resolve module path '{candidate}': {exc}"
        )
    if not _is_within(resolved, root):
        return coverage_config.discovery_error(
            f"Module path '{candidate}' resolves to '{resolved}', which is "
            f"outside the repository root ('{root}'); refusing to include it."
        )
    return resolved


def _contained_file(candidate: Path, root: Path):
    """`candidate` resolved (following symlinks) after confirming the resolved
    target stays inside `root`; otherwise `coverage_config.discovery_error(...)`.
    Separate from `_contained_dir` because a symlinked build file inside an
    already-contained directory can still point outside the repository."""
    try:
        resolved = candidate.resolve()
    except (OSError, ValueError) as exc:
        # ValueError, not just OSError: `resolve()` raises it for a path with
        # an embedded NUL, which is reachable from a settings file decoded
        # with errors="replace" (U+0000 is not replaced).
        return coverage_config.discovery_error(
            f"Could not resolve build file '{candidate}': {exc}"
        )
    if not _is_within(resolved, root):
        return coverage_config.discovery_error(
            f"Build file '{candidate}' resolves to '{resolved}', which is "
            f"outside the repository root ('{root}'); refusing to read it."
        )
    return resolved


def _parse_contained_xml(path: Path, root: Path):
    """The parsed root element of the XML at `path`, or
    `coverage_config.discovery_error(...)`.

    Containment-checks `path`, then reads it ONCE through
    `coverage_config.read_and_screen_xml` — the shared `<!DOCTYPE`/`<!ENTITY`
    entity-expansion screen — and parses THOSE bytes. Never re-opens the
    checked path, so there is no resolve-then-reopen window in which a
    symlink swap could redirect the read."""
    contained = _contained_file(path, root)
    if isinstance(contained, dict):
        return contained  # a discovery_error propagated up
    data, error = coverage_config.read_and_screen_xml(contained)
    if error is not None:
        return error
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        return coverage_config.discovery_error(
            f"Could not parse '{path}' as XML: {exc}"
        )


def _read_contained_text(path: Path, root: Path):
    """The text of the file at `path`, or
    `coverage_config.discovery_error(...)`.

    Containment-checks `path` and reads it exactly once. Decoded with
    `errors="replace"` because a Gradle settings/build file's encoding is not
    declared anywhere — an undecodable byte must not abort discovery. Callers
    that build a filesystem path from the decoded text must validate it first
    (see `_GRADLE_SPEC_ALLOWED_RE`): `errors="replace"` does not replace
    U+0000."""
    contained = _contained_file(path, root)
    if isinstance(contained, dict):
        return contained  # a discovery_error propagated up
    try:
        return contained.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return coverage_config.discovery_error(f"Could not read '{path}': {exc}")


# ---------------------------------------------------------------------------
# Module classification
# ---------------------------------------------------------------------------


def _classify_module(module_dir: Path, root: Path):
    """`TEST` when `module_dir` has both a test-source directory and a
    JUnit/TestNG dependency in its own build file; `AMBIGUOUS` when it has a
    test-source directory but no such dependency declared locally (it may be
    inherited — this module never evaluates inheritance); `NOT_TEST` when it
    has no test-source directory at all.

    Returns `coverage_config.discovery_error(...)` instead — never a
    classification — when a build file exists but cannot be read or parsed, or
    when it (or a test-source directory) resolves outside `root`."""
    has_test_sources = False
    for rel in _TEST_SOURCE_DIRS:
        # Route the probe through the containment check rather than a bare
        # `is_dir()`: `is_dir()` follows symlinks, so `mod/src/test/java -> /etc`
        # would otherwise stat outside the repository root and let an
        # out-of-root directory's existence decide this module's
        # classification.
        candidate = _contained_dir(module_dir / rel, root)
        if isinstance(candidate, dict):
            return candidate  # a discovery_error propagated up
        if candidate.is_dir():
            has_test_sources = True
            break
    if not has_test_sources:
        return TestClassification.NOT_TEST

    declares_framework = _declares_test_framework(module_dir, root)
    if isinstance(declares_framework, dict):
        return declares_framework  # a discovery_error propagated up
    return (
        TestClassification.TEST
        if declares_framework
        else TestClassification.AMBIGUOUS
    )


def _declares_test_framework(module_dir: Path, root: Path):
    """True when `module_dir`'s own build file declares a JUnit or TestNG
    dependency; False when no build file declares one (including when the
    module has no build file at all — an inherited-only declaration is
    indistinguishable from none here, which is exactly why the caller maps
    False to `AMBIGUOUS` rather than `NOT_TEST`). Returns
    `coverage_config.discovery_error(...)` when a build file exists but cannot
    be read or parsed.

    Both branches are scoped the SAME way, deliberately: to a real dependency
    declaration in the module's own build file. An earlier version scoped the
    POM branch carefully and then let the Gradle branch substring-scan the
    whole file — which resolved to a confident `TEST` for exactly the shapes
    the POM branch documents as wrong (a `platform('org.junit:junit-bom')`
    version pin, a `plugins { id 'org.junit...' }` id, a project name
    containing `junit`), silently spending the `AMBIGUOUS` signal
    `drift_check` needs."""
    pom_path = module_dir / _MAVEN_POM_FILE
    if pom_path.is_file():
        found = _pom_declares_test_framework(pom_path, root)
        if isinstance(found, dict) or found:
            return found

    for name in _GRADLE_BUILD_FILES:
        build_path = module_dir / name
        if not build_path.is_file():
            continue
        text = _read_contained_text(build_path, root)
        if isinstance(text, dict):
            return text  # a discovery_error propagated up
        if _gradle_text_declares_test_framework(text):
            return True

    return False


def _gradle_text_declares_test_framework(text: str) -> bool:
    """True when comment-stripped Gradle build-script `text` declares a
    JUnit/TestNG dependency on a TEST configuration.

    Scoped to match the POM branch's precision rather than substring-scanning
    the file:

    - only lines whose dependency configuration is a test one
      (`testImplementation`, `testCompileOnly`, `testRuntimeOnly`,
      `testApi`, `androidTestImplementation`, …) count. A `plugins { id
      'org.junit.platform...' }` line, an `archivesBaseName` containing
      `junit`, or a non-test `implementation` are not test dependencies.
    - a `platform(...)`/`enforcedPlatform(...)` BOM line is excluded: like
      Maven's `<dependencyManagement>`, it pins a version without declaring
      a dependency, so it must leave the module `AMBIGUOUS` rather than
      resolving it to `TEST`."""
    for line in _join_gradle_continuations(_strip_gradle_comments(text)):
        lowered = line.lower()
        if not any(token in lowered for token in _TEST_FRAMEWORK_TOKENS):
            continue
        if _GRADLE_BOM_RE.search(lowered):
            continue  # a version pin, not a dependency declaration
        if _GRADLE_TEST_CONFIG_RE.search(line):
            return True
    return False


def _join_gradle_continuations(text: str) -> list:
    """`text`'s lines, with a line that ends in `(` or `,` joined to the one
    after it.

    Without this, a Kotlin-DSL declaration split across lines —
    `testImplementation(\\n  "org.junit.jupiter:junit-jupiter"\\n)` — hides the
    configuration token from its own argument: the first line carries no
    framework token and the second does not begin with the configuration, so
    the module would classify `AMBIGUOUS` despite declaring the dependency
    locally."""
    joined = []
    pending = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        pending = f"{pending} {line}".strip() if pending else line
        if pending.endswith(_GRADLE_CONTINUATION_END):
            continue
        joined.append(pending)
        pending = ""
    if pending:
        joined.append(pending)
    return joined


def _pom_declares_test_framework(pom_path: Path, root: Path):
    """True when `pom_path`'s own top-level `<dependencies>` declare a JUnit or
    TestNG artifact; False otherwise; `coverage_config.discovery_error(...)`
    when the POM cannot be read or is not well-formed XML.

    Scoped deliberately to `<project>`'s DIRECT `<dependencies>` child, and
    within it to each `<dependency>`'s own `<groupId>`/`<artifactId>`. A
    whole-document scan would classify as `TEST`: a module merely *named*
    `junit-extensions` (its own `<artifactId>`), a `<dependencyManagement>`
    or `junit-bom` version declaration, a `junit-platform-maven-plugin` under
    `<build><plugins>`, and a `<profiles>`-scoped dependency. The first three
    are not dependencies of this module at all; the last is *conditional*, and
    a conditional declaration is exactly what this module reports as
    `AMBIGUOUS` (mirroring the .NET module's refusal to evaluate MSBuild
    `Condition` attributes) rather than resolving to a confident `TEST`.
    Returning False for those shapes is what preserves the `AMBIGUOUS` signal
    `drift_check` uses to force an operator decision."""
    root_el = _parse_contained_xml(pom_path, root)
    if isinstance(root_el, dict):
        return root_el  # a discovery_error propagated up

    for child in root_el:
        if _local_name(child.tag) != "dependencies":
            continue
        for dependency in child:
            if _local_name(dependency.tag) != "dependency":
                continue
            if _dependency_names_test_framework(dependency):
                return True
    return False


def _dependency_names_test_framework(dependency) -> bool:
    """True when a single `<dependency>` element's own `<groupId>`/
    `<artifactId>` names a JUnit or TestNG artifact."""
    for field in dependency:
        if _local_name(field.tag) not in ("groupId", "artifactId"):
            continue
        value = (field.text or "").lower()
        if any(token in value for token in _TEST_FRAMEWORK_TOKENS):
            return True
    return False
