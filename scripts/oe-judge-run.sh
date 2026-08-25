#!/usr/bin/env bash
# oe-judge-run.sh — drive the Ownership Engineering judge pass that PR #266
# needs to convert its projected scorecard into measured results.
#
# What this completes from plans/ownership-engineering-improvements.md:
#   1. Judge run over evals/ownership-engineering/fixtures/ (DoD #1)
#   2. Re-stamp the scorecard with measured cells (DoD #2)
#   3. Confirm oe-08 flips its knownGap sentinel off
#   4. Confirm Wave 2.3 QA rows still hit ER ≥4, DC ≥4 after the merge reframe
#
# What this does NOT do:
#   - Human ratification of Wave 3.1 (the (a) vs (b) call on progress-guardian).
#     That's a decision-required step; this script just records it as pending.
#   - Regenerate knowledge/index.json or run /agent-audit — those are guarded
#     by scripts/ci-local.sh; run it separately.
#
# Modes:
#   --plan          Print every (subject × fixture) pair that will run; no calls.
#                   Use this first to scope cost.
#   --run           Drive the judge over every pair. Writes per-pair verdicts to
#                   evals/ownership-engineering/runs/<run_id>/<fixture>__<subject>.json
#                   and an aggregated .csv at runs/<run_id>/results.csv.
#                   Re-running with --resume reuses anything already on disk.
#   --score         Read the latest run and produce a measured scorecard at
#                   evals/ownership-engineering/scorecard-measured.md (the
#                   projected scorecard.md is left untouched until --commit).
#   --commit        Replace the "Re-score after implementation" projected section
#                   in scorecard.md with the measured one. Atomic: backs up the
#                   old section to scorecard.md.bak first.
#   --check         CI-friendly: re-grade the latest measured scorecard against
#                   the Wave 2.3 floor (QA ER ≥4, DC ≥4) and the DoD floor
#                   (no in-role dimension below 3, human-oversight/PM/qa rows
#                   out of the 1–2 band). Exits non-zero on regression.
#   (no args)       Prints usage.
#
# Env vars:
#   OE_JUDGE_MODEL  Judge model id (default: sonnet alias resolved by claude).
#   OE_RUN_ID       Override the run directory name (default: timestamp).
#   OE_RESUME       Set to skip pairs whose verdict file already exists.
#   OE_DRY_RUN      Set to print prompts without calling the model (for debug).
#
# Requirements: jq, python3, claude CLI (or any LLM client; the call is
# isolated to oe_invoke_judge() below — swap it for an API call if you want).

set -uo pipefail

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

ROOT="$(git rev-parse --show-toplevel)"
OE_DIR="$ROOT/evals/ownership-engineering"
FIXTURES_DIR="$OE_DIR/fixtures"
EXPECTED_DIR="$OE_DIR/expected"
RUNS_DIR="$OE_DIR/runs"
SCORECARD="$OE_DIR/scorecard.md"
JUDGE_MODEL="${OE_JUDGE_MODEL:-sonnet}"

# Subjects → file path. Used to give the judge the *actual current prose*
# the subject would operate under. agents/* are obvious; skills/* expose
# the orchestrator-side prose for the skill. progress-guardian remains an
# agent even though Wave 3.1 (b) keeps it dispatch-only.
declare_subject_paths() {
  # Bash 3.2-safe: no associative arrays. Print "subject<TAB>path" lines.
  cat <<'EOF'
orchestrator	plugins/dev-team/agents/orchestrator.md
software-engineer	plugins/dev-team/agents/software-engineer.md
product-manager	plugins/dev-team/agents/product-manager.md
architect	plugins/dev-team/agents/architect.md
qa-engineer	plugins/dev-team/agents/qa-engineer.md
progress-guardian	plugins/dev-team/agents/progress-guardian.md
human-oversight-protocol	plugins/dev-team/skills/human-oversight-protocol/SKILL.md
build	plugins/dev-team/skills/build/SKILL.md
quality-gate-pipeline	plugins/dev-team/skills/quality-gate-pipeline/SKILL.md
test-driven-development	plugins/dev-team/skills/test-driven-development/SKILL.md
systematic-debugging	plugins/dev-team/skills/systematic-debugging/SKILL.md
EOF
}

subject_path() {
  declare_subject_paths | awk -F'\t' -v s="$1" '$1 == s { print $2; exit }'
}

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------

