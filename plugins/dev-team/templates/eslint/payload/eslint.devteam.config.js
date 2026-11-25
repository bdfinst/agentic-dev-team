// Dev-team lint rules for the checks the esm-enforcer and js-fp-review agents
// otherwise judge by reading code. Every rule is "warn", so a plain `eslint`
// run stays green; the opt-in post-edit hook is what turns findings into blocks.
//
// Import this array from your own flat config, for example:
//   import devteam from "./eslint.devteam.config.js";
//   export default [...yourConfig, ...devteam];
// Globs use forward slashes on every platform.

const SOURCE_FILES = ["**/*.{js,jsx,mjs,ts,tsx,mts}"];
const COMMONJS_FILES = ["**/*.{cjs,cts}"];

const esmReplacement = (what, instead) => `${what}. ${instead}`;

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
];
