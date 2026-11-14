export interface BillingLine {
  readonly sku: string;
  readonly quantity: number;
  readonly unitPriceCents: number;
  readonly discountRate: number;
  readonly taxRate: number;
}

export interface Invoice {
  readonly invoiceId: string;
  readonly customerId: string;
  readonly lines: readonly BillingLine[];
}

export interface CreditNote {
  readonly creditNoteId: string;
  readonly invoiceId: string;
  readonly returnedLines: readonly BillingLine[];
}

export interface Totals {
  readonly netCents: number;
  readonly taxCents: number;
  readonly grossCents: number;
}

export function computeInvoiceTotals(invoice: Invoice): Totals {
  let netCents = 0;
  let taxCents = 0;
  for (const line of invoice.lines) {
    const listCents = line.quantity * line.unitPriceCents;
    const discountedCents = Math.round(listCents * (1 - line.discountRate));
    netCents += discountedCents;
    taxCents += Math.round(discountedCents * line.taxRate);
  }
  return { netCents, taxCents, grossCents: netCents + taxCents };
}

export function computeCreditNoteTotals(creditNote: CreditNote): Totals {
  let refundNetCents = 0;
  let refundTaxCents = 0;
  for (const returned of creditNote.returnedLines) {
    const beforeDiscount = returned.unitPriceCents * returned.quantity;
    const afterDiscount = Math.round(
      beforeDiscount - beforeDiscount * returned.discountRate,
    );
    refundNetCents += afterDiscount;
    refundTaxCents += Math.round(afterDiscount * returned.taxRate);
  }
  return {
    netCents: -refundNetCents,
    taxCents: -refundTaxCents,
    grossCents: -(refundNetCents + refundTaxCents),
  };
}

export function formatCents(cents: number, currencyCode: string): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currencyCode,
  }).format(cents / 100);
}
