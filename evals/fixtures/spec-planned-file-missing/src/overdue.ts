export const OVERDUE_AFTER_DAYS = 7;
const MS_PER_DAY = 24 * 60 * 60 * 1000;

export interface Invoice {
  readonly id: string;
  readonly dueDate: Date;
  readonly paid: boolean;
  readonly overdue: boolean;
}

export function markOverdue(
  invoices: readonly Invoice[],
  now: Date,
): Invoice[] {
  return invoices.map((invoice) => {
    const daysLate = (now.getTime() - invoice.dueDate.getTime()) / MS_PER_DAY;
    const isOverdue = !invoice.paid && daysLate > OVERDUE_AFTER_DAYS;
    return isOverdue ? { ...invoice, overdue: true } : invoice;
  });
}
