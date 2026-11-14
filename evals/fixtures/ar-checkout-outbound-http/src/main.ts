import { Pool } from "pg";
import { PlaceOrder } from "./application/place-order";
import { PgOrderRepository } from "./infrastructure/db/order.repository";
import { HttpTaxRates } from "./infrastructure/http/tax-rates.client";

const pool = new Pool({ connectionString: process.env.DATABASE_URL });

export const placeOrder = new PlaceOrder(
  new HttpTaxRates(process.env.TAX_API_URL ?? "", process.env.TAX_API_KEY ?? ""),
  new PgOrderRepository(pool),
);
