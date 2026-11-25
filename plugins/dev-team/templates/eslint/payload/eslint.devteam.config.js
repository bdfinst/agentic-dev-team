// Dev-team lint rules for the checks the esm-enforcer and js-fp-review agents
// otherwise judge by reading code. Every rule is "warn", so a plain `eslint`
// run stays green; the opt-in post-edit hook is what turns findings into blocks.
//
// Import this array from your own flat config, for example:
//   import devteam from "./eslint.devteam.config.js";
//   export default [...devteam, ...yourConfig];
// Globs use forward slashes on every platform.
//
// Array-mutation checks need type information, so they run only on files your
// own `tsconfig.json` (next to this file) covers, and only when
// `eslint-plugin-functional`, `@typescript-eslint/parser` and `typescript` are
// installed. Otherwise they are skipped with one notice on stderr. Set
// `DEVTEAM_LINT_TYPED=0` to skip them silently. This file never creates or
// edits a tsconfig.

import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const SOURCE_FILES = ["**/*.{js,jsx,mjs,ts,tsx,mts}"];
const COMMONJS_FILES = ["**/*.{cjs,cts}"];

const esmReplacement = (what, instead) => `${what}. ${instead}`;

const rootDir = path.dirname(fileURLToPath(import.meta.url));

// Resolves to `{ value }`, `{ missing: true }` when `id` itself is not
// installed, or `{ failure }` when it is installed but cannot load.
const importOptional = async (id) => {
  try {
    const loaded = await import(id);
    return { value: loaded.default ?? loaded };
  } catch (error) {
    if (
      error?.code === "ERR_MODULE_NOT_FOUND" &&
      String(error.message).includes(`'${id}'`)
    ) {
      return { missing: true };
    }
    return { failure: String(error?.message ?? error).split("\n")[0] };
  }
};

// Backslash-escape every character a glob reads as syntax. A character class
// is not enough: `[!]` negates and `[{]a[,]b[}]` is still brace-expanded.
const literalGlob = (file) => file.replace(/[\\*?[\]{}()!+@]/g, "\\$&");

const isInside = (relative) =>
  relative !== ".." &&
  !relative.startsWith("../") &&
  !relative.startsWith("..\\") &&
  !path.isAbsolute(relative);

// Project-relative paths of the files the user's tsconfig.json covers.
const coveredFiles = (ts) => {
  const tsconfig = path.join(rootDir, "tsconfig.json");
  const { config, error } = ts.readConfigFile(tsconfig, ts.sys.readFile);
  if (error !== undefined) return [];
  return ts
    .parseJsonConfigFileContent(config, ts.sys, rootDir)
    .fileNames.map((file) => path.relative(rootDir, file))
    .filter(isInside)
    .map((relative) => literalGlob(relative.split(path.sep).join("/")));
};

// `functional/immutable-data` also reports property writes, `delete`,
// `Object.assign`, and Set/Map mutators. This config covers array mutators
// only, so the processor keeps that rule's array messages and drops the rest.
const arrayMutationOnly = {
  meta: { name: "devteam/array-mutation-only" },
  supportsAutofix: true,
  preprocess: (text) => [text],
  postprocess: ([messages]) =>
    messages.filter(
      ({ ruleId, messageId }) =>
        ruleId !== "functional/immutable-data" || messageId === "array",
    ),
};

// The one place that decides whether typed rules run, and for which files.
// It computes a value and reports a skipped-dependency reason as data; the
// config's export, below, is what writes the notice.
const typedSkipped = { configs: [], notice: null };
const typedConfig = async () => {
  if (process.env.DEVTEAM_LINT_TYPED === "0") return typedSkipped;
  if (!fs.existsSync(path.join(rootDir, "tsconfig.json"))) return typedSkipped;
  const ids = [
    "eslint-plugin-functional",
    "@typescript-eslint/parser",
    "typescript",
  ];
  const found = Object.fromEntries(
    await Promise.all(ids.map(async (id) => [id, await importOptional(id)])),
  );
  const missing = ids.filter((id) => found[id].missing);
  const failed = ids.filter((id) => found[id].failure !== undefined);
  if (missing.length > 0 || failed.length > 0) {
    const reasons = [
      ...(missing.length > 0 ? [`not installed: ${missing.join(", ")}`] : []),
      ...failed.map((id) => `failed to load ${id}: ${found[id].failure}`),
    ];
    return {
      configs: [],
      notice: `devteam-lint: typed rules skipped, ${reasons.join("; ")}\n`,
    };
  }
  const needed = Object.fromEntries(ids.map((id) => [id, found[id].value]));
  const files = coveredFiles(needed.typescript);
  if (files.length === 0) return typedSkipped;
  const configs = [
    {
      name: "devteam/array-mutation",
      files,
      processor: arrayMutationOnly,
      plugins: { functional: needed["eslint-plugin-functional"] },
      languageOptions: {
        parser: needed["@typescript-eslint/parser"],
        parserOptions: { projectService: true, tsconfigRootDir: rootDir },
      },
      rules: {
        "functional/immutable-data": [
          "warn",
          { ignoreAccessorPattern: ["this.**"] },
        ],
      },
    },
  ];
  return { configs, notice: null };
};

const typed = await typedConfig();
if (typed.notice !== null) process.stderr.write(typed.notice);

export default [
  {
    name: "devteam/functional-style",
    files: [...SOURCE_FILES, ...COMMONJS_FILES],
    rules: {
      "no-var": "warn",
      "prefer-const": "warn",
      "no-plusplus": ["warn", { allowForLoopAfterthoughts: true }],
      "no-param-reassign": ["warn", { props: true }],
    },
  },
  {
    name: "devteam/esm-only",
    files: SOURCE_FILES,
    ignores: COMMONJS_FILES,
    rules: {
      "no-restricted-globals": [
        "warn",
        {
          name: "__dirname",
          message: esmReplacement(
            "__dirname is CommonJS only",
            "Use import.meta.dirname or fileURLToPath(import.meta.url).",
          ),
        },
        {
          name: "__filename",
          message: esmReplacement(
            "__filename is CommonJS only",
            "Use import.meta.filename or fileURLToPath(import.meta.url).",
          ),
        },
      ],
      "no-restricted-syntax": [
        "warn",
        {
          selector: "CallExpression[callee.name='require']",
          message: esmReplacement(
            "require() is CommonJS",
            "Use ESM import/export instead of require().",
          ),
        },
        {
          selector:
            "AssignmentExpression[left.object.name='module'][left.property.name='exports']",
          message: esmReplacement(
            "module.exports is CommonJS",
            "Use ESM export instead of module.exports.",
          ),
        },
        {
          selector:
            "AssignmentExpression[left.object.object.name='module'][left.object.property.name='exports']",
          message: esmReplacement(
            "module.exports.* is CommonJS",
            "Use ESM named export instead of module.exports.",
          ),
        },
        {
          selector: "AssignmentExpression[left.object.name='exports']",
          message: esmReplacement(
            "exports.* is CommonJS",
            "Use ESM named export instead of exports.",
          ),
        },
      ],
    },
  },
  ...typed.configs,
];
