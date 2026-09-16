"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowClockwise, Check, IdentificationCard, ShieldCheck, X } from "@phosphor-icons/react";
import { AdminPlatformFilter, platformLabel } from "@/components/admin-platform-filter";
import { AdminQueuePagination } from "@/components/admin-queue-pagination";
import { normalizeAdminReviewPrompt } from "@/lib/admin-review-prompt";
import { ADMIN_QUEUE_PAGE_SIZE, adminQueuePageCount } from "@/lib/admin-queue-pagination";
import { errorMessage, formatDate } from "@/lib/commerce-ui";
import {
  financeVerificationPhoto,
  listFinanceVerifications,
  reviewFinanceVerification,
  type AuditPlatform,
  type FinanceVerification,
} from "@/lib/mobile-finance-api";

const labels: Record<string, string> = { pending: "待审核", verified: "已通过", rejected: "已驳回" };

export function AdminKycWorkspace() {
  const [rows, setRows] = useState<FinanceVerification[]>([]);
  const [status, setStatus] = useState("pending");
  const [platform, setPlatform] = useState<AuditPlatform | "">("");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState<number | null>(null);
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
      const result = await listFinanceVerifications({
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

  async function review(row: FinanceVerification, approved: boolean) {
    const reason = normalizeAdminReviewPrompt(window.prompt(
      approved ? "审核备注（可选）" : "请输入驳回原因",
      approved ? "证件信息与照片核验一致" : "",
    ),
      !approved,
    );
    if (reason === null) return;
    setBusy(row.id);
    try {
      await reviewFinanceVerification(row.id, approved, reason);
      await load();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  }

  return <section className="workspace-page commerce-workspace admin-kyc">
    <div className="workspace-page__head">
      <p>FINANCE / IDENTITY REVIEW</p>
      <h1>实名认证审核</h1>
      <span>审核队列直接来自统一业务后端；查看证件照片会记录审计日志。</span>
    </div>
    <div className="refund-toolbar">
      <select value={status} onChange={(event) => changeStatus(event.target.value)}>
        <option value="pending">待审核</option>
        <option value="verified">已通过</option>
        <option value="rejected">已驳回</option>
        <option value="">全部</option>
      </select>
      <AdminPlatformFilter value={platform} onChange={changePlatform}/>
      <button disabled={loading} onClick={() => void load()}><ArrowClockwise size={15}/>{loading ? "读取中" : "刷新"}</button>
    </div>
    {error && <div className="commerce-error">{error}</div>}
    <div className="admin-kyc-list">
      {rows.length ? rows.map((row) => <article key={row.id}>
        <header>
          <div>
            <small>KYC #{row.id} · USER #{row.user_id} · {platformLabel(row.created_platform)}</small>
            <h2>{row.real_name}</h2>
            <span>{row.username} · {formatDate(row.created_at)}</span>
          </div>
          <b className={`status-chip status-chip--${row.status === "verified" ? "published" : row.status === "rejected" ? "rejected" : "pending_review"}`}>{labels[row.status]}</b>
        </header>
        <dl>
          <div><dt>证件号码</dt><dd>{row.id_card_masked}</dd></div>
          <div><dt>授权同意</dt><dd>{row.consent_recorded ? "已记录" : "缺失"}</dd></div>
          <div><dt>OCR 状态</dt><dd>{row.ocr_status || "未执行"}</dd></div>
          <div><dt>最后操作端</dt><dd>{platformLabel(row.last_modified_platform)}</dd></div>
        </dl>
        <div className="finance-photo-links">
          {row.front_photo_uploaded && <a href={financeVerificationPhoto(row.id, "front")} target="_blank" rel="noreferrer">查看身份证正面</a>}
          {row.back_photo_uploaded && <a href={financeVerificationPhoto(row.id, "back")} target="_blank" rel="noreferrer">查看身份证反面</a>}
        </div>
        {row.reject_reason && <p>{row.reject_reason}</p>}
        {row.status === "pending" && <footer>
          <button disabled={busy === row.id} onClick={() => void review(row, false)}><X size={15}/>驳回</button>
          <button className="commerce-primary" disabled={busy === row.id} onClick={() => void review(row, true)}><Check size={15}/>通过认证</button>
        </footer>}
      </article>) : <div className="commerce-empty"><IdentificationCard size={25}/><strong>{loading ? "正在读取队列…" : "当前队列为空"}</strong></div>}
    </div>
    <AdminQueuePagination page={page} total={total} loading={loading} onPageChange={changePage}/>
    <div className="integration-safety-note"><ShieldCheck size={19}/><div><strong>敏感数据保护</strong><span>证件照片只通过登录态 BFF 临时读取，不保存到 Web，也不会暴露后端地址。</span></div></div>
  </section>;
}
