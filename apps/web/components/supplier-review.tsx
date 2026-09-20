"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Check, MagnifyingGlass, ShieldCheck, X } from "@phosphor-icons/react";
import { listSupplierApplications, reviewSupplierApplication, type SupplierApplication } from "@/lib/commerce-api";
import { errorMessage, formatDate } from "@/lib/commerce-ui";

const labels = { pending: "待审核", approved: "已通过", rejected: "已驳回" } as const;
const PAGE_SIZE = 30;

function mergeApplications(current: SupplierApplication[], incoming: SupplierApplication[]) {
  const rows = new Map(current.map((row) => [row.id, row]));
  incoming.forEach((row) => rows.set(row.id, row));
  return Array.from(rows.values());
}

export function SupplierReview() {
  const [rows, setRows] = useState<SupplierApplication[]>([]);
  const [selected, setSelected] = useState<SupplierApplication | null>(null);
  const [status, setStatus] = useState("pending");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [total, setTotal] = useState(0);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (
    nextStatus = status,
    nextSearch = search,
    nextPage = 1,
    append = false,
  ) => {
    setLoading(true);
    setError("");
    try {
      const result = await listSupplierApplications({
        status: nextStatus || undefined,
        search: nextSearch || undefined,
        page: nextPage,
        page_size: PAGE_SIZE,
      });
      setRows((current) => append ? mergeApplications(current, result.data) : mergeApplications([], result.data));
      setSelected((current) => append
        ? current ?? result.data[0] ?? null
        : result.data.find((row) => row.id === current?.id) ?? result.data[0] ?? null);
      setPage(result.meta.page);
      setTotal(result.meta.total);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setLoading(false);
    }
  }, [search, status]);

  useEffect(() => { void load(); }, []);

  function submit(event: FormEvent) {
    event.preventDefault();
    void load(status, search, 1, false);
  }

  async function review(action: "approve" | "reject") {
    if (!selected) return;
    if (action === "reject" && note.trim().length < 2) {
      setError("驳回时请填写至少 2 个字的原因");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await reviewSupplierApplication(selected.id, action, selected.version, note);
      setNote("");
      await load(status, search, 1, false);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  const hasMore = page * PAGE_SIZE < total;

  return <section className="workspace-page commerce-workspace">
    <div className="workspace-page__head"><p>ADMIN / SUPPLIER REVIEW</p><h1>商家准入审核</h1><span>商家入驻资料审核与实名认证是两个独立结论；只有实名认证已完成的申请人才能通过入驻审核。</span></div>
    <div className="review-console"><aside><form onSubmit={submit}><label><MagnifyingGlass size={15} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索主体、联系人或邮箱" /></label><select value={status} onChange={(event) => { setStatus(event.target.value); void load(event.target.value, search, 1, false); }}><option value="pending">待审核</option><option value="approved">已通过</option><option value="rejected">已驳回</option><option value="">全部</option></select></form>{loading && rows.length === 0 ? <div className="commerce-loading">正在读取申请…</div> : error && rows.length === 0 ? <div className="commerce-error">{error}</div> : rows.length === 0 ? <div className="commerce-empty"><ShieldCheck size={23} /><strong>没有符合条件的申请</strong></div> : <><div className="review-queue">{rows.map((row) => <button className={selected?.id === row.id ? "active" : ""} type="button" key={row.id} onClick={() => { setSelected(row); setNote(row.review_note || ""); }}><span><small>#{row.id} · {formatDate(row.created_at)}</small><strong>{row.company_name}</strong><em>{row.applicant.email || row.applicant.display_name}</em></span><b className={`status-chip status-chip--${row.status}`}>{labels[row.status]}</b></button>)}</div>{hasMore && <button className="admin-dispute-load-more" type="button" disabled={loading} onClick={() => void load(status, search, page + 1, true)}>{loading ? "正在加载…" : `加载更多（已显示 ${rows.length} / ${total}）`}</button>}</>}</aside>
      <article className="review-dossier">{selected ? <><header><div><p>APPLICATION #{selected.id} / V{selected.version}</p><h2>{selected.company_name}</h2></div><span className={`status-chip status-chip--${selected.status}`}>{labels[selected.status]}</span></header><dl><div><dt>申请账户</dt><dd>{selected.applicant.display_name}<small>{selected.applicant.email || "未绑定邮箱"}</small></dd></div><div><dt>实名认证</dt><dd>{selected.identity_verified ? "已完成" : "未完成"}<small>{selected.identity_verified ? "满足商家准入前置条件" : "完成实名认证后才可审核通过"}</small></dd></div><div><dt>联系人</dt><dd>{selected.contact_name}<small>{selected.contact_phone}</small></dd></div><div><dt>地区</dt><dd>{selected.region || "未填写"}</dd></div><div><dt>当前角色 / 状态</dt><dd>{selected.applicant.role} / {selected.applicant.status}</dd></div></dl><section><h3>商家提交的设备来源与业务说明</h3><p>{selected.description || "申请人未补充说明。"}</p></section>{selected.review_note && selected.status !== "pending" && <section><h3>最近审核意见</h3><p>{selected.review_note}</p></section>}{selected.status === "pending" && <footer><label><span>审核意见</span><textarea rows={4} value={note} onChange={(event) => setNote(event.target.value)} placeholder="通过时可选；驳回时必填" /></label><div><button className="commerce-danger" disabled={busy} onClick={() => void review("reject")}><X size={15} />驳回申请</button><button className="commerce-primary" disabled={busy || !selected.identity_verified} title={selected.identity_verified ? undefined : "申请人尚未完成实名认证"} onClick={() => void review("approve")}><Check size={15} />{selected.identity_verified ? "审核通过" : "未实名不可通过"}</button></div></footer>}</> : <div className="commerce-empty"><ShieldCheck size={25}/><strong>选择一条申请查看资料</strong></div>}</article>
    </div>{error && rows.length > 0 && <div className="commerce-error">{error}</div>}
  </section>;
}
