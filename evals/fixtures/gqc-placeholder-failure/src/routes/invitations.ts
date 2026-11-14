import { Router } from "express";
import { isValidEmail } from "../lib/email";
import type { WorkspaceStore } from "../stores/workspaces";

export function invitationsRouter(store: WorkspaceStore): Router {
  const router = Router();

  // POST /workspaces/:workspaceId/invitations
  // Body: { email: string, role?: "member" | "admin", message?: string }
  router.post("/workspaces/:workspaceId/invitations", async (req, res) => {
    const { workspaceId } = req.params;
    const { email, role = "member", message } = req.body ?? {};

    if (!email || !isValidEmail(email)) {
      return res.status(400).json({ error: "INVALID_EMAIL" });
    }
    if (role !== "member" && role !== "admin") {
      return res.status(400).json({ error: "INVALID_ROLE" });
    }

    const inviter = await store.membership(workspaceId, req.user.id);
    if (!inviter || inviter.role !== "admin") {
      return res.status(403).json({ error: "NOT_WORKSPACE_ADMIN" });
    }

    if (await store.isMember(workspaceId, email)) {
      return res.status(409).json({ error: "ALREADY_MEMBER" });
    }

    const invitation = await store.createInvitation(workspaceId, {
      email,
      role,
      message: message?.slice(0, 500),
      invitedBy: req.user.id,
    });
    return res.status(201).json(invitation);
  });

  return router;
}
