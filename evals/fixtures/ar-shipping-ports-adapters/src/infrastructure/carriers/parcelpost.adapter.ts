import { ParcelPostClient } from "@parcelpost/sdk";
import type { Parcel } from "../../domain/shipment";
import type { CarrierGateway, CarrierQuote } from "../../domain/ports/carrier-gateway.port";

export class ParcelPostGateway implements CarrierGateway {
  readonly carrier = "parcelpost";

  constructor(private readonly client: ParcelPostClient) {}

  async quote(parcel: Parcel): Promise<CarrierQuote> {
    const rate = await this.client.rates.get({
      grams: parcel.weightGrams,
      toZip: parcel.destinationPostalCode,
    });
    return { carrier: this.carrier, priceCents: rate.amountCents };
  }

  async book(parcel: Parcel): Promise<{ trackingNumber: string }> {
    const label = await this.client.labels.create({
      grams: parcel.weightGrams,
      toZip: parcel.destinationPostalCode,
    });
    return { trackingNumber: label.tracking };
  }
}
