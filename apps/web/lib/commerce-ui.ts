import type { OrderStatus } from "@/lib/commerce-api";
import { formatFinancialAmount } from "@/lib/financial-format";

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
  const value = formatFinancialAmount(amount);
  if (unit === "order_total") return `${currency} ${value}`;
  return `${currency} ${value} / ${unitLabel[unit] ?? unit}`;
}

export function errorMessage(reason: unknown, fallback = "操作失败，请稍后重试") {
  return reason instanceof Error ? reason.message : fallback;
}