require() {
  command -v "$1" >/dev/null 2>&1 || {
    printf 'oe-judge-run: missing %s — install it before running\n' "$1" >&2
    exit 2
  }
}

require jq
require python3
require claude

[ -d "$FIXTURES_DIR" ] || { printf 'oe-judge-run: %s not found\n' "$FIXTURES_DIR" >&2; exit 2; }
[ -d "$EXPECTED_DIR" ] || { printf 'oe-judge-run: %s not found\n' "$EXPECTED_DIR" >&2; exit 2; }

# ---------------------------------------------------------------------------
# Enumerate (subject × fixture) pairs from expected/*.json's `subjects` array
# ---------------------------------------------------------------------------

enumerate_pairs() {
  for exp in "$EXPECTED_DIR"/oe-*.json; do
    fixture="$(jq -r .fixture "$exp")"
    jq -r '.subjects[]' "$exp" | while read -r subject; do
      printf '%s\t%s\t%s\n' "$subject" "$fixture" "$exp"
    done
  done
}

# ---------------------------------------------------------------------------
# Judge invocation — wraps the LLM call.
#
# The judge sees:
#   - The fixture scenario (no expected/*.json — never leak the rubric to
#     the judge as instructions; we apply mustExhibit / mustNotExhibit after).
#   - The subject's current prose (the agent/skill file).
#   - The eight rubric dimensions (rubric.md, condensed).
#
# The judge returns a JSON object:
#   {
#     "behaviors_exhibited": [<one-line descriptions>],
#     "behaviors_avoided":   [<one-line descriptions>],
#     "scores": { "CW": 1-5|"N/A", ... },
#     "rationale": "<one paragraph>"
#   }
#
# We then mechanically check the expected/*.json mustExhibit / mustNotExhibit
# against behaviors_exhibited / behaviors_avoided to derive pass/fail.
# Scoring is the judge's; pass/fail is rule-based.
# ---------------------------------------------------------------------------

oe_invoke_judge() {
  local prompt_file="$1"
  if [ -n "${OE_DRY_RUN:-}" ]; then
    printf '{"behaviors_exhibited":[],"behaviors_avoided":[],"scores":{},"rationale":"DRY_RUN"}\n'
    return 0
  fi
  # Use claude -p (print/non-interactive) with the prompt on stdin. Force JSON
  # by instructing the system prompt; if the judge wraps it in markdown fences,
  # strip them.
  local raw
  raw="$(claude -p \
    --model "$JUDGE_MODEL" \
    --output-format text \
    < "$prompt_file" 2>/dev/null)" || {
    printf '{"error":"claude CLI invocation failed"}\n'
    return 1
  }
  # Strip ```json fences if present.
  printf '%s\n' "$raw" \
    | sed -E '/^```(json)?$/d' \
    | python3 -c 'import json,sys; t=sys.stdin.read().strip();
try:
    print(json.dumps(json.loads(t)))
except Exception:
    # Try to find the first { ... } block.
    import re
    m = re.search(r"\{.*\}", t, re.S)
    print(m.group(0) if m else json.dumps({"error":"non-JSON","raw":t[:500]}))'
}

