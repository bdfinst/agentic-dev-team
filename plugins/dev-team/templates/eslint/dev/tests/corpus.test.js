import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

import { ruleFound } from "../lib/corpus.js";
import { devDir, repoRoot } from "../lib/lint.js";

const readJson = (...parts) =>
  JSON.parse(fs.readFileSync(path.join(...parts), "utf8"));

const agentFound = readJson(devDir, "corpus", "agent-found.json").findings;

// A stability guard, not a spec: it fails whenever the config's findings on the
// corpus change, so the comparison in MEASUREMENTS.md is re-run on purpose.
test("committed rule-found.json matches what the config reports now", async () => {
  assert.deepEqual(
    await ruleFound(),
    readJson(devDir, "corpus", "rule-found.json"),
    "rule-found.json is stale; regenerate with `node lib/corpus.js > corpus/rule-found.json` in the dev directory, then re-run lint_corpus_compare.py",
  );
});

test("every agent-found case points at a non-blank source line", () => {
  for (const { file, line } of agentFound) {
    const lines = fs
      .readFileSync(path.join(repoRoot, file), "utf8")
      .split("\n");
    assert.ok(lines[line - 1]?.trim(), `${file}:${line} is blank or missing`);
  }
});

test("agent-found cases per eval fixture fit the committed issue-count range", () => {
  const evalFiles = [
    ...new Set(
      agentFound.map(({ file }) => file).filter((f) => f.startsWith("evals/")),
    ),
  ];
  assert.ok(evalFiles.length > 0);
  for (const file of evalFiles) {
    const stem = path.basename(file, ".ts");
    const spec = readJson(repoRoot, "evals", "expected", `${stem}.json`).agents[
      "js-fp-review"
    ];
    const count = agentFound.filter((f) => f.file === file).length;
    assert.equal(spec.expectedStatus, "fail", file);
    assert.ok(
      count >= spec.issueCount.min && count <= spec.issueCount.max,
      `${file}: ${count} not in ${spec.issueCount.min}-${spec.issueCount.max}`,
    );
  }
});
