"use client";

import { FormEvent, useState } from "react";
import { FloppyDisk, Trash } from "@phosphor-icons/react";
import { deleteBuyRequest, updateBuyRequest, type BuyRequest } from "@/lib/commerce-api";
import { errorMessage } from "@/lib/commerce-ui";

function localTime(value: string) {
  const date = new Date(value);
  date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
  return date.toISOString().slice(0, 16);
}

export function BuyRequestEditor({ row, onSaved, onDeleted }: { row: BuyRequest; onSaved: () => Promise<void>; onDeleted: () => void }) {
  const detail = row.cloud_details;
  const [form, setForm] = useState({
    title: row.title,
    gpu_model: row.gpu_model,
    gpu_quantity: String(row.gpu_quantity),
    min_gpu_memory_gb: row.min_gpu_memory_gb ? String(row.min_gpu_memory_gb) : "",
    regions: row.region_codes.join(", "),
    budget_amount: row.budget.amount ?? "",
    budget_currency: row.budget.currency,
    budget_unit: row.budget.unit,
    quote_deadline_at: localTime(row.quote_deadline_at),
    expected_duration_hours: row.expected_duration_hours ? String(row.expected_duration_hours) : "",
    min_cpu_cores: detail?.min_cpu_cores ? String(detail.min_cpu_cores) : "",
    min_ram_gb: detail?.min_ram_gb ? String(detail.min_ram_gb) : "",
    requirements: row.requirements,
  });
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  async function save(event: FormEvent) {
    event.preventDefault(); setBusy("save"); setError("");
    try {
      await updateBuyRequest(row.id!, {
        version: row.version,
        title: form.title,
        gpu_model: form.gpu_model,
        gpu_quantity: Number(form.gpu_quantity),
        min_gpu_memory_gb: form.min_gpu_memory_gb ? Number(form.min_gpu_memory_gb) : null,
        region_codes: form.regions.split(/[,，\s]+/).filter(Boolean),
        budget_amount: form.budget_amount || null,
        budget_currency: form.budget_currency,
        budget_unit: form.budget_unit,
        quote_deadline_at: new Date(form.quote_deadline_at).toISOString(),
        expected_duration_hours: form.expected_duration_hours ? Number(form.expected_duration_hours) : null,
        requirements: form.requirements,
        cloud_details: {
          min_cpu_cores: form.min_cpu_cores ? Number(form.min_cpu_cores) : null,
          min_ram_gb: form.min_ram_gb ? Number(form.min_ram_gb) : null,
          min_disk_gb: detail?.min_disk_gb ?? null,
          min_download_mbps: detail?.min_download_mbps ?? null,
          public_ip_required: detail?.public_ip_required ?? false,
          container_image: detail?.container_image ?? null,
          software_stack: detail?.software_stack ?? [],
          special_requirements: detail?.special_requirements ?? null,
        },
      });
      await onSaved();
    } catch (reason) { setError(errorMessage(reason, "草稿保存失败")); }
    finally { setBusy(""); }
  }

  async function remove() {
    if (!window.confirm("确认删除这份求购草稿？删除后无法恢复。")) return;
    setBusy("delete"); setError("");
    try { await deleteBuyRequest(row.id!, row.version!); onDeleted(); }
    catch (reason) { setError(errorMessage(reason, "草稿删除失败")); setBusy(""); }
  }

  return <form className="request-editor" onSubmit={save}>
    <header><div><p>EDIT DRAFT / V{row.version}</p><h2>编辑求购草稿</h2></div><span>只有草稿状态可以修改或删除</span></header>
    {error && <div className="commerce-error">{error}</div>}
    <div className="request-editor__grid">
      <label className="wide"><span>任务标题</span><input required minLength={3} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></label>
      <label><span>GPU 型号</span><input required value={form.gpu_model} onChange={(e) => setForm({ ...form, gpu_model: e.target.value })} /></label>
      <label><span>GPU 数量</span><input required type="number" min="1" value={form.gpu_quantity} onChange={(e) => setForm({ ...form, gpu_quantity: e.target.value })} /></label>
      <label><span>最低显存（GB）</span><input type="number" min="1" value={form.min_gpu_memory_gb} onChange={(e) => setForm({ ...form, min_gpu_memory_gb: e.target.value })} /></label>
      <label><span>地区代码</span><input value={form.regions} onChange={(e) => setForm({ ...form, regions: e.target.value })} /></label>
      <label><span>最低 CPU 核数</span><input type="number" min="1" value={form.min_cpu_cores} onChange={(e) => setForm({ ...form, min_cpu_cores: e.target.value })} /></label>
      <label><span>最低内存（GB）</span><input type="number" min="1" value={form.min_ram_gb} onChange={(e) => setForm({ ...form, min_ram_gb: e.target.value })} /></label>
      <label><span>单位预算</span><input type="number" min="0" step="0.000001" value={form.budget_amount} onChange={(e) => setForm({ ...form, budget_amount: e.target.value })} /></label>
      <label><span>币种</span><select value={form.budget_currency} onChange={(e) => setForm({ ...form, budget_currency: e.target.value })}><option>USD</option><option>CNY</option><option>USDT</option></select></label>
      <label><span>计价单位</span><select value={form.budget_unit} onChange={(e) => setForm({ ...form, budget_unit: e.target.value })}><option value="gpu_hour">GPU·小时</option><option value="gpu_day">GPU·天</option></select></label>
      <label><span>报价截止</span><input required type="datetime-local" value={form.quote_deadline_at} onChange={(e) => setForm({ ...form, quote_deadline_at: e.target.value })} /></label>
      <label><span>使用时长（小时）</span><input type="number" min="1" value={form.expected_duration_hours} onChange={(e) => setForm({ ...form, expected_duration_hours: e.target.value })} /></label>
      <label className="wide"><span>部署与服务要求</span><textarea rows={4} value={form.requirements} onChange={(e) => setForm({ ...form, requirements: e.target.value })} /></label>
    </div>
    <footer><button className="commerce-danger" type="button" disabled={Boolean(busy)} onClick={() => void remove()}><Trash size={15} />{busy === "delete" ? "删除中…" : "删除草稿"}</button><button className="commerce-primary" disabled={Boolean(busy)}><FloppyDisk size={15} />{busy === "save" ? "保存中…" : "保存修改"}</button></footer>
  </form>;
}
