// Dev-team lint rules for the checks the esm-enforcer and js-fp-review agents
// otherwise judge by reading code. Every rule is "warn", so a plain `eslint`
// run stays green; the opt-in post-edit hook is what turns findings into blocks.
//
// Import this array from your own flat config, for example:
//   import devteam from "./eslint.devteam.config.js";
//   export default [...yourConfig, ...devteam];
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

const importOptional = async (id) => {
  try {
    const loaded = await import(id);
    return loaded.default ?? loaded;
  } catch {
    return undefined;
  }
};

// Characters a glob would read as syntax, wrapped in a class so no backslash is needed.
const literalGlob = (file) => file.replace(/[*?[\]{}()!+@]/g, "[$&]");

// Project-relative paths of the files the user's tsconfig.json covers.
const coveredFiles = (ts) => {
  const tsconfig = path.join(rootDir, "tsconfig.json");
  const { config, error } = ts.readConfigFile(tsconfig, ts.sys.readFile);
  if (error !== undefined) return [];
  return ts
    .parseJsonConfigFileContent(config, ts.sys, rootDir)
    .fileNames.map((file) => path.relative(rootDir, file).split(path.sep).join("/"))
    .filter((relative) => !relative.startsWith(".."))
    .map(literalGlob);
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
const typedConfig = async () => {
  if (process.env.DEVTEAM_LINT_TYPED === "0") return [];
  if (!fs.existsSync(path.join(rootDir, "tsconfig.json"))) return [];
  const needed = {
    "eslint-plugin-functional": await importOptional("eslint-plugin-functional"),
    "@typescript-eslint/parser": await importOptional("@typescript-eslint/parser"),
    typescript: await importOptional("typescript"),
  };
  const missing = Object.keys(needed).filter((id) => needed[id] === undefined);
  if (missing.length > 0) {
    process.stderr.write(
      `devteam-lint: typed rules skipped, not installed: ${missing.join(", ")}\n`,
    );
    return [];
  }
  const files = coveredFiles(needed.typescript);
  if (files.length === 0) return [];
  return [
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
};

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
  ...(await typedConfig()),
];
