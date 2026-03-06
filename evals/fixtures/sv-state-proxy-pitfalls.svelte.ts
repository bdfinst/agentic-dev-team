// FAIL: $state proxy pitfalls — destructuring, deep mutation, spreading

import { getContext } from "svelte";

interface Todo {
  id: number;
  text: string;
  done: boolean;
  tags: string[];
}

let todos = $state<Todo[]>([
  { id: 1, text: "Learn Svelte 5", done: false, tags: ["svelte"] },
]);

// ISSUE: Destructuring $state breaks proxy tracking — `text` and `done`
// become plain values that no longer trigger reactive updates
const { text, done } = $state({ text: "hello", done: false });

function toggleFirst() {
  // ISSUE: Deep mutation without reassignment — pushing into a nested array
  // on a $state object may not trigger fine-grained reactivity
  todos[0].tags.push("updated");
}

function markDone(index: number) {
  // ISSUE: Deep property mutation — may not trigger UI update without
  // reassigning the parent object
  todos[index].done = true;
}

// ISSUE: Spreading $state into a plain object loses reactivity
function exportSnapshot() {
  const plain = { ...todos[0] };
  return plain;
}

// ISSUE: Assigning a pre-existing plain object into $state context
// and expecting deep tracking
function loadFromApi(data: Todo[]) {
  const existing = data[0]; // plain object, not a proxy
  todos[0] = existing; // assigned into $state, but nested props of `existing` may not be tracked
}

export { todos, text, done, toggleFirst, markDone, exportSnapshot, loadFromApi };
