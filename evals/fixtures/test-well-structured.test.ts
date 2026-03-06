import { createInvoice, InvoiceStatus } from "../billing";

describe("createInvoice", () => {
  it("creates an invoice with the correct line items and total", () => {
    // Arrange
    const lineItems = [
      { description: "Widget A", quantity: 2, unitPrice: 10.0 },
      { description: "Widget B", quantity: 1, unitPrice: 25.5 },
    ];

    // Act
    const invoice = createInvoice("customer-123", lineItems);

    // Assert
    expect(invoice.customerId).toBe("customer-123");
    expect(invoice.lineItems).toHaveLength(2);
    expect(invoice.total).toBe(45.5);
    expect(invoice.status).toBe(InvoiceStatus.Draft);
  });

  it("generates a unique invoice ID for each call", () => {
    const items = [{ description: "Item", quantity: 1, unitPrice: 5 }];

    const first = createInvoice("cust-1", items);
    const second = createInvoice("cust-1", items);

    expect(first.id).not.toBe(second.id);
    expect(first.id).toMatch(/^INV-/);
  });

  it("throws when line items array is empty", () => {
    expect(() => createInvoice("cust-1", [])).toThrow(
      "Invoice must have at least one line item"
    );
  });

  it("resolves pending invoice asynchronously", async () => {
    const items = [{ description: "Item", quantity: 1, unitPrice: 100 }];
    const invoice = createInvoice("cust-1", items);

    const result = await invoice.submit();

    expect(result.status).toBe(InvoiceStatus.Pending);
    expect(result.submittedAt).toBeInstanceOf(Date);
  });
});
