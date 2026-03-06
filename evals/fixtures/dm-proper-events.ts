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
    readonly shippingAddress: ShippingAddress,
    readonly items: ReadonlyArray<{ sku: string; quantity: number }>,
  ) {}
}

// Event bus abstraction — no knowledge of subscribers
interface EventBus {
  publish(event: DomainEvent): Promise<void>;
}

// Order context publishes events; does not call shipping directly
class OrderCompletionHandler {
  constructor(
    private readonly orderRepo: OrderRepository,
    private readonly eventBus: EventBus,
  ) {}

  async handle(paymentEvent: PaymentCompleted): Promise<void> {
    const order = await this.orderRepo.findById(paymentEvent.orderId);
    order.markPaid();
    await this.orderRepo.save(order);

    await this.eventBus.publish(
      new OrderFulfillmentRequested(
        order.id,
        order.shippingAddress,
        order.lineItems.map((li) => ({ sku: li.sku, quantity: li.quantity })),
      ),
    );
  }
}

// Shipping context listens independently — no import from order context
class ShipmentCreator {
  constructor(private readonly shipmentRepo: ShipmentRepository) {}

  async onFulfillmentRequested(event: OrderFulfillmentRequested): Promise<void> {
    const shipment = Shipment.create(event.orderId, event.shippingAddress, event.items);
    await this.shipmentRepo.save(shipment);
  }
}
