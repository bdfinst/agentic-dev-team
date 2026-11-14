// Builds the nightly ledger export: normalizes every raw ledger row posted in
// the export window (typically 200k-400k rows), groups them by account and
// month, computes running balances, and renders CSV.

export type Currency = "USD" | "EUR" | "GBP";

export interface RawLedgerRow {
  entryId: string;
  accountId: string;
  postedAt: string;
  amountMinor: number;
  currency: Currency;
  memo: string | null;
  reversalOf: string | null;
}

export interface LedgerEntry {
  entryId: string;
  accountId: string;
  postedAt: Date;
  monthKey: string;
  amountMinor: number;
  currency: Currency;
  memo: string;
  isReversal: boolean;
}

export interface AccountMonth {
  accountId: string;
  monthKey: string;
  currency: Currency;
  openingMinor: number;
  creditsMinor: number;
  debitsMinor: number;
  closingMinor: number;
  entryCount: number;
}

export interface ExportOptions {
  fromMonth: string;
  toMonth: string;
  includeReversals: boolean;
  delimiter: "," | ";";
}

export interface ExportResult {
  csv: string;
  accountCount: number;
  entryCount: number;
  skippedCount: number;
}

const MINOR_UNITS: Record<Currency, number> = { USD: 100, EUR: 100, GBP: 100 };
const CSV_HEADER = [
  "account_id",
  "month",
  "currency",
  "opening",
  "credits",
  "debits",
  "closing",
  "entries",
] as const;

// ---------------------------------------------------------------------------
// Parsing and validation
// ---------------------------------------------------------------------------

export function toMonthKey(date: Date): string {
  const month = String(date.getUTCMonth() + 1).padStart(2, "0");
  return `${date.getUTCFullYear()}-${month}`;
}

