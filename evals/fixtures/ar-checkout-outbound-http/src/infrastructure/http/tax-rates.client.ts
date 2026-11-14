import type { TaxRates } from "../../application/ports/tax-rates.port";

const TAX_API_TIMEOUT_MS = 2_000;

export class HttpTaxRates implements TaxRates {
  constructor(private readonly baseUrl: string, private readonly apiKey: string) {}

  async rateFor(region: string): Promise<number> {
    const response = await fetch(`${this.baseUrl}/rates/${encodeURIComponent(region)}`, {
      headers: { Authorization: `Bearer ${this.apiKey}` },
      signal: AbortSignal.timeout(TAX_API_TIMEOUT_MS),
    });
    if (!response.ok) throw new Error(`tax API returned ${response.status}`);
    const body = (await response.json()) as { rate: number };
    return body.rate;
  }
}
