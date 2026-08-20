"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowClockwise, Check, IdentificationCard, ShieldCheck, X } from "@phosphor-icons/react";
import { approveAdminKyc, listAdminKyc, rejectAdminKyc, type ManualKycApplication } from "@/lib/integration-api";
import { errorMessage, formatDate } from "@/lib/commerce-ui";

const labels: Record<string, string> = { pending: "待审核", approved: "已通过", rejected: "已驳回" };

export function AdminKycWorkspace() {
  const [rows, setRows] = useState<ManualKycApplication[]>([]);
  const [status, setStatus] = useState("pending");
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setError("");
    try { setRows(await listAdminKyc(status || undefined)); }
    catch (reason) { setError(errorMessage(reason)); }
  }, [status]);
  useEffect(() => { void load(); }, [load]);

  async function review(row: ManualKycApplication, approved: boolean) {
    const note = window.prompt(approved ? "审核备注（可选）" : "请输入驳回原因", approved ? "主体身份信息核验一致" : "");
    if (!approved && !note?.trim()) return;
    setBusy(row.id); setError("");
    try {
      if (approved) await approveAdminKyc(row.id, row.version, note?.trim() || undefined);
      else await rejectAdminKyc(row.id, row.version, note!.trim());
      await load();
    } catch (reason) { setError(errorMessage(reason)); }
    finally { setBusy(null); }
  }

  return <section className="workspace-page commerce-workspace admin-kyc">
    <div className="workspace-page__head"><p>ADMIN / IDENTITY REVIEW</p><h1>实名认证审核</h1><span>完整证件号码只在此审核队列展示；审核结论直接控制商家准入与提现权限。</span></div>
    <div className="refund-toolbar"><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="pending">待审核</option><option value="approved">已通过</option><option value="rejected">已驳回</option><option value="">全部</option></select><button onClick={() => void load()}><ArrowClockwise size={15}/>刷新</button></div>
    {error && <div className="commerce-error">{error}</div>}
    <div className="admin-kyc-list">{rows.length ? rows.map((row) => <article key={row.id}>
      <header><div><small>KYC #{row.id} · {row.verification_type === "business" ? "企业主体" : "个人主体"}</small><h2>{row.subject?.legal_name || "未提供主体名称"}</h2><span>{row.applicant?.display_name} · {row.applicant?.email}</span></div><b className={`status-chip status-chip--${row.status === "approved" ? "published" : row.status === "rejected" ? "rejected" : "pending_review"}`}>{labels[row.status] || row.status}</b></header>
      <dl><div><dt>证件类型</dt><dd>{row.subject?.identifier_type === "business_registration" ? "统一社会信用代码" : "身份证件"}</dd></div><div><dt>证件号码</dt><dd>{row.subject?.identifier_number}</dd></div><div><dt>法定代表人</dt><dd>{row.subject?.representative_name || "—"}</dd></div><div><dt>提交时间</dt><dd>{formatDate(row.submitted_at)}</dd></div></dl>
      {row.review_note && <p>{row.review_note}</p>}
      {row.status === "pending" && <footer><button disabled={busy === row.id} onClick={() => void review(row, false)}><X size={15}/>驳回</button><button className="commerce-primary" disabled={busy === row.id} onClick={() => void review(row, true)}><Check size={15}/>通过认证</button></footer>}
    </article>) : <div className="commerce-empty"><IdentificationCard size={25}/><strong>当前队列为空</strong><span>用户提交的实名认证会进入这里。</span></div>}</div>
    <div className="integration-safety-note"><ShieldCheck size={19}/><div><strong>审核要求</strong><span>核对主体名称、证件号码与法定代表人；不要复制或通过站外渠道传播完整身份信息。</span></div></div>
  </section>;
}
