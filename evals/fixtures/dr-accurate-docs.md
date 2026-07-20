# invoicer

A small library for building and exporting invoices.

## Installation

```bash
npm install invoicer
```

## Usage

Create an invoice, add line items, and export it:

```ts
import { createInvoice } from "invoicer";

// createInvoice(customerId, currency, taxRegion)
const invoice = createInvoice("cust_123", "USD", "US-CA");
// addItem(description, amountCents)
invoice.addItem("Consulting", 1500);
```

From the command line:

```bash
npx invoicer export-html ./invoice.json   # render an invoice to HTML
npx invoicer validate ./invoice.json      # validate an invoice file
```

## API

### `createInvoice(customerId, currency, taxRegion)`

Returns a new `Invoice`. `currency` is an ISO-4217 string and `taxRegion` is a
tax jurisdiction code used to compute line-item tax.

### `Invoice.addItem(description, amountCents)`

Appends a line item with the given description and integer cent amount.

### CLI commands

- `export-html <file>` — renders the invoice to HTML.
- `validate <file>` — validates the invoice file's shape.

## Current source (for reference)

Every symbol and command documented above appears in the source below, and the
source exposes nothing the docs omit — the README and the implementation are a
one-to-one match.

```ts
// src/invoice.ts
export function createInvoice(
  customerId: string,
  currency: string,
  taxRegion: string,
): Invoice {
  /* ... */
}

export class Invoice {
  addItem(description: string, amountCents: number): void {
    /* ... */
  }
}
```

```ts
// src/cli.ts — package.json "bin": { "invoicer": "./dist/cli.js" }
registerCommand("export-html", exportHtmlHandler);
registerCommand("validate", validateHandler);
```

## Changelog

- **v2.0** — Replaced `export-pdf` with `export-html`. Added the required
  `taxRegion` parameter to `createInvoice`. Both this README and the source
  above reflect the v2.0 contract exactly.
