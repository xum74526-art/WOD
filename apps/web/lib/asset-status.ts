type Translate = (key: string, fallback: string) => string;

export function assetStatusLabel(
  status: string | null | undefined,
  purchaseType: string | null | undefined,
  t: Translate,
) {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "active" || normalized === "running") {
    return purchaseType === "holding"
      ? t("asset.status.holding", "持有中")
      : t("asset.status.running", "运行中");
  }
  if (normalized === "expired") return t("asset.status.expired", "已到期");
  if (normalized === "sold") return t("asset.status.sold", "已出售");
  if (normalized === "used") return t("asset.status.used", "使用中");
  if (normalized === "done" || normalized === "completed") return t("asset.status.completed", "已完成");
  if (normalized === "canceled") return t("asset.status.canceled", "已取消");
  return t("asset.status.pending", "待生效");
}
