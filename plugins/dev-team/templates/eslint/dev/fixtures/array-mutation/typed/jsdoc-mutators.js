// Typed fixture: JSDoc-typed JavaScript. `expected.json` lists every flagged line.
/** @type {number[]} */
const moduleList = [];
/** @type {string[]} */
const captured = [];

/** @param {number[]} xs */
export function onParameter(xs) {
  xs.push(1);
  xs.pop();
  xs.shift();
  xs.unshift(0);
  xs.splice(0, 1);
  xs.sort();
  xs.reverse();
  xs.fill(0);
}

export function onCaptured() {
  captured.push("a");
  captured.pop();
  captured.shift();
  captured.unshift("b");
  captured.splice(0, 1);
  captured.sort();
  captured.reverse();
  captured.fill("c");
}

export function onModuleLevel() {
  moduleList.push(1);
  moduleList.pop();
  moduleList.shift();
  moduleList.unshift(0);
  moduleList.splice(0, 1);
  moduleList.sort();
  moduleList.reverse();
  moduleList.fill(0);
}

/**
 * @param {readonly number[]} items
 * @returns {number[]}
 */
export function localAccumulator(items) {
  /** @type {number[]} */
  const out = [];
  for (const item of items) {
    out.push(item);
  }
  return out;
}

/**
 * @param {number[]} xs
 * @returns {number[][]}
 */
export function copiesAreFine(xs) {
  return [
    [...xs].sort(),
    xs.slice().reverse(),
    xs.toSorted(),
    xs.toReversed(),
    xs.toSpliced(0, 1),
  ];
}

/** @returns {Set<number>} */
export function setIsNotAnArray() {
  const seen = new Set();
  seen.add(1);
  seen.delete(1);
  seen.clear();
  return seen;
}

class Stack {
  /** @type {number[]} */
  items = [];

  /** @param {number} value */
  push(value) {
    this.items.push(value);
  }

  /** @returns {number[]} */
  sort() {
    return [...this.items].sort();
  }
}

/**
 * @param {Stack} stack
 * @returns {number[]}
 */
export function customClass(stack) {
  stack.push(1);
  return stack.sort();
}

/** @returns {Map<string, number>} */
export function otherMutationsAreOutOfScope() {
  const box = { n: 0 };
  box.n = 1;
  box.n += 1;
  Object.assign(box, { n: 2 });
  /** @type {Map<string, number>} */
  const lookup = new Map();
  lookup.set("a", box.n);
  return lookup;
}
