// Violating fixture: every flagged line is listed in expected.json.

var legacyName = "a";
let neverReassigned = 1;
let counter = 0;

const fs = require("node:fs");
const path = require("node:path");

function bump(items) {
  counter++;
  return items.length + neverReassigned;
}

function rename(user) {
  user.name = "x";
  user["email"] = "y";
  return user;
}

module.exports = { bump, rename, legacyName, fs, path };
exports.extra = 1;
module.exports.more = 2;
const here = __dirname;
const file = __filename;
