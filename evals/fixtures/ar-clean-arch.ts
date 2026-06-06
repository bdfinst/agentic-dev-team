// PASS: Correct dependency direction — domain depends only on a domain-owned port
//
// Architecture (by directory convention): dependencies point inward.
//   presentation -> application -> domain        (allowed)
//   infrastructure -> domain (implements ports)  (allowed; the adapter depends inward)
//   domain -> infrastructure                     (never)
//
// This file lives in the DOMAIN layer (src/domain/pricing/). It imports only
// from within the domain layer: the Invoice domain model and a repository PORT
// (an interface the domain owns). No infrastructure import appears here, so the
// dependency arrow points the correct way — infrastructure will implement the
// port, not the other way around.

import { Invoice } from "./invoice";
import type { InvoiceRepository } from "./invoice-repository.port";

const LATE_FEE_RATE = 1.15;
const LATE_FEE_GRACE_DAYS = 30;
const MILLIS_PER_DAY = 86_400_000;

export class PricingService {
  // Depend on the abstraction (port), injected from the outside.
  constructor(private readonly invoices: InvoiceRepository) {}

  async applyLateFee(invoiceId: string): Promise<Invoice> {
    const invoice = await this.invoices.findById(invoiceId);
    const overdueDays = Math.floor(
      (Date.now() - invoice.dueDate.getTime()) / MILLIS_PER_DAY,
    );
    if (overdueDays > LATE_FEE_GRACE_DAYS) {
      // Business rule stays in the domain model; persistence is the port's job.
      invoice.increaseTotal(LATE_FEE_RATE);
    }
    await this.invoices.save(invoice);
    return invoice;
  }
}
