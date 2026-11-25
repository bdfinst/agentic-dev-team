// Cases written from js-fp-review's Detect text. The agent-found baseline for
// this file is that text, not a live agent run.
var legacyFlag = true;
let neverChanged = 1;
let mutScratch = 0;
let _cache = new Map();
let counter = 0;

function tick(): number {
  counter++;
  return counter;
}

function sum(list: number[]): number {
  let total = 0;
  for (let i = 0; i < list.length; i++) {
    total = total + list[i];
  }
  return total;
}

function rename(user: { name: string }): void {
  user.name = "x";
}

class Counter {
  value = 0;
  bump(): void {
    this.value = this.value + 1;
  }
}

// Exceptions the agent grants and the rules do not: a `mut` prefix exempts a
// `var`, and a `while` loop counter is a loop counter outside the `for` header.
var mutLegacy = 1;
let spin = 0;
while (spin < 3) {
  spin++;
}

export { legacyFlag, neverChanged, mutScratch, _cache, mutLegacy, tick, sum, rename, Counter };
