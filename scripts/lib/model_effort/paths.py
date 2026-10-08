"""Repo locations the A/B harness reads from or writes to."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "dev-team"
AGENTS_DIR = PLUGIN_ROOT / "agents"
# The only extra directory an agent may read. It must never contain answer files.
KNOWLEDGE_DIR = PLUGIN_ROOT / "knowledge"
PRICING_PATH = KNOWLEDGE_DIR / "model-pricing.json"
EXPECTED_DIR = REPO_ROOT / "evals" / "expected"
FIXTURES_DIR = REPO_ROOT / "evals" / "fixtures"
RUNS_DIR = REPO_ROOT / "evals" / "model-effort" / "runs"


@dataclass(frozen=True)
class EvalPaths:
    """The directories a run reads: agent files, expected entries, fixtures and the plugin.

    `default()` is the repo checkout; a test or another caller names its own.
    """

    agents_dir: Path
    expected_dir: Path
    fixtures_dir: Path
    plugin_root: Path
    knowledge_dir: Path

    @classmethod
    def default(cls) -> EvalPaths:
        return cls(
            agents_dir=AGENTS_DIR,
            expected_dir=EXPECTED_DIR,
            fixtures_dir=FIXTURES_DIR,
            plugin_root=PLUGIN_ROOT,
            knowledge_dir=KNOWLEDGE_DIR,
        )


# Existing repo scripts the harness reuses, loaded by file path (see external.py).
AGENT_CONTRACT_VALIDATOR = (
    REPO_ROOT / "plugins" / "marketplace-dev" / "scripts" / "validate_agent_contract.py"
)
ISOLATED_DISPATCH = (
    PLUGIN_ROOT / "skills" / "headless-run" / "scripts" / "isolated_dispatch.py"
)
MINIMAL_YAML = PLUGIN_ROOT / "hooks" / "lib" / "minimal_yaml.py"
PRICING_MODULE = PLUGIN_ROOT / "hooks" / "lib" / "pricing.py"
EVAL_GRADE = REPO_ROOT / "scripts" / "eval_grade.py"
