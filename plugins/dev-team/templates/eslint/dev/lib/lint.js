// Shared helpers for the dev-team ESLint template tests and the corpus runner.
//
// ESLint resolves from `DEVTEAM_ESLINT_ROOT` (a directory with `node_modules`)
// when set, else from this dev tree, falling back to the repo root. That one
// switch lets the same tests run under ESLint 9 and 10.
import { createRequire } from "node:module";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { arrayMutationDir, loadStagedConfig, payloadConfig } from "./stage.js";

export const devDir = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
export const repoRoot = path.resolve(devDir, "../../../../..");
export const configPath = payloadConfig;

const eslintRequire = createRequire(
  path.join(process.env.DEVTEAM_ESLINT_ROOT ?? devDir, "resolve.js"),
);
export const { ESLint } = eslintRequire("eslint");
const eslintPackage = eslintRequire.resolve("eslint/package.json");

export const eslintVersion = eslintRequire("eslint/package.json").version;
export const eslintBin = path.join(
  path.dirname(eslintPackage),
  "bin",
  "eslint.js",
);

const tsParser = createRequire(import.meta.url)("@typescript-eslint/parser");

/** The shipped config as it loads beside the array-mutation fixtures' tsconfig. */
export const devteamConfig = await loadStagedConfig(arrayMutationDir);

/** The shipped config plus the TypeScript parser the user's own config would supply. */
export const devteamWithTypeScript = [
  ...devteamConfig,
  { files: ["**/*.ts"], languageOptions: { parser: tsParser } },
];

export const createESLint = () =>
  new ESLint({
    cwd: repoRoot,
    overrideConfigFile: true,
    overrideConfig: devteamWithTypeScript,
  });

export const relativeToRepo = (absolute) =>
  path.relative(repoRoot, absolute).split(path.sep).join("/");

/** Flatten ESLint results into `{ rule, file, line, severity }`, failing on parse errors. */
export const toFindings = (results) =>
  results.flatMap((result) =>
    result.messages.map((message) => {
      if (message.ruleId === null) {
        throw new Error(
          `${relativeToRepo(result.filePath)}:${message.line} ${message.message}`,
        );
      }
      return {
        rule: message.ruleId,
        file: relativeToRepo(result.filePath),
        line: message.line,
        severity: message.severity,
      };
    }),
  );

export const compareFindings = (a, b) =>
  a.file.localeCompare(b.file) ||
  a.line - b.line ||
  a.rule.localeCompare(b.rule);

export const lintFiles = async (files) =>
  toFindings(await createESLint().lintFiles(files)).sort(compareFindings);

export const lintText = async (text, filePath) =>
  toFindings(await createESLint().lintText(text, { filePath })).sort(
    compareFindings,
  );

/** `[ruleId, line]` pairs, sorted, for one file's findings. */
export const toPairs = (findings) =>
  findings.map(({ rule, line }) => [rule, line]);

const pairKey = ([rule, line]) => `${rule}:${line}`;

/** Pairs present in only one of the two lists. Empty when the sets are equal. */
export const diffPairs = (actual, expected) => {
  const actualKeys = new Set(actual.map(pairKey));
  const expectedKeys = new Set(expected.map(pairKey));
  return {
    extra: actual.filter((pair) => !expectedKeys.has(pairKey(pair))),
    missing: expected.filter((pair) => !actualKeys.has(pairKey(pair))),
  };
};
