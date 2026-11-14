import type { Parcel } from "../shipment";

export interface CarrierQuote {
  readonly carrier: string;
  readonly priceCents: number;
}

export interface CarrierGateway {
  readonly carrier: string;
  quote(parcel: Parcel): Promise<CarrierQuote>;
  book(parcel: Parcel): Promise<{ trackingNumber: string }>;
}
