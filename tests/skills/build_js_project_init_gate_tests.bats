#!/usr/bin/env bats
# #251 — /build must gate on a JS bootstrap step (Step 1.5) that invokes
# js-project-init when a JS-flavored plan has no package.json, and skips
# silently otherwise. Documentation gate over the skill prose.

BUILD="$BATS_TEST_DIRNAME/../../plugins/dev-team/skills/build/SKILL.md"

@test "Step 1.5 is documented as a heading" {
  grep -qE '^### 1\.5\. ' "$BUILD"
}

@test "Step 1.5 sits between 'Find the plan' (Step 1) and 'Verify plan status' (Step 2)" {
  step1=$(grep -n '^### 1\. ' "$BUILD" | head -1 | cut -d: -f1)
  step15=$(grep -n '^### 1\.5\. ' "$BUILD" | head -1 | cut -d: -f1)
  step2=$(grep -n '^### 2\. ' "$BUILD" | head -1 | cut -d: -f1)
  [ -n "$step1" ] && [ -n "$step15" ] && [ -n "$step2" ]
  [ "$step1" -lt "$step15" ]
  [ "$step15" -lt "$step2" ]
}

@test "gate checks for package.json" {
  grep -q 'package.json' "$BUILD"
}

@test "gate enumerates JS/TS signals" {
  section=$(awk '/^### 1\.5\. /{f=1;next} /^### 2\. /{f=0} f' "$BUILD")
  for sig in '.js' '.mjs' '.ts' '.jsx' '.tsx' 'node' 'npm' 'vitest' 'jest' 'eslint'; do
    echo "$section" | grep -qF "$sig"
  done
}

@test "gate invokes js-project-init when bootstrapping" {
  section=$(awk '/^### 1\.5\. /{f=1;next} /^### 2\. /{f=0} f' "$BUILD")
  echo "$section" | grep -q 'js-project-init'
}

@test "gate skips silently when package.json exists or plan is non-JS" {
  section=$(awk '/^### 1\.5\. /{f=1;next} /^### 2\. /{f=0} f' "$BUILD")
  echo "$section" | grep -qi 'skip this gate silently'
}

@test "gate emits exactly one notice line before bootstrapping" {
  section=$(awk '/^### 1\.5\. /{f=1;next} /^### 2\. /{f=0} f' "$BUILD")
  echo "$section" | grep -qi 'one line'
}

@test "gate halts /build when js-project-init fails" {
  section=$(awk '/^### 1\.5\. /{f=1;next} /^### 2\. /{f=0} f' "$BUILD")
  echo "$section" | grep -qiE 'halt|stop'
  echo "$section" | grep -qi 'fail'
}
