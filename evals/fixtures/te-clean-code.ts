import { Result, ok, err } from "./result";

// --- Types ---

interface Task {
  readonly id: string;
  readonly title: string;
  readonly status: TaskStatus;
  readonly assigneeId: string | null;
  readonly createdAt: Date;
  readonly updatedAt: Date;
}

const TASK_STATUSES = ["open", "in_progress", "done", "cancelled"] as const;

type TaskStatus = (typeof TASK_STATUSES)[number];

interface CreateTaskInput {
  readonly title: string;
  readonly assigneeId?: string;
}

interface UpdateTaskInput {
  readonly title?: string;
  readonly status?: TaskStatus;
  readonly assigneeId?: string | null;
}

interface TaskFilter {
  readonly status?: TaskStatus;
  readonly assigneeId?: string;
  readonly limit?: number;
}

// --- Validation ---

function validateTitle(title: string): Result<string, string> {
  const trimmed = title.trim();
  if (trimmed.length === 0) return err("Title must not be empty");
  if (trimmed.length > 200) return err("Title must be at most 200 characters");
  return ok(trimmed);
}

function isTaskStatus(value: string): value is TaskStatus {
  return (TASK_STATUSES as readonly string[]).includes(value);
}

function validateStatus(status: string): Result<TaskStatus, string> {
  if (!isTaskStatus(status)) {
    const allowed = TASK_STATUSES.join(", ");
    return err(`Invalid status: ${status}. Must be one of: ${allowed}`);
  }
  return ok(status);
}

function validateLimit(raw: unknown): Result<number, string> {
  const limit = Number(raw);
  if (!Number.isInteger(limit) || limit < 1 || limit > 100) {
    return err("Limit must be an integer between 1 and 100");
  }
  return ok(limit);
}

function validateFilter(
  raw: Record<string, unknown>,
): Result<TaskFilter, string> {
  let filter: TaskFilter = {};
  if (raw.status !== undefined) {
    const status = validateStatus(String(raw.status));
    if (!status.ok) return err(status.error);
    filter = { ...filter, status: status.value };
  }
  if (raw.limit !== undefined) {
    const limit = validateLimit(raw.limit);
    if (!limit.ok) return err(limit.error);
    filter = { ...filter, limit: limit.value };
  }
  if (raw.assigneeId !== undefined) {
    if (typeof raw.assigneeId !== "string" || raw.assigneeId === "") {
      return err("Assignee id must be a non-empty string");
    }
    filter = { ...filter, assigneeId: raw.assigneeId };
  }
  return ok(filter);
}

// --- Service ---

class TaskService {
  constructor(private readonly db: TaskRepository) {}

  async create(input: CreateTaskInput): Promise<Result<Task, string>> {
    const titleResult = validateTitle(input.title);
    if (!titleResult.ok) return err(titleResult.error);

    const task = await this.db.insert({
      title: titleResult.value,
      assigneeId: input.assigneeId ?? null,
      status: "open",
    });
    return ok(task);
  }

  async update(
    id: string,
    input: UpdateTaskInput,
  ): Promise<Result<Task, string>> {
    const existing = await this.findExisting(id);
    if (!existing.ok) return err(existing.error);

    let changes = input;
    if (input.title !== undefined) {
      const titleResult = validateTitle(input.title);
      if (!titleResult.ok) return err(titleResult.error);
      changes = { ...changes, title: titleResult.value };
    }

    if (input.status !== undefined) {
      const transition = validateTransition(
        existing.value.status,
        input.status,
      );
      if (!transition.ok) return err(transition.error);
    }

    const updated = await this.db.update(id, changes);
    return ok(updated);
  }

  async list(
    query: Record<string, unknown>,
  ): Promise<Result<readonly Task[], string>> {
    const filter = validateFilter(query);
    if (!filter.ok) return err(filter.error);
    const tasks = await this.db.findMany(filter.value);
    return ok(tasks);
  }

  async remove(id: string): Promise<Result<void, string>> {
    const existing = await this.findExisting(id);
    if (!existing.ok) return err(existing.error);
    if (existing.value.status === "in_progress") {
      return err("Cannot delete an in-progress task");
    }
    await this.db.delete(id);
    return ok(undefined);
  }

  private async findExisting(id: string): Promise<Result<Task, string>> {
    const task = await this.db.findById(id);
    return task ? ok(task) : err(`Task not found: ${id}`);
  }
}

// --- Transitions ---

const VALID_TRANSITIONS: Record<TaskStatus, readonly TaskStatus[]> = {
  open: ["in_progress", "cancelled"],
  in_progress: ["done", "cancelled"],
  done: [],
  cancelled: ["open"],
};

function validateTransition(
  from: TaskStatus,
  to: TaskStatus,
): Result<TaskStatus, string> {
  const allowed = VALID_TRANSITIONS[from];
  if (!allowed.includes(to)) {
    return err(`Cannot transition from ${from} to ${to}`);
  }
  return ok(to);
}

// --- Repository interface ---

interface TaskRepository {
  insert(data: Omit<Task, "id" | "createdAt" | "updatedAt">): Promise<Task>;
  findById(id: string): Promise<Task | null>;
  findMany(filter: TaskFilter): Promise<readonly Task[]>;
  update(id: string, data: UpdateTaskInput): Promise<Task>;
  delete(id: string): Promise<void>;
}

export { TaskService, TaskRepository, Task, TaskStatus, CreateTaskInput };