export function parsePostedAt(value: string): Date | null {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function isWithinRange(monthKey: string, options: ExportOptions): boolean {
  return monthKey >= options.fromMonth && monthKey <= options.toMonth;
}

export function normalizeMemo(memo: string | null): string {
  if (memo === null) return "";
  return memo.replace(/\s+/g, " ").trim();
}

export function toEntry(row: RawLedgerRow): LedgerEntry | null {
  const postedAt = parsePostedAt(row.postedAt);
  if (postedAt === null) return null;
  if (!Number.isInteger(row.amountMinor)) return null;
  return {
    entryId: row.entryId,
    accountId: row.accountId,
    postedAt,
    monthKey: toMonthKey(postedAt),
    amountMinor: row.amountMinor,
    currency: row.currency,
    memo: normalizeMemo(row.memo),
    isReversal: row.reversalOf !== null,
  };
}

// The upstream ledger feed can deliver the same entry twice when a batch is
// retried, so entries are de-duplicated by entryId, keeping the first copy.
export function dedupeEntries(entries: readonly LedgerEntry[]): LedgerEntry[] {
  return entries.filter(
    (entry, index) =>
      entries.findIndex((other) => other.entryId === entry.entryId) === index,
  );
}

export function selectEntries(
  rows: readonly RawLedgerRow[],
  options: ExportOptions,
): { entries: LedgerEntry[]; skippedCount: number } {
  const parsed = rows.map(toEntry);
  const valid = parsed.filter((entry): entry is LedgerEntry => entry !== null);
  const inRange = valid.filter((entry) => isWithinRange(entry.monthKey, options));
  const visible = options.includeReversals
    ? inRange
    : inRange.filter((entry) => !entry.isReversal);
  return {
    entries: dedupeEntries(visible),
    skippedCount: rows.length - valid.length,
  };
}

// ---------------------------------------------------------------------------
// Grouping
// ---------------------------------------------------------------------------

export function groupKey(accountId: string, monthKey: string): string {
  return `${accountId}|${monthKey}`;
}

export function groupByAccountMonth(
  entries: readonly LedgerEntry[],
): Map<string, LedgerEntry[]> {
  const groups = new Map<string, LedgerEntry[]>();
  for (const entry of entries) {
    const key = groupKey(entry.accountId, entry.monthKey);
    const bucket = groups.get(key);
    if (bucket) {
      bucket.push(entry);
    } else {
      groups.set(key, [entry]);
    }
  }
  return groups;
}

export function sortGroupKeys(keys: Iterable<string>): string[] {
  return [...keys].sort((left, right) => left.localeCompare(right));
}

// ---------------------------------------------------------------------------
// Balances
// ---------------------------------------------------------------------------

export function sumCredits(entries: readonly LedgerEntry[]): number {
  return entries
    .filter((entry) => entry.amountMinor > 0)
    .reduce((total, entry) => total + entry.amountMinor, 0);
}

export function sumDebits(entries: readonly LedgerEntry[]): number {
  return entries
    .filter((entry) => entry.amountMinor < 0)
    .reduce((total, entry) => total + entry.amountMinor, 0);
}

export function summarizeMonth(
  accountId: string,
  monthKey: string,
  entries: readonly LedgerEntry[],
  openingMinor: number,
): AccountMonth {
  const creditsMinor = sumCredits(entries);
  const debitsMinor = sumDebits(entries);
  return {
    accountId,
    monthKey,
    currency: entries[0].currency,
    openingMinor,
    creditsMinor,
    debitsMinor,
    closingMinor: openingMinor + creditsMinor + debitsMinor,
    entryCount: entries.length,
  };
}

export function buildAccountMonths(
  groups: ReadonlyMap<string, LedgerEntry[]>,
  openingBalances: ReadonlyMap<string, number>,
): AccountMonth[] {
  const closingByAccount = new Map<string, number>();
  const months: AccountMonth[] = [];
  for (const key of sortGroupKeys(groups.keys())) {
    const [accountId, monthKey] = key.split("|");
    const entries = groups.get(key) ?? [];
    const opening =
      closingByAccount.get(accountId) ?? openingBalances.get(accountId) ?? 0;
    const month = summarizeMonth(accountId, monthKey, entries, opening);
    closingByAccount.set(accountId, month.closingMinor);
    months.push(month);
  }
  return months;
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

export function formatMinor(amountMinor: number, currency: Currency): string {
  const units = MINOR_UNITS[currency];
  const sign = amountMinor < 0 ? "-" : "";
  const absolute = Math.abs(amountMinor);
  const whole = Math.floor(absolute / units);
  const fraction = String(absolute % units).padStart(2, "0");
  return `${sign}${whole}.${fraction}`;
}

export function escapeCell(value: string, delimiter: string): string {
  const needsQuotes =
    value.includes(delimiter) || value.includes('"') || value.includes("\n");
  return needsQuotes ? `"${value.replace(/"/g, '""')}"` : value;
}

export function renderRow(month: AccountMonth, delimiter: string): string {
  const cells = [
    month.accountId,
    month.monthKey,
    month.currency,
    formatMinor(month.openingMinor, month.currency),
    formatMinor(month.creditsMinor, month.currency),
    formatMinor(month.debitsMinor, month.currency),
    formatMinor(month.closingMinor, month.currency),
    String(month.entryCount),
  ];
  return cells.map((cell) => escapeCell(cell, delimiter)).join(delimiter);
}

export function renderCsv(
  months: readonly AccountMonth[],
  delimiter: string,
): string {
  const lines = [
    CSV_HEADER.join(delimiter),
    ...months.map((month) => renderRow(month, delimiter)),
  ];
  return `${lines.join("\n")}\n`;
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

export function buildLedgerExport(
  rows: readonly RawLedgerRow[],
  openingBalances: ReadonlyMap<string, number>,
  options: ExportOptions,
): ExportResult {
  const { entries, skippedCount } = selectEntries(rows, options);
  const groups = groupByAccountMonth(entries);
  const months = buildAccountMonths(groups, openingBalances);
  const accountCount = new Set(months.map((month) => month.accountId)).size;
  return {
    csv: renderCsv(months, options.delimiter),
    accountCount,
    entryCount: entries.length,
    skippedCount,
  };
}
