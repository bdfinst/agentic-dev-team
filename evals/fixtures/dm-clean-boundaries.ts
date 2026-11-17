// PASS: Clean domain boundaries — entities, DTOs, and coordinating services

// Domain entity with business logic encapsulated
class Order {
  private items: OrderItem[] = [];
  private status: OrderStatus = OrderStatus.Draft;

  constructor(readonly id: string) {}

  addItem(product: Product, quantity: number): void {
    if (this.status !== OrderStatus.Draft) throw new OrderNotEditableError(this.status);
    if (quantity <= 0) throw new InvalidQuantityError(quantity);
    const existing = this.items.find((i) => i.productId === product.id);
    if (existing) {
      existing.increaseQuantity(quantity);
    } else {
      this.items.push(new OrderItem(product.id, product.priceCents, quantity));
    }
  }

  submit(): void {
    if (this.items.length === 0) throw new EmptyOrderError();
    if (this.status !== OrderStatus.Draft) throw new InvalidTransitionError(this.status, OrderStatus.Submitted);
    this.status = OrderStatus.Submitted;
  }

  get totalCents(): number {
    return this.items.reduce((sum, item) => sum + item.lineTotalCents, 0);
  }

  get itemCount(): number {
    return this.items.length;
  }

  get statusLabel(): string {
    return this.status;
  }
}

// DTO for API boundary — no business logic, flat structure
interface OrderResponseDto {
  orderId: string;
  totalCents: number;
  itemCount: number;
  status: string;
}

// Service coordinates but contains no business rules
class OrderService {
  constructor(
    private readonly orderRepo: OrderRepository,
    private readonly mapper: OrderMapper,
  ) {}

  async submitOrder(orderId: string): Promise<OrderResponseDto> {
    const order = await this.orderRepo.findById(orderId);
    if (!order) throw new OrderNotFoundError(orderId);
    order.submit();
    await this.orderRepo.save(order);
    return this.mapper.toDto(order);
  }
}

// Mapper handles translation between domain and DTO
class OrderMapper {
  toDto(order: Order): OrderResponseDto {
    return {
      orderId: order.id,
      totalCents: order.totalCents,
      itemCount: order.itemCount,
      status: order.statusLabel,
    };
  }
}
