// Per-file lint latency, typed versus untyped, as a post-edit hook would pay it:
// one fresh `node eslint.js` process per file. Prints a Markdown table.
//
//   node lib/time-lint.js [runs]
import { spawnSync } from "node:child_process";
import os from "node:os";
import process from "node:process";

import { eslintBin, eslintVersion } from "./lint.js";
import { arrayMutationDir, stageConfig } from "./stage.js";

const RUNS = Number(process.argv[2] ?? 15);
const WARMUP = 2;
const config = stageConfig(arrayMutationDir);

const CASES = [
  { label: "typed, rule runs", file: "typed/jsdoc-mutators.js", env: {} },
  { label: "typed, rule runs", file: "typed/mutators.ts", env: {} },
  {
    label: "untyped, DEVTEAM_LINT_TYPED=0",
    file: "typed/jsdoc-mutators.js",
    env: { DEVTEAM_LINT_TYPED: "0" },
  },
  { label: "untyped file, typed deps installed", file: "untyped/mutators.js", env: {} },
];

const timeLintRun = ({ file, env }) => {
  const started = process.hrtime.bigint();
  const run = spawnSync(
    process.execPath,
    [eslintBin, "--config", config, "--format", "json", file],
    {
      cwd: arrayMutationDir,
      encoding: "utf8",
      env: { ...process.env, ...env },
    },
  );
  if (run.status !== 0) throw new Error(`${file}: ${run.stderr}`);
  return Number(process.hrtime.bigint() - started) / 1e6;
};

const percentile = (sorted, p) =>
  sorted[Math.min(sorted.length - 1, Math.ceil(p * sorted.length) - 1)];
const seconds = (ms) => (ms / 1000).toFixed(2);

const rows = CASES.map((entry) => {
  Array.from({ length: WARMUP }, () => timeLintRun(entry));
  const times = Array.from({ length: RUNS }, () => timeLintRun(entry)).sort(
    (a, b) => a - b,
  );
  return `| ${entry.label} | \`${entry.file}\` | ${seconds(percentile(times, 0.5))} | ${seconds(percentile(times, 0.95))} | ${seconds(times[0])} | ${seconds(times.at(-1))} |`;
});

process.stdout.write(
  [
    `ESLint ${eslintVersion}, Node ${process.version}, ${os.type()} ${os.release()} ${os.arch()}, ${RUNS} runs per file after ${WARMUP} warm-up runs`,
    "",
    "| Mode | File | p50 (s) | p95 (s) | min (s) | max (s) |",
    "| --- | --- | --- | --- | --- | --- |",
    ...rows,
    "",
  ].join("\n"),
);
