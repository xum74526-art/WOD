"use client";

import { ADMIN_QUEUE_PAGE_SIZE, adminQueuePageCount, adminQueuePageRange } from "@/lib/admin-queue-pagination";

type AdminQueuePaginationProps = {
  page: number;
  total: number;
  pageSize?: number;
  loading?: boolean;
  onPageChange: (page: number) => void;
};

export function AdminQueuePagination({
  page,
  total,
  pageSize = ADMIN_QUEUE_PAGE_SIZE,
  loading = false,
  onPageChange,
}: AdminQueuePaginationProps) {
  if (total <= 0) return null;
  const pageCount = adminQueuePageCount(total, pageSize);
  const range = adminQueuePageRange(page, total, pageSize);

  return <nav className="community-page-nav admin-queue-pagination" aria-label="管理队列分页">
    <button type="button" disabled={loading || page <= 1} onClick={() => onPageChange(page - 1)}>上一页</button>
    <span aria-live="polite">第 {page} / {pageCount} 页 · {range.first}–{range.last} 条 · 共 {total} 条</span>
    <button type="button" disabled={loading || page >= pageCount} onClick={() => onPageChange(page + 1)}>下一页</button>
  </nav>;
}
