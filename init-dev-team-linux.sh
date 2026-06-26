#!/usr/bin/env bash
#
# init-dev-team-linux.sh — Linux replica of the dev-team plugin's /init-dev-team skill.
#
# Non-interactive: installs ALL dev-team prerequisites by default.
#   * hard deps: jq, python3
#   * CodeGraph: auto-init if installed; otherwise print install instructions
#   * mutation tools for every language whose toolchain is present:
#       JS/TS  -> Stryker        (needs node/npm + package.json)
#       Java   -> pitest         (needs mvn/gradle + build file)
#       C#     -> Stryker.NET    (needs dotnet)
#
# Mirrors plugins/dev-team/skills/init-dev-team/SKILL.md, Linux paths only.
# WSL reports "Linux" and is handled here. macOS/Windows are out of scope.
#
# Usage:
#   ./init-dev-team-linux.sh
#
# Env toggles:
#   NO_CODEGRAPH=1 never auto-init CodeGraph
#
set -uo pipefail

# --- helpers ----------------------------------------------------------------

say()  { printf '%s\n' "$*"; }
warn() { printf '%s\n' "$*" >&2; }
have() { command -v "$1" >/dev/null 2>&1; }

SUMMARY_JS="✗ skipped (toolchain absent)"
SUMMARY_JAVA="✗ skipped (toolchain absent)"
SUMMARY_CS="✗ skipped (toolchain absent)"

# --- Step 1: confirm Linux & find a package manager -------------------------

OS="$(uname -s)"
if [ "$OS" != "Linux" ]; then
  warn "This script targets Linux only (uname -s = '$OS')."
  warn "For macOS use brew; for Windows Git Bash use winget/choco/scoop."
  warn "See plugins/dev-team/skills/init-dev-team/SKILL.md for those paths."
  exit 1
fi

PM=""
PM_INSTALL=""
if   have apt-get; then PM="apt";    PM_INSTALL="sudo apt-get install -y"
elif have dnf;     then PM="dnf";    PM_INSTALL="sudo dnf install -y"
elif have yum;     then PM="yum";    PM_INSTALL="sudo yum install -y"
elif have pacman;  then PM="pacman"; PM_INSTALL="sudo pacman -S --noconfirm"
fi

if [ -n "$PM" ]; then
  say "Package manager: $PM"
else
  warn "No supported package manager found (apt-get/dnf/yum/pacman)."
  warn "Install jq and python3 manually, then re-run."
fi

# pacman names python as 'python', not 'python3'.
PY_PKG="python3"
[ "$PM" = "pacman" ] && PY_PKG="python"

# install_pkg <check-cmd> <package> <friendly> <manual-url>
install_pkg() {
  local check="$1" pkg="$2" friendly="$3" url="$4"
  if have "$check"; then
    say "$friendly: already installed ($("$check" --version 2>&1 | head -1))"
    return 0
  fi
  if [ -z "$PM_INSTALL" ]; then
    warn "$friendly missing and no package manager. Install from $url and re-run."
    return 1
  fi
  say "Installing $friendly ..."
  if $PM_INSTALL "$pkg"; then
    say "$friendly: installed ($("$check" --version 2>&1 | head -1))"
    return 0
  fi
  warn "Could not install $friendly. Install it manually from $url and re-run."
  return 1
}

# --- Step 2: hard dependencies ----------------------------------------------

say ""
say "=== Hard dependencies ==="
install_pkg jq      jq        "jq"      "https://jqlang.github.io/jq/"  || HARD_FAIL=1
install_pkg python3 "$PY_PKG" "python3" "https://python.org"            || HARD_FAIL=1

if [ "${HARD_FAIL:-0}" = "1" ]; then
  warn ""
  warn "A hard dependency could not be installed. Resolve the above and re-run."
  exit 1
fi

# --- Step 2.5: CodeGraph (auto) ---------------------------------------------

say ""
say "=== CodeGraph ==="
if [ "${NO_CODEGRAPH:-0}" = "1" ]; then
  say "CodeGraph: skipped (NO_CODEGRAPH=1)."
elif [ -d "${PWD}/.codegraph" ]; then
  say "CodeGraph: initialized ✓"
elif have codegraph; then
  say "CodeGraph installed but not initialized — running 'codegraph init -i'..."
  if codegraph init -i; then
    say "CodeGraph: initialized ✓"
    # Share with the team: the .db is machine-local (gitignored), so commit a
    # project-root .mcp.json registering the MCP server. Every clone then
    # auto-bootstraps its own index via codegraph-bootstrap.sh. Merge without
    # clobbering existing servers.
    MCP_BLOCK='{"mcpServers":{"codegraph":{"type":"stdio","command":"codegraph","args":["serve","--mcp"]}}}'
    if have jq; then
      if [ -f .mcp.json ]; then
        if tmp="$(mktemp)" && jq --argjson add "$MCP_BLOCK" '. * $add' .mcp.json > "$tmp" 2>/dev/null; then
          mv -f "$tmp" .mcp.json
        else
          rm -f "$tmp"
          warn "CodeGraph: could not merge .mcp.json — leaving it unchanged."
        fi
      else
        printf '%s\n' "$MCP_BLOCK" | jq . > .mcp.json
      fi
      say "CodeGraph: wrote .mcp.json — commit it with .codegraph/.gitignore so teammates auto-bootstrap CodeGraph on clone."
    fi
  else
    say "CodeGraph init failed (exit $?). Continuing without CodeGraph."
  fi
