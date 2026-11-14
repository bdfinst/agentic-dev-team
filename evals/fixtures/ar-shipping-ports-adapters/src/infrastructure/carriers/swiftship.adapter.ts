import { SwiftShip } from "swiftship-node";
import type { Parcel } from "../../domain/shipment";
import type { CarrierGateway, CarrierQuote } from "../../domain/ports/carrier-gateway.port";

export class SwiftShipGateway implements CarrierGateway {
  readonly carrier = "swiftship";

  constructor(private readonly api: SwiftShip) {}

  async quote(parcel: Parcel): Promise<CarrierQuote> {
    const offer = await this.api.quote(parcel.weightGrams, parcel.destinationPostalCode);
    return { carrier: this.carrier, priceCents: offer.cents };
  }

  async book(parcel: Parcel): Promise<{ trackingNumber: string }> {
    const booking = await this.api.book(parcel.weightGrams, parcel.destinationPostalCode);
    return { trackingNumber: booking.trackingId };
  }
}
