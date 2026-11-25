// Cases written from esm-enforcer's Detect text. The agent-found baseline for
// this file is that text, not a live agent run.
const fs = require("node:fs");
const { join } = require("node:path");
module.exports = { fs, join };
exports.helper = () => 1;
const here = __dirname;
const self = __filename;
const lazy = () => require("./lazy.js");
