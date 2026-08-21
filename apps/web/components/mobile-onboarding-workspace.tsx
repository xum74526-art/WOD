"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { Buildings, Cpu, HardDrives, MapPin } from "@phosphor-icons/react";
import { getOnboardingMine, submitOnboarding, type OnboardingItem } from "@/lib/mobile-business-api";
import { errorMessage, formatDate } from "@/lib/commerce-ui";

const statusLabels: Record<string, string> = { submitted: "已提交", contacted: "已联系", approved: "已通过", rejected: "已驳回" };

export function MobileOnboardingWorkspace() {
  const [rows, setRows] = useState<OnboardingItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({ entity_type: "personal" as "personal" | "company", contact: "", phone: "", device_model: "", device_count: "1", location: "", remark: "" });
  const load = useCallback(async () => { try { setRows(await getOnboardingMine()); } catch (reason) { setError(errorMessage(reason)); } }, []);
  useEffect(() => { void load(); }, [load]);
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      await submitOnboarding({ ...form, device_count: Number(form.device_count) });
      setForm((current) => ({ ...current, device_model: "", device_count: "1", location: "", remark: "" }));
      await load();
    } catch (reason) { setError(errorMessage(reason)); } finally { setBusy(false); }
  }
  return <section className="workspace-page mobile-onboarding-workspace"><div className="workspace-page__head"><p>ACCOUNT / DEVICE HOSTING</p><h1>设备托管</h1><span>托管申请和处理状态直接来自手机端后端；个人需实名认证，企业需通过商家认证。</span></div>{error && <div className="commerce-error">{error} {error.includes("实名") && <Link href="/account/verification">前往实名认证</Link>}</div>}<div className="mobile-service-columns onboarding-layout"><form className="mobile-business-form" onSubmit={submit}><header><HardDrives size={21}/><div><small>HOSTING APPLICATION</small><h2>提交托管申请</h2></div></header><label>主体类型<select value={form.entity_type} onChange={(event) => setForm({ ...form, entity_type: event.target.value as "personal" | "company" })}><option value="personal">个人</option><option value="company">企业</option></select></label><label>联系人<input required value={form.contact} onChange={(event) => setForm({ ...form, contact: event.target.value })}/></label><label>联系电话<input required inputMode="tel" value={form.phone} onChange={(event) => setForm({ ...form, phone: event.target.value })}/></label><label>设备型号<input required value={form.device_model} onChange={(event) => setForm({ ...form, device_model: event.target.value })} placeholder="如 RTX 4090"/></label><label>设备数量<input required type="number" min="1" value={form.device_count} onChange={(event) => setForm({ ...form, device_count: event.target.value })}/></label><label>设备所在地<input required value={form.location} onChange={(event) => setForm({ ...form, location: event.target.value })}/></label><label>补充说明<textarea value={form.remark} onChange={(event) => setForm({ ...form, remark: event.target.value })}/></label><button className="commerce-primary" disabled={busy}>{busy ? "提交中…" : "提交托管申请"}</button></form><section className="mobile-record-panel onboarding-records"><header><Buildings size={20}/><div><small>APPLICATION HISTORY</small><h2>申请记录</h2></div><b>{rows.length}</b></header>{rows.length ? rows.map((row) => <article key={row.id}><Cpu size={19}/><span><strong>{row.device_model} × {row.device_count}</strong><small>{row.entity_type === "company" ? "企业" : "个人"} · {row.contact} · {formatDate(row.created_at)}</small><small><MapPin size={13}/>{row.location || "未填写所在地"}</small></span><b>{statusLabels[row.status] || row.status}</b></article>) : <div className="mobile-inline-empty">还没有托管申请</div>}</section></div></section>;
}
