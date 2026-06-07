#!/usr/bin/env bash
# Cloud-session setup for agentic-dev-team.
#
# HOW TO USE: this is NOT auto-run. Claude Code on the web takes its setup script
# from the cloud environment UI, not from a repo file. So: open your environment's
# settings (claude.ai/code → Environment → Setup script) and PASTE the body of
# this file into the "Setup script" field. It runs as root on a fresh Ubuntu VM
# before Claude launches, and installs the tooling this repo's tests/gates need.
#
# IT DOES NOT INSTALL THE dev-team PLUGIN. The `claude` CLI is not available in
# cloud environments, so `claude plugin marketplace add` / `claude plugin install`
# cannot run there. See CLAUDE.md → "Cloud sessions" for how to use the plugin's
# workflow in a cloud session (read its skill files directly).
set -euo pipefail

apt-get update -y
apt-get install -y jq shellcheck bats

# Python dev deps — several bats suites shell out to Python that imports these.
python3 -m pip install --quiet -r requirements-dev.txt \
  || pip3 install --quiet -r requirements-dev.txt

# gh CLI (PR operations), if the image doesn't already ship it.
command -v gh >/dev/null 2>&1 || apt-get install -y gh || true

echo "agentic-dev-team cloud setup complete: jq shellcheck bats python-deps gh"
