/**
 * Money formatting for invoices and receipts.
 *
 * Amounts are integer minor units (cents for USD). Currency codes follow
 * ISO 4217, and timestamps on receipts use the RFC-3339 profile of ISO-8601.
 */

/** Minor-unit exponent per ISO 4217 currency code; JPY has no minor unit. */
const MINOR_UNIT_DIGITS: Record<string, number> = {
  USD: 2,
  EUR: 2,
  GBP: 2,
  JPY: 0,
};

/**
 * Formats an amount of minor units as a localized currency string.
 *
 * @param amountMinor - The amount in minor units, for example 1999 for $19.99.
 * @param currency - An ISO 4217 code listed in `MINOR_UNIT_DIGITS`.
 * @param locale - An RFC-5646 language tag such as `en-US` or `de-DE`.
 * @returns The formatted amount, for example `$19.99` or `19,99 €`.
 * @throws RangeError when `currency` is not listed in `MINOR_UNIT_DIGITS`.
 */
export function formatMoney(
  amountMinor: number,
  currency: string,
  locale: string,
): string {
  const digits = MINOR_UNIT_DIGITS[currency];
  if (digits === undefined) {
    throw new RangeError(`Unsupported currency: ${currency}`);
  }
  const major = amountMinor / 10 ** digits;
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency,
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(major);
}

/**
 * Formats a receipt timestamp as an RFC-3339 string in UTC.
 *
 * @param issuedAt - When the receipt was issued.
 * @returns The timestamp, for example `2026-03-01T12:00:00.000Z`.
 */
export function formatReceiptTimestamp(issuedAt: Date): string {
  return issuedAt.toISOString();
}

/**
 * Sums line-item amounts. All amounts must share one currency, so the caller
 * converts before summing.
 *
 * @param amountsMinor - Line-item amounts in minor units.
 * @returns The total in minor units; 0 for an empty list.
 */
export function sumMinorUnits(amountsMinor: readonly number[]): number {
  return amountsMinor.reduce((total, amount) => total + amount, 0);
}
