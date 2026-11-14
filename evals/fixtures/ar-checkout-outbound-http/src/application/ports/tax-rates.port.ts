export interface TaxRates {
  rateFor(region: string): Promise<number>;
}
