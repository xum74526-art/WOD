import type { OrderStatus, QuoteStatus, RequestStatus } from "@/lib/commerce-api";

export const requestStatusLabel: Record<RequestStatus, string> = {
  draft: "草稿", reviewing: "审核中", published: "开放报价", negotiating: "报价洽谈", matched: "已匹配",
  completed: "已完成", closed: "已关闭", expired: "已过期", rejected: "未通过",
};
export const quoteStatusLabel: Record<QuoteStatus, string> = {
  draft: "草稿", submitted: "已提交", shortlisted: "候选", accepted: "已接受", rejected: "未选中",
  withdrawn: "已撤回", expired: "已过期",
};
export const orderStatusLabel: Record<OrderStatus, string> = {
  paid: "待卖方交付", delivering: "待买家验收", disputed: "争议处理中",
  completed: "已完成", running: "服务中（历史订单）", done: "已到期", canceled: "已取消",
};
export const unitLabel: Record<string, string> = { server_hour: "整机·小时", gpu_hour: "GPU·小时", gpu_day: "GPU·天", unit: "台" };

export function formatDate(value?: string | null, locale = "zh-CN") {
  if (!value) return "—";
  return new Intl.DateTimeFormat(locale, { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

export function formatMoney(amount: string | null, currency: string, unit: string) {
  if (amount === null) return "预算面议";
  const value = Number(amount).toLocaleString("zh-CN", { maximumFractionDigits: 6 });
  if (unit === "order_total") return `${currency} ${value}`;
  return `${currency} ${value} / ${unitLabel[unit] ?? unit}`;
}

export function errorMessage(reason: unknown, fallback = "操作失败，请稍后重试") {
  return reason instanceof Error ? reason.message : fallback;
}
