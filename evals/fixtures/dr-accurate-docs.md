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

// Signature: createInvoice(customerId, currency, taxRegion)
const invoice = createInvoice("cust_123", "USD", "US-CA");
invoice.addItem("Consulting", 1500);
```

Export an invoice to HTML from the command line:

```bash
npx invoicer export-html ./invoice.json
```

## API

### `createInvoice(customerId, currency, taxRegion)`

Returns a new `Invoice`. `currency` is an ISO-4217 string and `taxRegion` is a
tax jurisdiction code used to compute line-item tax.

## Current source (for reference)

The exported signature in `src/invoice.ts` matches the docs above:

```ts
// src/invoice.ts
export function createInvoice(
  customerId: string,
  currency: string,
  taxRegion: string,
): Invoice {
  /* ... */
}
```

And the registered CLI commands in `src/cli.ts` match the documented command:

```ts
// src/cli.ts — package.json "bin": { "invoicer": "./dist/cli.js" }
registerCommand("export-html", exportHtmlHandler);
registerCommand("validate", validateHandler);
```

## Changelog

- **v2.0** — Replaced `export-pdf` with `export-html`. Added the required
  `taxRegion` parameter to `createInvoice`. Both this README and the source
  above reflect the v2.0 contract.
