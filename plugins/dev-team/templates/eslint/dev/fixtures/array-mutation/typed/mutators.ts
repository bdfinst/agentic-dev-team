// Typed fixture: array mutators. `expected.json` lists every flagged line.
const moduleList: number[] = [];
const captured: string[] = [];

export function onParameter(xs: number[]): void {
  xs.push(1);
  xs.pop();
  xs.shift();
  xs.unshift(0);
  xs.splice(0, 1);
  xs.sort();
  xs.reverse();
  xs.fill(0);
}

export function onCaptured(): void {
  captured.push("a");
  captured.pop();
  captured.shift();
  captured.unshift("b");
  captured.splice(0, 1);
  captured.sort();
  captured.reverse();
  captured.fill("c");
}

export function onModuleLevel(): void {
  moduleList.push(1);
  moduleList.pop();
  moduleList.shift();
  moduleList.unshift(0);
  moduleList.splice(0, 1);
  moduleList.sort();
  moduleList.reverse();
  moduleList.fill(0);
}

export function localAccumulator(items: readonly number[]): number[] {
  const out: number[] = [];
  for (const item of items) {
    out.push(item);
  }
  return out;
}

export function copiesAreFine(xs: number[]): number[][] {
  return [
    [...xs].sort(),
    xs.slice().reverse(),
    xs.toSorted(),
    xs.toReversed(),
    xs.toSpliced(0, 1),
  ];
}

export function setIsNotAnArray(): Set<number> {
  const seen = new Set<number>();
  seen.add(1);
  seen.delete(1);
  seen.clear();
  return seen;
}

class Stack {
  private readonly items: number[] = [];

  push(value: number): void {
    this.items.push(value);
  }

  sort(): number[] {
    return [...this.items].sort();
  }
}

export function customClass(stack: Stack): number[] {
  stack.push(1);
  return stack.sort();
}

export function otherMutationsAreOutOfScope(): Map<string, number> {
  const box = { n: 0 };
  box.n = 1;
  box.n += 1;
  Object.assign(box, { n: 2 });
  const lookup = new Map<string, number>();
  lookup.set("a", box.n);
  return lookup;
}
