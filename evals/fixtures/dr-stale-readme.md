# invoicer

A small library for building and exporting invoices.

## Installation

```bash
npm install invoicer
```

## Usage

Create an invoice and add line items:

```ts
import { createInvoice } from "invoicer";

// Documented signature: createInvoice(customerId, currency)
const invoice = createInvoice("cust_123", "USD");
invoice.addItem("Consulting", 1500);
```

Export an invoice to PDF from the command line:

```bash
npx invoicer export-pdf ./invoice.json
```

## API

### `createInvoice(customerId, currency)`

Returns a new `Invoice`. `currency` is an ISO-4217 string.

## Current source (for reference)

The actual exported signature in `src/invoice.ts` today is:

```ts
// src/invoice.ts
export function createInvoice(
  customerId: string,
  currency: string,
  taxRegion: string, // added in v2.0 — required, no default
): Invoice {
  /* ... */
}
```

And the registered CLI commands in `src/cli.ts` today are:

```ts
// src/cli.ts — package.json "bin": { "invoicer": "./dist/cli.js" }
registerCommand("export-html", exportHtmlHandler);
registerCommand("validate", validateHandler);
```

## Changelog

- **v2.0** — Removed the `export-pdf` command (replaced by `export-html`).
  Added the required `taxRegion` parameter to `createInvoice`.
