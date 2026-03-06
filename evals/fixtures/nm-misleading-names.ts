// FAIL: Variables named opposite to their purpose, vague names, temp used permanently.

interface Item {
  id: string;
  name: string;
  price: number;
  active: boolean;
}

// issue: "data" is a function, not a data value
function data(items: Item[]): number {
  return items.reduce((sum, item) => sum + item.price, 0);
}

// issue: "temp" is the permanent return value, not a temporary variable
function buildReport(items: Item[]): string[] {
  const temp = items.map((item) => {
    const val = `${item.name}: $${item.price.toFixed(2)}`; // issue: "val" is vague
    return val;
  });
  return temp;
}

// issue: "flag" has no context about what it represents
function processItems(items: Item[], flag: boolean): Item[] {
  if (flag) {
    return items.filter((item) => item.price > 0);
  }
  return items;
}

// issue: "list2" says nothing about what the list contains
function mergeInventory(list1: Item[], list2: Item[]): Item[] {
  const result = [...list1];
  for (const item of list2) {
    const found = result.find((existing) => existing.id === item.id);
    if (!found) {
      result.push(item);
    }
  }
  return result;
}

function handleStuff(items: Item[]): { count: number; total: number } {
  const x = items.filter((i) => i.active); // issue: "x" is meaningless
  const total = data(x);
  return { count: x.length, total };
}
