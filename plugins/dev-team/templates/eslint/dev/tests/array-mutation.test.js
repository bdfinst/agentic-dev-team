import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createRequire } from "node:module";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import test from "node:test";

import {
  ESLint,
  devDir,
  devteamConfig,
  diffPairs,
  eslintBin,
  toPairs,
} from "../lib/lint.js";
import { arrayMutationDir, stageConfig } from "../lib/stage.js";

const tsParser = createRequire(import.meta.url)("@typescript-eslint/parser");
const expected = JSON.parse(
  fs.readFileSync(path.join(arrayMutationDir, "expected.json"), "utf8"),
);
const readFixture = (rel) =>
  fs.readFileSync(path.join(arrayMutationDir, rel), "utf8");
const toCrlf = (text) => text.replace(/\r?\n/g, "\r\n");
const sortPairs = (pairs) =>
  [...pairs].sort(
    ([ruleA, lineA], [ruleB, lineB]) =>
      lineA - lineB || ruleA.localeCompare(ruleB),
  );

// A user's own config supplies the TypeScript parser for files the typed
// block does not cover; the typed block sets it for the files it does.
const eslint = new ESLint({
  cwd: arrayMutationDir,
  overrideConfigFile: true,
  overrideConfig: [
    { files: ["**/*.ts"], languageOptions: { parser: tsParser } },
    ...devteamConfig,
  ],
});

const messagesFor = async (rel, text = readFixture(rel)) => {
  const [result] = await eslint.lintText(text, {
    filePath: path.join(arrayMutationDir, rel),
  });
  return result.messages;
};
const pairsFor = async (rel, text) =>
  sortPairs(toPairs((await messagesFor(rel, text)).map(
    ({ ruleId, line }) => ({ rule: ruleId, line }),
  )));
const lineOf = (rel, needle, text = readFixture(rel)) => {
  const index = text.split(/\r?\n/).findIndex((line) => line.includes(needle));
  assert.notEqual(index, -1, `${rel} has no line containing ${needle}`);
  return index + 1;
};

const tsconfigExcludes = JSON.parse(readFixture("tsconfig.json")).exclude;

test("typed TS and JSDoc JS flag exactly the expected mutations", async () => {
  const keys = Object.keys(expected);
  const typedFiles = fs
    .readdirSync(path.join(arrayMutationDir, "typed"))
    .filter((name) => /\.(ts|js)$/.test(name))
    .map((name) => `typed/${name}`)
    .filter((rel) => !tsconfigExcludes.includes(rel));
  assert.deepEqual([...keys].sort(), [...typedFiles].sort());
  for (const rel of keys) {
    assert.deepEqual(await pairsFor(rel), sortPairs(expected[rel]), rel);
  }
});

test("a local accumulator is a finding; this.* in a class method is not", async () => {
  for (const rel of ["typed/mutators.ts", "typed/jsdoc-mutators.js"]) {
    const flagged = (await pairsFor(rel)).map(([, line]) => line);
    assert.ok(flagged.includes(lineOf(rel, "out.push(item)")), rel);
    assert.ok(!flagged.includes(lineOf(rel, "this.items.push(value)")), rel);
  }
});

test("a file the tsconfig does not cover is not reported and does not fail to parse", async () => {
  const rel = "uncovered/not-in-tsconfig.ts";
  assert.ok(readFixture(rel).includes("xs.push(1)"));
  assert.deepEqual(await messagesFor(rel), []);
});

// Each excluded file differs by one character from a covered file whose name
// holds glob syntax; a glob that over-matches would report it.
test("a file the tsconfig excludes is not matched by a glob-metacharacter sibling", async () => {
  assert.deepEqual(tsconfigExcludes, ["typed/aXb.ts", "typed/xa.ts"]);
  for (const rel of tsconfigExcludes) {
    assert.ok(readFixture(rel).includes("ids.push"), rel);
    assert.deepEqual(await messagesFor(rel), [], rel);
  }
});

test("typed files keep autofix for the other rules", async () => {
  const rel = "typed/util.ts";
  const text = `var legacy = 1;\n${readFixture(rel)}`;
  const fixer = new ESLint({
    cwd: arrayMutationDir,
    overrideConfigFile: true,
    overrideConfig: devteamConfig,
    fix: true,
  });
  const [result] = await fixer.lintText(text, {
    filePath: path.join(arrayMutationDir, rel),
  });
  assert.match(result.output ?? "", /^const legacy/);
});

test("adding a violation makes the comparison report one extra finding", async () => {
  const rel = "typed/mutators.ts";
  const added = `${readFixture(rel)}\nexport function added(xs: number[]): void {\n  xs.push(9);\n}\n`;
  const { extra, missing } = diffPairs(
    await pairsFor(rel, added),
    expected[rel],
  );
  assert.deepEqual(extra, [
    ["functional/immutable-data", lineOf(rel, "xs.push(9)", added)],
  ]);
  assert.deepEqual(missing, []);
});

