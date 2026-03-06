// FAIL: UI rendering, business logic, and data access tangled together

interface Order {
  id: string;
  items: { name: string; qty: number; unitPrice: number }[];
  customerId: string;
  status: string;
}

const db: any = require("./db");

async function renderOrderPage(orderId: string): Promise<string> {
  // data access
  const order: Order = await db.query("SELECT * FROM orders WHERE id = ?", [orderId]);
  const customer = await db.query("SELECT * FROM customers WHERE id = ?", [order.customerId]);

  // business logic — discount calculation
  let subtotal = 0;
  for (const item of order.items) {
    subtotal += item.qty * item.unitPrice;
  }
  let discount = 0;
  if (customer.tier === "gold") discount = subtotal * 0.15;
  else if (customer.tier === "silver") discount = subtotal * 0.08;
  const tax = (subtotal - discount) * 0.09;
  const total = subtotal - discount + tax;

  // UI rendering
  let html = `<div class="order-page">`;
  html += `<h1>Order #${order.id}</h1>`;
  html += `<p>Customer: ${customer.name} (${customer.tier})</p>`;
  html += `<table><tr><th>Item</th><th>Qty</th><th>Price</th></tr>`;
  for (const item of order.items) {
    html += `<tr><td>${item.name}</td><td>${item.qty}</td><td>$${(item.qty * item.unitPrice).toFixed(2)}</td></tr>`;
  }
  html += `</table>`;
  html += `<p>Subtotal: $${subtotal.toFixed(2)}</p>`;
  html += `<p>Discount: -$${discount.toFixed(2)}</p>`;
  html += `<p>Tax: $${tax.toFixed(2)}</p>`;
  html += `<h2>Total: $${total.toFixed(2)}</h2>`;
  html += `</div>`;
  return html;
}

async function renderInventoryReport(): Promise<string> {
  const products = await db.query("SELECT * FROM products WHERE stock > 0");

  // business logic — stock status
  const rows = products.map((p: any) => {
    let status = "OK";
    if (p.stock < 5) status = "CRITICAL";
    else if (p.stock < 20) status = "LOW";
    const value = p.stock * p.cost;
    return { ...p, status, value };
  });

  // UI rendering
  let html = `<div class="inventory"><h1>Inventory Report</h1><table>`;
  html += `<tr><th>Product</th><th>Stock</th><th>Status</th><th>Value</th></tr>`;
  for (const r of rows) {
    const cls = r.status === "CRITICAL" ? "danger" : r.status === "LOW" ? "warn" : "";
    html += `<tr class="${cls}"><td>${r.name}</td><td>${r.stock}</td><td>${r.status}</td><td>$${r.value.toFixed(2)}</td></tr>`;
  }
  html += `</table></div>`;
  return html;
}

export { renderOrderPage, renderInventoryReport };
