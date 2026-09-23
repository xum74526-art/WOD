"use client";

import { useI18n } from "@/components/locale-root";
import type { AuditPlatform } from "@/lib/mobile-finance-api";

export const platformLabels: Record<string, string> = {
  web: "Web",
  ios: "iOS",
  android: "Android",
  admin: "管理后台",
  legacy: "历史数据",
  system: "系统",
};

export function platformLabel(value?: string | null) {
  return platformLabels[value || ""] || value || "未标记";
}

export function AdminPlatformFilter({
  value,
  onChange,
}: {
  value: AuditPlatform | "";
  onChange: (value: AuditPlatform | "") => void;
}) {
  const { t } = useI18n();
  return (
    <select aria-label={t("admin.filter.sourceAria", "数据来源")} value={value} onChange={(event) => onChange(event.target.value as AuditPlatform | "")}>
      <option value="">{t("admin.filter.allSources", "全部来源")}</option>
      <option value="web">Web</option>
      <option value="ios">iOS</option>
      <option value="android">Android</option>
      <option value="admin">{t("admin.filter.backend", "管理后台")}</option>
      <option value="legacy">{t("admin.filter.legacy", "历史数据")}</option>
    </select>
  );
}
