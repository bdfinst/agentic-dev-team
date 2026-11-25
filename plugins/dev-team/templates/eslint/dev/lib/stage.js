// The shipped config decides per file from the `tsconfig.json` and
// `node_modules` beside it. Tests copy it next to the array-mutation fixtures'
// own test tsconfig, so it behaves as it would in a user's project root.
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const payloadConfig = path.resolve(
  here,
  "../../payload/eslint.devteam.config.js",
);

export const arrayMutationDir = path.resolve(
  here,
  "../fixtures/array-mutation",
);

/** Copy the shipped config into `dir` (removed at process exit); returns its path. */
export const stageConfig = (dir) => {
  const staged = path.join(dir, `eslint.devteam.${process.pid}.config.js`);
  fs.copyFileSync(payloadConfig, staged);
  process.on("exit", () => fs.rmSync(staged, { force: true }));
  return staged;
};

/** The staged copy's default export, loaded as a user's flat config would. */
export const loadStagedConfig = async (dir) =>
  (await import(pathToFileURL(stageConfig(dir)).href)).default;
