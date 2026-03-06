// FAIL: Duplicated logic across functions with only minor variations

interface Product {
  id: string;
  name: string;
  price: number;
  category: string;
}

function formatProductForAdmin(product: Product): string {
  const label = product.name.trim().toUpperCase();
  const price = `$${product.price.toFixed(2)}`;
  const category = product.category.toLowerCase().replace(/\s+/g, "-");
  return `[ADMIN] ${label} | ${price} | cat:${category} | id:${product.id}`;
}

function formatProductForCustomer(product: Product): string {
  const label = product.name.trim().toUpperCase();
  const price = `$${product.price.toFixed(2)}`;
  const category = product.category.toLowerCase().replace(/\s+/g, "-");
  return `${label} — ${price} (${category})`;
}

function formatProductForCsv(product: Product): string {
  const label = product.name.trim().toUpperCase();
  const price = `$${product.price.toFixed(2)}`;
  const category = product.category.toLowerCase().replace(/\s+/g, "-");
  return `"${label}","${price}","${category}","${product.id}"`;
}

function validateAdminProduct(p: Product): string[] {
  const errors: string[] = [];
  if (!p.name || p.name.length < 2) errors.push("Name too short");
  if (p.price < 0) errors.push("Price cannot be negative");
  if (!p.category) errors.push("Category required");
  if (!p.id) errors.push("ID required");
  return errors;
}

function validateCustomerProduct(p: Product): string[] {
  const errors: string[] = [];
  if (!p.name || p.name.length < 2) errors.push("Name too short");
  if (p.price < 0) errors.push("Price cannot be negative");
  if (!p.category) errors.push("Category required");
  return errors;
}

function validateCsvProduct(p: Product): string[] {
  const errors: string[] = [];
  if (!p.name || p.name.length < 2) errors.push("Name too short");
  if (p.price < 0) errors.push("Price cannot be negative");
  if (!p.category) errors.push("Category required");
  if (!p.id) errors.push("ID required");
  return errors;
}

export {
  formatProductForAdmin,
  formatProductForCustomer,
  formatProductForCsv,
  validateAdminProduct,
  validateCustomerProduct,
  validateCsvProduct,
};
