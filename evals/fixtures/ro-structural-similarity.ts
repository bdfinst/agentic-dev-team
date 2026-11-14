const LIBRARY_GRACE_DAYS = 3;
const LATE_FEE_PER_DAY_CENTS = 25;
const LATE_FEE_CAP_CENTS = 1_000;

const EARLY_BOOKING_THRESHOLD_DAYS = 30;
const DISCOUNT_PER_DAY_PERCENT = 0.5;
const DISCOUNT_CAP_PERCENT = 20;

export function lateReturnFeeCents(daysLate: number): number {
  const chargeableDays = Math.max(0, daysLate - LIBRARY_GRACE_DAYS);
  return Math.min(chargeableDays * LATE_FEE_PER_DAY_CENTS, LATE_FEE_CAP_CENTS);
}

export function earlyBookingDiscountPercent(daysBeforeTravel: number): number {
  const qualifyingDays = Math.max(0, daysBeforeTravel - EARLY_BOOKING_THRESHOLD_DAYS);
  return Math.min(qualifyingDays * DISCOUNT_PER_DAY_PERCENT, DISCOUNT_CAP_PERCENT);
}
