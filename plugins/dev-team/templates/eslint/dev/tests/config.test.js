import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import test from "node:test";

import {
  configPath,
  createESLint,
  devDir,
  devteamConfig,
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

const sortPairs = (pairs) =>
  [...pairs].sort(([ruleA, lineA], [ruleB, lineB]) =>
    lineA - lineB || ruleA.localeCompare(ruleB),
  );

// A stability guard, not a spec: `fixtures/expected.json` is a hand-kept list of
// every flagged line in `fixtures/violating.js`. Edit it with the fixture.
test("violating fixture yields exactly the expected findings", async () => {
  const actual = sortPairs(toPairs(await lintFixture("violating.js")));
  assert.deepEqual(
    actual,
    sortPairs(expected["violating.js"]),
    "findings on fixtures/violating.js differ from fixtures/expected.json; update expected.json by hand with the fixture",
  );
});

test("a non-empty clean control yields nothing", async () => {
  assert.ok(readFixture("clean.js").trim().length > 0);
  assert.deepEqual(await lintFixture("clean.js"), []);
});

test("lookalike identifiers are not flagged", async () => {
  assert.ok(readFixture("lookalikes.js").includes("module.exports"));
  assert.deepEqual(await lintFixture("lookalikes.js"), []);
});

// A selector cannot see scope, so a local binding named `require` that is
// CALLED is flagged. This pins that documented false positive.
test("a createRequire binding named require is flagged (documented false positive)", async () => {
  const text = [
    'import { createRequire } from "node:module";',
    "const require = createRequire(import.meta.url);",
    'const pkg = require("./package.json");',
    "export { pkg };",
    "",
  ].join("\n");
  const findings = await lintText(text, path.join(fixturesDir, "scoped.js"));
  assert.deepEqual(toPairs(findings), [["no-restricted-syntax", 3]]);
});

const CJS_TEXT = [
  "module.exports = { here: __dirname };",
  'const fs = require("node:fs");',
  "",
].join("\n");
const restricted = (findings) =>
  findings.filter(({ rule }) => rule.startsWith("no-restricted-"));

test(".cjs files are exempt from the ESM-only rules", async () => {
  assert.deepEqual(
    restricted(await lintText(CJS_TEXT, path.join(fixturesDir, "x.cjs"))),
    [],
  );
});

test("the same CommonJS text in a .js file is flagged", async () => {
  assert.deepEqual(
    toPairs(restricted(await lintText(CJS_TEXT, path.join(fixturesDir, "x.js")))),
    [
      ["no-restricted-globals", 1],
      ["no-restricted-syntax", 1],
      ["no-restricted-syntax", 2],
    ],
  );
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
    fs.readFileSync(path.join(devDir, "..", "rule-ids.json"), "utf8"),
  );
  assert.deepEqual(enabledRuleIds(devteamConfig), new Set(enabled));
});

test("every enabled rule is severity warn", () => {
  const settings = devteamConfig
    .flatMap((entry) => Object.entries(entry.rules ?? {}))
    .filter(([, setting]) => ![0, "off"].includes([setting].flat()[0]));
  assert.ok(settings.length > 0, "no enabled rules found");
  for (const [id, setting] of settings) {
    assert.ok(["warn", 1].includes([setting].flat()[0]), id);
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

// Each restricted message starts with what it found and ends with the
// replacement the user should write. Keyed by the message's opening words.
const REPLACEMENT_BY_MESSAGE = {
  "require() is CommonJS": "Use ESM import/export instead of require()",
  "module.exports is CommonJS": "Use ESM export instead of module.exports",
  "module.exports.* is CommonJS":
    "Use ESM named export instead of module.exports",
  "exports.* is CommonJS": "Use ESM named export instead of exports",
  "__dirname is CommonJS only": "Use import.meta.dirname",
  "__filename is CommonJS only": "Use import.meta.filename",
};

test("messages name the replacement", async () => {
  const [result] = await createESLint().lintText(readFixture("violating.js"), {
    filePath: path.join(fixturesDir, "violating.js"),
  });
  const cjs = result.messages.filter((m) =>
    ["no-restricted-syntax", "no-restricted-globals"].includes(m.ruleId),
  );
  const seen = new Set();
  for (const { message: raw } of cjs) {
    // no-restricted-globals prefixes its own "Unexpected use of '<name>'. ".
    const message = raw.replace(/^Unexpected use of '[^']+'\. /, "");
    const key = Object.keys(REPLACEMENT_BY_MESSAGE).find((opening) =>
      message.startsWith(`${opening}.`),
    );
    assert.ok(key, `no replacement phrase registered for: ${message}`);
    assert.ok(
      message.includes(REPLACEMENT_BY_MESSAGE[key]),
      `${message} lacks "${REPLACEMENT_BY_MESSAGE[key]}"`,
    );
    seen.add(key);
  }
  assert.deepEqual([...seen].sort(), Object.keys(REPLACEMENT_BY_MESSAGE).sort());
});
