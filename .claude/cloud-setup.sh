#!/usr/bin/env bash
# Cloud-session setup for agentic-dev-team.
#
# HOW TO USE: this is NOT auto-run. Claude Code on the web takes its setup script
# from the cloud environment UI, not from a repo file. So: open your environment's
# settings (claude.ai/code → Environment → Setup script) and PASTE the body of
# this file into the "Setup script" field. It runs on a fresh Ubuntu VM BEFORE
# Claude launches, and its filesystem is snapshotted and reused by later sessions.
#
# Because it runs pre-boot, anything it installs is on disk before Claude
# enumerates skills/agents/commands — so installing the dev-team plugin here makes
# it load in the SAME session (unlike the SessionStart hook, whose install only
# takes effect next session). The `claude` CLI IS available in cloud environments.
#
# IMPORTANT: a non-zero exit from the Setup script FAILS session startup. Every
# optional step is guarded with `|| true` and the script always ends with exit 0.
set -uo pipefail

# --- Anchor to the repo root ------------------------------------------------
# Every path below is relative — requirements-dev.txt, .nvmrc, package.json (for
# `npm ci`), scripts/verify_toolchain.py, plugins/dev-team/... — and every step
# is guarded with `|| true` so it cannot fail session startup. Those two facts
# combine badly: invoked from the wrong working directory, this script skips its
# entire job in silence and still prints "cloud setup complete". That is exactly
# the false-green class scripts/verify_toolchain.py exists to catch, so don't
# reproduce it here.
#
# A caller that resolves the root and then does not `cd` to it is the common
# shape of this bug — the value gets used to locate this file and is then
# dropped. So resolve the root here rather than trusting the caller's cwd, and
# VALIDATE each candidate against a marker instead of assuming the first one is
# right. Markers are the same pair /setup Step 2 uses for its in-repo check.
_is_repo_root() {
  [ -n "${1:-}" ] &&
    [ -f "$1/requirements-dev.txt" ] &&
    [ -f "$1/plugins/dev-team/.claude-plugin/plugin.json" ]
}

# This file lives at <root>/.claude/cloud-setup.sh, so its own directory's
# parent is the root — correct whenever it is invoked as the repo file. When the
# BODY of this script was pasted into the cloud UI instead, BASH_SOURCE points
# at a temp file whose parent fails the marker check, and the loop falls through
# to the next candidate. No special-casing needed either way.
_self_parent=""
_self_dir="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd)" || _self_dir=""
[ -n "$_self_dir" ] && _self_parent="$(dirname "$_self_dir")"

ROOT=""
for _cand in "$_self_parent" "${CLAUDE_PROJECT_DIR:-}" \
             "$(git rev-parse --show-toplevel 2>/dev/null)" "$PWD"; do
  if _is_repo_root "$_cand"; then
    ROOT="$_cand"
    break
  fi
done

if [ -n "$ROOT" ]; then
  cd "$ROOT" || { echo "cloud setup: cannot cd to $ROOT — aborting."; exit 0; }
  echo "cloud setup: repo root = $ROOT"
else
  # Say so loudly rather than proceeding to no-op behind a wall of `|| true`.
  echo "cloud setup: WARNING — could not locate the repo root (no candidate had"
  echo "cloud setup: requirements-dev.txt + plugins/dev-team/.claude-plugin/plugin.json)."
  echo "cloud setup: continuing from $PWD; relative steps will likely be skipped."
fi

# --- Toolchain the repo's tests/gates need ---------------------------------
apt-get update -y || true
apt-get install -y jq shellcheck || true

# Python dev deps — several content-guard suites shell out to Python that imports these.
python3 -m pip install --quiet -r requirements-dev.txt \
  || pip3 install --quiet -r requirements-dev.txt \
  || true

# Repair the interpreter after the requirements-dev.txt install.
#
# On Debian/Ubuntu images, `pip install semgrep` pulls a newer PyJWT into
# user-site but CANNOT remove the distro-packaged one ("Cannot uninstall PyJWT
# 2.7.0, RECORD file not found. Hint: The package was installed by debian").
# The surviving mix leaves user-site `jwt` importing the SYSTEM `cryptography`,
# whose Rust bindings then abort with
# `ModuleNotFoundError: No module named '_cffi_backend'` — a pyo3 panic, not a
# catchable ImportError. semgrep imports jwt, so semgrep dies on startup while
# still sitting on PATH looking perfectly healthy. Downstream, every
# plugins/security-assessment/ rule reports NO-FIRE and the fixture audit fails
# with no clue why. Reinstalling both into user-site makes the resolution
# consistent. Cheap, idempotent, and harmless when the conflict never happened.
python3 -m pip install --quiet --user --upgrade --force-reinstall cffi cryptography || true

# gh CLI (PR operations), if the image doesn't already ship it.
command -v gh >/dev/null 2>&1 || apt-get install -y gh || true

# --- uv: the installer for tools pip cannot build ---------------------------
# Needed below for mutmut, and used by scripts/dev-setup.sh for the Python 3.8
# floor interpreter and graphify.
if ! command -v uv >/dev/null 2>&1; then
  curl -fsSL https://astral.sh/uv/install.sh | sh >/dev/null 2>&1 || true
fi
export PATH="$HOME/.local/bin:$PATH"