build_judge_prompt() {
  local subject="$1"
  local fixture_file="$2"
  local subject_file
  subject_file="$(subject_path "$subject")"
  [ -n "$subject_file" ] || { printf 'no subject path for %s\n' "$subject" >&2; return 1; }
  [ -f "$ROOT/$subject_file" ] || { printf 'subject file missing: %s\n' "$subject_file" >&2; return 1; }

  cat <<EOF
You are grading a subject (an agent or skill prose file from a Claude Code
plugin) against an Ownership Engineering rubric and a behavioral fixture.

# Rubric (8 dimensions, score 1–5, or "N/A" if outside the subject's role)

- **CW** Clarification Window — ask everything up front in one round, then commit.
- **UA** Uncertainty Absorption — investigate to resolve unknowns; don't escalate every one.
- **CD** Committed Decisions — decide and own it (with override); don't hand over a menu.
- **ER** Evidence Over Reasoning — fresh observed output, not assertion.
- **LV** Live Validation — run the real thing; static reading isn't proof.
- **DD** Debug, Don't Stop — a failure is a debugging task, not a hand-back.
- **DC** Demonstrable Completion — done = proven working, not "code changed."
- **QO** Quality Ownership — a failing test is failure regardless of whose change caused it; own the suite, not just your delta.

# Subject under test: \`$subject\`

Prose the subject would operate under (verbatim from the repository):

\`\`\`markdown
$(cat "$ROOT/$subject_file")
\`\`\`

# Fixture scenario

\`\`\`markdown
$(cat "$fixture_file")
\`\`\`

# Your task

Reason about how the subject — given **only** its own prose — would behave in
the fixture scenario. You do NOT see a rubric of what the fixture wants; you
infer behavior directly from the subject's prose and the scenario.

Return a single JSON object with this exact shape (no markdown fences):

{
  "behaviors_exhibited": ["short noun phrase", "..."],
  "behaviors_avoided":   ["short noun phrase", "..."],
  "scores": {
    "CW": 1|2|3|4|5|"N/A",
    "UA": 1|2|3|4|5|"N/A",
    "CD": 1|2|3|4|5|"N/A",
    "ER": 1|2|3|4|5|"N/A",
    "LV": 1|2|3|4|5|"N/A",
    "DD": 1|2|3|4|5|"N/A",
    "DC": 1|2|3|4|5|"N/A",
    "QO": 1|2|3|4|5|"N/A"
  },
  "rationale": "one paragraph naming the prose lines that drove the verdict"
}

The behaviors_exhibited / behaviors_avoided lists must be specific and
falsifiable — they will be matched against a hidden mustExhibit / mustNotExhibit
list afterward. Use "N/A" only when the dimension is genuinely outside the
subject's role (e.g. ER/LV on product-manager).
EOF
}

# ---------------------------------------------------------------------------
# Per-pair grading
# ---------------------------------------------------------------------------

grade_pair() {
  local subject="$1"
  local fixture_file="$2"
  local expected_file="$3"
  local out_dir="$4"

  local fixture_name
  fixture_name="$(basename "$fixture_file" .md)"
  local out_file="$out_dir/${fixture_name}__${subject}.json"

  if [ -n "${OE_RESUME:-}" ] && [ -s "$out_file" ]; then
    printf 'SKIP  %s × %s (resumed)\n' "$fixture_name" "$subject"
    return 0
  fi

  local prompt_file
  # Full template path, not `-t` — see .husky/pre-push (issue #1993).
  prompt_file="$(mktemp "${TMPDIR:-/tmp}/oe-prompt.XXXXXX")"
  build_judge_prompt "$subject" "$fixture_file" > "$prompt_file" || {
    rm -f "$prompt_file"
    return 1
  }

  printf 'JUDGE %s × %s\n' "$fixture_name" "$subject"
  local verdict_raw
  verdict_raw="$(oe_invoke_judge "$prompt_file")"
  rm -f "$prompt_file"

  # Apply the rule-based pass/fail by comparing the judge's lists against
  # the expected mustExhibit / mustNotExhibit. The comparison uses cheap
  # case-insensitive substring matching with a small synonym expansion.
  python3 - "$expected_file" "$subject" "$fixture_name" "$out_file" <<'PY' "$verdict_raw"
import json, sys, re

expected_file = sys.argv[1]
subject       = sys.argv[2]
fixture_name  = sys.argv[3]
out_file      = sys.argv[4]
verdict_raw   = sys.argv[5]

try:
    verdict = json.loads(verdict_raw)
except Exception as e:
    verdict = {"error": f"unparseable judge output: {e}", "raw": verdict_raw[:1000]}

with open(expected_file) as f:
    expected = json.load(f)

def norm(s): return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()
def has_match(needle, haystack):
    n_words = set(norm(needle).split())
    for h in haystack:
        h_words = set(norm(h).split())
        # >=50% of needle's content words appear in this haystack item.
        if not n_words: continue
        overlap = len(n_words & h_words) / max(len(n_words), 1)
        if overlap >= 0.5: return True
    return False

exhibited = verdict.get("behaviors_exhibited", []) or []
avoided   = verdict.get("behaviors_avoided", []) or []

must_exhibit = expected.get("mustExhibit", [])
must_avoid   = expected.get("mustNotExhibit", [])

exhibit_hits = [m for m in must_exhibit if has_match(m, exhibited)]
exhibit_miss = [m for m in must_exhibit if m not in exhibit_hits]

# A mustNotExhibit fails if it shows up in exhibited (the subject exhibited it).
violation_hits = [m for m in must_avoid if has_match(m, exhibited)]

passed = (len(exhibit_miss) == 0) and (len(violation_hits) == 0)

record = {
  "fixture":    fixture_name,
  "subject":    subject,
  "passed":     passed,
  "dimensions": expected.get("dimensions", []),
  "must_exhibit_total":     len(must_exhibit),
  "must_exhibit_matched":   len(exhibit_hits),
  "must_exhibit_missing":   exhibit_miss,
  "must_not_exhibit_violated": violation_hits,
  "judge_scores": verdict.get("scores", {}),
  "judge_rationale": verdict.get("rationale", ""),
  "judge_raw_exhibited": exhibited,
  "judge_raw_avoided":   avoided,
  "judge_error": verdict.get("error"),
  "knownGap": expected.get("knownGap", False),
}

with open(out_file, "w") as f:
    json.dump(record, f, indent=2)
    f.write("\n")

flag = "PASS" if passed else "FAIL"
print(f"{flag}  {fixture_name} × {subject}  "
      f"(mE {len(exhibit_hits)}/{len(must_exhibit)}, "
      f"mNE {len(must_avoid) - len(violation_hits)}/{len(must_avoid)})")
PY
}

# ---------------------------------------------------------------------------
# Aggregation — per-subject scores derived from per-pair judge scores.
# A subject's dimension score is the mean of the judge's scores for that
# dimension across every fixture the subject appears in (rounded to nearest
# integer; "N/A" votes are excluded). Dimensions never voted on stay N/A.
# ---------------------------------------------------------------------------

aggregate_scores() {
  local run_dir="$1"
  python3 - "$run_dir" <<'PY'
import json, os, sys, statistics, csv
run_dir = sys.argv[1]

subject_dim = {}        # subject -> dim -> [scores]
subject_fixtures = {}   # subject -> [(fixture, passed)]
fixtures_seen = set()

for fname in sorted(os.listdir(run_dir)):
    if not fname.endswith(".json"): continue
    with open(os.path.join(run_dir, fname)) as f:
        r = json.load(f)
    subj = r["subject"]; fx = r["fixture"]
    fixtures_seen.add(fx)
    subject_fixtures.setdefault(subj, []).append((fx, r["passed"]))
    for dim, score in (r.get("judge_scores") or {}).items():
        if score == "N/A" or score is None: continue
        try:
            score = int(score)
        except Exception:
            continue
        if not (1 <= score <= 5): continue
        subject_dim.setdefault(subj, {}).setdefault(dim, []).append(score)

DIMS = ["CW","UA","CD","ER","LV","DD","DC","QO"]
table_rows = []
for subj in sorted(subject_dim):
    row = [subj]
    for d in DIMS:
        scores = subject_dim[subj].get(d, [])
        if not scores:
            row.append("N/A")
        else:
            row.append(str(int(round(statistics.mean(scores)))))
    # Pass/fail tally for the subject across its fixtures.
    fxs = subject_fixtures.get(subj, [])
    passes = sum(1 for _, p in fxs if p)
    row.append(f"{passes}/{len(fxs)}")
    table_rows.append(row)

# Write CSV for downstream tooling.
with open(os.path.join(run_dir, "results.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["subject"] + DIMS + ["fixtures_passed"])
    w.writerows(table_rows)

# Also emit a JSON summary for --check / --commit.
summary = {
    "fixtures_seen": sorted(fixtures_seen),
    "subjects": {
        r[0]: {d: r[i+1] for i, d in enumerate(DIMS)} | {"fixtures_passed": r[-1]}
        for r in table_rows
    },
}
with open(os.path.join(run_dir, "summary.json"), "w") as f:
    json.dump(summary, f, indent=2)
    f.write("\n")

# Print a quick human-readable table.
print("| subject | " + " | ".join(DIMS) + " | fixtures |")
print("| --- | " + " | ".join([":-:"]*len(DIMS)) + " | :-: |")
for row in table_rows:
    print("| " + " | ".join(row) + " |")
PY
}

# ---------------------------------------------------------------------------
# Mode implementations
# ---------------------------------------------------------------------------

cmd_plan() {
  printf 'Planned (subject × fixture) pairs:\n\n'
  enumerate_pairs | awk -F'\t' '{ printf "  %-30s × %s\n", $1, $2 }' | sort
  local total
  total="$(enumerate_pairs | wc -l | tr -d ' ')"
  printf '\nTotal: %s pairs. Judge model: %s.\n' "$total" "$JUDGE_MODEL"
  printf 'Estimated cost: %s judge calls.\n' "$total"
}

cmd_run() {
  local run_id="${OE_RUN_ID:-$(python3 -c 'import time; print(time.strftime("%Y-%m-%dT%H-%M-%S"))')}"
  local run_dir="$RUNS_DIR/$run_id"
  mkdir -p "$run_dir"
  printf 'Run id: %s\nOutput dir: %s\nJudge model: %s\n\n' "$run_id" "$run_dir" "$JUDGE_MODEL"

  local fail=0
  while IFS=$'\t' read -r subject fixture_name expected_file; do
    local fixture_file="$FIXTURES_DIR/$fixture_name"
    [ -f "$fixture_file" ] || {
      printf 'MISS  fixture file %s not found, skipping\n' "$fixture_file"
      fail=$((fail + 1))
      continue
    }
    grade_pair "$subject" "$fixture_file" "$expected_file" "$run_dir" || fail=$((fail + 1))
  done < <(enumerate_pairs)

  printf '\nAggregating per-subject scores:\n\n'
  aggregate_scores "$run_dir"

  # Update the convenience symlink to the latest run.
  ln -sfn "$run_id" "$RUNS_DIR/latest"
  printf '\nLatest symlink: %s -> %s\n' "$RUNS_DIR/latest" "$run_id"

  if [ "$fail" -gt 0 ]; then
    printf '\n%s pair(s) errored during the run; inspect their .json output.\n' "$fail" >&2
  fi
}

cmd_score() {
  local run_dir="$RUNS_DIR/latest"
  [ -d "$run_dir" ] || { printf 'oe-judge-run: no latest run; run --run first\n' >&2; exit 2; }
  local summary="$run_dir/summary.json"
  [ -s "$summary" ] || { printf 'oe-judge-run: no summary.json in latest run; re-run --run\n' >&2; exit 2; }

  local out="$OE_DIR/scorecard-measured.md"
  python3 - "$summary" "$run_dir" "$out" <<'PY'
import json, os, sys, time
summary_path, run_dir, out_path = sys.argv[1:4]
with open(summary_path) as f: summary = json.load(f)

DIMS = ["CW","UA","CD","ER","LV","DD","DC","QO"]

# Per-fixture pass tally.
fixture_pass = {fx: {"pass": 0, "fail": 0} for fx in summary["fixtures_seen"]}
oe08_known_gap = None
for fname in sorted(os.listdir(run_dir)):
    if not fname.endswith(".json") or fname in ("summary.json",): continue
    with open(os.path.join(run_dir, fname)) as f:
        r = json.load(f)
    bucket = fixture_pass.setdefault(r["fixture"], {"pass": 0, "fail": 0})
    bucket["pass" if r["passed"] else "fail"] += 1
    if r["fixture"].startswith("oe-08") and r["knownGap"]:
        oe08_known_gap = True

lines = [
    "# Ownership Engineering scorecard — measured re-score",
    "",
    f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
    f"Run dir: `evals/ownership-engineering/runs/{os.path.basename(run_dir)}/`",
    "",
    "**Provenance.** Each cell is the integer mean of the judge model's scores",
    "for that dimension across every fixture the subject appears in. N/A means",
    "the dimension is outside the subject's role and was never scored. The",
    "scorecard.md projected re-score is hand-authored from prose; this one is",
    "measured via judge calls and is the artifact PR #266's Definition of Done",
    "step 1 requires.",
    "",
    "## Per-subject measured scores",
    "",
    "| Subject | " + " | ".join(DIMS) + " | fixtures |",
    "| --- | " + " | ".join([":-:"]*len(DIMS)) + " | :-: |",
]
for subj in sorted(summary["subjects"]):
    row = summary["subjects"][subj]
    cells = [str(row.get(d, "N/A")) for d in DIMS]
    lines.append(f"| {subj} | " + " | ".join(cells) + f" | {row['fixtures_passed']} |")

lines += [
    "",
    "## Fixture pass/fail",
    "",
    "| Fixture | Passes | Fails |",
    "| --- | :-: | :-: |",
]
for fx in sorted(fixture_pass):
    p = fixture_pass[fx]; lines.append(f"| {fx} | {p['pass']} | {p['fail']} |")

lines += [
    "",
    "## Definition-of-Done floor",
    "",
    "- No subject below 3 on any in-role dimension.",
    "- human-oversight-protocol, product-manager, qa-engineer rows rise out of the 1–2 band.",
    "- Wave 2.3 (qa-engineer): ER ≥4, DC ≥4.",
    "- oe-08-medium-severity-escalation flips its `knownGap` sentinel off (regression sentinel).",
    "",
    "Run `bash scripts/oe-judge-run.sh --check` to assert these floors against this scorecard.",
]
with open(out_path, "w") as f:
    f.write("\n".join(lines) + "\n")
print(f"Wrote {out_path}")
PY
}

cmd_commit() {
  local measured="$OE_DIR/scorecard-measured.md"
  [ -s "$measured" ] || { printf 'oe-judge-run: no measured scorecard; run --score first\n' >&2; exit 2; }
  [ -f "$SCORECARD" ] || { printf 'oe-judge-run: %s not found\n' "$SCORECARD" >&2; exit 2; }

  cp "$SCORECARD" "$SCORECARD.bak"
  python3 - "$SCORECARD" "$measured" <<'PY'
import sys
sc_path, measured_path = sys.argv[1], sys.argv[2]
with open(sc_path) as f: text = f.read()
with open(measured_path) as f: measured = f.read()

needle = "## Re-score after implementation"
if needle not in text:
    sys.exit(f"could not find '{needle}' in {sc_path}; aborting commit")

head, _, _tail = text.partition(needle)
new = head + "## Re-score after implementation (Waves 1–3) — measured\n\n" + \
      measured.split("## Per-subject measured scores", 1)[0] + \
      "## Per-subject measured scores" + \
      measured.split("## Per-subject measured scores", 1)[1]
with open(sc_path, "w") as f: f.write(new)
print(f"Updated {sc_path} (backup at {sc_path}.bak)")
PY
}

cmd_check() {
  local run_dir="$RUNS_DIR/latest"
  [ -d "$run_dir" ] || { printf 'oe-judge-run: no latest run; run --run first\n' >&2; exit 2; }
  python3 - "$run_dir/summary.json" "$run_dir" <<'PY'
import json, os, sys
summary_path, run_dir = sys.argv[1], sys.argv[2]
with open(summary_path) as f: summary = json.load(f)

DIMS = ["CW","UA","CD","ER","LV","DD","DC","QO"]
band_rows = {"human-oversight-protocol", "product-manager", "qa-engineer"}
errors = []

for subj, row in summary["subjects"].items():
    for d in DIMS:
        v = row.get(d, "N/A")
        if v == "N/A": continue
        try: vi = int(v)
        except Exception: errors.append(f"{subj}.{d} non-integer: {v}"); continue
        if vi < 3:
            errors.append(f"{subj}.{d} = {vi} below DoD floor of 3")
        if subj in band_rows and vi < 3:
            errors.append(f"{subj}.{d} = {vi} stuck in 1-2 band (DoD requires rise)")

qa = summary["subjects"].get("qa-engineer", {})
for d, floor in [("ER", 4), ("DC", 4)]:
    v = qa.get(d, "N/A")
    if v == "N/A" or int(v) < floor:
        errors.append(f"Wave 2.3 floor breached: qa-engineer.{d} = {v} (need >= {floor})")

# oe-08 regression sentinel: every oe-08 record must be passed=true AND knownGap=false.
for fname in sorted(os.listdir(run_dir)):
    if not fname.startswith("oe-08") or not fname.endswith(".json"): continue
    if fname == "summary.json": continue
    with open(os.path.join(run_dir, fname)) as f: r = json.load(f)
    if r.get("knownGap"):
        errors.append(f"oe-08 regression: {fname} still marks knownGap=true")
    if not r.get("passed"):
        errors.append(f"oe-08 regression: {fname} failed (sentinel must stay green)")

if errors:
    print("OE judge check FAILED:")
    for e in errors: print(f"  - {e}")
    sys.exit(1)
print("OE judge check PASSED.")
PY
}

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

usage() {
  sed -n '1,55p' "$0"
}

case "${1:-}" in
  --plan)   cmd_plan ;;
  --run)    cmd_run ;;
  --score)  cmd_score ;;
  --commit) cmd_commit ;;
  --check)  cmd_check ;;
  -h|--help|"") usage ;;
  *) printf 'oe-judge-run: unknown mode %s\n' "$1" >&2; usage; exit 2 ;;
esac
