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

test("a SIGTERM removes the staged config", () => {
  withTempDir((dir) => {
    const script = `
      import { stageConfig } from ${JSON.stringify(stageUrl)};
      process.stdout.write(stageConfig(${JSON.stringify(dir)}));
      process.kill(process.pid, "SIGTERM");
      setTimeout(() => {}, 5000);
    `;
    const run = spawnSync(
      process.execPath,
      ["--input-type=module", "-e", script],
      { encoding: "utf8", timeout: 60_000 },
    );
    assert.equal(run.signal, "SIGTERM", run.stderr);
    assert.ok(run.stdout.endsWith(".config.js"), run.stdout);
    assert.equal(fs.existsSync(run.stdout), false);
  });
});
