import { ParcelPostClient } from "@parcelpost/sdk";
import { Pool } from "pg";
import { SwiftShip } from "swiftship-node";
import { BookCheapestShipment } from "./application/book-cheapest-shipment";
import { ParcelPostGateway } from "./infrastructure/carriers/parcelpost.adapter";
import { SwiftShipGateway } from "./infrastructure/carriers/swiftship.adapter";
import { PgShipmentRepository } from "./infrastructure/persistence/pg-shipment.repository";

const pool = new Pool({ connectionString: process.env.DATABASE_URL });

export const bookCheapestShipment = new BookCheapestShipment(
  [
    new ParcelPostGateway(new ParcelPostClient({ apiKey: process.env.PARCELPOST_KEY ?? "" })),
    new SwiftShipGateway(new SwiftShip(process.env.SWIFTSHIP_TOKEN ?? "")),
  ],
  new PgShipmentRepository(pool),
);
