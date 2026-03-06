// FAIL: Domain entities used directly as API responses, no boundary objects

import { Entity, Column, PrimaryGeneratedColumn, OneToMany } from "typeorm";

// Issue 1: ORM entity exposed directly to API consumers
@Entity("users")
export class User {
  @PrimaryGeneratedColumn("uuid")
  id: string;

  @Column()
  email: string;

  @Column()
  passwordHash: string; // Sensitive field — no DTO means this can leak

  @Column({ name: "failed_login_attempts" })
  failedLoginAttempts: number;

  @Column({ name: "internal_notes", nullable: true })
  internalNotes: string | null; // Internal-only field exposed to clients

  @Column({ name: "created_at" })
  createdAt: Date;

  @OneToMany(() => Order, (order) => order.user)
  orders: Order[];
}

// Issue 2: Domain entity returned directly from API route
export async function getUser(req: any, res: any) {
  const userRepo = getRepository(User);
  const user = await userRepo.findOne({ where: { id: req.params.id }, relations: ["orders"] });
  // Sends the full entity including passwordHash, internalNotes, failedLoginAttempts
  return res.json(user);
}

// Issue 3: Another entity with database column names leaking to clients
@Entity("products")
export class Product {
  @PrimaryGeneratedColumn()
  id: number;

  @Column()
  name: string;

  @Column({ name: "cost_cents" })
  costCents: number; // Internal cost — should never reach clients

  @Column({ name: "markup_pct" })
  markupPct: number; // Internal pricing strategy exposed

  @Column({ name: "supplier_sku" })
  supplierSku: string; // Supplier details leaked to consumers

  @Column({ name: "is_discontinued", default: false })
  isDiscontinued: boolean;
}

// Issue 4: List endpoint returns raw entities with no transformation
export async function listProducts(req: any, res: any) {
  const products = await getRepository(Product).find();
  // costCents, markupPct, and supplierSku all sent to the client
  return res.json({ products, count: products.length });
}

// Issue 5: Search returns join results with no boundary shaping
export async function searchOrders(req: any, res: any) {
  const orders = await getRepository(Order)
    .createQueryBuilder("order")
    .leftJoinAndSelect("order.user", "user")
    .where("order.status = :status", { status: req.query.status })
    .getMany();
  // Nested user entities (with passwordHash) included in response
  return res.json(orders);
}
