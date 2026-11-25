// A .cjs config file: esm-enforcer's Detect text exempts it, so the agent
// reports nothing here and the rules must stay silent too.
const base = require("./base.cjs");
module.exports = { ...base, testEnvironment: "node" };
