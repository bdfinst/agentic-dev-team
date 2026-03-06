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

type TaskStatus = "open" | "in_progress" | "done" | "cancelled";

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
  readonly offset?: number;
}

// --- Validation ---

function validateTitle(title: string): Result<string, string> {
  const trimmed = title.trim();
  if (trimmed.length === 0) return err("Title must not be empty");
  if (trimmed.length > 200) return err("Title must be under 200 characters");
  return ok(trimmed);
}

function validateStatus(status: string): Result<TaskStatus, string> {
  const valid: ReadonlyArray<TaskStatus> = [
    "open",
    "in_progress",
    "done",
    "cancelled",
  ];
  if (!valid.includes(status as TaskStatus)) {
    return err(`Invalid status: ${status}. Must be one of: ${valid.join(", ")}`);
  }
  return ok(status as TaskStatus);
}

function validateFilter(raw: Record<string, unknown>): Result<TaskFilter, string> {
  const filter: TaskFilter = {};
  if (raw.status !== undefined) {
    const result = validateStatus(String(raw.status));
    if (!result.ok) return err(result.error);
    return ok({ ...filter, status: result.value });
  }
  if (raw.limit !== undefined) {
    const limit = Number(raw.limit);
    if (isNaN(limit) || limit < 1 || limit > 100) {
      return err("Limit must be between 1 and 100");
    }
    return ok({ ...filter, limit });
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
    input: UpdateTaskInput
  ): Promise<Result<Task, string>> {
    const existing = await this.db.findById(id);
    if (!existing) return err(`Task not found: ${id}`);

    if (input.title !== undefined) {
      const titleResult = validateTitle(input.title);
      if (!titleResult.ok) return err(titleResult.error);
    }

    if (input.status !== undefined) {
      const transition = validateTransition(existing.status, input.status);
      if (!transition.ok) return err(transition.error);
    }

    const updated = await this.db.update(id, input);
    return ok(updated);
  }

  async list(filter: TaskFilter): Promise<Result<readonly Task[], string>> {
    const tasks = await this.db.findMany(filter);
    return ok(tasks);
  }

  async remove(id: string): Promise<Result<void, string>> {
    const existing = await this.db.findById(id);
    if (!existing) return err(`Task not found: ${id}`);
    if (existing.status === "in_progress") {
      return err("Cannot delete an in-progress task");
    }
    await this.db.delete(id);
    return ok(undefined);
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
  to: TaskStatus
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
