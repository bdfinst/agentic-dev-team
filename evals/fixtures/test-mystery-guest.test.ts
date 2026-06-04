import { readFileSync } from "fs";
import { InvoiceParser } from "../domain/InvoiceParser";

// Smell: Mystery Guest — the test depends on external data it does not
// create or show. The reader cannot see the inputs; the file on disk and
// the seeded DB row can drift and silently break the test.
describe("InvoiceParser", () => {
  it("parses the sample invoice", () => {
    // Where does this file come from? What's in it? Invisible to the reader.
    const raw = readFileSync("./test/fixtures/sample-invoice.xml", "utf8");

    const invoice = new InvoiceParser().parse(raw);

    // Magic expected values tied to an unseen external file.
    expect(invoice.total).toBe(1499.0);
    expect(invoice.lineItems).toHaveLength(7);
  });
});
