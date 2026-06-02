# User guide: security assessment

Running a security assessment against a target repository. Two paths:

- **Path A (recommended)** — install the plugin and use `/security-assessment`
- **Path B (zero-install)** — use the local script `scripts/run-assessment-local.sh`

Both produce output in the same layout under `memory/` (or a directory you choose) and score against the comparative-testing harness at `evals/comparative/score.py`. Path B auto-detects the `claude` CLI and runs the same LLM judgment phases when it is available; when it isn't (or with `--no-llm`), Path B degrades to deterministic-only output.

---

## Tool install matrix

Tools are the foundation of both paths. What you install directly determines what findings surface. Missing tools degrade gracefully — the pipeline does not fail — but scan concerns lose coverage.

### Required — install these before doing real work

| Tool | Install | Covers (scan concern) | Missing impact |
|---|---|---|---|
| **Python 3.10+** | pre-installed on modern systems | All scripts + red-team harness | Pipeline won't run |
| **jq** | `brew install jq` / `apt install jq` | Shell scripts parse JSON | Pipeline won't run |
| **semgrep** | `pip install semgrep` | SAST across every scan concern — especially crypto (scan-07), secrets (scan-01), business-logic (scan-03), supply-chain (scan-08) | ~60% recall loss |

### Tier-1 (strongly recommended) — closes the main coverage gaps

| Tool | Install | Covers | Missing impact |
|---|---|---|---|
| **gitleaks** | `brew install gitleaks` | scan-01 (secrets, credentials in committed files) | entropy-check.py catches a narrower subset; you miss AWS/Slack/GitHub-token patterns that gitleaks detects |
| **hadolint** | `brew install hadolint` | scan-05 (Dockerfile — USER directive, base image pinning, apt-get root) | Semgrep covers some Dockerfile patterns but not DL*-series rules |
| **actionlint** | `brew install actionlint` | scan-06 (GitHub Actions — `printenv`, `continue-on-error`, excessive `permissions:`) | scan-06 coverage drops to zero unless you have semgrep with `p/github-actions` installed |
| **trivy** | `brew install trivy` | scan-05 (IaC config) + scan-08 (vulnerability DB on OS packages) | CVE scanning of container deps missed; IaC config drift missed |

**Install all five with one line**:

```bash
brew install jq semgrep gitleaks hadolint actionlint trivy
```

On Linux:

```bash
apt install jq && \
  pip install semgrep && \
  # gitleaks, hadolint, actionlint, trivy: download prebuilt binaries from their GitHub releases
  curl -sL https://github.com/gitleaks/gitleaks/releases/latest/download/gitleaks-linux-amd64 -o /usr/local/bin/gitleaks && chmod +x /usr/local/bin/gitleaks
```

(Adapt the curl pattern for hadolint, actionlint, trivy — each has prebuilt Linux/darwin binaries on GitHub releases.)

### Tier-2 (optional, broader coverage)

Install these if you work with the ecosystems they cover.

| Tool | Install | Covers | When to install |
|---|---|---|---|
| **checkov** | `pip install checkov` | Terraform + Kubernetes + CloudFormation policy | IaC-heavy projects |
| **bandit** | `pip install bandit` | Python-specific SAST (supplements semgrep) | Python services |
| **gosec** | `brew install gosec` | Go-specific SAST | Go services |
| **bearer** | `brew install bearer` | Data-flow / PII scanning | Services handling PII/PHI |
| **osv-scanner** | `brew install osv-scanner` | OSV-backed CVE scanning on dep manifests | Deep supply-chain audits |
| **grype** | `brew install grype` | Container vulnerability scanning | Docker image audits |
| **kube-linter** | `brew install kube-linter` | Kubernetes manifest linting | k8s-heavy projects |
| **trufflehog** | `brew install trufflehog` | Secrets across git history | Deep-history scans |
| **joern** | `brew install joern` (~400 MB) | Call-graph reachability for FP-reduction | Plugin's full pipeline (Phase 2); falls back to LLM reasoning when absent |
| **pandoc** + **weasyprint** | `brew install pandoc weasyprint` | PDF export of reports | You want to hand reports to executives |

**Joern is a special case**: ~400 MB install but enables deterministic call-graph reachability in FP-reduction. Without it, the agent falls back to LLM reasoning and the exec report carries a banner noting the fallback. Install if you run assessments routinely; skip if you try the plugin occasionally.

### How to check what's installed

```bash
for tool in jq semgrep gitleaks hadolint actionlint trivy joern python3; do
  command -v "$tool" >/dev/null 2>&1 && echo "  [ok]   $tool" || echo "  [MISS] $tool"
done
```

---

