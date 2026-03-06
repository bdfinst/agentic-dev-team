import { Request, Response } from "express";
import { db } from "./database";
import { logger } from "./logger";

/**
 * InvoiceProcessor handles the creation, validation, and processing
 * of invoices in the billing system. It manages line items, tax
 * calculations, discount applications, payment term assignments,
 * currency conversions, audit trail generation, notification dispatch,
 * PDF generation triggers, accounting system synchronization, and
 * regulatory compliance checks for multi-jurisdiction support.
 *
 * This class is used by the billing controller to process incoming
 * invoice requests from the API and from scheduled batch jobs.
 *
 * @class InvoiceProcessor
 * @since 2.0.0
 * @author billing-team
 * @see BillingController
 * @see PaymentService
 */
interface InvoiceLineItem {
  productId: string;
  quantity: number;
  unitPrice: number;
  taxRate: number;
  discount: number;
}

interface Invoice {
  id: string;
  customerId: string;
  lineItems: InvoiceLineItem[];
  status: string;
  total: number;
  tax: number;
  currency: string;
  createdAt: Date;
}

// /**
//  * Old invoice processor - replaced in v2.0
//  *
//  * function processInvoiceLegacy(data: any) {
//  *   const invoice = {
//  *     id: generateId(),
//  *     items: data.items.map((item: any) => ({
//  *       ...item,
//  *       total: item.qty * item.price,
//  *       tax: item.qty * item.price * 0.1,
//  *     })),
//  *     status: 'draft',
//  *     createdAt: new Date(),
//  *   };
//  *   return db.invoices.insert(invoice);
//  * }
//  */

async function handleCreateInvoice(req: Request, res: Response) {
  try {
    const { customerId, lineItems, currency, paymentTerms, notes } = req.body;

    // Validate customer exists
    const customer = await db.customer.findUnique({ where: { id: customerId } });
    if (!customer) {
      return res.status(404).json({ error: "Customer not found" });
    }

    // Validate customer is active
    if (customer.status !== "active") {
      return res.status(400).json({ error: "Customer account is not active" });
    }

    // Check customer credit limit
    const existingInvoices = await db.invoice.findMany({
      where: { customerId, status: { in: ["pending", "sent"] } },
    });
    let outstandingBalance = 0;
    for (const inv of existingInvoices) {
      outstandingBalance += inv.total;
    }
    if (customer.creditLimit && outstandingBalance > customer.creditLimit) {
      return res.status(400).json({ error: "Customer has exceeded credit limit" });
    }

    // Validate line items
    if (!lineItems || !Array.isArray(lineItems) || lineItems.length === 0) {
      return res.status(400).json({ error: "At least one line item required" });
    }

    // Process each line item
    const processedItems: InvoiceLineItem[] = [];
    let subtotal = 0;
    let totalTax = 0;
    let totalDiscount = 0;

    for (let i = 0; i < lineItems.length; i++) {
      const item = lineItems[i];
      // Validate product exists
      const product = await db.product.findUnique({ where: { id: item.productId } });
      if (!product) {
        return res.status(400).json({
          error: `Product not found: ${item.productId}`,
          lineItem: i,
        });
      }

      // Check product availability
      if (product.status !== "available") {
        if (product.status === "discontinued") {
          if (product.replacementId) {
            const replacement = await db.product.findUnique({
              where: { id: product.replacementId },
            });
            if (replacement) {
              if (replacement.status === "available") {
                logger.info(`Suggesting replacement product ${replacement.id}`);
                return res.status(400).json({
                  error: `Product ${item.productId} is discontinued`,
                  suggestion: `Use ${replacement.id} instead`,
                });
              } else {
                return res.status(400).json({
                  error: `Product ${item.productId} is discontinued and replacement is unavailable`,
                });
              }
            }
          }
          return res.status(400).json({
            error: `Product ${item.productId} is discontinued`,
          });
        }
        return res.status(400).json({
          error: `Product ${item.productId} is not available`,
        });
      }

      // Validate quantity
      if (!item.quantity || item.quantity <= 0) {
        return res.status(400).json({
          error: `Invalid quantity for line item ${i}`,
        });
      }

      // Calculate pricing
      const unitPrice = product.price;
      const lineTotal = unitPrice * item.quantity;

      // Apply volume discount
      let discount = 0;
      if (item.quantity >= 100) {
        discount = lineTotal * 0.15;
      } else if (item.quantity >= 50) {
        discount = lineTotal * 0.1;
      } else if (item.quantity >= 20) {
        discount = lineTotal * 0.05;
      }

      // Apply customer tier discount
      if (customer.tier === "platinum") {
        discount += (lineTotal - discount) * 0.1;
      } else if (customer.tier === "gold") {
        discount += (lineTotal - discount) * 0.05;
      }

      // Calculate tax based on jurisdiction
      let taxRate = 0;
      if (customer.country === "US") {
        if (customer.state === "CA") {
          taxRate = 0.0725;
        } else if (customer.state === "NY") {
          taxRate = 0.08;
        } else if (customer.state === "TX") {
          taxRate = 0.0625;
        } else if (customer.state === "FL") {
          taxRate = 0.06;
        } else {
          taxRate = 0.05;
        }
        if (product.category === "software") {
          if (customer.state === "CA" || customer.state === "NY") {
            taxRate = 0;
          }
        }
      } else if (customer.country === "GB") {
        taxRate = 0.2;
        if (product.category === "books" || product.category === "education") {
          taxRate = 0;
        }
      } else if (customer.country === "DE") {
        taxRate = 0.19;
      } else if (customer.country === "JP") {
        taxRate = 0.1;
      } else {
        taxRate = 0;
      }

      const taxAmount = (lineTotal - discount) * taxRate;

      processedItems.push({
        productId: item.productId,
        quantity: item.quantity,
        unitPrice,
        taxRate,
        discount,
      });

      subtotal += lineTotal;
      totalTax += taxAmount;
      totalDiscount += discount;
    }

    // Currency conversion
    let conversionRate = 1;
    if (currency && currency !== "USD") {
      const rate = await db.exchangeRate.findFirst({
        where: { from: "USD", to: currency },
        orderBy: { date: "desc" },
      });
      if (!rate) {
        return res.status(400).json({ error: `Unsupported currency: ${currency}` });
      }
      conversionRate = rate.rate;
    }

    const total = (subtotal - totalDiscount + totalTax) * conversionRate;

    // Create invoice
    const invoice = await db.invoice.create({
      data: {
        customerId,
        lineItems: { create: processedItems },
        subtotal: subtotal * conversionRate,
        discount: totalDiscount * conversionRate,
        tax: totalTax * conversionRate,
        total,
        currency: currency || "USD",
        status: "draft",
        paymentTerms: paymentTerms || "net30",
        notes: notes || null,
      },
    });

    // Create audit log entry
    await db.auditLog.create({
      data: {
        action: "invoice.created",
        entityType: "invoice",
        entityId: invoice.id,
        userId: req.user?.id || "system",
        metadata: { customerId, itemCount: processedItems.length, total },
      },
    });

    logger.info(`Invoice created: ${invoice.id}, total: ${total}`);

    return res.status(201).json(invoice);
  } catch (error) {
    logger.error("Failed to create invoice", error);
    return res.status(500).json({ error: "Internal server error" });
  }
}

