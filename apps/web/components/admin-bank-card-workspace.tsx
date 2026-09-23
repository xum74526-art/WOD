"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowClockwise, Bank, Check, ShieldCheck, X } from "@phosphor-icons/react";
import { AdminPlatformFilter, platformLabel } from "@/components/admin-platform-filter";
import { AdminQueuePagination } from "@/components/admin-queue-pagination";
import { normalizeAdminReviewPrompt } from "@/lib/admin-review-prompt";
import { ADMIN_QUEUE_PAGE_SIZE, adminQueuePageCount } from "@/lib/admin-queue-pagination";
import { errorMessage } from "@/lib/commerce-ui";
import {
  listFinanceBankCards,
  reviewFinanceBankCard,
  type AuditPlatform,
  type FinanceBankCard,
} from "@/lib/mobile-finance-api";

const labels: Record<string, string> = { registered: "已登记", pending_review: "待复核", active: "已启用", rejected: "已驳回", disabled: "已停用" };

export function AdminBankCardWorkspace() {
  const [rows, setRows] = useState<FinanceBankCard[]>([]);
  const [status, setStatus] = useState("registered");
  const [platform, setPlatform] = useState<AuditPlatform | "">("");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(0);
  const [error, setError] = useState("");
  const queryRef = useRef({ status, platform, page });
  const requestSequence = useRef(0);
  queryRef.current = { status, platform, page };

  const load = useCallback(async () => {
    const requestId = ++requestSequence.current;
    const query = queryRef.current;
    const isCurrentQuery = () => requestId === requestSequence.current
      && query.status === queryRef.current.status
      && query.platform === queryRef.current.platform
      && query.page === queryRef.current.page;
    setLoading(true);
    setError("");
    try {
      const result = await listFinanceBankCards({
        status: query.status,
        platform: query.platform || undefined,
        page: query.page,
        pageSize: ADMIN_QUEUE_PAGE_SIZE,
      });
      if (!isCurrentQuery()) return;
      const pageCount = adminQueuePageCount(result.total);
      setTotal(result.total);
      if (query.page > pageCount) {
        setRows([]);
        setPage(pageCount);
        return;
      }
      setRows(result.items);
    } catch (reason) {
      if (isCurrentQuery()) setError(errorMessage(reason));
    } finally {
      if (isCurrentQuery()) setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load, page, platform, status]);

  function changePage(value: number) { if (value === page) return; requestSequence.current += 1; setPage(value); }
  function changeStatus(value: string) { if (value === status && page === 1) return; requestSequence.current += 1; setStatus(value); setPage(1); }
  function changePlatform(value: AuditPlatform | "") { if (value === platform && page === 1) return; requestSequence.current += 1; setPlatform(value); setPage(1); }

  async function review(row: FinanceBankCard, approved: boolean) {
    const reason = normalizeAdminReviewPrompt(window.prompt(
      approved ? "复核备注（可选）" : "请输入驳回原因",
      approved ? "登记资料核对一致" : "",
    ),
      !approved,
    );
    if (reason === null) return;
    setBusy(row.id);
    try {
      await reviewFinanceBankCard(row.id, approved, reason);
      await load();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(0);
    }
  }

  return <section className="workspace-page commerce-workspace">
    <div className="workspace-page__head">
      <p>FINANCE / BANK CARD REVIEW</p>
      <h1>银行卡登记复核</h1>
      <span>列表和复核结论写入统一业务后端；银行卡状态不代表银行已完成真实性验证。</span>
    </div>
    <div className="refund-toolbar">
      <select value={status} onChange={(event) => changeStatus(event.target.value)}>
        <option value="registered">已登记</option>
        <option value="pending_review">待复核</option>
        <option value="active">已启用</option>
        <option value="rejected">已驳回</option>
        <option value="disabled">已停用</option>
        <option value="">全部</option>
      </select>
      <AdminPlatformFilter value={platform} onChange={changePlatform}/>
      <button disabled={loading} onClick={() => void load()}><ArrowClockwise size={15}/>{loading ? "读取中" : "刷新"}</button>
    </div>
    {error && <div className="commerce-error">{error}</div>}
    <div className="admin-bank-review-list">
      {rows.length ? rows.map((row) => <article key={row.id}>
        <header>
          <Bank size={21}/>
          <span>
            <small>CARD #{row.id} · USER #{row.user_id} · {platformLabel(row.created_platform)}</small>
            <h2 data-i18n-skip>{row.bank_name}</h2>
            <p><span data-i18n-skip={Boolean(row.username) || undefined}>{row.username || "用户"}</span> · <span data-i18n-skip>{row.holder}</span></p>
          </span>
          <b>{labels[row.status] || row.status}</b>
        </header>
        <dl>
          <div><dt>银行卡</dt><dd>{row.card_number}</dd></div>
          <div><dt>预留手机</dt><dd>{row.phone || "未提供"}</dd></div>
          <div><dt>登记模式</dt><dd>{row.verification_mode}</dd></div>
          <div><dt>最后操作端</dt><dd>{platformLabel(row.last_modified_platform)}</dd></div>
        </dl>
        {row.reject_reason && <p className="finance-review-reason" data-i18n-skip>{row.reject_reason}</p>}
        {row.verification_mode === "manual_review" && ["registered", "pending_review", "rejected"].includes(row.status) && <footer>
          <button disabled={busy === row.id} onClick={() => void review(row, false)}><X size={15}/>驳回</button>
          <button className="commerce-primary" disabled={busy === row.id} onClick={() => void review(row, true)}><Check size={15}/>通过复核</button>
        </footer>}
      </article>) : <div className="commerce-empty"><Bank size={27}/><strong>{loading ? "正在读取队列…" : "当前没有银行卡记录"}</strong></div>}
    </div>
    <AdminQueuePagination page={page} total={total} loading={loading} onPageChange={changePage}/>
    <div className="integration-safety-note"><ShieldCheck size={19}/><div><strong>复核边界</strong><span>这里只核对平台登记信息，不应把格式校验或人工复核描述成银行验卡。</span></div></div>
  </section>;
}
