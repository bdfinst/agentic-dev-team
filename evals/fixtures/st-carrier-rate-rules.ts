export type Carrier = "ground" | "express" | "freight";

export interface Parcel {
  readonly weightGrams: number;
  readonly longestSideCm: number;
  readonly isHazardous: boolean;
}

export interface Quote {
  readonly carrier: Carrier;
  readonly priceCents: number;
}

export interface RateTable {
  readonly groundBaseCents: number;
  readonly groundPerKgCents: number;
  readonly expressBaseCents: number;
  readonly expressPerKgCents: number;
  readonly expressOversizeSurchargeCents: number;
  readonly expressOversizeThresholdCm: number;
  readonly freightFlatCents: number;
  readonly hazardousSurchargeCents: number;
}

const GRAMS_PER_KG = 1000;

function billableKilograms(parcel: Parcel): number {
  return Math.ceil(parcel.weightGrams / GRAMS_PER_KG);
}

function hazardousSurcharge(parcel: Parcel, rates: RateTable): number {
  return parcel.isHazardous ? rates.hazardousSurchargeCents : 0;
}

function groundPrice(parcel: Parcel, rates: RateTable): number {
  return (
    rates.groundBaseCents + billableKilograms(parcel) * rates.groundPerKgCents
  );
}

function expressPrice(parcel: Parcel, rates: RateTable): number {
  const isOversize = parcel.longestSideCm > rates.expressOversizeThresholdCm;
  const oversize = isOversize ? rates.expressOversizeSurchargeCents : 0;
  return (
    rates.expressBaseCents +
    billableKilograms(parcel) * rates.expressPerKgCents +
    oversize
  );
}

function freightPrice(_parcel: Parcel, rates: RateTable): number {
  return rates.freightFlatCents;
}

function basePrice(carrier: Carrier, parcel: Parcel, rates: RateTable): number {
  switch (carrier) {
    case "ground":
      return groundPrice(parcel, rates);
    case "express":
      return expressPrice(parcel, rates);
    case "freight":
      return freightPrice(parcel, rates);
  }
}

export function quote(carrier: Carrier, parcel: Parcel, rates: RateTable): Quote {
  return {
    carrier,
    priceCents: basePrice(carrier, parcel, rates) + hazardousSurcharge(parcel, rates),
  };
}

export function cheapestQuote(
  carriers: readonly Carrier[],
  parcel: Parcel,
  rates: RateTable,
): Quote {
  return carriers
    .map((carrier) => quote(carrier, parcel, rates))
    .reduce((best, candidate) =>
      candidate.priceCents < best.priceCents ? candidate : best,
    );
}
