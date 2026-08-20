"use client";

import { useCallback, useEffect, useState } from "react";
import { FloppyDisk, Storefront } from "@phosphor-icons/react";
import { getSupplierSettings, saveSupplierSettings, type SupplierSettingsSnapshot } from "@/lib/internal-api";
import { errorMessage } from "@/lib/commerce-ui";

export function SupplierSettingsWorkspace() {
  const [snapshot, setSnapshot] = useState<SupplierSettingsSnapshot | null>(null); const [form, setForm] = useState({ store_name: "", contact_name: "", contact_phone: "", service_regions: "", introduction: "", version: undefined as number | undefined }); const [error, setError] = useState(""); const [saved, setSaved] = useState(""); const [busy, setBusy] = useState(false);
  const load = useCallback(async () => { try { const data = await getSupplierSettings(); setSnapshot(data); const source = data.profile; setForm({ store_name: source?.store_name || data.application.company_name, contact_name: source?.contact_name || data.application.contact_name, contact_phone: source?.contact_phone || data.application.contact_phone, service_regions: (source?.service_regions || (data.application.region ? [data.application.region] : [])).join(", "), introduction: source?.introduction || "", version: source?.version }); } catch (reason) { setError(errorMessage(reason)); } }, []);
  useEffect(() => { void load(); }, [load]);
  async function submit(event: React.FormEvent) { event.preventDefault(); setBusy(true); setError(""); setSaved(""); try { await saveSupplierSettings({ ...form, service_regions: form.service_regions.split(",").map((item) => item.trim()).filter(Boolean) }); setSaved("商家资料已保存"); await load(); } catch (reason) { setError(errorMessage(reason)); } finally { setBusy(false); } }
  return <section className="workspace-page internal-workspace"><div className="workspace-page__head"><p>SUPPLIER / PROFILE</p><h1>商家设置</h1><span>维护审核通过后的店铺名称、联系人和服务区域。</span></div>{error && <div className="commerce-error">{error}</div>}{saved && <div className="commerce-success">{saved}</div>}
    <form className="supplier-profile-form" onSubmit={submit}><header><Storefront size={24}/><div><small>APPROVED SUPPLIER</small><h2>{snapshot?.application.company_name || "读取商家资料…"}</h2></div></header><label>店铺名称<input value={form.store_name} onChange={(e) => setForm({ ...form, store_name: e.target.value })} required /></label><div className="form-pair"><label>联系人<input value={form.contact_name} onChange={(e) => setForm({ ...form, contact_name: e.target.value })} required /></label><label>联系电话<input value={form.contact_phone} onChange={(e) => setForm({ ...form, contact_phone: e.target.value })} required /></label></div><label>服务区域（英文逗号分隔）<input value={form.service_regions} onChange={(e) => setForm({ ...form, service_regions: e.target.value })} /></label><label>店铺简介<textarea maxLength={2000} value={form.introduction} onChange={(e) => setForm({ ...form, introduction: e.target.value })} /></label><button className="commerce-primary" disabled={busy}><FloppyDisk size={16}/>{busy ? "保存中…" : "保存设置"}</button></form>
  </section>;
}
