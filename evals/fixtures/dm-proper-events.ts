// PASS: Domain events for cross-boundary communication, no direct dependencies

// Domain event base
interface DomainEvent {
  readonly occurredAt: Date;
  readonly eventType: string;
}

// Events carry data, not references to other contexts
class PaymentCompleted implements DomainEvent {
  readonly eventType = "payment.completed";
  readonly occurredAt = new Date();
  constructor(
    readonly paymentId: string,
    readonly orderId: string,
    readonly amountCents: number,
  ) {}
}

class OrderFulfillmentRequested implements DomainEvent {
  readonly eventType = "order.fulfillment_requested";
  readonly occurredAt = new Date();
  constructor(
    readonly orderId: string,
    readonly shippingAddress: ShippingAddressSnapshot,
    readonly items: ReadonlyArray<{ sku: string; quantity: number }>,
  ) {}
}

// Published language: the event carries its own address shape, not an Order-context type
interface ShippingAddressSnapshot {
  readonly line1: string;
  readonly city: string;
  readonly postalCode: string;
  readonly country: string;
}

// Event bus abstraction — no knowledge of subscribers; the outbox relay publishes through it
interface EventBus {
  publish(event: DomainEvent): Promise<void>;
}

interface OrderRepository {
  findById(orderId: string): Promise<Order | null>;
  saveWithOutbox(order: Order, events: readonly DomainEvent[]): Promise<void>;
}

// Order context publishes events; does not call shipping directly
class OrderCompletionHandler {
  constructor(private readonly orderRepo: OrderRepository) {}

  async handle(paymentEvent: PaymentCompleted): Promise<void> {
    const order = await this.orderRepo.findById(paymentEvent.orderId);
    if (!order) throw new OrderNotFoundError(paymentEvent.orderId);
    if (order.isPaid) return; // redelivered event: already handled

    order.markPaid();
    const fulfillment = new OrderFulfillmentRequested(
      order.id,
      order.shippingAddress.toSnapshot(),
      order.lineItems.map((li) => ({ sku: li.sku, quantity: li.quantity })),
    );
    // Saves the order and appends the event to the outbox in one transaction;
    // an outbox relay hands it to the EventBus, so no event is lost or orphaned
    await this.orderRepo.saveWithOutbox(order, [fulfillment]);
  }
}

// Shipping context listens independently — no import from order context
class ShipmentCreator {
  constructor(private readonly shipmentRepo: ShipmentRepository) {}

  async onFulfillmentRequested(event: OrderFulfillmentRequested): Promise<void> {
    if (await this.shipmentRepo.existsForOrder(event.orderId)) return; // redelivered event
    const shipment = Shipment.create(event.orderId, event.shippingAddress, event.items);
    await this.shipmentRepo.save(shipment);
  }
}
