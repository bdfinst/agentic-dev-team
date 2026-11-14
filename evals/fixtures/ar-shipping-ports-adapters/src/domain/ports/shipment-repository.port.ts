import type { Shipment } from "../shipment";

export interface ShipmentRepository {
  save(shipment: Shipment): Promise<void>;
}
