// Untyped JavaScript: no tsconfig covers this file, so no array-mutation rule
// runs. Each `// miss:` marker is a real array mutation the config cannot see;
// `expected-misses.json` lists them. Everything else here must stay unreported.
const moduleList = [];
const captured = [];

export function onParameter(xs) {
  xs.push(1); // miss: parameter
  xs.pop(); // miss: parameter
  xs.shift(); // miss: parameter
  xs.unshift(0); // miss: parameter
  xs.splice(0, 1); // miss: parameter
  xs.sort(); // miss: parameter
  xs.reverse(); // miss: parameter
  xs.fill(0); // miss: parameter
}

export function onCaptured() {
  captured.push("a"); // miss: captured
  captured.pop(); // miss: captured
  captured.shift(); // miss: captured
  captured.unshift("b"); // miss: captured
  captured.splice(0, 1); // miss: captured
  captured.sort(); // miss: captured
  captured.reverse(); // miss: captured
  captured.fill("c"); // miss: captured
}

export function onModuleLevel() {
  moduleList.push(1); // miss: module-level
  moduleList.pop(); // miss: module-level
  moduleList.shift(); // miss: module-level
  moduleList.unshift(0); // miss: module-level
  moduleList.splice(0, 1); // miss: module-level
  moduleList.sort(); // miss: module-level
  moduleList.reverse(); // miss: module-level
  moduleList.fill(0); // miss: module-level
}

export function localAccumulator(items) {
  const out = [];
  for (const item of items) {
    out.push(item); // miss: accumulator
  }
  return out;
}

export function copiesAreFine(xs) {
  return [[...xs].sort(), xs.slice().reverse(), xs.toSorted(), xs.toSpliced(0, 1)];
}

export function setIsNotAnArray() {
  const seen = new Set();
  seen.add(1);
  seen.delete(1);
  seen.clear();
  return seen;
}

class Stack {
  items = [];

  push(value) {
    this.items.push(value);
  }

  sort() {
    return [...this.items].sort();
  }
}

export function customClass(stack) {
  stack.push(1);
  return stack.sort();
}
