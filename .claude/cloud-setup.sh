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

# --- Toolchain the repo's tests/gates need ---------------------------------
apt-get update -y || true
apt-get install -y jq shellcheck bats || true

# Python dev deps — several bats suites shell out to Python that imports these.
python3 -m pip install --quiet -r requirements-dev.txt \
  || pip3 install --quiet -r requirements-dev.txt \
  || true

# gh CLI (PR operations), if the image doesn't already ship it.
command -v gh >/dev/null 2>&1 || apt-get install -y gh || true

# --- Node + git hooks (husky) ----------------------------------------------
# `npm ci` runs the package.json `prepare: husky` script, which writes the
# pre-commit / pre-push / commit-msg hooks into .husky/_ and points
# core.hooksPath at them — and installs the tools those hooks invoke
# (lint-staged, commitlint, eslint). Without it the hooks are absent in the
# cloud session, so commits/pushes skip the local gates. Needs Node 20+
# (commitlint@21); do NOT set HUSKY=0 — that would skip embedding the hooks.
if ! command -v npm >/dev/null 2>&1; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash - >/dev/null 2>&1 || true
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
if command -v claude >/dev/null 2>&1; then
  claude plugin marketplace add bdfinst/agentic-dev-team >/dev/null 2>&1 || true
  claude plugin install dev-team@bfinster >/dev/null 2>&1 || true
else
  echo "cloud setup: claude CLI not found — skipping plugin install (run skills from files)."
fi

echo "agentic-dev-team cloud setup complete: jq shellcheck bats python-deps gh node+husky-hooks dev-team-plugin"
exit 0
