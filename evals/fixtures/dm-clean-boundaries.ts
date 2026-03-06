// PASS: Clean domain boundaries — entities, DTOs, and coordinating services

// Domain entity with business logic encapsulated
class Order {
  private items: OrderItem[] = [];
  private status: OrderStatus = OrderStatus.Draft;

  addItem(product: Product, quantity: number): void {
    if (quantity <= 0) throw new InvalidQuantityError(quantity);
    const existing = this.items.find((i) => i.productId === product.id);
    if (existing) {
      existing.increaseQuantity(quantity);
    } else {
      this.items.push(new OrderItem(product.id, product.price, quantity));
    }
  }

  submit(): void {
    if (this.items.length === 0) throw new EmptyOrderError();
    if (this.status !== OrderStatus.Draft) throw new InvalidTransitionError(this.status, OrderStatus.Submitted);
    this.status = OrderStatus.Submitted;
  }

  get total(): number {
    return this.items.reduce((sum, item) => sum + item.lineTotal, 0);
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
      totalCents: order.total,
      itemCount: order.itemCount,
      status: order.statusLabel,
    };
  }
}
