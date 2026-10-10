"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { ClockCounterClockwise, MagnifyingGlass } from "@phosphor-icons/react";
import { AdminQueuePagination } from "@/components/admin-queue-pagination";
import { useI18n } from "@/components/locale-root";
import { listAdminFinanceAuditLogs, type AdminFinanceAuditLog } from "@/lib/admin-audit-api";
import { errorMessage, formatDate } from "@/lib/commerce-ui";

const PAGE_SIZE = 20;

export function AdminAuditLogWorkspace() {
  const { locale } = useI18n();
  const en = locale === "en";
  const [rows, setRows] = useState<AdminFinanceAuditLog[]>([]);
  const [selected, setSelected] = useState<AdminFinanceAuditLog | null>(null);
  const [action, setAction] = useState("");
  const [objectType, setObjectType] = useState("");
  const [objectId, setObjectId] = useState("");
  const [actorId, setActorId] = useState("");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async (nextPage = 1) => {
    setLoading(true);
    setError("");
    try {
      const result = await listAdminFinanceAuditLogs({
        action,
        objectType,
        objectId: objectId ? Number(objectId) : undefined,
        actorUserId: actorId ? Number(actorId) : undefined,
        page: nextPage,
        pageSize: PAGE_SIZE,
      });
      setRows(result.items);
      setPage(result.page);
      setTotal(result.total);
      setSelected((current) => result.items.find((item) => item.id === current?.id) ?? result.items[0] ?? null);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setLoading(false);
    }
  }, [action, actorId, objectId, objectType]);

  useEffect(() => { void load(1); }, []);

  function submit(event: FormEvent) {
    event.preventDefault();
    void load(1);
  }

  return <section className="workspace-page commerce-workspace admin-audit-log-workspace">
    <div className="workspace-page__head"><p>SECURITY / OPERATION AUDIT</p><h1>{en ? "Administrator audit log" : "管理员操作审计"}</h1><span>{en ? "Trace sensitive account, support, merchant, payment, and settlement actions by operator and object." : "按操作人和业务对象追溯账号、客服、商家、支付与结算等敏感管理操作。"}</span></div>
    <form className="admin-audit-log-filters" onSubmit={submit}>
      <label><MagnifyingGlass size={15}/><input value={action} onChange={(event) => setAction(event.target.value)} placeholder={en ? "Exact action" : "精确操作名称"}/></label>
      <input value={objectType} onChange={(event) => setObjectType(event.target.value)} placeholder={en ? "Object type" : "对象类型"}/>
      <input inputMode="numeric" value={objectId} onChange={(event) => setObjectId(event.target.value.replace(/\D/g, ""))} placeholder={en ? "Object ID" : "对象 ID"}/>
      <input inputMode="numeric" value={actorId} onChange={(event) => setActorId(event.target.value.replace(/\D/g, ""))} placeholder={en ? "Operator ID" : "操作人 ID"}/>
      <button type="submit" disabled={loading}>{en ? "Filter" : "筛选"}</button>
    </form>
    {error && <div className="commerce-error" role="alert">{error}</div>}
    <div className="admin-audit-log-layout">
      <div className="admin-audit-log-list">{loading && rows.length === 0 ? <div className="commerce-loading">{en ? "Loading audit records…" : "正在读取审计记录…"}</div> : rows.length === 0 ? <div className="commerce-empty"><ClockCounterClockwise size={24}/><strong>{en ? "No matching records" : "没有符合条件的审计记录"}</strong></div> : rows.map((row) => <button type="button" className={selected?.id === row.id ? "active" : ""} key={row.id} onClick={() => setSelected(row)}><span><strong>{row.action}</strong><small>{row.object_type} #{row.object_id}</small></span><span><b data-i18n-skip>{row.actor_username || `#${row.actor_user_id}`}</b><small>{formatDate(row.created_at)}</small></span></button>)}</div>
      <aside className="admin-audit-log-detail">{selected ? <><p>AUDIT #{selected.id}</p><h2>{selected.action}</h2><dl><div><dt>{en ? "Operator" : "操作人"}</dt><dd data-i18n-skip>{selected.actor_username || `#${selected.actor_user_id}`} (#{selected.actor_user_id})</dd></div><div><dt>{en ? "Object" : "业务对象"}</dt><dd>{selected.object_type} #{selected.object_id}</dd></div><div><dt>{en ? "Time" : "操作时间"}</dt><dd>{formatDate(selected.created_at)}</dd></div></dl><h3>{en ? "Structured detail" : "结构化详情"}</h3><pre data-i18n-skip>{JSON.stringify(selected.detail ?? {}, null, 2)}</pre></> : <div className="commerce-empty"><ClockCounterClockwise size={24}/><strong>{en ? "Select a record" : "选择一条记录查看详情"}</strong></div>}</aside>
    </div>
    <AdminQueuePagination page={page} total={total} loading={loading} onPageChange={(value) => void load(value)}/>
  </section>;
}