# --- mutmut: the Python mutation lane (/mutation-testing) -------------------
# MUST be `mutmut<3`: mutmut 3.x changed its config/CLI contract (source_paths
# in a [mutmut] setup.cfg section, no --paths-to-mutate) and the shipped
# adapter (plugins/dev-team/hooks/mutation_adapters/mutmut.py) does not speak it.
#
# MUST go through uv, not pip: mutmut 2.x depends on glob2 0.7, whose setup.py
# uses `install_layout` and fails to build against setuptools >= 60 with
# `AttributeError: install_layout`. uv's build isolation supplies a compatible
# setuptools; a bare `pip install "mutmut<3"` fails outright on a modern image.
# The adapter resolves it via shutil.which("mutmut"), so uv's isolated
# console-script install is exactly what it looks for.
if ! command -v mutmut >/dev/null 2>&1; then
  uv tool install "mutmut<3" >/dev/null 2>&1 || true
fi

# --- adr-tools: /adr-tools + the adr-author agent ---------------------------
# There is no apt package on Ubuntu. The scripts resolve their siblings through
# `$(dirname $0)`, so EVERY executable in src/ has to land on PATH — symlinking
# only `adr` yields "adr-config: No such file or directory".
if ! command -v adr >/dev/null 2>&1; then
  mkdir -p "$HOME/.local/opt" "$HOME/.local/bin" || true
  if [ ! -d "$HOME/.local/opt/adr-tools" ]; then
    git clone --depth 1 https://github.com/npryce/adr-tools \
      "$HOME/.local/opt/adr-tools" >/dev/null 2>&1 || true
  fi
  for f in "$HOME"/.local/opt/adr-tools/src/*; do
    case "$f" in *.md) continue ;; esac
    if [ -f "$f" ]; then
      ln -sf "$f" "$HOME/.local/bin/$(basename "$f")" || true
    fi
  done
fi

# --- Node + git hooks (husky) ----------------------------------------------
# `npm ci` runs the package.json `prepare: husky` script, which writes the
# pre-commit / pre-push / commit-msg hooks into .husky/_ and points
# core.hooksPath at them — and installs the tools those hooks invoke
# (lint-staged, commitlint, eslint). Without it the hooks are absent in the
# cloud session, so commits/pushes skip the local gates. Needs Node 24+
# (the repo's engines floor); do NOT set HUSKY=0 — that would skip the hooks.
if ! command -v npm >/dev/null 2>&1; then
  # Single source of truth for the Node version: .nvmrc (fallback 24).
  node_major="$(tr -dc '0-9.' < .nvmrc 2>/dev/null | cut -d. -f1)"
  curl -fsSL "https://deb.nodesource.com/setup_${node_major:-24}.x" | bash - >/dev/null 2>&1 || true
  apt-get install -y nodejs || true
fi
if command -v npm >/dev/null 2>&1; then
  npm ci || true
  echo "cloud setup: npm ci done — husky hooks embedded (pre-commit, pre-push, commit-msg)."
else
  echo "cloud setup: npm unavailable — husky hooks NOT embedded; commits/pushes skip local gates."
fi

# --- Install the dev-team plugin (loads THIS session) ----------------------
# The plugin must be on disk before Claude boots to be enumerated. This setup
# script runs pre-boot, so installing here is the supported way to get the
# plugin's skills/agents in the current session. Best-effort: never fail startup.
#
# Freshness matters: the environment filesystem (including ~/.claude/plugins/
# cache) is snapshotted and reused, and `plugin install` is a no-op once a
# version is cached — so we must REFRESH, not just install. Re-pull the
# marketplace catalog and `plugin update` on every run, then enable auto-update
# so future releases refresh at launch even when this script is not re-run.
if command -v claude >/dev/null 2>&1; then
  claude plugin marketplace add    bdfinst/agentic-dev-team >/dev/null 2>&1 || true
  claude plugin marketplace update bfinster                 >/dev/null 2>&1 || true
  # Install at user scope (the CLI default); update is pinned to it because
  # `claude plugin update` needs an explicit --scope or it assumes user.
  claude plugin install              dev-team@bfinster >/dev/null 2>&1 || true
  claude plugin update  --scope user dev-team@bfinster >/dev/null 2>&1 || true
  python3 plugins/dev-team/skills/upgrade/scripts/enable_autoupdate.py --enable || true
  # Report version drift (pending-restart update or a blocked refresh); silent when current.
  python3 plugins/dev-team/skills/upgrade/scripts/check_version_drift.py || true
else
  echo "cloud setup: claude CLI not found — skipping plugin install (run skills from files)."
fi

# --- Verify by EXECUTING every tool, not by looking for it ------------------
# The whole point of this step: `command -v <tool>` passes for a tool that
# cannot start, so a provisioning run can report success and hand back a broken
# environment. verify_toolchain.py spawns each tool and reads its exit status.
#
# Its non-zero exit is deliberately NOT propagated — a non-zero Setup script
# fails session startup, and a partially-provisioned session you can see the
# failures in beats no session at all. Read the ✗ lines; they name the tool and
# quote the interpreter's own error.
if [ -f scripts/verify_toolchain.py ]; then
  python3 scripts/verify_toolchain.py || \
    echo "cloud setup: WARNING — required tools above could not run; the gates that need them will fail."
fi

echo "agentic-dev-team cloud setup complete: jq shellcheck python-deps gh node+husky-hooks uv mutmut adr dev-team-plugin"
exit 0
