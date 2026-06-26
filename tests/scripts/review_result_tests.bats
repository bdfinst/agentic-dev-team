#!/usr/bin/env bats
# Tests for scripts/lib/review_result.py — shared review output helper

HELPER="$BATS_TEST_DIRNAME/../../scripts/lib/review_result.py"

call_helper() {
  python3 -c "
import sys, json
sys.path.insert(0, '$BATS_TEST_DIRNAME/../../scripts')
from lib.review_result import build_result, main_exit

errors   = json.loads(sys.argv[1])
warnings = json.loads(sys.argv[2])
result   = build_result(errors, warnings)
sys.exit(main_exit(result))
" "$@"
}

ERR='[{"severity":"error","confidence":"high","file":"a.md","line":1,"message":"bad","suggestedFix":""}]'
WARN='[{"severity":"warning","confidence":"medium","file":"b.md","line":2,"message":"meh","suggestedFix":""}]'
NONE='[]'

@test "build_result with errors: exit 1 and status=fail" {
  run call_helper "$ERR" "$NONE"
  [ "$status" -eq 1 ]
  echo "$output" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['status']=='fail', d"
}

@test "build_result with warnings only: exit 2 and status=warn" {
  run call_helper "$NONE" "$WARN"
  [ "$status" -eq 2 ]
  echo "$output" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['status']=='warn', d"
}

@test "build_result with no issues: exit 0 and status=pass" {
  run call_helper "$NONE" "$NONE"
  [ "$status" -eq 0 ]
  echo "$output" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['status']=='pass', d"
}

@test "stdout is valid JSON containing issues array and summary field" {
  run call_helper "$ERR" "$NONE"
  echo "$output" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert 'status' in d
assert 'issues' in d
assert isinstance(d['issues'], list)
assert 'summary' in d
"
}

@test "errors take precedence over warnings: exit 1 when both present" {
  run call_helper "$ERR" "$WARN"
  [ "$status" -eq 1 ]
  echo "$output" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['status']=='fail', d"
}

@test "issues list contains both errors and warnings" {
  run call_helper "$ERR" "$WARN"
  echo "$output" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert len(d['issues']) == 2, d['issues']
severities = {i['severity'] for i in d['issues']}
assert 'error' in severities
assert 'warning' in severities
"
}
