export const ADMIN_QUEUE_PAGE_SIZE = 20;

function nonNegativeInteger(value: number) {
  return Number.isFinite(value) ? Math.max(0, Math.trunc(value)) : 0;
}

export function adminQueuePageCount(total: number, pageSize = ADMIN_QUEUE_PAGE_SIZE) {
  const safeTotal = nonNegativeInteger(total);
  const safePageSize = Math.max(1, nonNegativeInteger(pageSize));
  return Math.max(1, Math.ceil(safeTotal / safePageSize));
}

export function adminQueuePageRange(page: number, total: number, pageSize = ADMIN_QUEUE_PAGE_SIZE) {
  const safeTotal = nonNegativeInteger(total);
  const safePageSize = Math.max(1, nonNegativeInteger(pageSize));
  const safePage = Math.min(
    adminQueuePageCount(safeTotal, safePageSize),
    Math.max(1, nonNegativeInteger(page)),
  );
  if (safeTotal === 0) return { first: 0, last: 0 };
  const first = (safePage - 1) * safePageSize + 1;
  return { first, last: Math.min(safeTotal, first + safePageSize - 1) };
}
