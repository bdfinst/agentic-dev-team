// This module is the harness's effect boundary (`lib/effects/`): it copies files,
// registers process exit and signal listeners, and clears an ambient opt-out
// variable. Everything else in `lib/` stays free of those effects.
//
// The shipped config decides per file from the `tsconfig.json` and
// `node_modules` beside it. Tests copy it next to the array-mutation fixtures'
// own test tsconfig, so it behaves as it would in a user's project root.
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
export const payloadConfig = path.resolve(
  here,
  "../../../payload/eslint.devteam.config.js",
);

export const arrayMutationDir = path.resolve(
  here,
  "../../fixtures/array-mutation",
);

const staged = new Map();

const removeStaged = () => {
  for (const file of staged.values()) fs.rmSync(file, { force: true });
};

// The exit listener does not run on a signal's default action, so a signal
// removes the files and then re-raises itself with the default action restored.
let cleanupRegistered = false;
const registerCleanup = () => {
  if (cleanupRegistered) return;
  cleanupRegistered = true;
  process.on("exit", removeStaged);
  for (const signal of ["SIGINT", "SIGTERM"]) {
    process.once(signal, () => {
      removeStaged();
      process.kill(process.pid, signal);
    });
  }
};

/** Copy the shipped config into `dir` once (removed at process exit or on SIGINT/SIGTERM); returns its path. */
export const stageConfig = (dir) => {
  const known = staged.get(dir);
  if (known !== undefined) return known;
  const file = path.join(dir, `eslint.devteam.${process.pid}.config.js`);
  fs.copyFileSync(payloadConfig, file);
  staged.set(dir, file);
  registerCleanup();
  return file;
};

/** An ambient opt-out would make every typed-rule run pass vacuously. */
export const clearAmbientTypedOptOut = () => {
  delete process.env.DEVTEAM_LINT_TYPED;
};

/** The staged copy's default export, loaded as a user's flat config would. */
export const loadStagedConfig = async (dir) => {
  clearAmbientTypedOptOut();
  return (await import(pathToFileURL(stageConfig(dir)).href)).default;
};