## Path A — install the plugin

### Approach A1: Register the local marketplace

Fastest for development (install from the repo you cloned):

1. Open Claude Code in the repo:

   ```bash
   cd /path/to/agentic-dev-team
   claude
   ```

2. In the Claude Code session, run:

   ```
   /plugin marketplace add .
   /plugin install agentic-dev-team@bfinster
   /plugin install agentic-security-assessment@bfinster
   ```

   The `.` tells Claude Code to look for `.claude-plugin/marketplace.json` in the current directory. Both plugins become available.

3. Verify:

   ```
   /plugin list
   ```

4. Run the assessment:

   ```
   /security-assessment /path/to/target
   ```

### Approach A2: Start Claude Code with `--plugin-dir`

Skip the marketplace registration — load plugins at session start:

```bash
cd /path/to/agentic-dev-team
claude \
  --plugin-dir ./plugins/agentic-dev-team \
  --plugin-dir ./plugins/agentic-security-assessment
```

Then in the session:

```
/security-assessment /path/to/target
```

### What `/security-assessment` does

Phases are declared in `plugins/agentic-security-assessment/commands/security-assessment.md`:

| Phase | What runs | Deterministic? |
|---|---|---|
| 0. Recon | `codebase-recon` agent (opus) | LLM |
| 1. Tool-first detection | static-analysis-integration skill dispatches semgrep/gitleaks/hadolint/actionlint/trivy on the target + `.github/workflows/` (via `scripts/find-ci-files.sh`) | **deterministic** |
| 1b. Judgment detection | `security-review` + `business-logic-domain-review` agents (opus, parallel) | LLM |
| 1c. ACCEPTED-RISKS suppression | `scripts/apply-accepted-risks.sh` | **deterministic** |
| 2. FP-reduction | `fp-reduction` agent (opus) | LLM |
| 2b. Severity floors | `scripts/apply-severity-floors.sh` | **deterministic** |
| 3. Narrative + compliance | `tool-finding-narrative-annotator` (sonnet) + `compliance-mapping` skill | LLM + deterministic |
| 4. Service-communication | `service-comm-parser.py` | **deterministic** |
| 5. Report generation | `exec-report-generator` agent (opus) | LLM |

Outputs land in `memory/`:

```
memory/
├── recon-<slug>.{json,md}
├── findings-<slug>.jsonl
├── suppressed-<slug>.jsonl       (if ACCEPTED-RISKS.md is present)
├── suppression-log-<slug>.jsonl
├── disposition-<slug>.json
├── severity-floors-log-<slug>.jsonl
├── narratives-<slug>.md
├── compliance-<slug>.json
├── service-comm-<slug>.mermaid   (multi-target only)
├── shared-creds-<slug>.sarif     (multi-target only)
└── report-<slug>.md
```

---

## Path B — local script

For CI integration, ruleset iteration, or when you don't want to install the plugin. Deterministic phases always run; LLM judgment phases run automatically when the `claude` CLI is on PATH.

### Quickstart

```bash
cd /path/to/agentic-dev-team
./scripts/run-assessment-local.sh /path/to/target
```

For multi-target cross-repo analysis:

```bash
./scripts/run-assessment-local.sh \
  /path/to/service-a \
  /path/to/service-b
```

Custom output directory:

```bash
./scripts/run-assessment-local.sh \
  --output /tmp/my-assessment \
  /path/to/target
```

Force deterministic-only (skip LLM phases even if `claude` is available):

```bash
./scripts/run-assessment-local.sh --no-llm /path/to/target
```

### LLM auto-detection

The script probes `command -v claude` at startup:

- **claude present** — runs every phase: Phase 0 recon enrichment, Phase 1b judgment (security-review + business-logic-domain-review), Phase 2 fp-reduction, Phase 3 narratives + compliance, Phase 5 exec report. Each LLM phase uses headless `claude -p <prompt>` and times itself via `scripts/phase-timer.sh`.
- **claude missing or `--no-llm`** — runs only deterministic phases (recon skeleton, SARIF tools, custom scripts, suppression gate, skeleton report). The run logs each skipped LLM phase in `meta-<slug>.json` under `llm_phases_skipped`.

Headless Claude calls go through `scripts/lib/invoke_claude.sh`, which adds `--allow-dangerously-skip-permissions` and passes a fixed allowlist (`Read Glob Grep Bash Edit Write Agent`). Every LLM phase writes to `<OUTPUT_DIR>` and is verified by file-existence check — the wrapper does not parse prose to determine success.

### Deterministic-only coverage expectations

