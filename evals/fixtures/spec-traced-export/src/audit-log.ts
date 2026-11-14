export type Role = "admin" | "editor" | "viewer";

export interface AuditEntry {
  readonly time: string;
  readonly actor: string;
  readonly target: string;
  readonly from: Role;
  readonly to: Role;
}

export interface AuditLog {
  recordRoleChange(entry: AuditEntry): void;
  entries(): readonly AuditEntry[];
}

export function createAuditLog(): AuditLog {
  const recorded: AuditEntry[] = [];
  return {
    recordRoleChange(entry) {
      recorded.push(Object.freeze({ ...entry }));
    },
    entries() {
      return Object.freeze([...recorded]);
    },
  };
}

const CSV_HEADER = "time,actor,target,from,to";

export function exportAuditCsv(
  log: AuditLog,
  requesterRole: Role,
): { ok: true; csv: string } | { ok: false; reason: "forbidden" } {
  if (requesterRole !== "admin") {
    return { ok: false, reason: "forbidden" };
  }
  const rows = [...log.entries()]
    .sort((a, b) => a.time.localeCompare(b.time))
    .map((e) => [e.time, e.actor, e.target, e.from, e.to].join(","));
  return { ok: true, csv: [CSV_HEADER, ...rows].join("\n") };
}
