const RENEWAL_NOTICE_DAYS = 14;
const MILLISECONDS_PER_DAY = 86_400_000;

interface Subscription {
  subscriptionId: string;
  customerEmail: string;
  planName: string;
  renewsAt: Date;
  cancelledAt: Date | null;
  isAutoRenewEnabled: boolean;
}

interface RenewalNotice {
  subscriptionId: string;
  recipientEmail: string;
  planName: string;
  daysUntilRenewal: number;
}

function daysBetween(earlier: Date, later: Date): number {
  return Math.ceil(
    (later.getTime() - earlier.getTime()) / MILLISECONDS_PER_DAY,
  );
}

function isDueForRenewalNotice(
  subscription: Subscription,
  today: Date,
): boolean {
  const daysUntilRenewal = daysBetween(today, subscription.renewsAt);
  return daysUntilRenewal >= 0 && daysUntilRenewal <= RENEWAL_NOTICE_DAYS;
}

function buildRenewalNotice(
  subscription: Subscription,
  today: Date,
): RenewalNotice {
  return {
    subscriptionId: subscription.subscriptionId,
    recipientEmail: subscription.customerEmail,
    planName: subscription.planName,
    daysUntilRenewal: daysBetween(today, subscription.renewsAt),
  };
}

function collectRenewalNotices(
  subscriptions: Subscription[],
  today: Date,
): RenewalNotice[] {
  const activeSubscriptions = subscriptions.filter(
    (subscription) => subscription.cancelledAt !== null,
  );
  const autoRenewingSubscriptions = activeSubscriptions.filter(
    (subscription) => subscription.isAutoRenewEnabled,
  );
  return autoRenewingSubscriptions
    .filter((subscription) => isDueForRenewalNotice(subscription, today))
    .map((subscription) => buildRenewalNotice(subscription, today));
}

export { collectRenewalNotices, isDueForRenewalNotice, buildRenewalNotice };
