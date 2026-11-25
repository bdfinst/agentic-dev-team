// The comparison corpus: the js-fp-review eval fixtures plus small dev cases
// written from the agents' Detect text. Run directly to print the findings the
// dev-team config reports on it, as JSON for lint_corpus_compare.py.
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { devDir, lintFiles, repoRoot } from "./lint.js";

const EVAL_FIXTURES = "evals/fixtures";
const DEV_CORPUS = path
  .relative(repoRoot, path.join(devDir, "corpus"))
  .split(path.sep)
  .join("/");

const listed = (dir, keep) =>
  fs
    .readdirSync(path.join(repoRoot, dir))
    .filter(keep)
    .sort()
    .map((name) => `${dir}/${name}`);

export const corpusFiles = () => [
  ...listed(EVAL_FIXTURES, (name) => /^fp-.*\.ts$/.test(name)),
  ...listed(DEV_CORPUS, (name) => /\.(js|cjs|ts)$/.test(name)),
];

/** Findings as `{ rule, file, line }`, the shape lint_corpus_compare.py reads. */
export const ruleFound = async () =>
  (await lintFiles(corpusFiles())).map(({ rule, file, line }) => ({
    rule,
    file,
    line,
  }));

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  process.stdout.write(`${JSON.stringify(await ruleFound(), null, 2)}\n`);
}
