"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, CheckCircle, ShieldCheck } from "@phosphor-icons/react";
import { createBuyRequest } from "@/lib/commerce-api";
import { errorMessage } from "@/lib/commerce-ui";
import { ApiError, getCurrentUser } from "@/lib/api";
import { loginHref } from "@/lib/auth-navigation";

function initialDeadline() {
  const date = new Date(Date.now() + 3 * 24 * 60 * 60 * 1000);
  date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
  return date.toISOString().slice(0, 16);
}

export function BuyRequestForm() {
  const router = useRouter();
  const [authChecking, setAuthChecking] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({ title: "", gpu_model: "", min_gpu_memory_gb: "", gpu_quantity: "1", region: "", budget_amount: "", budget_currency: "USD", budget_unit: "gpu_hour", quote_deadline_at: initialDeadline(), expected_duration_hours: "", requirements: "", min_cpu_cores: "", min_ram_gb: "" });

  useEffect(() => {
    getCurrentUser().then(() => setAuthChecking(false)).catch((reason) => {
      if (reason instanceof ApiError && reason.status === 401) window.location.assign(loginHref("/requests/new"));
      else { setError(errorMessage(reason, "无法验证登录状态")); setAuthChecking(false); }
    });
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault(); setSubmitting(true); setError("");
    try {
      const created = await createBuyRequest({
        request_type: "cloud_compute", title: form.title, visibility: "public", gpu_model: form.gpu_model,
        min_gpu_memory_gb: form.min_gpu_memory_gb ? Number(form.min_gpu_memory_gb) : null,
        gpu_quantity: Number(form.gpu_quantity), region_codes: form.region ? form.region.split(/[,，\s]+/).filter(Boolean) : [],
        delivery_mode: "remote", budget_amount: form.budget_amount || null, budget_currency: form.budget_currency,
        budget_unit: form.budget_unit, quote_deadline_at: new Date(form.quote_deadline_at).toISOString(), expected_start_at: null,
        expected_duration_hours: form.expected_duration_hours ? Number(form.expected_duration_hours) : null, requirements: form.requirements,
        cloud_details: { min_cpu_cores: form.min_cpu_cores ? Number(form.min_cpu_cores) : null, min_ram_gb: form.min_ram_gb ? Number(form.min_ram_gb) : null, public_ip_required: false, software_stack: [] },
      });
      router.push(`/account/requests/${created.id}`);
    } catch (reason) { setError(errorMessage(reason, "求购保存失败")); setSubmitting(false); }
  }

  if (authChecking) return <div className="commerce-loading">正在验证登录状态…</div>;
  return <div className="request-compose">
    <section className="request-compose__intro">
      <Link href="/requests"><ArrowLeft size={15} />返回求购市场</Link>
      <p className="hero-eyebrow">NEW PROCUREMENT BRIEF</p><h1>发布一份可执行的算力需求</h1>
      <p>先保存为草稿，再到个人工作台确认发布。P0 阶段开放线上算力求购，线下设备采购将在后续规则确认后开放。</p>
      <div className="request-guardrail"><ShieldCheck size={22} /><div><strong>隐私边界</strong><span>公开市场不会展示账户、手机号或邮箱；本阶段也不会接收未加密的敏感联系方式。</span></div></div>
    </section>
    <form className="commerce-form" onSubmit={submit}>
      <header><span>01 / REQUIREMENT</span><h2>基础需求</h2></header>
      {error && <div className="commerce-error">{error}{error.includes("登录") && <Link href="/login">前往登录</Link>}</div>}
      <label className="commerce-field commerce-field--wide"><span>任务标题</span><input required minLength={3} maxLength={160} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="例如：8 张 H100 训练算力需求" /></label>
      <div className="commerce-form__grid">
        <label className="commerce-field"><span>GPU 型号</span><input required value={form.gpu_model} onChange={(e) => setForm({ ...form, gpu_model: e.target.value })} placeholder="H100" /></label>
        <label className="commerce-field"><span>GPU 数量</span><input required type="number" min="1" value={form.gpu_quantity} onChange={(e) => setForm({ ...form, gpu_quantity: e.target.value })} /></label>
        <label className="commerce-field"><span>最低显存（GB）</span><input type="number" min="1" value={form.min_gpu_memory_gb} onChange={(e) => setForm({ ...form, min_gpu_memory_gb: e.target.value })} placeholder="80" /></label>
        <label className="commerce-field"><span>地区代码</span><input value={form.region} onChange={(e) => setForm({ ...form, region: e.target.value })} placeholder="CN-SH，多地区用逗号分隔" /></label>
        <label className="commerce-field"><span>最低 CPU 核数</span><input type="number" min="1" value={form.min_cpu_cores} onChange={(e) => setForm({ ...form, min_cpu_cores: e.target.value })} /></label>
        <label className="commerce-field"><span>最低内存（GB）</span><input type="number" min="1" value={form.min_ram_gb} onChange={(e) => setForm({ ...form, min_ram_gb: e.target.value })} /></label>
      </div>
      <header><span>02 / COMMERCIAL</span><h2>预算与时限</h2></header>
      <div className="commerce-form__grid commerce-form__grid--three">
        <label className="commerce-field"><span>单位预算（可留空面议）</span><input type="number" min="0" step="0.000001" value={form.budget_amount} onChange={(e) => setForm({ ...form, budget_amount: e.target.value })} /></label>
        <label className="commerce-field"><span>币种</span><select value={form.budget_currency} onChange={(e) => setForm({ ...form, budget_currency: e.target.value })}><option>USD</option><option>CNY</option><option>USDT</option></select></label>
        <label className="commerce-field"><span>计价单位</span><select value={form.budget_unit} onChange={(e) => setForm({ ...form, budget_unit: e.target.value })}><option value="gpu_hour">GPU·小时</option><option value="gpu_day">GPU·天</option></select></label>
        <label className="commerce-field"><span>报价截止</span><input required type="datetime-local" value={form.quote_deadline_at} onChange={(e) => setForm({ ...form, quote_deadline_at: e.target.value })} /></label>
        <label className="commerce-field"><span>预计使用时长（小时）</span><input type="number" min="1" value={form.expected_duration_hours} onChange={(e) => setForm({ ...form, expected_duration_hours: e.target.value })} /></label>
      </div>
      <label className="commerce-field commerce-field--wide"><span>部署与服务要求</span><textarea rows={5} maxLength={5000} value={form.requirements} onChange={(e) => setForm({ ...form, requirements: e.target.value })} placeholder="镜像、CUDA 版本、网络、交付方式等" /></label>
      <footer><span><CheckCircle size={16} />保存后仍是草稿，不会自动公开</span><button className="commerce-primary" disabled={submitting} type="submit">{submitting ? "正在保存…" : "保存草稿并检查"}</button></footer>
    </form>
  </div>;
}
