"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { Button, Callout, TextArea, TextField } from "@radix-ui/themes";
import { apiBaseUrl, readApiError } from "@/lib/api";

type Status = { status: string; company_name?: string; created_at?: string };

function cookie(name: string) {
  return document.cookie.split("; ").find((item) => item.startsWith(`${name}=`))?.split("=").slice(1).join("=") ?? "";
}

export function SupplierApplicationForm() {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState({ company_name: "", contact_name: "", contact_phone: "", region: "", description: "" });

  async function loadStatus() {
    setError("");
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/supplier/application`, { credentials: "include", cache: "no-store" });
      if (!response.ok) throw new Error(await readApiError(response));
      const payload = await response.json();
      setStatus(payload.data);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法读取申请状态");
    }
  }

  useEffect(() => { void loadStatus(); }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/supplier/application`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": decodeURIComponent(cookie("wod_web_csrf")) },
        body: JSON.stringify(form),
      });
      if (!response.ok) throw new Error(await readApiError(response));
      await loadStatus();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "申请提交失败");
    } finally {
      setSubmitting(false);
    }
  }

  if (status && status.status !== "not_applied") {
    if (status.status === "auth_required") {
      return <div className="application-status"><span>需要登录</span><strong>先使用个人账号登录</strong><p>登录后可提交商家申请并持续查看真实审核状态。</p><Link className="primary-link" href="/login">前往登录</Link></div>;
    }
    return <div className="application-status"><span>当前状态</span><strong>{status.status === "pending" ? "审核中" : status.status === "approved" ? "已通过" : "未通过"}</strong><p>{status.company_name} 的申请已保存。审核结果会显示在这里，不会自动通过。</p><Link className="outline-link" href="/account">返回个人工作台</Link></div>;
  }

  return <>
    {error && <Callout.Root color="red"><Callout.Text>{error}。尚未登录时请先前往 <Link href="/login">登录</Link>。</Callout.Text></Callout.Root>}
    <form className="supplier-application" onSubmit={submit}>
      <label><span>主体或商家名称</span><TextField.Root value={form.company_name} onChange={(event) => setForm({ ...form, company_name: event.target.value })} required /></label>
      <div className="supplier-application__row">
        <label><span>联系人</span><TextField.Root value={form.contact_name} onChange={(event) => setForm({ ...form, contact_name: event.target.value })} required /></label>
        <label><span>联系电话</span><TextField.Root type="tel" value={form.contact_phone} onChange={(event) => setForm({ ...form, contact_phone: event.target.value })} required /></label>
      </div>
      <label><span>所在地区</span><TextField.Root value={form.region} onChange={(event) => setForm({ ...form, region: event.target.value })} /></label>
      <label><span>设备来源与业务说明</span><TextArea value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} resize="vertical" /></label>
      <Button type="submit" size="3" disabled={submitting}>{submitting ? "正在提交" : "提交审核"}</Button>
    </form>
  </>;
}