// util.ts is committed in lower case; if "Util.ts" resolves, the file system
// that holds the fixtures ignores case.
const caseInsensitive = () =>
  fs.existsSync(path.join(arrayMutationDir, "typed", "Util.ts"));

test(
  "a mis-cased import reports no false finding and no parse error",
  { skip: caseInsensitive() ? "case-insensitive file system" : false },
  async () => {
    const rel = "typed/mis-cased.ts";
    assert.ok(readFixture(rel).includes('"./Util"'));
    const messages = await messagesFor(rel);
    assert.ok(messages.every((message) => !message.fatal));
    assert.deepEqual(await pairsFor(rel), sortPairs(expected[rel]));
  },
);

test("CRLF array-mutation fixtures match LF", async () => {
  for (const rel of ["typed/mutators.ts", "typed/jsdoc-mutators.js"]) {
    assert.deepEqual(
      await pairsFor(rel, toCrlf(readFixture(rel))),
      sortPairs(expected[rel]),
      rel,
    );
  }
});

// Runs the ESLint CLI. `report` parses stdout only when read, so a failed run
// surfaces its status and stderr rather than a JSON syntax error.
const runCli = ({ dir, config, file, env = {} }) => {
  const inherited = { ...process.env };
  delete inherited.DEVTEAM_LINT_TYPED;
  const run = spawnSync(
    process.execPath,
    [eslintBin, "--config", config, "--format", "json", file],
    {
      cwd: dir,
      encoding: "utf8",
      env: { ...inherited, ...env },
      timeout: 60_000,
    },
  );
  assert.equal(run.error, undefined, `eslint did not run: ${run.error}`);
  return {
    status: run.status,
    stderr: run.stderr,
    get report() {
      try {
        return JSON.parse(run.stdout);
      } catch {
        throw new Error(
          `eslint printed no JSON (status ${run.status}): ${run.stderr}`,
        );
      }
    },
  };
};

const messagePairs = (run) =>
  sortPairs(run.report.flatMap(({ messages }) =>
    messages.map(({ ruleId, line }) => [ruleId, line]),
  ));

test("typed mode keeps stdout parseable JSON and prints no notice", () => {
  const config = stageConfig(arrayMutationDir);
  const run = runCli({
    dir: arrayMutationDir,
    config,
    file: "typed/mutators.ts",
  });
  assert.equal(run.status, 0, run.stderr);
  assert.equal(run.stderr, "");
  assert.deepEqual(messagePairs(run), sortPairs(expected["typed/mutators.ts"]));
});

test("DEVTEAM_LINT_TYPED=0 skips the typed rules silently", () => {
  const run = runCli({
    dir: arrayMutationDir,
    config: stageConfig(arrayMutationDir),
    file: "typed/jsdoc-mutators.js",
    env: { DEVTEAM_LINT_TYPED: "0" },
  });
  assert.equal(run.status, 0, run.stderr);
  assert.equal(run.stderr, "");
  assert.deepEqual(run.report[0].messages, []);
});

// A throwaway project directory. It resolves the dev tree's dependencies
// unless `files` supplies its own `node_modules/`.
const withTempProject = (files, body) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "devteam-project-"));
  try {
    if (!Object.keys(files).some((name) => name.startsWith("node_modules/"))) {
      fs.symlinkSync(
        path.join(devDir, "node_modules"),
        path.join(dir, "node_modules"),
        "junction",
      );
    }
    for (const [name, content] of Object.entries(files)) {
      fs.mkdirSync(path.dirname(path.join(dir, name)), { recursive: true });
      fs.writeFileSync(path.join(dir, name), content);
    }
    return body({ dir, config: stageConfig(dir) });
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
};

const PUSH_SOURCE = "export function f(xs: number[]): void {\n  xs.push(1);\n}\n";
const TS_INCLUDE = (include) =>
  JSON.stringify({
    compilerOptions: { strict: true, noEmit: true },
    include,
  });

test("a covered root file whose name starts with two dots is still linted", () => {
  withTempProject(
    { "tsconfig.json": TS_INCLUDE(["..dots.ts"]), "..dots.ts": PUSH_SOURCE },
    ({ dir, config }) => {
      const run = runCli({ dir, config, file: "..dots.ts" });
      assert.equal(run.status, 0, run.stderr);
      assert.deepEqual(
        run.report[0].messages.map(({ ruleId, line }) => [ruleId, line]),
        [["functional/immutable-data", 2]],
      );
    },
  );
});

