// PASS: Correct $state, $derived, $effect with cleanup, defensive copies

interface Item {
  id: number;
  label: string;
  done: boolean;
}

let items = $state<Item[]>([]);
let filter = $state<"all" | "active" | "done">("all");

// Correct: derived state uses $derived
const filtered = $derived(
  items.filter((item) =>
    filter === "all" ? true : filter === "done" ? item.done : !item.done,
  ),
);

const activeCount = $derived(items.filter((i) => !i.done).length);
const allDone = $derived(items.length > 0 && activeCount === 0);

// Correct: $effect with proper cleanup return
$effect(() => {
  const handler = () => {
    console.log("visibility change");
  };
  document.addEventListener("visibilitychange", handler);
  return () => {
    document.removeEventListener("visibilitychange", handler);
  };
});

// Correct: $effect for side effect (not derived state)
$effect(() => {
  document.title = `Todos (${activeCount} remaining)`;
});

// Correct: defensive copy — returns a new array, not the internal reference
function getSnapshot(): Item[] {
  return items.map((item) => ({ ...item }));
}

// Correct: full reassignment for state updates
function addItem(label: string) {
  items = [...items, { id: Date.now(), label, done: false }];
}

function toggleItem(id: number) {
  items = items.map((item) =>
    item.id === id ? { ...item, done: !item.done } : item,
  );
}

function removeCompleted() {
  items = items.filter((i) => !i.done);
}

export {
  items,
  filter,
  filtered,
  activeCount,
  allDone,
  getSnapshot,
  addItem,
  toggleItem,
  removeCompleted,
};
