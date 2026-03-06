// FAIL: Hardcoded numbers and strings without named constants or enums.

interface Invoice {
  amount: number;
  currency: string;
  status: string;
  createdAt: number;
}

function calculateLateFee(invoice: Invoice): number {
  const now = Date.now() / 1000;
  const ageInDays = (now - invoice.createdAt) / 86400; // issue: magic 86400

  if (ageInDays > 30) {
    return invoice.amount * 0.15; // issue: magic 0.15
  }
  if (ageInDays > 14) {
    return invoice.amount * 0.05; // issue: magic 0.05
  }
  return 0;
}

function formatFileSize(bytes: number): string {
  if (bytes >= 1073741824) { // issue: magic 1073741824
    return (bytes / 1073741824).toFixed(2) + " GB";
  }
  if (bytes >= 1048576) {
    return (bytes / 1048576).toFixed(2) + " MB";
  }
  if (bytes >= 1024) { // issue: magic 1024
    return (bytes / 1024).toFixed(2) + " KB";
  }
  return bytes + " B";
}

function getInvoiceLabel(invoice: Invoice): string {
  if (invoice.status === "pd") { // issue: magic string abbreviation
    return "Paid";
  }
  if (invoice.status === "ov") {
    return "Overdue";
  }
  if (invoice.status === "dr") {
    return "Draft";
  }
  return "Unknown";
}

function isEligibleForDiscount(amount: number, itemCount: number): boolean {
  return amount > 250 && itemCount >= 3; // two more magic numbers
}
