// FAIL: Direct array mutations — push, sort, splice, reverse

interface Task {
  id: string;
  title: string;
  priority: number;
  completed: boolean;
}

const taskQueue: Task[] = [];

function addTask(task: Task): void {
  taskQueue.push(task); // mutation: push on module-level array
}

function addMultipleTasks(tasks: Task[]): void {
  tasks.forEach((task) => {
    taskQueue.push(task); // mutation: push inside loop
  });
}

function sortTasksByPriority(tasks: Task[]): Task[] {
  tasks.sort((a, b) => a.priority - b.priority); // mutation: in-place sort
  return tasks;
}

function removeTaskAt(tasks: Task[], index: number): Task | undefined {
  const removed = tasks.splice(index, 1); // mutation: splice
  return removed[0];
}

function insertTaskAt(tasks: Task[], index: number, task: Task): void {
  tasks.splice(index, 0, task); // mutation: splice insert
}

function reverseTaskOrder(tasks: Task[]): Task[] {
  tasks.reverse(); // mutation: in-place reverse
  return tasks;
}

function processCompletedTasks(tasks: Task[]): Task[] {
  const completed: Task[] = [];
  for (let i = tasks.length - 1; i >= 0; i--) {
    if (tasks[i].completed) {
      completed.push(tasks[i]);
      tasks.splice(i, 1); // mutation: splice to remove in loop
    }
  }
  return completed;
}

function reorderByCompletion(tasks: Task[]): Task[] {
  tasks.sort((a, b) => {
    if (a.completed === b.completed) return a.priority - b.priority;
    return a.completed ? 1 : -1;
  }); // mutation: in-place sort
  return tasks;
}

export {
  taskQueue,
  addTask,
  addMultipleTasks,
  sortTasksByPriority,
  removeTaskAt,
  insertTaskAt,
  reverseTaskOrder,
  processCompletedTasks,
  reorderByCompletion,
};
