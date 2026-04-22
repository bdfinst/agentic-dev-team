#!/usr/bin/env bash
# run-assessment-local.sh — zero-install deterministic security assessment.
#
# Runs the deterministic 60-70% of what /security-assessment does: static
# analysis tools + custom SARIF-emitting scripts + structural recon +
# service-comm + shared-cred cross-repo analysis. Produces artifacts in
# the same format the full pipeline emits (recon-<slug>.json, findings-
# <slug>.jsonl, report-<slug>.md, etc.) so downstream tooling like
# evals/comparative/score.py works on the output.
#
# Skipped: LLM judgment agents (security-review, business-logic-domain-
# review, fp-reduction, narrative annotator, exec-report-generator,
# compliance edge annotator). Those require either the plugin installed
# OR manual Claude prompting.
#
# Usage:
#     ./scripts/run-assessment-local.sh <target-path> [<target-path> ...]
#     ./scripts/run-assessment-local.sh --output <dir> <target-path> ...
#     ./scripts/run-assessment-local.sh --help
#
# Default output directory: ./memory/ (matches the plugin's convention).

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LIB_DIR="$SCRIPT_DIR/lib"
OUTPUT_DIR=""
TARGETS=()

print_help() {
  cat <<'EOF'
run-assessment-local.sh — zero-install deterministic security assessment.

usage:
  ./scripts/run-assessment-local.sh <target-path> [<target-path> ...]
  ./scripts/run-assessment-local.sh --output <dir> <target-path> ...

Produces in <OUTPUT_DIR> (default: ./memory):
  recon-<slug>.{json,md}        structural reconnaissance
  findings-<slug>.jsonl         unified finding envelope (one per line)
  service-comm-<slug>.mermaid   (multi-target only)
  shared-creds-<slug>.sarif     (multi-target only)
  report-<slug>.md              deterministic-only skeleton report
  meta-<slug>.json              run metadata (tools present, timings, counts)

Exits 0 on successful run (regardless of findings). Missing external tools
are silently skipped and recorded in meta-<slug>.json.

Required on PATH: python3, jq. Optional: semgrep, gitleaks, trivy, hadolint,
actionlint. More tools = broader coverage.
EOF
}

# ── Parse args ────────────────────────────────────────────────────────────────

while (( $# > 0 )); do
  case "$1" in
    --help|-h) print_help; exit 0 ;;
    --output)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --)
      shift
      TARGETS+=("$@")
      break
      ;;
    -*)
      echo "unknown flag: $1" >&2
      print_help
      exit 2
      ;;
    *)
      TARGETS+=("$1")
      shift
      ;;
  esac
done

