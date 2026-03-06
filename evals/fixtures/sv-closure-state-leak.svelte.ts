// FAIL: Factory returning closure-backed object; getter exposes internal array ref

function createTodoManager() {
  let todos: string[] = [];
  let nextId = 0;

  return {
    add(text: string) {
      todos.push(text);
      nextId++;
    },

    // ISSUE: Closure state leak — Svelte cannot observe `todos` because
    // it lives in a plain closure, not in $state
    get items() {
      return todos;
    },

    // ISSUE: Mutable reference return — exposes the internal array directly;
    // callers can mutate it without triggering any reactive update
    getAll() {
      return todos;
    },

    get count() {
      return todos.length;
    },
  };
}

// Component-level usage: looks reactive but isn't
const manager = createTodoManager();

function handleAdd(text: string) {
  manager.add(text);
  // UI won't update — `manager.items` is not reactively tracked
}

// ISSUE: Another closure state leak — mutable object held outside $state
function createCounter() {
  let value = 0;

  return {
    increment() {
      value++;
    },
    get current() {
      return value;
    },
  };
}

const counter = createCounter();

export { manager, counter, handleAdd };
