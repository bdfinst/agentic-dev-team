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

export { legacyFlag, neverChanged, mutScratch, _cache, tick, sum, rename, Counter };
