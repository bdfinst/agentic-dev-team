import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import test from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";

import { stageConfig } from "../lib/stage.js";

const stageUrl = pathToFileURL(
  path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../lib/stage.js"),
).href;

const withTempDir = (body) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "devteam-stage-"));
  try {
    return body(dir);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
};

test("staging the same directory twice returns one path and adds no listener", () => {
  withTempDir((dir) => {
    const first = stageConfig(dir);
    const listeners = process.listenerCount("exit");
    assert.equal(stageConfig(dir), first);
    assert.equal(process.listenerCount("exit"), listeners);
  });
});

test("staging many directories registers one exit listener", () => {
  withTempDir((a) =>
    withTempDir((b) => {
      stageConfig(a);
      const listeners = process.listenerCount("exit");
      stageConfig(b);
      assert.equal(process.listenerCount("exit"), listeners);
    }),
  );
});

// Runs a fresh process that stages a config in `dir`, reports the staged path
// and whether it existed, then runs `ending`.
const runStagingChild = (dir, ending) => {
  const script = `
    import fs from "node:fs";
    import { stageConfig } from ${JSON.stringify(stageUrl)};
    const file = stageConfig(${JSON.stringify(dir)});
    process.stdout.write(JSON.stringify({ file, existedBefore: fs.existsSync(file) }));
    ${ending}
  `;
  const run = spawnSync(process.execPath, ["--input-type=module", "-e", script], {
    encoding: "utf8",
    timeout: 60_000,
  });
  assert.ifError(run.error);
  return { run, ...JSON.parse(run.stdout) };
};

test("a SIGTERM removes the staged config", () => {
  withTempDir((dir) => {
    const { run, file, existedBefore } = runStagingChild(
      dir,
      'process.kill(process.pid, "SIGTERM"); setTimeout(() => {}, 5000);',
    );
    assert.equal(run.signal, "SIGTERM", run.stderr);
    assert.ok(file.endsWith(".config.js"), file);
    assert.equal(existedBefore, true);
    assert.equal(fs.existsSync(file), false);
  });
});

test("a normal exit removes the staged config", () => {
  withTempDir((dir) => {
    const { run, file, existedBefore } = runStagingChild(dir, "");
    assert.equal(run.status, 0, run.stderr);
    assert.equal(existedBefore, true);
    assert.equal(fs.existsSync(file), false);
  });
});
