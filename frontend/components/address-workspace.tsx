"use client";

import { useCallback, useEffect, useState } from "react";
import { CheckCircle, MapPin, PencilSimple, Plus, Trash } from "@phosphor-icons/react";
import { createAddress, deleteAddress, listAddresses, setDefaultAddress, updateAddress, type Address } from "@/lib/internal-api";
import { errorMessage } from "@/lib/commerce-ui";

const emptyForm = { label: "常用地址", recipient_name: "", phone: "", province: "", city: "", district: "", address_line: "", postal_code: "" };

export function AddressWorkspace() {
  const [rows, setRows] = useState<Address[]>([]);
  const [form, setForm] = useState(emptyForm);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const load = useCallback(async () => { try { setRows(await listAddresses()); } catch (reason) { setError(errorMessage(reason)); } }, []);
  useEffect(() => { void load(); }, [load]);
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try { await createAddress(form); setForm(emptyForm); await load(); } catch (reason) { setError(errorMessage(reason)); } finally { setBusy(false); }
  }
  async function act(action: () => Promise<unknown>) { setError(""); try { await action(); await load(); } catch (reason) { setError(errorMessage(reason)); } }
  function rename(row: Address) {
    const label = window.prompt("修改地址标签", row.label);
    if (label?.trim()) void act(() => updateAddress(row.id, { version: row.version, label: label.trim() }));
  }
  return <section className="workspace-page internal-workspace">
    <div className="workspace-page__head"><p>ACCOUNT / DELIVERY</p><h1>地址管理</h1><span>保存设备交付和线下采购使用的真实地址。</span></div>
    {error && <div className="commerce-error">{error}</div>}
    <div className="internal-grid"><div className="internal-list">
      <header><div><small>ADDRESS BOOK</small><h2>已保存地址</h2></div><strong>{rows.length}</strong></header>
      {rows.length === 0 ? <div className="internal-empty"><MapPin size={28}/><strong>还没有地址</strong><span>新增后第一条地址会自动设为默认。</span></div> : rows.map((row) => <article className="address-card" key={row.id}>
        <div className="address-card__top"><span>{row.label}</span>{row.is_default && <b><CheckCircle size={15}/>默认</b>}</div>
        <h3>{row.recipient_name} · {row.phone}</h3><p>{row.province} {row.city} {row.district} {row.address_line}</p>
        <footer><button onClick={() => rename(row)}><PencilSimple size={15}/>改标签</button>{!row.is_default && <button onClick={() => void act(() => setDefaultAddress(row.id))}>设为默认</button>}<button className="danger" onClick={() => { if (window.confirm("确定删除这个地址？")) void act(() => deleteAddress(row.id)); }}><Trash size={15}/>删除</button></footer>
      </article>)}
    </div><form className="internal-form" onSubmit={submit}><header><Plus size={20}/><div><small>NEW ADDRESS</small><h2>新增地址</h2></div></header>
      <label>地址标签<input value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} required /></label>
      <div className="form-pair"><label>收件人<input value={form.recipient_name} onChange={(e) => setForm({ ...form, recipient_name: e.target.value })} required /></label><label>联系电话<input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} required /></label></div>
      <div className="form-pair"><label>省份<input value={form.province} onChange={(e) => setForm({ ...form, province: e.target.value })} required /></label><label>城市<input value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} required /></label></div>
      <label>区县<input value={form.district} onChange={(e) => setForm({ ...form, district: e.target.value })} /></label><label>详细地址<textarea value={form.address_line} onChange={(e) => setForm({ ...form, address_line: e.target.value })} required /></label>
      <button className="commerce-primary" disabled={busy}>{busy ? "保存中…" : "保存地址"}</button>
    </form></div>
  </section>;
}
