import { Router } from "express";
import rateLimit from "express-rate-limit";
import { z } from "zod";
import { requireSession } from "./middleware/session";
import { documents } from "./repositories/documents";
import { storage } from "./storage";

const router = Router();

router.use(requireSession);
router.use(rateLimit({ windowMs: 60_000, limit: 120 }));

const DocumentIdSchema = z.string().uuid();
const CreateDocumentSchema = z.object({
  title: z.string().min(1).max(200),
  folderId: z.string().uuid().nullable(),
});

router.get("/documents", async (req, res) => {
  const rows = await documents.findMany({
    where: { ownerId: req.session.userId },
    orderBy: { updatedAt: "desc" },
  });
  res.json(rows.map(({ id, title, updatedAt }) => ({ id, title, updatedAt })));
});

router.get("/documents/:id", async (req, res) => {
  const id = DocumentIdSchema.parse(req.params.id);
  const doc = await documents.findFirst({
    where: { id, ownerId: req.session.userId },
  });
  if (!doc) {
    return res.status(404).json({ error: "Not found" });
  }
  res.json({ id: doc.id, title: doc.title, updatedAt: doc.updatedAt });
});

router.post("/documents", async (req, res) => {
  const input = CreateDocumentSchema.parse(req.body);
  const doc = await documents.create({
    data: { ...input, ownerId: req.session.userId },
  });
  res.status(201).json({ id: doc.id });
});

router.get("/documents/:id/download", async (req, res) => {
  const id = DocumentIdSchema.parse(req.params.id);
  const doc = await documents.findUnique({ where: { id } });
  if (!doc) {
    return res.status(404).json({ error: "Not found" });
  }
  const stream = await storage.openRead(doc.storageKey);
  res.setHeader("Content-Type", "application/pdf");
  res.setHeader(
    "Content-Disposition",
    `attachment; filename="${encodeURIComponent(doc.title)}.pdf"`,
  );
  stream.pipe(res);
});

router.delete("/documents/:id", async (req, res) => {
  const id = DocumentIdSchema.parse(req.params.id);
  const deleted = await documents.deleteMany({
    where: { id, ownerId: req.session.userId },
  });
  if (deleted.count === 0) {
    return res.status(404).json({ error: "Not found" });
  }
  res.status(204).end();
});

export default router;
