// Lookalikes: look like a CommonJS or mutation pattern but are not one.
const x = { id: 1 };
const require = x;
const label = "module.exports";
const note = "exports.value = 1 and __dirname and var y";
// module.exports = a comment
const config = { module: { exports: 1 }, __dirname: "key, not a reference" };
config.module.exports = 2;
const loader = { require: (name) => name, exports: {} };
loader.require("pkg");
loader.exports.value = 3;

function describe(__dirname) {
  return __dirname;
}

function copyWith(user) {
  const copy = { ...user };
  copy.name = "local";
  return copy;
}

function pick(flag) {
  let value;
  if (flag) {
    value = 1;
  } else {
    value = 2;
  }
  return value;
}

export { require, label, note, config, loader, describe, copyWith, pick };