// // Old report generation code - keeping for reference
// async function generateMonthlyReport(month: number, year: number) {
//   const start = new Date(year, month - 1, 1);
//   const end = new Date(year, month, 0);
//   const invoices = await db.invoice.findMany({
//     where: { createdAt: { gte: start, lte: end } },
//   });
//   const total = invoices.reduce((sum, inv) => sum + inv.total, 0);
//   const byStatus = {};
//   for (const inv of invoices) {
//     byStatus[inv.status] = (byStatus[inv.status] || 0) + 1;
//   }
//   return { month, year, total, count: invoices.length, byStatus };
// }

async function handleGetInvoiceReport(req: Request, res: Response) {
  try {
    const { startDate, endDate, customerId, status, groupBy, format } = req.query;

    // Parse and validate dates
    const start = startDate ? new Date(String(startDate)) : new Date(Date.now() - 30 * 24 * 60 * 60 * 1000);
    const end = endDate ? new Date(String(endDate)) : new Date();

    if (isNaN(start.getTime())) {
      return res.status(400).json({ error: "Invalid start date" });
    }
    if (isNaN(end.getTime())) {
      return res.status(400).json({ error: "Invalid end date" });
    }
    if (start > end) {
      return res.status(400).json({ error: "Start date must be before end date" });
    }

    // Build query filters
    const where: Record<string, unknown> = {
      createdAt: { gte: start, lte: end },
    };
    if (customerId) {
      where.customerId = String(customerId);
    }
    if (status) {
      where.status = String(status);
    }

    // Fetch invoices
    const invoices = await db.invoice.findMany({
      where,
      include: { lineItems: true, customer: true },
      orderBy: { createdAt: "desc" },
    });

    // Calculate totals
    let totalRevenue = 0;
    let totalTax = 0;
    let totalDiscount = 0;
    const statusCounts: Record<string, number> = {};
    const customerTotals: Record<string, number> = {};
    const monthlyTotals: Record<string, number> = {};

    for (const invoice of invoices) {
      totalRevenue += invoice.total;
      totalTax += invoice.tax;
      totalDiscount += invoice.discount || 0;

      // Count by status
      statusCounts[invoice.status] = (statusCounts[invoice.status] || 0) + 1;

      // Sum by customer
      const custName = invoice.customer?.name || "Unknown";
      customerTotals[custName] = (customerTotals[custName] || 0) + invoice.total;

      // Sum by month
      const monthKey = `${invoice.createdAt.getFullYear()}-${String(invoice.createdAt.getMonth() + 1).padStart(2, "0")}`;
      monthlyTotals[monthKey] = (monthlyTotals[monthKey] || 0) + invoice.total;
    }

    // Build report
    const report = {
      period: { start, end },
      summary: {
        invoiceCount: invoices.length,
        totalRevenue,
        totalTax,
        totalDiscount,
        averageInvoice: invoices.length > 0 ? totalRevenue / invoices.length : 0,
      },
      byStatus: statusCounts,
      byCustomer: customerTotals,
      byMonth: monthlyTotals,
    };

    return res.json(report);
  } catch (error) {
    logger.error("Failed to generate report", error);
    return res.status(500).json({ error: "Internal server error" });
  }
}

export { handleCreateInvoice, handleGetInvoiceReport };