else
  say "CodeGraph not installed. Install for code intelligence:"
  say "  https://github.com/colbymchenry/codegraph#installation"
fi

# --- Step 4a: JS/TS — Stryker -----------------------------------------------

say ""
say "=== Mutation testing tools (installing for every available toolchain) ==="

say ""
say "--- JS/TS — Stryker ---"
if ! have node || ! have npm; then
  say "node/npm not found — skipping Stryker."
elif [ ! -f package.json ]; then
  say "No package.json — skipping Stryker (scaffold a JS project, then re-run)."
  SUMMARY_JS="✗ skipped (no package.json)"
else
  if [ -f node_modules/.bin/stryker ]; then
    say "Stryker already installed."
  else
    npm install --save-dev @stryker-mutator/core || true
  fi
  runner="vitest"
  if   grep -q '"jest"'    package.json 2>/dev/null; then runner="jest"
  elif grep -q '"mocha"'   package.json 2>/dev/null; then runner="mocha"
  elif grep -q '"jasmine"' package.json 2>/dev/null; then runner="jasmine"
  elif grep -q '"vitest"'  package.json 2>/dev/null; then runner="vitest"
  else say "No test runner detected — defaulting to vitest runner (swap if needed)."
  fi
  npm install --save-dev "@stryker-mutator/${runner}-runner" || true
  if ls stryker.config.* .strykerrc.json >/dev/null 2>&1; then
    say "Stryker config already present."
  else
    say "Note: run 'npx stryker init' to generate stryker.config.mjs (interactive)."
  fi
  if npx stryker --version >/dev/null 2>&1; then
    SUMMARY_JS="✓ $(npx stryker --version 2>/dev/null)"
  else
    SUMMARY_JS="✓ installed"
  fi
fi

# --- Step 4b: Java/Kotlin — pitest ------------------------------------------

say ""
say "--- Java/Kotlin — pitest ---"
if ! have mvn && ! have gradle; then
  say "mvn/gradle not found — skipping pitest."
elif [ -f pom.xml ]; then
  if grep -q 'pitest-maven' pom.xml 2>/dev/null; then
    say "pitest-maven already configured in pom.xml."
    SUMMARY_JAVA="✓ configured"
  else
    say "Add the pitest-maven plugin to <build><plugins> in pom.xml:"
    cat <<'XML'
  <plugin>
    <groupId>org.pitest</groupId>
    <artifactId>pitest-maven</artifactId>
    <version>1.17.4</version>
    <configuration>
      <outputFormats><param>XML</param></outputFormats>
      <timestampedReports>false</timestampedReports>
    </configuration>
  </plugin>
XML
    say "Then run: mvn pitest:mutationCoverage"
    SUMMARY_JAVA="✗ manual steps needed (edit pom.xml)"
  fi
elif [ -f build.gradle ] || [ -f build.gradle.kts ]; then
  if grep -q 'pitest' build.gradle build.gradle.kts 2>/dev/null; then
    say "pitest plugin already applied in Gradle build."
    SUMMARY_JAVA="✓ configured"
  else
    say "Add the pitest plugin manually (Gradle plugins can't be added programmatically):"
    say "  build.gradle:     id 'info.solidsoft.pitest' version '1.15.0'"
    say "  build.gradle.kts: id(\"info.solidsoft.pitest\") version \"1.15.0\""
    SUMMARY_JAVA="✗ manual steps needed (edit Gradle build)"
  fi
else
  say "No pom.xml or Gradle build file — skipping pitest."
  SUMMARY_JAVA="✗ skipped (no build file)"
fi

# --- Step 4c: C#/.NET — Stryker.NET -----------------------------------------

say ""
say "--- C#/.NET — Stryker.NET ---"
if ! have dotnet; then
  say "dotnet not found — skipping Stryker.NET."
elif dotnet tool list --global 2>/dev/null | grep -q stryker \
  || dotnet tool list --local 2>/dev/null | grep -q stryker; then
  say "dotnet-stryker already installed."
  SUMMARY_CS="✓ installed"
else
  [ -f .config/dotnet-tools.json ] || dotnet new tool-manifest || true
  if dotnet tool install dotnet-stryker; then
    ver="$(dotnet stryker --version 2>/dev/null || echo installed)"
    SUMMARY_CS="✓ ${ver}"
  else
    SUMMARY_CS="✗ failed (install error)"
  fi
fi

# --- Step 5: summary --------------------------------------------------------

say ""
say "dev-team: init complete"
say ""
say "Hard dependencies:"
say "  jq:       ✓ $(jq --version 2>/dev/null)"
say "  python3:  ✓ $(python3 --version 2>/dev/null)"
say ""
say "Mutation testing:"
say "  JS/TS  (Stryker):      $SUMMARY_JS"
say "  Java   (pitest):       $SUMMARY_JAVA"
say "  C#     (Stryker.NET):  $SUMMARY_CS"
say ""
say "The mutation gate will now block zero-kill tests after each RED→GREEN transition."