if (( ${#TARGETS[@]} == 0 )); then
  echo "error: at least one target path required" >&2
  print_help
  exit 2
fi

# Default output directory
if [[ -z "$OUTPUT_DIR" ]]; then
  OUTPUT_DIR="$(pwd)/memory"
fi
mkdir -p "$OUTPUT_DIR"

# Resolve targets to absolute paths
ABS_TARGETS=()
for t in "${TARGETS[@]}"; do
  if [[ ! -d "$t" ]]; then
    echo "error: target not a directory: $t" >&2
    exit 2
  fi
  ABS_TARGETS+=("$(cd "$t" && pwd)")
done

# Slug derivation
if (( ${#ABS_TARGETS[@]} == 1 )); then
  SLUG="$(basename "${ABS_TARGETS[0]}" | tr '[:upper:]_' '[:lower:]-')"
else
  # Multi-target: dash-joined basenames
  SLUG_PARTS=()
  for t in "${ABS_TARGETS[@]}"; do
    SLUG_PARTS+=("$(basename "$t" | tr '[:upper:]_' '[:lower:]-')")
  done
  SLUG="$(IFS=-; echo "${SLUG_PARTS[*]}")"
fi

echo "─────────────────────────────────────────────────────────"
echo "  run-assessment-local.sh"
echo "  Targets: ${ABS_TARGETS[*]}"
echo "  Output:  $OUTPUT_DIR"
echo "  Slug:    $SLUG"
echo "─────────────────────────────────────────────────────────"

# ── Required binaries ────────────────────────────────────────────────────────

for bin in python3 jq; do
  if ! command -v "$bin" &>/dev/null; then
    echo "error: required binary '$bin' not on PATH" >&2
    exit 2
  fi
done

# Scratch directory for intermediate SARIF
SARIF_DIR="$(mktemp -d -t run-assess-XXXXXX)"
trap 'rm -rf "$SARIF_DIR"' EXIT

# Tool availability bookkeeping
TOOLS_PRESENT=()
TOOLS_MISSING=()

check_tool() {
  if command -v "$1" &>/dev/null; then
    TOOLS_PRESENT+=("$1")
    return 0
  fi
  TOOLS_MISSING+=("$1")
  return 1
}

for tool in semgrep gitleaks hadolint actionlint trivy; do
  check_tool "$tool" >/dev/null || true
done

echo
echo "Tool availability: ${TOOLS_PRESENT[*]:-(none)}"
[[ ${#TOOLS_MISSING[@]} -gt 0 ]] && echo "             missing: ${TOOLS_MISSING[*]}"
echo

# ── Phase timer helper ───────────────────────────────────────────────────────

TIMER="$SCRIPT_DIR/phase-timer.sh"

timer_start() {
  "$TIMER" start "$1" "$SLUG" "$OUTPUT_DIR"
}
timer_end() {
  "$TIMER" end "$1" "$SLUG" "$OUTPUT_DIR"
}
# One-shot wrapping: timer_run <phase-name> -- <command>
timer_run() {
  "$TIMER" run "$1" "$SLUG" "$OUTPUT_DIR" -- "${@:2}"
}

# ── Phase 0 — Deterministic Recon (parallel across targets) ──────────────────

echo "[phase 0] deterministic recon (parallel across targets)"
timer_start "phase-0-recon"

RECON_PRIMARY=""
pids=()
for t in "${ABS_TARGETS[@]}"; do
  sub_slug="$(basename "$t" | tr '[:upper:]_' '[:lower:]-')"
  out_json="$OUTPUT_DIR/recon-$sub_slug.json"
  [[ -z "$RECON_PRIMARY" ]] && RECON_PRIMARY="$out_json"
  python3 "$LIB_DIR/deterministic_recon.py" "$t" "$out_json" &
  pids+=($!)
done
# wait for all recon jobs
for pid in "${pids[@]}"; do wait "$pid" || true; done
timer_end "phase-0-recon"
echo "  → $OUTPUT_DIR/recon-*.json"

# ── Phase 1 — Tool-first detection (parallel: targets × tools × rulesets) ────

echo
echo "[phase 1] tool-first detection (parallel)"
timer_start "phase-1-tool-first"

# Each (target, tool, ruleset) combination is an independent process writing
# its own SARIF file. Launch all in the background, then wait once.

run_semgrep_rule() {
  # one invocation = one ruleset against one target
  local rs="$1" target="$2"
  local name="$(basename "$rs" .yaml)"
  semgrep --quiet --sarif --config "$rs" "$target" \
    > "$SARIF_DIR/semgrep-$name-$(basename "$target").sarif" 2>/dev/null || true
}

run_semgrep_bundle() {
  # community bundle against one target
  local bundle="$1" target="$2"
  local safe_name
  safe_name="$(echo "$bundle" | tr '/' '-')"
  semgrep --quiet --sarif --config "$bundle" "$target" \
    > "$SARIF_DIR/semgrep-$safe_name-$(basename "$target").sarif" 2>/dev/null || true
}

pids=()
for t in "${ABS_TARGETS[@]}"; do
  sub="$(basename "$t")"

  if command -v semgrep &>/dev/null; then
    for rs in \
        "$REPO_ROOT/plugins/agentic-security-review/knowledge/semgrep-rules/ml-patterns.yaml" \
        "$REPO_ROOT/plugins/agentic-security-review/knowledge/semgrep-rules/llm-safety.yaml" \
        "$REPO_ROOT/plugins/agentic-security-review/knowledge/semgrep-rules/fraud-domain.yaml" \
        "$REPO_ROOT/plugins/agentic-security-review/knowledge/semgrep-rules/crypto-anti-patterns.yaml"; do
      [[ -f "$rs" ]] || continue
      run_semgrep_rule "$rs" "$t" &
      pids+=($!)
    done
    for bundle in "p/security-audit" "p/secrets"; do
      run_semgrep_bundle "$bundle" "$t" &
      pids+=($!)
    done
  fi

  if command -v gitleaks &>/dev/null; then
    ( gitleaks detect --no-git --source "$t" --report-format sarif \
        --report-path "$SARIF_DIR/gitleaks-$sub.sarif" 2>/dev/null || true ) &
    pids+=($!)
  fi

  if command -v trivy &>/dev/null; then
    ( trivy config --quiet --format sarif --output "$SARIF_DIR/trivy-config-$sub.sarif" "$t" \
        2>/dev/null || true ) &
    pids+=($!)
  fi

  if command -v hadolint &>/dev/null; then
    for df in "$t"/*/Dockerfile "$t"/Dockerfile; do
      [[ -f "$df" ]] || continue
      ( hadolint --format sarif "$df" \
          > "$SARIF_DIR/hadolint-$(basename "$(dirname "$df")").sarif" 2>/dev/null || true ) &
      pids+=($!)
    done
  fi

  if command -v actionlint &>/dev/null; then
    for wf in "$t"/.github/workflows/*.yml "$t"/.github/workflows/*.yaml; do
      [[ -f "$wf" ]] || continue
      ( actionlint -format '{{json .}}' "$wf" \
          > "$SARIF_DIR/actionlint-$(basename "$wf").json" 2>/dev/null || true ) &
      pids+=($!)
    done
  fi

  # Custom scripts — run in parallel with the external tools
  ( python3 "$REPO_ROOT/plugins/agentic-dev-team/tools/entropy-check.py" "$t" \
      > "$SARIF_DIR/entropy-check-$sub.sarif" 2>/dev/null || true ) &
  pids+=($!)
  ( python3 "$REPO_ROOT/plugins/agentic-dev-team/tools/model-hash-verify.py" "$t" \
      > "$SARIF_DIR/model-hash-verify-$sub.sarif" 2>/dev/null || true ) &
  pids+=($!)
done

echo "  dispatched ${#pids[@]} tool processes across ${#ABS_TARGETS[@]} target(s); waiting..."
for pid in "${pids[@]}"; do wait "$pid" || true; done
timer_end "phase-1-tool-first"
echo "  done"

# ── Phase 2 / Phase 4 — Cross-repo (parallel with post-tools) ──────────────

SERVICE_COMM_FILE=""
SHARED_CREDS_FILE=""
if (( ${#ABS_TARGETS[@]} > 1 )); then
  echo
  echo "[phase 4] cross-repo analysis (parallel)"
  timer_start "phase-4-cross-repo"
  SERVICE_COMM_FILE="$OUTPUT_DIR/service-comm-$SLUG.mermaid"
  SHARED_CREDS_FILE="$OUTPUT_DIR/shared-creds-$SLUG.sarif"
  pids=()
  ( python3 "$REPO_ROOT/plugins/agentic-security-review/harness/tools/service-comm-parser.py" \
      "${ABS_TARGETS[@]}" > "$SERVICE_COMM_FILE" 2>/dev/null || true ) &
  pids+=($!)
  ( python3 "$REPO_ROOT/plugins/agentic-security-review/harness/tools/shared-cred-hash-match.py" \
      "${ABS_TARGETS[@]}" > "$SHARED_CREDS_FILE" 2>/dev/null || true ) &
  pids+=($!)
  for pid in "${pids[@]}"; do wait "$pid" || true; done
  cp "$SHARED_CREDS_FILE" "$SARIF_DIR/shared-creds.sarif" 2>/dev/null || true
  timer_end "phase-4-cross-repo"
  echo "  → $SERVICE_COMM_FILE"
  echo "  → $SHARED_CREDS_FILE"
fi

# ── Normalize all SARIF to unified findings ────────────────────────────────

echo
echo "[normalize] SARIF → unified findings"
timer_start "normalize-sarif"
FINDINGS_FILE="$OUTPUT_DIR/findings-$SLUG.jsonl"
python3 "$LIB_DIR/normalize_findings.py" "$SARIF_DIR" "$FINDINGS_FILE"
timer_end "normalize-sarif"

# ── Build skeleton report ──────────────────────────────────────────────────

echo
echo "[report] skeleton report"
timer_start "skeleton-report"
REPORT_FILE="$OUTPUT_DIR/report-$SLUG.md"
SKELETON_ARGS=(--recon "$RECON_PRIMARY" --findings "$FINDINGS_FILE" --output "$REPORT_FILE")
[[ -n "$SERVICE_COMM_FILE" && -f "$SERVICE_COMM_FILE" ]] && SKELETON_ARGS+=(--service-comm "$SERVICE_COMM_FILE")
[[ -n "$SHARED_CREDS_FILE" && -f "$SHARED_CREDS_FILE" ]] && SKELETON_ARGS+=(--shared-creds "$SHARED_CREDS_FILE")
python3 "$LIB_DIR/skeleton_report.py" "${SKELETON_ARGS[@]}"
timer_end "skeleton-report"

# ── Run metadata ───────────────────────────────────────────────────────────

META_FILE="$OUTPUT_DIR/meta-$SLUG.json"
# Get jq arrays safely — even empty arrays produce valid JSON
present_json=$(printf '%s\n' "${TOOLS_PRESENT[@]:-}" | jq -R . | jq -s 'map(select(. != ""))')
missing_json=$(printf '%s\n' "${TOOLS_MISSING[@]:-}" | jq -R . | jq -s 'map(select(. != ""))')
finding_count=$(wc -l < "$FINDINGS_FILE" | tr -d '[:space:]')
target_json=$(printf '%s\n' "${ABS_TARGETS[@]}" | jq -R . | jq -s .)

jq -n \
  --arg slug "$SLUG" \
  --arg generated_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --argjson targets "$target_json" \
  --argjson tools_present "$present_json" \
  --argjson tools_missing "$missing_json" \
  --argjson finding_count "$finding_count" \
  --arg findings_file "$FINDINGS_FILE" \
  --arg report_file "$REPORT_FILE" \
  --arg recon_file "$RECON_PRIMARY" \
  '{
    slug: $slug,
    generated_at: $generated_at,
    targets: $targets,
    tools_present: $tools_present,
    tools_missing: $tools_missing,
    finding_count: $finding_count,
    findings_file: $findings_file,
    report_file: $report_file,
    recon_file: $recon_file,
    note: "Deterministic-only run — LLM judgment phases skipped. Install the agentic-security-review plugin to run the full /security-assessment pipeline."
  }' > "$META_FILE"

echo "  → $META_FILE"

# ── Summary ────────────────────────────────────────────────────────────────

echo
echo "─────────────────────────────────────────────────────────"
echo "  Run complete."
echo "  Findings: $finding_count total (see $FINDINGS_FILE)"
echo "  Report:   $REPORT_FILE"
echo "  Meta:     $META_FILE"
echo "─────────────────────────────────────────────────────────"
echo
echo "Skipped phases (need /security-assessment or manual Claude prompts):"
echo "  - security-review, business-logic-domain-review agents"
echo "  - fp-reduction 5-stage rubric"
echo "  - tool-finding-narrative-annotator (PII / ML / NATS / crypto narratives)"
echo "  - compliance-mapping LLM edge annotation"
echo "  - exec-report-generator (narrative exec summary, Top 3 Actions, remediation prose)"
echo
echo "To run the full pipeline, install the plugin:"
echo "  claude plugin install --scope project ./plugins/agentic-security-review"
echo "  /security-assessment ${ABS_TARGETS[*]}"
