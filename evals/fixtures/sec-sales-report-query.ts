import { Router } from "express";
import rateLimit from "express-rate-limit";
import { z } from "zod";
import { requireSession } from "./middleware/session";
import { pool } from "./db";

const router = Router();

router.use(requireSession);
router.use(rateLimit({ windowMs: 60_000, limit: 30 }));

const SORT_COLUMNS = {
  date: "s.sold_on",
  region: "r.name",
  revenue: "s.revenue_cents",
} as const;

const SORT_DIRECTIONS = { asc: "ASC", desc: "DESC" } as const;

const ReportQuerySchema = z.object({
  from: z.string().date(),
  to: z.string().date(),
  sort: z.enum(["date", "region", "revenue"]).default("date"),
  direction: z.enum(["asc", "desc"]).default("desc"),
  limit: z.coerce.number().int().min(1).max(500).default(100),
});

router.get("/reports/sales", async (req, res) => {
  const query = ReportQuerySchema.safeParse(req.query);
  if (!query.success) {
    return res.status(400).json({ error: "Invalid report parameters" });
  }
  const { from, to, sort, direction, limit } = query.data;

  const orderBy = `${SORT_COLUMNS[sort]} ${SORT_DIRECTIONS[direction]}`;
  const sql = `
    SELECT s.sold_on, r.name AS region, s.revenue_cents
    FROM sales s
    JOIN regions r ON r.id = s.region_id
    WHERE s.org_id = $1
      AND s.sold_on BETWEEN $2 AND $3
    ORDER BY ${orderBy}
    LIMIT $4
  `;

  const { rows } = await pool.query(sql, [req.session.orgId, from, to, limit]);
  res.json(rows);
});

export default router;
