import { describe, it, expect } from "vitest";
import {
  createAuditLog,
  exportAuditCsv,
  type AuditEntry,
} from "../src/audit-log";

const earlier: AuditEntry = {
  time: "2026-03-01T09:00:00Z",
  actor: "ann",
  target: "bob",
  from: "viewer",
  to: "editor",
};
const later: AuditEntry = {
  time: "2026-03-02T09:00:00Z",
  actor: "ann",
  target: "bob",
  from: "editor",
  to: "admin",
};

describe("audit log", () => {
  it("records a role change with actor, target, old role, new role and time", () => {
    const log = createAuditLog();
    log.recordRoleChange(earlier);
    expect(log.entries()).toEqual([earlier]);
  });

  it("does not let callers edit or delete recorded entries", () => {
    const log = createAuditLog();
    log.recordRoleChange(earlier);
    const entries = log.entries() as AuditEntry[];
    expect(() => entries.pop()).toThrow(TypeError);
    expect(() => {
      (entries[0] as { actor: string }).actor = "mallory";
    }).toThrow(TypeError);
    expect(log.entries()).toEqual([earlier]);
  });

  it("exports a header row and one row per entry, oldest first, for an admin", () => {
    const log = createAuditLog();
    log.recordRoleChange(later);
    log.recordRoleChange(earlier);
    const result = exportAuditCsv(log, "admin");
    expect(result).toEqual({
      ok: true,
      csv: [
        "time,actor,target,from,to",
        "2026-03-01T09:00:00Z,ann,bob,viewer,editor",
        "2026-03-02T09:00:00Z,ann,bob,editor,admin",
      ].join("\n"),
    });
  });

  it("refuses an export request from a viewer", () => {
    const log = createAuditLog();
    expect(exportAuditCsv(log, "viewer")).toEqual({
      ok: false,
      reason: "forbidden",
    });
  });
});
