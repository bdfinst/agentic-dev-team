// FAIL: Layer boundary violation — domain layer imports infrastructure directly
//
// Architecture (by directory convention): dependencies must point inward.
//   presentation -> application -> domain        (allowed)
//   infrastructure -> domain (implements ports)  (allowed; adapter depends inward)
//   domain -> infrastructure                     (PROHIBITED — domain is the core)
//
// This file lives in the DOMAIN layer (src/domain/pricing/), so it must not
// import from src/infrastructure/* . It does, in two places.

// Violation 1: domain layer imports a TypeORM entity from the infrastructure
// layer. The ORM entity is a persistence concern; importing it into the domain
// couples the core to the database and reverses the dependency direction.
import { InvoiceEntity } from "../../infrastructure/orm/invoice.entity";

// Violation 2: domain layer imports the concrete repository implementation from
// infrastructure instead of depending on a domain-owned port interface.
import { TypeOrmInvoiceRepository } from "../../infrastructure/orm/invoice.repository";

const LATE_FEE_RATE = 1.15;
const LATE_FEE_GRACE_DAYS = 30;
const MILLIS_PER_DAY = 86_400_000;

export class PricingService {
  // Depends on a concrete infrastructure type, not a domain port.
  constructor(private readonly repo: TypeOrmInvoiceRepository) {}

  // Domain logic operates directly on an ORM entity rather than a domain model.
  async applyLateFee(invoice: InvoiceEntity): Promise<InvoiceEntity> {
    const overdueDays = Math.floor(
      (Date.now() - invoice.dueDate.getTime()) / MILLIS_PER_DAY,
    );
    if (overdueDays > LATE_FEE_GRACE_DAYS) {
      invoice.totalCents = Math.round(invoice.totalCents * LATE_FEE_RATE);
    }
    await this.repo.save(invoice);
    return invoice;
  }
}
