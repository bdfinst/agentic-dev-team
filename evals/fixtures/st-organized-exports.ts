// PASS: Clean file organization, consistent exports, no circular deps

// --- Types ---

export interface PaginationParams {
  page: number;
  pageSize: number;
}

export interface PaginatedResult<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
  hasNext: boolean;
}

// --- Constants ---

export const DEFAULT_PAGE_SIZE = 25;
export const MAX_PAGE_SIZE = 100;

// --- Helpers ---

export function clampPageSize(size: number): number {
  return Math.min(Math.max(1, size), MAX_PAGE_SIZE);
}

export function buildPaginatedResult<T>(
  items: T[],
  total: number,
  params: PaginationParams,
): PaginatedResult<T> {
  const pageSize = clampPageSize(params.pageSize);
  return {
    items,
    total,
    page: params.page,
    pageSize,
    hasNext: params.page * pageSize < total,
  };
}

// --- Factory ---

export function defaultPagination(): PaginationParams {
  return { page: 1, pageSize: DEFAULT_PAGE_SIZE };
}
