// src/contexts/shipping/application/dispatch-paid-orders.ts
//
// Architecture (docs/architecture.md): the system is split into bounded
// contexts under src/contexts/<context>/. A context never imports another
// context's domain or infrastructure modules. Contexts communicate through
// the integration events published in src/shared/events/.

import type { EventBus } from "../../../shared/events/event-bus";
import type { InvoicePaid } from "../../../shared/events/billing-events";
import { Invoice } from "../../billing/domain/invoice";
import { InvoiceRepository } from "../../billing/infrastructure/invoice.repository";
import type { DispatchQueue } from "../domain/ports/dispatch-queue.port";
import { Consignment } from "../domain/consignment";

export class DispatchPaidOrders {
  constructor(
    private readonly events: EventBus,
    private readonly invoices: InvoiceRepository,
    private readonly dispatchQueue: DispatchQueue,
  ) {}

  start(): void {
    this.events.subscribe<InvoicePaid>("billing.invoice-paid", (event) =>
      this.onInvoicePaid(event),
    );
  }

  private async onInvoicePaid(event: InvoicePaid): Promise<void> {
    const invoice: Invoice = await this.invoices.findById(event.invoiceId);
    if (!invoice.isFullySettled()) return;
    const consignment = Consignment.forOrder(
      invoice.orderId,
      invoice.shippingAddress,
    );
    await this.dispatchQueue.enqueue(consignment);
  }
}
