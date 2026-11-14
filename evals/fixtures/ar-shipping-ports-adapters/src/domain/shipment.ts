export interface Parcel {
  readonly weightGrams: number;
  readonly destinationPostalCode: string;
}

export interface Shipment {
  readonly id: string;
  readonly parcel: Parcel;
  readonly carrier: string;
  readonly trackingNumber: string;
}

export function cheapestQuote<T extends { priceCents: number }>(quotes: readonly T[]): T {
  if (quotes.length === 0) throw new Error("no carrier quoted this parcel");
  return quotes.reduce((best, quote) => (quote.priceCents < best.priceCents ? quote : best));
}
