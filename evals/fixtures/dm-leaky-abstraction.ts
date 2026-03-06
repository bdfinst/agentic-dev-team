// FAIL: Leaky abstractions — SQL in domain, HTTP in business logic, infra mixed with domain

import { Pool } from "pg";
import axios from "axios";

// Issue 1: Domain entity contains raw SQL queries
class Invoice {
  id: string;
  customerId: string;
  totalCents: number;
  status: string;

  async save(pool: Pool): Promise<void> {
    await pool.query(
      `INSERT INTO invoices (id, customer_id, total_cents, status)
       VALUES ($1, $2, $3, $4)
       ON CONFLICT (id) DO UPDATE SET status = $4, total_cents = $3`,
      [this.id, this.customerId, this.totalCents, this.status],
    );
  }

  async loadLineItems(pool: Pool): Promise<LineItem[]> {
    const result = await pool.query(
      "SELECT * FROM line_items WHERE invoice_id = $1 ORDER BY created_at",
      [this.id],
    );
    return result.rows;
  }
}

// Issue 2: Business logic depends on HTTP implementation details
class PricingService {
  constructor(private readonly pool: Pool) {}

  async calculateDiscount(customerId: string, subtotal: number): Promise<number> {
    // Fetches loyalty tier from external service using raw HTTP
    const response = await axios.get(
      `https://loyalty-api.internal/v2/customers/${customerId}/tier`,
      { headers: { "X-Service-Auth": process.env.LOYALTY_API_KEY } },
    );

    if (response.status !== 200) {
      throw new Error(`Loyalty API returned ${response.status}`);
    }

    const tier = response.data.tier;
    return tier === "gold" ? subtotal * 0.15 : tier === "silver" ? subtotal * 0.08 : 0;
  }
}

// Issue 3: Repository mixed into domain entity as a method
class Customer {
  name: string;
  email: string;

  // Domain entity directly queries the database
  async getOutstandingInvoices(pool: Pool): Promise<Invoice[]> {
    const { rows } = await pool.query(
      "SELECT * FROM invoices WHERE customer_id = $1 AND status = 'unpaid'",
      [this.id],
    );
    return rows.map((r) => Object.assign(new Invoice(), r));
  }
}

// Issue 4: Infrastructure error handling leaks into domain decisions
class PaymentProcessor {
  async charge(invoice: Invoice): Promise<void> {
    try {
      await axios.post("https://payments.stripe.com/v1/charges", {
        amount: invoice.totalCents,
        currency: "usd",
      });
      invoice.status = "paid";
    } catch (err: any) {
      // HTTP status codes driving business logic
      if (err.response?.status === 402) {
        invoice.status = "declined";
      } else if (err.response?.status === 429) {
        invoice.status = "retry_later";
      }
    }
  }
}
