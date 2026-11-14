import type { Pool } from "pg";
import type { Shipment } from "../../domain/shipment";
import type { ShipmentRepository } from "../../domain/ports/shipment-repository.port";

export class PgShipmentRepository implements ShipmentRepository {
  constructor(private readonly pool: Pool) {}

  async save(shipment: Shipment): Promise<void> {
    await this.pool.query(
      "INSERT INTO shipments (id, carrier, tracking_number, weight_grams, postal_code) VALUES ($1, $2, $3, $4, $5)",
      [
        shipment.id,
        shipment.carrier,
        shipment.trackingNumber,
        shipment.parcel.weightGrams,
        shipment.parcel.destinationPostalCode,
      ],
    );
  }
}
