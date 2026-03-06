// PASS: Pure functional transforms — no mutations

interface Product {
  id: string;
  name: string;
  price: number;
  category: string;
  inStock: boolean;
}

const applyDiscount = (products: Product[], discountPct: number): Product[] =>
  products.map((product) => ({
    ...product,
    price: product.price * (1 - discountPct / 100),
  }));

const filterInStock = (products: Product[]): Product[] =>
  products.filter((product) => product.inStock);

const groupByCategory = (products: Product[]): Record<string, Product[]> =>
  products.reduce<Record<string, Product[]>>((acc, product) => {
    const existing = acc[product.category] ?? [];
    return { ...acc, [product.category]: [...existing, product] };
  }, {});

const totalRevenue = (products: Product[]): number =>
  products.reduce((sum, product) => sum + product.price, 0);

const enrichWithTags = (
  products: Product[],
  tagMap: Record<string, string[]>,
): (Product & { tags: string[] })[] =>
  products.map((product) => ({
    ...product,
    tags: tagMap[product.category] ?? [],
  }));

const paginateResults = <T>(items: T[], page: number, pageSize: number): T[] =>
  items.slice((page - 1) * pageSize, page * pageSize);

const buildSummary = (products: Product[]) => {
  const inStock = filterInStock(products);
  const grouped = groupByCategory(inStock);
  const categoryTotals = Object.entries(grouped).map(([category, items]) => ({
    category,
    count: items.length,
    revenue: totalRevenue(items),
  }));
  return { categoryTotals, totalProducts: inStock.length };
};

export {
  applyDiscount,
  filterInStock,
  groupByCategory,
  totalRevenue,
  enrichWithTags,
  paginateResults,
  buildSummary,
};
