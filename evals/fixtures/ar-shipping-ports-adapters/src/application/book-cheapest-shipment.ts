import { cheapestQuote, type Parcel, type Shipment } from "../domain/shipment";
import type { CarrierGateway } from "../domain/ports/carrier-gateway.port";
import type { ShipmentRepository } from "../domain/ports/shipment-repository.port";

export class BookCheapestShipment {
  constructor(
    private readonly carriers: readonly CarrierGateway[],
    private readonly shipments: ShipmentRepository,
  ) {}

  async execute(shipmentId: string, parcel: Parcel): Promise<Shipment> {
    const quotes = await Promise.all(this.carriers.map((gateway) => gateway.quote(parcel)));
    const best = cheapestQuote(quotes);
    const gateway = this.carriers.find((candidate) => candidate.carrier === best.carrier);
    if (!gateway) throw new Error(`no gateway for carrier ${best.carrier}`);
    const { trackingNumber } = await gateway.book(parcel);
    const shipment: Shipment = { id: shipmentId, parcel, carrier: best.carrier, trackingNumber };
    await this.shipments.save(shipment);
    return shipment;
  }
}
