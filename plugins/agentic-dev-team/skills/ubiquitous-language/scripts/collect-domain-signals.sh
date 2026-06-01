#!/usr/bin/env bash
# collect-domain-signals.sh
# Gathers grep-based domain signals for the ubiquitous-language skill.
# Usage: bash collect-domain-signals.sh [source-root]
# Output: .plans/raw/domain-language/{class-names,enum-values,domain-events,bdd-names,validator-rules,interface-names}.txt

set -euo pipefail

ROOT="${1:-.}"
OUT=".plans/raw/domain-language"
mkdir -p "$OUT"

echo "Collecting domain signals from: $ROOT"

# ---------------------------------------------------------------------------
# Helper: grep with fallback (ignore errors on binary/missing files)
# ---------------------------------------------------------------------------
safe_grep() {
  grep -rn --include="$1" "$2" -- "$ROOT" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# Class / struct / record names from domain and application layers
# Targets directories commonly named: domain, application, app, core, model, models
# ---------------------------------------------------------------------------
echo "  → class names..."
{
  safe_grep "*.ts"   "^export (abstract )?class [A-Z][a-zA-Z]+"
  safe_grep "*.ts"   "^export (abstract )?interface [A-Z][a-zA-Z]+"
  safe_grep "*.cs"   "^\s*(public|internal|sealed|abstract) (partial )?(class|record|struct) [A-Z][a-zA-Z]+"
  safe_grep "*.java" "^public (abstract |final )?(class|interface|enum|record) [A-Z][a-zA-Z]+"
  safe_grep "*.py"   "^class [A-Z][a-zA-Z]+"
  safe_grep "*.go"   "^type [A-Z][a-zA-Z]+ struct"
  safe_grep "*.go"   "^type [A-Z][a-zA-Z]+ interface"
  safe_grep "*.rb"   "^class [A-Z][a-zA-Z]+"
} | grep -v "Test\|Spec\|Mock\|Fake\|Stub\|Builder\|Factory\|Repository\|Controller\|Handler\|Middleware\|Config\|Settings\|Helper\|Util\|Base\|Abstract\|Migration" \
  | sed 's/.*class \([A-Z][a-zA-Z]*\).*/\1/' \
  | sed 's/.*interface \([A-Z][a-zA-Z]*\).*/\1/' \
  | sed 's/.*struct \([A-Z][a-zA-Z]*\).*/\1/' \
  | sed 's/.*record \([A-Z][a-zA-Z]*\).*/\1/' \
  | sort -u > "$OUT/class-names.txt"
echo "    $(wc -l < "$OUT/class-names.txt") candidates"

# ---------------------------------------------------------------------------
# Enum declarations and their values
# ---------------------------------------------------------------------------
echo "  → enum values..."
{
  safe_grep "*.ts"   "^export (const )?enum [A-Z]"
  safe_grep "*.cs"   "^\s*(public|internal) enum [A-Z]"
  safe_grep "*.java" "^public enum [A-Z]"
  safe_grep "*.py"   "class [A-Z][a-zA-Z]*(Enum|Status|Type|State)\b"
  safe_grep "*.go"   "// [A-Z][a-zA-Z]+ (is|represents|indicates)"
} | sort -u > "$OUT/enum-values.txt"
echo "    $(wc -l < "$OUT/enum-values.txt") candidates"

# ---------------------------------------------------------------------------
# Domain event names: types ending in past-tense business verbs
# ---------------------------------------------------------------------------
echo "  → domain events..."
{
  safe_grep "*.ts"   "class [A-Z][a-zA-Z]*(Created|Updated|Submitted|Approved|Cancelled|Rejected|Completed|Failed|Requested|Issued|Revoked|Expired|Activated|Deactivated|Shipped|Delivered|Refunded|Disputed)"
  safe_grep "*.cs"   "class [A-Z][a-zA-Z]*(Created|Updated|Submitted|Approved|Cancelled|Rejected|Completed|Failed|Requested|Issued|Revoked|Expired|Activated|Deactivated|Shipped|Delivered|Refunded|Disputed)"
  safe_grep "*.java" "class [A-Z][a-zA-Z]*(Created|Updated|Submitted|Approved|Cancelled|Rejected|Completed|Failed|Requested|Issued|Revoked|Expired|Activated|Deactivated|Shipped|Delivered|Refunded|Disputed)"
  safe_grep "*.go"   "type [A-Z][a-zA-Z]*(Created|Updated|Submitted|Approved|Cancelled|Rejected|Completed|Failed|Requested|Issued|Revoked|Expired|Activated|Deactivated|Shipped|Delivered|Refunded|Disputed) struct"
} | sed 's/.*class \([A-Z][a-zA-Z]*\).*/\1/' \
  | sed 's/.*type \([A-Z][a-zA-Z]*\) struct.*/\1/' \
  | sort -u > "$OUT/domain-events.txt"
echo "    $(wc -l < "$OUT/domain-events.txt") candidates"

# ---------------------------------------------------------------------------
# BDD scenario and step names from .feature files
# ---------------------------------------------------------------------------
echo "  → BDD names..."
{
  safe_grep "*.feature" "^\s*(Scenario|Given|When|Then|And)\s"
  # Also catch xUnit/Jest test names with business-language patterns
  safe_grep "*.ts"   "it\(['\"].*['\"]"
  safe_grep "*.ts"   "describe\(['\"].*['\"]"
  safe_grep "*.cs"   "\[Fact\]|public void (Given|When|Then|Should)[A-Z]"
  safe_grep "*.java" "@Test.*\n.*void (given|when|then|should)[A-Z]"
} | sort -u > "$OUT/bdd-names.txt"
echo "    $(wc -l < "$OUT/bdd-names.txt") candidates"

# ---------------------------------------------------------------------------
# Validator rule names and error messages (business invariants expressed in validation)
# ---------------------------------------------------------------------------
echo "  → validator rules..."
{
  safe_grep "*.ts"   "\.withMessage\|\.mustBe\|\.isRequired\|z\.string\(\)\.refine\|yup\."
  safe_grep "*.cs"   "RuleFor\|\.Must\|\.WithMessage\|\.NotNull\|\.NotEmpty"
  safe_grep "*.java" "@NotNull\|@NotBlank\|@Size\|@Min\|@Max\|@Pattern\|@Valid\|@Constraint"
  safe_grep "*.py"   "raise ValueError\|raise TypeError\|assert .*, ['\"]"
} | sort -u > "$OUT/validator-rules.txt"
echo "    $(wc -l < "$OUT/validator-rules.txt") candidates"

# ---------------------------------------------------------------------------
# Interface / protocol names from domain and application layers
# ---------------------------------------------------------------------------
echo "  → interface names..."
{
  safe_grep "*.ts"   "^export interface [A-Z][a-zA-Z]+"
  safe_grep "*.cs"   "^\s*(public|internal) interface I[A-Z][a-zA-Z]+"
  safe_grep "*.java" "^public interface [A-Z][a-zA-Z]+"
  safe_grep "*.go"   "type [A-Z][a-zA-Z]+ interface"
} | grep -v "Repository\|Controller\|Handler\|Middleware\|Factory\|Builder\|Config\|Logger\|Cache\|Queue\|Bus\|Mapper\|Serializer\|Parser" \
  | sed 's/.*interface \(I\?\)\([A-Z][a-zA-Z]*\).*/\2/' \
  | sort -u > "$OUT/interface-names.txt"
echo "    $(wc -l < "$OUT/interface-names.txt") candidates"

echo ""
echo "Signal collection complete. Results in $OUT/"
echo "Total raw candidates: $(cat "$OUT"/*.txt | sort -u | wc -l)"
