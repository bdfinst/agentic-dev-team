import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import test from "node:test";

import devteamConfig from "../../payload/eslint.devteam.config.js";
import {
  configPath,
  createESLint,
  devDir,
  diffPairs,
  eslintBin,
  eslintVersion,
  lintText,
  repoRoot,
  toPairs,
} from "../lib/lint.js";

const fixturesDir = path.join(devDir, "fixtures");
const expected = JSON.parse(
  fs.readFileSync(path.join(fixturesDir, "expected.json"), "utf8"),
);
const readFixture = (name) =>
  fs.readFileSync(path.join(fixturesDir, name), "utf8");
const toCrlf = (text) => text.replace(/\r?\n/g, "\r\n");
const lintFixture = (name, text = readFixture(name)) =>
  lintText(text, path.join(fixturesDir, name));

test(`runs under ESLint ${eslintVersion}`, () => {
  assert.match(eslintVersion, /^(9|10)\./);
});

test("violating fixture yields exactly the expected findings", async () => {
  const actual = toPairs(await lintFixture("violating.js"));
  assert.deepEqual(diffPairs(actual, expected["violating.js"]), {
    extra: [],
    missing: [],
  });
});

test("a non-empty clean control yields nothing", async () => {
  assert.ok(readFixture("clean.js").trim().length > 0);
  assert.deepEqual(await lintFixture("clean.js"), []);
});

test("lookalike identifiers are not flagged", async () => {
  assert.ok(readFixture("lookalikes.js").includes("module.exports"));
  assert.deepEqual(await lintFixture("lookalikes.js"), []);
});

test("CRLF fixtures match LF", async () => {
  for (const name of ["violating.js", "clean.js", "lookalikes.js"]) {
    const lf = toPairs(await lintFixture(name));
    const crlf = toPairs(await lintFixture(name, toCrlf(readFixture(name))));
    assert.deepEqual(crlf, lf, name);
  }
});

test("advisory severity keeps plain eslint green", () => {
  const run = spawnSync(
    process.execPath,
    [
      eslintBin,
      "--config",
      configPath,
      "--format",
      "json",
      path.join(fixturesDir, "violating.js"),
    ],
    { cwd: repoRoot, encoding: "utf8" },
  );
  const messages = JSON.parse(run.stdout).flatMap((r) => r.messages);
  assert.ok(messages.length > 0);
  assert.deepEqual([...new Set(messages.map((m) => m.severity))], [1]);
  assert.equal(run.status, 0, run.stderr);
});

test("config globs use forward slashes only", () => {
  const patterns = devteamConfig
    .flatMap((entry) => [...(entry.files ?? []), ...(entry.ignores ?? [])])
    .flat();
  assert.ok(patterns.length > 0);
  for (const pattern of patterns) {
    assert.ok(!pattern.includes("\\"), `backslash in glob ${pattern}`);
  }
});

const enabledRuleIds = (config) =>
  new Set(
    config.flatMap((entry) =>
      Object.entries(entry.rules ?? {})
        .filter(([, setting]) => ![0, "off"].includes([setting].flat()[0]))
        .map(([id]) => id),
    ),
  );

test("config and rule-ids.json agree", () => {
  const { enabled } = JSON.parse(
    fs.readFileSync(path.join(devDir, "rule-ids.json"), "utf8"),
  );
  assert.deepEqual(enabledRuleIds(devteamConfig), new Set(enabled));
});

test("every enabled rule is severity warn", () => {
  for (const entry of devteamConfig) {
    for (const [id, setting] of Object.entries(entry.rules ?? {})) {
      assert.ok(["warn", 1].includes([setting].flat()[0]), id);
    }
  }
});

test("an added violation makes the comparison report one extra finding", async () => {
  const mutated = `${readFixture("violating.js")}var added = 1;\n`;
  const actual = toPairs(await lintFixture("violating.js", mutated));
  const { extra, missing } = diffPairs(actual, expected["violating.js"]);
  assert.equal(extra.length, 1);
  assert.equal(extra[0][0], "no-var");
  assert.deepEqual(missing, []);
});

test("messages name the replacement", async () => {
  const [result] = await createESLint().lintText(readFixture("violating.js"), {
    filePath: path.join(fixturesDir, "violating.js"),
  });
  const cjs = result.messages.filter((m) =>
    ["no-restricted-syntax", "no-restricted-globals"].includes(m.ruleId),
  );
  assert.ok(cjs.length > 0);
  for (const message of cjs) {
    assert.match(message.message, /import|export/, message.message);
  }
});
