// FAIL: Single function >40 lines with >10 branches and >5 parameters

interface ProcessResult {
  success: boolean;
  message: string;
  data?: any;
}

function processTransaction(
  userId: string,
  amount: number,
  currency: string,
  paymentMethod: string,
  discountCode: string | null,
  retryCount: number,
  dryRun: boolean
): ProcessResult {
  if (!userId) {
    return { success: false, message: "Missing user ID" };
  }
  if (amount <= 0) {
    return { success: false, message: "Invalid amount" };
  }
  if (!["USD", "EUR", "GBP", "JPY", "CAD"].includes(currency)) {
    return { success: false, message: "Unsupported currency" };
  }

  let finalAmount = amount;
  if (discountCode === "VIP50") {
    finalAmount = amount * 0.5;
  } else if (discountCode === "SAVE20") {
    finalAmount = amount * 0.8;
  } else if (discountCode === "FLAT10") {
    finalAmount = amount - 10 > 0 ? amount - 10 : amount;
  } else if (discountCode !== null) {
    return { success: false, message: "Unknown discount code" };
  }

  if (currency === "JPY") {
    finalAmount = Math.round(finalAmount);
  } else {
    finalAmount = Math.round(finalAmount * 100) / 100;
  }

  if (paymentMethod === "credit_card") {
    if (finalAmount > 10000) {
      return { success: false, message: "Amount exceeds credit card limit" };
    }
  } else if (paymentMethod === "debit") {
    if (finalAmount > 5000) {
      return { success: false, message: "Amount exceeds debit limit" };
    }
  } else if (paymentMethod === "wire") {
    if (finalAmount < 100) {
      return { success: false, message: "Wire minimum not met" };
    }
  } else if (paymentMethod === "crypto") {
    if (currency !== "USD") {
      return { success: false, message: "Crypto only supports USD" };
    }
  } else {
    return { success: false, message: "Unknown payment method" };
  }

  if (dryRun) {
    return { success: true, message: "Dry run complete", data: { finalAmount } };
  }

  if (retryCount > 3) {
    return { success: false, message: "Max retries exceeded" };
  }

  const transactionId = `txn_${userId}_${Date.now()}`;
  return {
    success: true,
    message: "Transaction processed",
    data: { transactionId, finalAmount, currency },
  };
}
