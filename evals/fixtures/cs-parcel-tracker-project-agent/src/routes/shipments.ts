import { Router } from "express";
import { z } from "zod";

const createShipmentBody = z.object({
  carrier: z.literal("ups"),
  trackingNumber: z.string().min(8),
});

export const shipmentsRouter = Router();

shipmentsRouter.post("/", (req, res) => {
  const parsed = createShipmentBody.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({ data: null, error: parsed.error.message });
    return;
  }
  res.status(201).json({ data: parsed.data, error: null });
});