When LLM is unavailable, expected recall is **40-50%** on a typical target. The gap is primarily in scan-02 (auth), scan-03 (business-logic), and scan-04 (PII flows) — concerns that require semantic reasoning static tools can't perform. With LLM enabled, recall climbs to the 85-95% range the full plugin produces.

### What Path B is useful for

- **CI integration** — drop `run-assessment-local.sh` into a Docker container with the tools pre-installed; no Claude account needed
- **Iterating on semgrep rulesets** — change a rule, re-run, re-score against ground-truth
- **Comparative testing** — produce a deterministic baseline for `evals/comparative/score.py`
- **Fast sanity checks** — catch obvious issues before committing, without API calls
- **Offline environments** — works on air-gapped hosts once tools are in place

---

## Scoring a run

Both paths produce output in `memory/` (or `--output <dir>`). The comparative-testing harness at `evals/comparative/score.py` scores against a reference baseline:

```bash
python3 evals/comparative/score.py \
  --reference evals/comparative/reference-baseline/<date> \
  --ours memory
```

- `--reference` points at a previously-captured `opus_repo_scan_test` run's markdown reports (see `docs/comparative-testing.md` for how to capture one).
- `--ours` points at the directory containing your run's `findings-*.jsonl`, `disposition-*.json`, etc.
- Prints recall / severity-agreement / suppression-correctness / extra-emissions scorecard.

You can also run with just `--ours` to get a single-column summary.

See `docs/comparative-testing.md` for the full comparative-testing runbook and metric interpretation.

---

## Troubleshooting

### "plugin not found in any configured marketplace"

`claude plugin install --scope project <path>` doesn't accept direct filesystem paths. Use `/plugin marketplace add .` from inside Claude Code first (Approach A1), or start Claude Code with `--plugin-dir` (Approach A2).

### Recall lower than expected

Check `memory/meta-<slug>.json` (if produced by the zero-install script) or the exec report's Methodology section for tool availability. Missing Tier-1 tools cap recall:

- No `gitleaks` → scan-01 (secrets) recall drops
- No `hadolint` → scan-05 (container) recall drops
- No `actionlint` → scan-06 (CI/CD) recall drops to near zero
- No `trivy` → scan-05 (IaC) + scan-08 (CVE) recall drops

Install the missing tools and re-run.

### Every finding is `MEDIUM` severity

Likely cause: the disposition register's exploitability scores are uniform (~5 default) because the LLM agent didn't differentiate. This is what `scripts/apply-severity-floors.sh` fixes by applying domain-class floors deterministically. If you invoked the plugin, the floor script runs automatically; if you ran Path B, exec-report generation is LLM-SKIPPED so severity comes from tool-emitted values directly — which may still cluster around MEDIUM unless you invoke the LLM phases manually.

### `ACCEPTED-RISKS.md` not being applied

Run `scripts/apply-accepted-risks.sh <target-dir> <slug>` manually to verify the rules parse and match. Check the schema with:

```bash
python3 scripts/lib/apply_accepted_risks.py \
  --findings memory/findings-<slug>.jsonl \
  --accepted-risks <target>/ACCEPTED-RISKS.md \
  --suppressed-out /tmp/test-supp.jsonl \
  --audit-log-out /tmp/test-audit.jsonl \
  --dry-run
```

If the dry-run reports parse errors, the `ACCEPTED-RISKS.md` needs fixing. See `plugins/agentic-dev-team/knowledge/accepted-risks-schema.md` for the required schema.

### Red-team target refused with scope-violation

`/redteam-model` refuses public targets by default. To test against a public target you own, pass `--self-certify-owned <path-to-authorization-artifact>`. See `plugins/agentic-security-assessment/knowledge/redteam-authorization.md` for the required artifact format.

---

## Quick reference card

```bash
# Install all Tier-1 tools (macOS)
brew install jq semgrep gitleaks hadolint actionlint trivy

# Path A: install the plugin and run
cd /path/to/agentic-dev-team
claude                                    # opens Claude Code in this dir
/plugin marketplace add .                 # register the local marketplace
/plugin install agentic-dev-team@bfinster
/plugin install agentic-security-assessment@bfinster
/security-assessment /path/to/target

# Path B: zero-install deterministic run
./scripts/run-assessment-local.sh /path/to/target

# Path B multi-target
./scripts/run-assessment-local.sh /path/to/service-a /path/to/service-b

# Score against a reference baseline
python3 evals/comparative/score.py \
  --reference evals/comparative/reference-baseline/<date> \
  --ours memory

# Check tool availability
for t in jq semgrep gitleaks hadolint actionlint trivy joern python3; do
  command -v "$t" >/dev/null 2>&1 && echo "  [ok]   $t" || echo "  [MISS] $t"
done
```
