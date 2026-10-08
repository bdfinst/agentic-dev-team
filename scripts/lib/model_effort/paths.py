"""Repo locations the A/B harness reads from or writes to."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "scripts"
PLUGIN_ROOT = REPO_ROOT / "plugins" / "dev-team"
AGENTS_DIR = PLUGIN_ROOT / "agents"
# The only extra directory an agent may read. It must never contain answer files.
KNOWLEDGE_DIR = PLUGIN_ROOT / "knowledge"
PRICING_PATH = KNOWLEDGE_DIR / "model-pricing.json"
EXPECTED_DIR = REPO_ROOT / "evals" / "expected"
FIXTURES_DIR = REPO_ROOT / "evals" / "fixtures"
RUNS_DIR = REPO_ROOT / "evals" / "model-effort" / "runs"

# Existing repo scripts the harness reuses, loaded by file path (see external.py).
AGENT_CONTRACT_VALIDATOR = (
    REPO_ROOT / "plugins" / "marketplace-dev" / "scripts" / "validate_agent_contract.py"
)
ISOLATED_DISPATCH = (
    PLUGIN_ROOT / "skills" / "headless-run" / "scripts" / "isolated_dispatch.py"
)
