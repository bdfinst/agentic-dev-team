#!/usr/bin/env bash
# run-assessment-local.sh — zero-install security assessment.
#
# Runs the full /security-assessment pipeline without requiring the plugin
# to be installed. Deterministic phases (recon surface, SARIF tools, custom
# SARIF emitters, service-comm, shared-cred hash, suppression gate,
# severity floors) always run. LLM-judgment phases (security-review,
# business-logic-domain-review, fp-reduction, narrative + compliance,
# exec-report) run only when the `claude` CLI is on PATH and authenticated;
# otherwise the script degrades gracefully to deterministic artifacts.
#
# Usage:
#     ./scripts/run-assessment-local.sh <target-path> [<target-path> ...]
#     ./scripts/run-assessment-local.sh --output <dir> <target-path> ...
#     ./scripts/run-assessment-local.sh --no-llm <target-path> ...
#     ./scripts/run-assessment-local.sh --help
#
# Default output directory: ./memory/ (matches the plugin's convention).

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LIB_DIR="$SCRIPT_DIR/lib"
OUTPUT_DIR=""
TARGETS=()
USE_LLM=1  # 1 = try; 0 = force off. Auto-downgraded to 0 if claude missing.

print_help() {
  cat <<'EOF'
run-assessment-local.sh — zero-install security assessment.

usage:
  ./scripts/run-assessment-local.sh <target-path> [<target-path> ...]
  ./scripts/run-assessment-local.sh --output <dir> <target-path> ...
  ./scripts/run-assessment-local.sh --no-llm <target-path> ...

Produces in <OUTPUT_DIR> (default: ./memory):
  recon-<slug>.{json,md}        structural reconnaissance (LLM-enriched when available)
  findings-<slug>.jsonl         unified finding envelope (tools + LLM agents appended)
  suppressed-<slug>.jsonl       findings removed by ACCEPTED-RISKS.md (if any)
  suppression-log-<slug>.jsonl  per-finding audit trail for the suppression gate
  disposition-<slug>.json       fp-reduction register (LLM phase)
  severity-floors-log-<slug>.jsonl  Phase 2b adjustments
  narratives-<slug>.md          four-domain narrative (LLM phase)
  compliance-<slug>.json        compliance mapping (LLM phase)
  service-comm-<slug>.mermaid   (multi-target only)
  shared-creds-<slug>.sarif     (multi-target only)
  report-<slug>.md              executive report (LLM phase) or skeleton fallback
  meta-<slug>.json              run metadata (tools present, LLM phases, counts)

Exits 0 on successful run. Missing external tools and missing claude CLI are
silently skipped and recorded in meta-<slug>.json.

Required on PATH: python3, jq. Optional SAST: semgrep, gitleaks, trivy,
hadolint, actionlint. Optional LLM judgment: claude (https://claude.ai/code).
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
    --no-llm)
      USE_LLM=0
      shift
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
  SLUG_PARTS=()
  for t in "${ABS_TARGETS[@]}"; do
    SLUG_PARTS+=("$(basename "$t" | tr '[:upper:]_' '[:lower:]-')")
  done
  SLUG="$(IFS=-; echo "${SLUG_PARTS[*]}")"
fi

# ── LLM availability gate ────────────────────────────────────────────────────

if (( USE_LLM == 1 )) && ! command -v claude &>/dev/null; then
  echo "note: claude CLI not on PATH — LLM judgment phases will be skipped." >&2
  USE_LLM=0
fi

LLM_PHASES_RUN=()
LLM_PHASES_SKIPPED=()

echo "─────────────────────────────────────────────────────────"
echo "  run-assessment-local.sh"
echo "  Targets: ${ABS_TARGETS[*]}"
echo "  Output:  $OUTPUT_DIR"
echo "  Slug:    $SLUG"
echo "  LLM:     $([ $USE_LLM -eq 1 ] && echo enabled || echo disabled)"
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
timer_start() { "$TIMER" start "$1" "$SLUG" "$OUTPUT_DIR"; }
timer_end()   { "$TIMER" end   "$1" "$SLUG" "$OUTPUT_DIR"; }

# ── LLM phase wrapper ────────────────────────────────────────────────────────
#
# invoke_llm_phase <phase-label> <expected-output> <<<'prompt text'
# Returns 0 on success (expected-output produced), non-zero otherwise.
# When USE_LLM=0, the call is a no-op returning 127 (caller handles fallback).

INVOKE="$LIB_DIR/invoke_claude.sh"

invoke_llm_phase() {
  local label="$1" expected="$2"
  if (( USE_LLM == 0 )); then
    LLM_PHASES_SKIPPED+=("$label")
    return 127
  fi
  timer_start "$label"
  local rc=0
  "$INVOKE" "$label" "$expected" - || rc=$?
  timer_end "$label"
  if [[ $rc -eq 0 ]]; then
    LLM_PHASES_RUN+=("$label")
  else
    LLM_PHASES_SKIPPED+=("$label (rc=$rc)")
  fi
  return $rc
}

# ── Phase 0 — Recon: deterministic first, optional LLM enrichment ────────────

echo "[phase 0] deterministic recon (parallel across targets)"
timer_start "phase-0-recon-deterministic"

RECON_PRIMARY=""
pids=()
for t in "${ABS_TARGETS[@]}"; do
  sub_slug="$(basename "$t" | tr '[:upper:]_' '[:lower:]-')"
  out_json="$OUTPUT_DIR/recon-$sub_slug.json"
  [[ -z "$RECON_PRIMARY" ]] && RECON_PRIMARY="$out_json"
  python3 "$LIB_DIR/deterministic_recon.py" "$t" "$out_json" &
  pids+=($!)
done
for pid in "${pids[@]}"; do wait "$pid" || true; done
timer_end "phase-0-recon-deterministic"
echo "  → $OUTPUT_DIR/recon-*.json (deterministic)"

if (( USE_LLM == 1 )); then
  echo "[phase 0] LLM recon enrichment (parallel across targets)"
  for t in "${ABS_TARGETS[@]}"; do
    sub_slug="$(basename "$t" | tr '[:upper:]_' '[:lower:]-')"
    expected_md="$OUTPUT_DIR/recon-$sub_slug.md"
    prompt=$(cat <<EOF
You are executing the codebase-recon agent against the target repository:
  TARGET = $t

Read the agent specification at:
  $REPO_ROOT/plugins/agentic-dev-team/agents/codebase-recon.md

Follow its seven-step procedure exactly. A deterministic-recon JSON skeleton
already exists at:
  $OUTPUT_DIR/recon-$sub_slug.json

Read it, refine fields the script could not infer (architecture.summary,
entry-point rationale narratives, security_surface edge signals), and
rewrite both artifacts:
  - $OUTPUT_DIR/recon-$sub_slug.json  (schema_version "0.1", conformant)
  - $OUTPUT_DIR/recon-$sub_slug.md    (human-readable companion)

Do not modify any files outside $OUTPUT_DIR. When finished, verify both
files exist. Emit only the "RECON written:" summary line from the spec.
EOF
)
    echo "$prompt" | invoke_llm_phase "phase-0-recon-llm-$sub_slug" "$expected_md" || \
      echo "  [warn] LLM recon enrichment skipped/failed for $sub_slug (deterministic JSON still present)"
  done
fi

# ── Phase 1 — Tool-first detection (parallel: targets × tools × rulesets) ────

echo
echo "[phase 1] tool-first detection (parallel)"
timer_start "phase-1-tool-first"

run_semgrep_rule() {
  local rs="$1" target="$2"
  local name="$(basename "$rs" .yaml)"
  semgrep --quiet --sarif --config "$rs" "$target" \
    > "$SARIF_DIR/semgrep-$name-$(basename "$target").sarif" 2>/dev/null || true
}

run_semgrep_bundle() {
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

# ── Phase 4 — Cross-repo (runs concurrently-eligible with later LLM work) ────

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

# ── Normalize SARIF → unified findings (precondition for 1b/1c/2/2b/3/5) ───

echo
echo "[normalize] SARIF → unified findings"
timer_start "normalize-sarif"
FINDINGS_FILE="$OUTPUT_DIR/findings-$SLUG.jsonl"
python3 "$LIB_DIR/normalize_findings.py" "$SARIF_DIR" "$FINDINGS_FILE"
timer_end "normalize-sarif"

# ── Phase 1b — Judgment-layer LLM agents (parallel across targets) ─────────

if (( USE_LLM == 1 )); then
  echo
  echo "[phase 1b] LLM judgment (security-review + business-logic-domain-review)"
  for t in "${ABS_TARGETS[@]}"; do
    sub_slug="$(basename "$t" | tr '[:upper:]_' '[:lower:]-')"
    prompt=$(cat <<EOF
You are executing TWO review agents against the target repository:
  TARGET = $t

Agent 1: security-review — spec at:
  $REPO_ROOT/plugins/agentic-dev-team/agents/security-review.md
  Knowledge: $REPO_ROOT/plugins/agentic-dev-team/knowledge/owasp-detection.md

Agent 2: business-logic-domain-review — spec at:
  $REPO_ROOT/plugins/agentic-security-review/agents/business-logic-domain-review.md
  Knowledge: $REPO_ROOT/plugins/agentic-security-review/knowledge/domain-logic-patterns.md

For each agent, analyze the target and APPEND unified-finding entries to:
  $FINDINGS_FILE

Unified finding schema:
  $REPO_ROOT/plugins/agentic-dev-team/knowledge/schemas/unified-finding-v1.json

Required fields per finding: rule_id (dotted), file (repo-relative), line,
severity (error|warning|suggestion|info), message, metadata.source
("security-review" or "business-logic-domain-review"), metadata.confidence
(high|medium|none). Optional: cwe, owasp.

Do NOT duplicate findings already present in the file (read it first; skip
any rule_id+file+line triple that is already recorded).

Scope: examine source tree and ALL files enumerated in the security-review
"Scope — files always in scope" section (CI workflows, Dockerfiles,
infrastructure manifests).

Respect ACCEPTED-RISKS.md if present at $t/ACCEPTED-RISKS.md (consult per
knowledge/accepted-risks-schema.md; do NOT pre-suppress — emit and let the
Phase 1c gate filter).

Write ONLY to $FINDINGS_FILE. Do not produce any other output files.
Verify the file exists at the end. Print a one-line summary
"judgment findings appended: <N>".
EOF
)
    echo "$prompt" | invoke_llm_phase "phase-1b-judgment-$sub_slug" "$FINDINGS_FILE" || \
      echo "  [warn] phase 1b skipped for $sub_slug"
  done
fi

# ── Phase 1c — ACCEPTED-RISKS suppression gate (deterministic) ──────────────
#
# ACCEPTED-RISKS.md commonly lives at a monorepo root rather than each
# service subdirectory. For each target, walk upward (target → parent →
# grandparent …) until ACCEPTED-RISKS.md is found or the filesystem root
# is reached. That directory is passed as the "target-root" so path globs
# in the rules resolve against the monorepo root.

echo
echo "[phase 1c] ACCEPTED-RISKS suppression gate (deterministic)"
find_accepted_risks_root() {
  local dir="$1"
  while [[ "$dir" != "/" && -n "$dir" ]]; do
    [[ -f "$dir/ACCEPTED-RISKS.md" ]] && { echo "$dir"; return 0; }
    dir="$(dirname "$dir")"
  done
  return 1
}

# Dedup roots: many targets can share the same ancestor with ACCEPTED-RISKS.md.
# (bash 3.2 on macOS lacks associative arrays; use a newline-separated string.)
SEEN_RISKS_ROOTS=""
for t in "${ABS_TARGETS[@]}"; do
  sub_slug="$(basename "$t" | tr '[:upper:]_' '[:lower:]-')"
  risks_root="$(find_accepted_risks_root "$t" || true)"
  if [[ -z "$risks_root" ]]; then
    echo "  note: no ACCEPTED-RISKS.md on the path from $t upward — skipping"
    continue
  fi
  if [[ $'\n'"$SEEN_RISKS_ROOTS"$'\n' == *$'\n'"$risks_root"$'\n'* ]]; then
    echo "  note: $risks_root already applied for another target — skipping dup"
    continue
  fi
  SEEN_RISKS_ROOTS="$SEEN_RISKS_ROOTS"$'\n'"$risks_root"
  echo "  target=$t → ACCEPTED-RISKS.md at $risks_root"
  "$SCRIPT_DIR/apply-accepted-risks.sh" "$risks_root" "$SLUG" "$OUTPUT_DIR" \
    || echo "  [warn] suppression gate failed for $sub_slug (risks-root=$risks_root)"
done

# ── Phase 2 — fp-reduction LLM ──────────────────────────────────────────────

DISPOSITION_FILE="$OUTPUT_DIR/disposition-$SLUG.json"
if (( USE_LLM == 1 )); then
  echo
  echo "[phase 2] fp-reduction (LLM)"
  prompt=$(cat <<EOF
You are executing the fp-reduction agent. Spec:
  $REPO_ROOT/plugins/agentic-security-review/agents/fp-reduction.md
Rubric skill:
  $REPO_ROOT/plugins/agentic-security-review/skills/false-positive-reduction/SKILL.md

Inputs:
  Findings (post-suppression):   $FINDINGS_FILE
  RECON (primary target):        $RECON_PRIMARY
  Repo roots:                    ${ABS_TARGETS[*]}

Apply the 5-stage rubric (reachability, environment, compensating controls,
dedup, severity calibration). Probe for joern (command -v joern) and set
reachability_tool accordingly; if absent, use the LLM-fallback mode.

Output schema:
  $REPO_ROOT/plugins/agentic-dev-team/knowledge/schemas/disposition-register-v1.json

Write the disposition register to:
  $DISPOSITION_FILE

One entry per input finding, no silent drops. When complete, verify the
file exists and print a one-line summary "disposition entries: <N>".
EOF
)
  echo "$prompt" | invoke_llm_phase "phase-2-fp-reduction" "$DISPOSITION_FILE" || \
    echo "  [warn] phase 2 skipped — Phase 2b and Phase 3+ will run on raw findings"
fi

# ── Phase 2b — Domain-class severity floors (deterministic) ─────────────────

if [[ -f "$DISPOSITION_FILE" ]]; then
  echo
  echo "[phase 2b] severity floors (deterministic)"
  "$SCRIPT_DIR/apply-severity-floors.sh" "$SLUG" "$OUTPUT_DIR" \
    || echo "  [warn] severity-floor pass failed"
else
  echo
  echo "[phase 2b] skipped — no disposition register to adjust"
fi

# ── Phase 3 — Narratives + compliance (LLM, parallel) ───────────────────────

NARRATIVES_FILE="$OUTPUT_DIR/narratives-$SLUG.md"
COMPLIANCE_FILE="$OUTPUT_DIR/compliance-$SLUG.json"

if (( USE_LLM == 1 )); then
  echo
  echo "[phase 3] narratives + compliance (LLM, parallel)"

  narr_prompt=$(cat <<EOF
You are executing the tool-finding-narrative-annotator agent. Spec:
  $REPO_ROOT/plugins/agentic-security-review/agents/tool-finding-narrative-annotator.md

Inputs:
  Findings / disposition: $FINDINGS_FILE and $DISPOSITION_FILE (if present)
  RECON (primary):        $RECON_PRIMARY

Produce the four-domain narrative (PII flow, ML edge cases, NATS /
messaging auth, crypto cross-file) as a single markdown file:
  $NARRATIVES_FILE

Do NOT describe any finding suppressed by ACCEPTED-RISKS.md (read
$OUTPUT_DIR/suppressed-$SLUG.jsonl if it exists — those are excluded).

Verify the file exists when done.
EOF
)

  comp_prompt=$(cat <<EOF
You are executing the compliance-mapping skill + compliance-edge-annotator.
Skill:   $REPO_ROOT/plugins/agentic-security-review/skills/compliance-mapping/SKILL.md
Agent:   $REPO_ROOT/plugins/agentic-security-review/agents/compliance-edge-annotator.md
Patterns: $REPO_ROOT/plugins/agentic-security-review/knowledge/compliance-patterns.yaml

Inputs:
  Findings:       $FINDINGS_FILE
  Disposition:    $DISPOSITION_FILE (optional; may not exist)

Produce a JSON compliance mapping at:
  $COMPLIANCE_FILE

Include the mandatory disclaimer verbatim (per the skill spec). Verify
the file exists when done.
EOF
)

  # Dispatch both in the background. Each uses its own invoke_claude.sh call,
  # which handles its own timing bracket.
  (echo "$narr_prompt" | invoke_llm_phase "phase-3-narratives" "$NARRATIVES_FILE") &
  p1=$!
  (echo "$comp_prompt" | invoke_llm_phase "phase-3-compliance" "$COMPLIANCE_FILE") &
  p2=$!
  wait "$p1" || true
  wait "$p2" || true
fi

# ── Phase 5 — Executive report (LLM with skeleton fallback) ─────────────────

echo
echo "[phase 5] report generation"
REPORT_FILE="$OUTPUT_DIR/report-$SLUG.md"

if (( USE_LLM == 1 )); then
  rpt_prompt=$(cat <<EOF
You are executing the exec-report-generator agent. Spec:
  $REPO_ROOT/plugins/agentic-security-review/agents/exec-report-generator.md

Inputs (read whatever exists; missing inputs are documented below):
  Recon:          $RECON_PRIMARY
  Findings:       $FINDINGS_FILE
  Disposition:    $DISPOSITION_FILE
  Narratives:     $NARRATIVES_FILE
  Compliance:     $COMPLIANCE_FILE
  Suppressed:     $OUTPUT_DIR/suppressed-$SLUG.jsonl
  Suppress log:   $OUTPUT_DIR/suppression-log-$SLUG.jsonl
  Service-comm:   ${SERVICE_COMM_FILE:-(single-target run; omit)}
  Shared-creds:   ${SHARED_CREDS_FILE:-(single-target run; omit)}
  Phase timings:  $OUTPUT_DIR/phase-timings-$SLUG.jsonl
  Severity-floor log: $OUTPUT_DIR/severity-floors-log-$SLUG.jsonl

Write the publication-ready report to:
  $REPORT_FILE

Follow the seven-section structure exactly. Honor all banner rules (FP-
reduction skipped, LLM-fallback reachability). Include Appendix C (suppressed
findings) when suppression artifacts exist. Include the Phase timings section
with drift detection.

Verify the file exists when done.
EOF
)
  if ! echo "$rpt_prompt" | invoke_llm_phase "phase-5-report" "$REPORT_FILE"; then
    echo "  [warn] LLM report failed — falling back to deterministic skeleton"
  fi
fi

# Fallback: produce skeleton when LLM didn't or report wasn't written
if [[ ! -f "$REPORT_FILE" ]]; then
  timer_start "phase-5-skeleton-fallback"
  SKELETON_ARGS=(--recon "$RECON_PRIMARY" --findings "$FINDINGS_FILE" --output "$REPORT_FILE")
  [[ -n "$SERVICE_COMM_FILE" && -f "$SERVICE_COMM_FILE" ]] && SKELETON_ARGS+=(--service-comm "$SERVICE_COMM_FILE")
  [[ -n "$SHARED_CREDS_FILE" && -f "$SHARED_CREDS_FILE" ]] && SKELETON_ARGS+=(--shared-creds "$SHARED_CREDS_FILE")
  python3 "$LIB_DIR/skeleton_report.py" "${SKELETON_ARGS[@]}"
  timer_end "phase-5-skeleton-fallback"
fi

# ── Run metadata ───────────────────────────────────────────────────────────

META_FILE="$OUTPUT_DIR/meta-$SLUG.json"
present_json=$(printf '%s\n' "${TOOLS_PRESENT[@]:-}" | jq -R . | jq -s 'map(select(. != ""))')
missing_json=$(printf '%s\n' "${TOOLS_MISSING[@]:-}" | jq -R . | jq -s 'map(select(. != ""))')
llm_run_json=$(printf '%s\n' "${LLM_PHASES_RUN[@]:-}" | jq -R . | jq -s 'map(select(. != ""))')
llm_skipped_json=$(printf '%s\n' "${LLM_PHASES_SKIPPED[@]:-}" | jq -R . | jq -s 'map(select(. != ""))')
finding_count=$(wc -l < "$FINDINGS_FILE" | tr -d '[:space:]')
target_json=$(printf '%s\n' "${ABS_TARGETS[@]}" | jq -R . | jq -s .)

jq -n \
  --arg slug "$SLUG" \
  --arg generated_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --argjson targets "$target_json" \
  --argjson tools_present "$present_json" \
  --argjson tools_missing "$missing_json" \
  --argjson llm_phases_run "$llm_run_json" \
  --argjson llm_phases_skipped "$llm_skipped_json" \
  --argjson finding_count "$finding_count" \
  --arg llm_enabled "$([ $USE_LLM -eq 1 ] && echo true || echo false)" \
  --arg findings_file "$FINDINGS_FILE" \
  --arg report_file "$REPORT_FILE" \
  --arg recon_file "$RECON_PRIMARY" \
  '{
    slug: $slug,
    generated_at: $generated_at,
    targets: $targets,
    tools_present: $tools_present,
    tools_missing: $tools_missing,
    llm_enabled: ($llm_enabled == "true"),
    llm_phases_run: $llm_phases_run,
    llm_phases_skipped: $llm_phases_skipped,
    finding_count: $finding_count,
    findings_file: $findings_file,
    report_file: $report_file,
    recon_file: $recon_file
  }' > "$META_FILE"

echo "  → $META_FILE"

# ── Summary ────────────────────────────────────────────────────────────────

echo
echo "─────────────────────────────────────────────────────────"
echo "  Run complete."
echo "  Findings: $finding_count total (see $FINDINGS_FILE)"
echo "  Report:   $REPORT_FILE"
echo "  Meta:     $META_FILE"
if (( USE_LLM == 1 )); then
  echo "  LLM phases run:     ${LLM_PHASES_RUN[*]:-(none)}"
  [[ ${#LLM_PHASES_SKIPPED[@]} -gt 0 ]] && \
    echo "  LLM phases skipped: ${LLM_PHASES_SKIPPED[*]}"
else
  echo "  LLM phases: disabled (claude CLI missing or --no-llm)."
  echo "    To enable, install Claude Code (https://claude.ai/code) and rerun."
fi
echo "─────────────────────────────────────────────────────────"
