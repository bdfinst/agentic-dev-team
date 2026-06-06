// ESLint flat config.
//
// First-party JavaScript (this config, future scripts) is linted normally.
//
// TypeScript is a special case: this repo has no application TypeScript — every
// `.ts` file is an eval fixture under `evals/`. Many fixtures are *intentionally*
// bad code (SQL injection, mutations, magic values, god objects, …): they are the
// inputs the review agents must flag, so linting them would fail by design.
// We therefore lint only the CLEAN fixtures — those whose `expected/*.json`
// declares `expectedStatus: "pass"` for every applicable agent. That set is the
// single source of truth, derived below at config-load time, so adding a fixture
// + its expected file auto-includes/excludes it without editing this file.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import eslint from "@eslint/js";
import tseslint from "typescript-eslint";

const rootDir = path.dirname(fileURLToPath(import.meta.url));
const expectedDir = path.join(rootDir, "evals", "expected");
const fixturesRel = "evals/fixtures";

// Fixture source extensions, in the order an `expected/<stem>.json` maps to a file.
const fixtureExts = [".ts", ".svelte.ts", ".js", ".cjs", ".mjs", ".svelte.js"];

/**
 * The clean fixtures, as repo-relative paths. A fixture is "clean" when it has
 * applicable agents and every one of them expects a `pass` verdict — i.e. the
 * fixture contains no planted issues.
 */
function cleanFixtures() {
  const out = [];
  for (const entry of fs.readdirSync(expectedDir)) {
    if (!entry.endsWith(".json")) continue;
    const stem = entry.slice(0, -".json".length);

    let spec;
    try {
      spec = JSON.parse(fs.readFileSync(path.join(expectedDir, entry), "utf8"));
    } catch {
      continue; // malformed expected file — the eval grader's job to flag, not ours
    }

    const verdicts = Object.values(spec.agents ?? {}).map(
      (a) => a.expectedStatus,
    );
    const isClean = verdicts.length > 0 && verdicts.every((v) => v === "pass");
    if (!isClean) continue;

    for (const ext of fixtureExts) {
      const rel = `${fixturesRel}/${stem}${ext}`;
      if (fs.existsSync(path.join(rootDir, rel))) out.push(rel);
    }
  }
  return out.sort();
}

const clean = cleanFixtures();
const cleanSvelte = clean.filter(
  (f) => f.endsWith(".svelte.ts") || f.endsWith(".svelte.js"),
);

export default tseslint.config(
  // Never lint dependencies or generated build output. The `build/`/`dist/` `.js`
  // files under the recon fixtures are placeholders representing artifacts the
  // codebase-recon agent is meant to exclude — they are not source.
  //
  // `knowledge/rule-fixtures/**/*.js` are the positive/negative fixtures for the
  // security semgrep rules: positives are *intentionally* vulnerable (eval of
  // user input, wildcard CORS, JWT alg=none, …) and negatives are minimal
  // snippets. They are detection inputs, not source — linting them only ever
  // produces no-undef/no-unused-vars noise by design.
  //
  // `tests/fixtures/agent-readiness/**/*.js` are config files inside mock repos
  // used to exercise the agent-readiness scanner (e.g. a CommonJS
  // `commitlint.config.js` using `module.exports`). They are fixture data, not
  // first-party source.
  {
    ignores: [
      "node_modules/**",
      "**/build/**",
      "**/dist/**",
      "**/knowledge/rule-fixtures/**/*.js",
      "**/tests/fixtures/agent-readiness/**/*.js",
    ],
  },

  // First-party JavaScript (this config file, and any future js/cjs/mjs).
  {
    files: ["**/*.{js,cjs,mjs}"],
    extends: [eslint.configs.recommended],
  },

  // Clean TypeScript / JavaScript fixtures — the only `.ts` we lint.
  {
    files: clean,
    extends: [eslint.configs.recommended, ...tseslint.configs.recommended],
    rules: {
      // TypeScript itself resolves identifiers; `no-undef` only produces false
      // positives here (e.g. test globals like `describe`/`it`, Svelte 5 runes
      // like `$state` in the `.svelte.ts` fixtures).
      "no-undef": "off",
      // Fixtures are illustrative snippets: they define functions/classes for a
      // review agent to read, not to call. "Defined but never used" is inherent
      // to that format and carries no signal about whether the code is clean.
      "@typescript-eslint/no-unused-vars": "off",
    },
  },

  // Svelte fixtures: `$state` runes MUST be declared with `let` (they are
  // reassigned in markup/handlers this module can't see). Without
  // `svelte-eslint-parser`, `prefer-const` misfires on them.
  {
    files: cleanSvelte,
    rules: {
      "prefer-const": "off",
    },
  },
);
