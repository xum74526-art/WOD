"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Button, Callout, TextArea, TextField } from "@radix-ui/themes";
import { apiBaseUrl, readApiError } from "@/lib/api";
import { useI18n } from "@/components/locale-root";

type Status = { status: string; company_name?: string; created_at?: string };

function cookie(name: string) {
  return document.cookie.split("; ").find((item) => item.startsWith(`${name}=`))?.split("=").slice(1).join("=") ?? "";
}

export function SupplierApplicationForm() {
  const { t } = useI18n();
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState({ company_name: "", contact_name: "", contact_phone: "", region: "", description: "" });

  const loadStatus = useCallback(async () => {
    setError("");
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/supplier/application`, { credentials: "include", cache: "no-store" });
      if (!response.ok) throw new Error(await readApiError(response));
      const payload = await response.json();
      setStatus(payload.data);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("supplier.apply.status.readError", "无法读取申请状态"));
    }
  }, [t]);

  useEffect(() => { void loadStatus(); }, [loadStatus]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/supplier/application`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": decodeURIComponent(cookie("kai_csrf")) },
        body: JSON.stringify(form),
      });
      if (!response.ok) throw new Error(await readApiError(response));
      await loadStatus();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("supplier.apply.status.submitError", "申请提交失败"));
    } finally {
      setSubmitting(false);
    }
  }

  if (status && status.status !== "not_applied") {
    if (status.status === "auth_required") {
      return <div className="application-status"><span>{t("supplier.apply.status.loginRequired", "需要登录")}</span><strong>{t("supplier.apply.status.loginTitle", "先使用个人账号登录")}</strong><p>{t("supplier.apply.status.loginDescription", "登录后可提交商家申请并持续查看真实审核状态。")}</p><Link className="primary-link" href="/login">{t("supplier.apply.status.loginAction", "前往登录")}</Link></div>;
    }
    const statusLabel = status.status === "pending"
      ? t("supplier.apply.status.pending", "审核中")
      : status.status === "approved"
        ? t("supplier.apply.status.approved", "已通过")
        : t("supplier.apply.status.rejected", "未通过");
    return <div className="application-status"><span>{t("supplier.apply.status.current", "当前状态")}</span><strong>{statusLabel}</strong><p>{t("supplier.apply.status.saved", "{company} 的申请已保存。审核结果会显示在这里，不会自动通过。", { company: status.company_name || "—" })}</p><Link className="outline-link" href="/account">{t("supplier.apply.status.back", "返回个人工作台")}</Link></div>;
  }

  return <>
    {error && <Callout.Root color="red"><Callout.Text>{error}{t("supplier.apply.error.separator", "。")} {t("supplier.apply.error.loginHintBefore", "尚未登录时请先前往 ")}<Link href="/login">{t("supplier.apply.error.loginHintLink", "登录")}</Link>{t("supplier.apply.error.loginHintAfter", "。")}</Callout.Text></Callout.Root>}
    <form className="supplier-application" onSubmit={submit}>
      <label><span>{t("supplier.apply.field.company", "主体或商家名称")}</span><TextField.Root value={form.company_name} onChange={(event) => setForm({ ...form, company_name: event.target.value })} required /></label>
      <div className="supplier-application__row">
        <label><span>{t("supplier.apply.field.contact", "联系人")}</span><TextField.Root value={form.contact_name} onChange={(event) => setForm({ ...form, contact_name: event.target.value })} required /></label>
        <label><span>{t("supplier.apply.field.phone", "联系电话")}</span><TextField.Root type="tel" value={form.contact_phone} onChange={(event) => setForm({ ...form, contact_phone: event.target.value })} required /></label>
      </div>
      <label><span>{t("supplier.apply.field.region", "所在地区")}</span><TextField.Root value={form.region} onChange={(event) => setForm({ ...form, region: event.target.value })} /></label>
      <label><span>{t("supplier.apply.field.description", "设备来源与业务说明")}</span><TextArea value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} resize="vertical" /></label>
      <Button type="submit" size="3" disabled={submitting}>{submitting ? t("supplier.apply.submitting", "正在提交") : t("supplier.apply.submit", "提交审核")}</Button>
    </form>
  </>;
}
