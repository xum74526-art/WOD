"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, Gavel, ShieldWarning, X } from "@phosphor-icons/react";
import { listAdminDisputes, resolveAdminDispute, type Dispute } from "@/lib/internal-api";
import { errorMessage, formatDate } from "@/lib/commerce-ui";

const statusLabels: Record<string, string> = { open: "待处理", under_review: "处理中", resolved: "已解决", rejected: "已驳回", cancelled: "已取消" };
const reasonLabels: Record<string, string> = { not_delivered: "未按约交付", service_unavailable: "服务不可用", configuration_mismatch: "配置不符", billing_issue: "计费问题", other: "其他" };

export function AdminDisputeWorkspace() {
  const [rows, setRows] = useState<Dispute[]>([]);
  const [selected, setSelected] = useState<Dispute | null>(null);
  const [status, setStatus] = useState("open");
  const [resolution, setResolution] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (nextStatus = status) => {
    setError("");
    try {
      const result = await listAdminDisputes(nextStatus);
      setRows(result);
      setSelected((current) => result.find((row) => row.id === current?.id) ?? result[0] ?? null);
    } catch (reason) { setError(errorMessage(reason)); }
  }, [status]);

  useEffect(() => { void load(); }, [load]);

  async function decide(nextStatus: "under_review" | "resolved" | "rejected", resolutionAction?: "release_to_supplier" | "refund_buyer") {
    if (!selected) return;
    if (["resolved", "rejected"].includes(nextStatus) && !resolution.trim()) { setError("关闭争议前请填写处理结论"); return; }
    setBusy(true); setError("");
    try {
      await resolveAdminDispute(selected.id, { version: selected.version, status: nextStatus, resolution: resolution.trim() || undefined, resolution_action: resolutionAction });
      setResolution("");
      await load(status);
    } catch (reason) { setError(errorMessage(reason)); } finally { setBusy(false); }
  }

  return <section className="workspace-page commerce-workspace"><div className="workspace-page__head"><p>ADMIN / DISPUTE RESOLUTION</p><h1>订单争议仲裁</h1><span>买家胜诉会冻结 SSH 权限并生成退款；商家胜诉后订单继续按 T+1 规则结算。</span></div>
    <div className="review-console admin-dispute-console"><aside><form><label className="admin-filter-label"><Gavel size={15}/><span>争议状态</span></label><select aria-label="争议状态" value={status} onChange={(event) => { setStatus(event.target.value); void load(event.target.value); }}><option value="open">待处理</option><option value="under_review">处理中</option><option value="resolved">已解决</option><option value="rejected">已驳回</option><option value="">全部</option></select></form>
      {rows.length === 0 ? <div className="commerce-empty"><Gavel size={24}/><strong>当前队列为空</strong></div> : <div className="review-queue">{rows.map((row) => <button type="button" className={selected?.id === row.id ? "active" : ""} onClick={() => { setSelected(row); setResolution(row.resolution || ""); }} key={row.id}><span><small>{row.dispute_no} · {formatDate(row.updated_at)}</small><strong>{reasonLabels[row.reason] || row.reason}</strong><em>订单 #{row.order_id}</em></span><b className={`status-chip status-chip--${row.status}`}>{statusLabels[row.status] || row.status}</b></button>)}</div>}
    </aside><article className="review-dossier">{selected ? <><header><div><p>{selected.dispute_no} / V{selected.version}</p><h2>{reasonLabels[selected.reason] || selected.reason}</h2></div><span className={`status-chip status-chip--${selected.status}`}>{statusLabels[selected.status] || selected.status}</span></header><section><h3>用户提交的问题</h3><p>{selected.description}</p></section><dl><div><dt>关联订单</dt><dd>#{selected.order_id}</dd></div><div><dt>创建时间</dt><dd>{formatDate(selected.created_at)}</dd></div></dl>{selected.resolution && <section><h3>当前处理结论</h3><p>{selected.resolution}</p>{selected.resolution_action && <small>{selected.resolution_action === "refund_buyer" ? "资金动作：生成买家退款" : "资金动作：继续商家结算"}</small>}</section>}{!["resolved", "rejected", "cancelled"].includes(selected.status) && <footer><label><span>处理结论</span><textarea rows={5} maxLength={2000} value={resolution} onChange={(event) => setResolution(event.target.value)} placeholder="说明证据、责任判断以及选择退款或继续结算的原因" /></label><div><button disabled={busy} onClick={() => void decide("rejected", "release_to_supplier")}><X size={15}/>商家胜诉 · 继续结算</button>{selected.status === "open" && <button disabled={busy} onClick={() => void decide("under_review")}><ShieldWarning size={15}/>开始处理</button>}<button disabled={busy} onClick={() => void decide("resolved", "refund_buyer")} className="commerce-danger"><Check size={15}/>买家胜诉 · 生成退款</button></div></footer>}</> : <div className="commerce-empty"><Gavel size={25}/><strong>选择一条争议查看详情</strong></div>}</article></div>{error && <div className="commerce-error">{error}</div>}
  </section>;
}