test("absent typed dependencies print one stderr notice and keep stdout parseable", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "devteam-nodeps-"));
  try {
    fs.writeFileSync(path.join(dir, "tsconfig.json"), "{}\n");
    fs.writeFileSync(path.join(dir, "a.js"), "export const a = 1;\n");
    const config = path.join(dir, "eslint.devteam.config.js");
    fs.copyFileSync(stageConfig(arrayMutationDir), config);
    const run = runCli({ dir, config, file: "a.js" });
    assert.equal(run.status, 0, run.stderr);
    assert.deepEqual(run.report[0].messages, []);
    assert.equal(run.stderr.match(/devteam-lint/g)?.length, 1, run.stderr);
    assert.match(run.stderr, /eslint-plugin-functional/);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

// Each of these leaves the typed rules off with no notice and no finding, even
// though every typed dependency is installed.
const SKIPPED_PROJECTS = {
  "no tsconfig.json": {},
  "a tsconfig with only references": {
    "tsconfig.json": '{"references":[]}\n',
  },
  "an unparseable tsconfig": { "tsconfig.json": "{ not json" },
};

for (const [name, tsconfig] of Object.entries(SKIPPED_PROJECTS)) {
  test(`${name} skips the typed rules silently`, () => {
    withTempProject(
      { ...tsconfig, "a.js": "export const a = 1;\n" },
      ({ dir, config }) => {
        const run = runCli({ dir, config, file: "a.js" });
        assert.equal(run.status, 0, run.stderr);
        assert.equal(run.stderr, "");
        assert.deepEqual(run.report[0].messages, []);
      },
    );
  });
}

// A dependency that is installed but fails to load must be reported as such,
// not as "not installed".
const brokenFunctionalPlugin = (source) => ({
  "tsconfig.json": TS_INCLUDE(["*.ts"]),
  "a.ts": "export const a = 1;\n",
  "node_modules/eslint-plugin-functional/package.json": JSON.stringify({
    name: "eslint-plugin-functional",
    type: "module",
    main: "index.js",
  }),
  "node_modules/eslint-plugin-functional/index.js": source,
});

test("a typed dependency that throws on load is reported as a load failure", () => {
  withTempProject(
    brokenFunctionalPlugin('throw new Error("boom in plugin");\n'),
    ({ dir, config }) => {
      const run = runCli({ dir, config, file: "a.ts" });
      assert.match(run.stderr, /failed to load eslint-plugin-functional: boom in plugin/);
      assert.doesNotMatch(run.stderr, /not installed: [^;\n]*eslint-plugin-functional/);
    },
  );
});

test("a typed dependency whose own import is missing is a load failure, not 'not installed'", () => {
  withTempProject(
    brokenFunctionalPlugin('import "devteam-no-such-dependency";\n'),
    ({ dir, config }) => {
      const run = runCli({ dir, config, file: "a.ts" });
      assert.match(run.stderr, /failed to load eslint-plugin-functional: .*devteam-no-such-dependency/);
      assert.doesNotMatch(run.stderr, /not installed: [^;\n]*eslint-plugin-functional/);
    },
  );
});

const UNTYPED = "untyped/mutators.js";
const manifest = JSON.parse(readFixture("untyped/expected-misses.json"));

// Sites the fixture marks `// miss: <case>`: real array mutations that the
// untyped config cannot see, grouped by case.
const markedMisses = () =>
  readFixture(UNTYPED)
    .split(/\r?\n/)
    .flatMap((text, index) => {
      const marker = text.match(/\/\/ miss: (\S+)$/);
      return marker ? [[marker[1], index + 1]] : [];
    })
    .reduce(
      (cases, [name, line]) => ({
        ...cases,
        [name]: [...(cases[name] ?? []), line],
      }),
      {},
    );

test("untyped JS reports nothing, and its unreported mutations equal the manifest", async () => {
  assert.equal(manifest.file, UNTYPED);
  assert.deepEqual(await messagesFor(UNTYPED), []);
  assert.deepEqual(markedMisses(), manifest.cases);
});

// The README lists each untyped limit as "- `<case>`: ..." under one heading.
const readmeCases = (readme) => {
  const section = readme.split(/^## /m).find((part) =>
    part.startsWith("Untyped JavaScript limits"),
  );
  assert.ok(section, "README has no 'Untyped JavaScript limits' section");
  return [...section.matchAll(/^- `([^`]+)`:/gm)].map(([, name]) => name);
};

test("the README lists the same untyped misses as the manifest", () => {
  const readme = fs.readFileSync(path.join(devDir, "..", "README.md"), "utf8");
  assert.deepEqual(
    readmeCases(readme).sort(),
    Object.keys(manifest.cases).sort(),
  );
});
