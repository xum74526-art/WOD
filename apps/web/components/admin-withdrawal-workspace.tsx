"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { ArrowClockwise, Bank, Check, Money, Warning, X } from "@phosphor-icons/react";
import { AdminPlatformFilter, platformLabel } from "@/components/admin-platform-filter";
import { AdminQueuePagination } from "@/components/admin-queue-pagination";
import { normalizeAdminReviewPrompt } from "@/lib/admin-review-prompt";
import { ADMIN_QUEUE_PAGE_SIZE, adminQueuePageCount } from "@/lib/admin-queue-pagination";
import { errorMessage } from "@/lib/commerce-ui";
import { formatFinancialAmount } from "@/lib/financial-format";
import { formatPlatformDateTime, localDateTimeInputToUtcIso, toLocalDateTimeInputValue } from "@/lib/date-time";
import {
  approveFinanceWithdrawal,
  failFinanceWithdrawal,
  financeWithdrawalReceipt,
  getPaymentInstructions,
  listFinanceWithdrawals,
  markFinanceWithdrawalPaid,
  rejectFinanceWithdrawal,
  type AuditPlatform,
  type FinanceWithdrawal,
  type PaymentInstructions,
} from "@/lib/mobile-finance-api";
import { canViewPayoutReceipt, PAYOUT_RECEIPT_ACCEPT, PAYOUT_RECEIPT_HELP_TEXT } from "@/lib/payout-receipt";
import { useI18n } from "@/components/locale-root";

const labels: Record<string, string> = { reviewing: "待审核", manual_payment_pending: "待打款", paid: "已打款", rejected: "已驳回", failed: "打款失败", canceled: "已取消" };

export function AdminWithdrawalWorkspace() {
  const { formatLedgerMoney } = useI18n();
  const [rows, setRows] = useState<FinanceWithdrawal[]>([]);
  const [status, setStatus] = useState("reviewing");
  const [platform, setPlatform] = useState<AuditPlatform | "">("");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [paying, setPaying] = useState<{ row: FinanceWithdrawal; instructions: PaymentInstructions } | null>(null);
  const [payment, setPayment] = useState({ bank_reference: "", paid_amount_cny: "", paid_at: "" });
  const [receipt, setReceipt] = useState<File | null>(null);
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
      const result = await listFinanceWithdrawals({
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

  function changePage(value: number) { if (value === page) return; requestSequence.current += 1; setPaying(null); setReceipt(null); setPage(value); }
  function changeStatus(value: string) { if (value === status && page === 1) return; requestSequence.current += 1; setPaying(null); setReceipt(null); setStatus(value); setPage(1); }
  function changePlatform(value: AuditPlatform | "") { if (value === platform && page === 1) return; requestSequence.current += 1; setPaying(null); setReceipt(null); setPlatform(value); setPage(1); }

  async function action(row: FinanceWithdrawal, kind: "approve" | "reject" | "failed") {
    const note = normalizeAdminReviewPrompt(window.prompt(
        kind === "approve" ? "审核备注（可选）" : kind === "reject" ? "请输入驳回原因" : "请输入打款失败原因",
        kind === "approve" ? "收款资料已核对" : "",
      ),
      kind !== "approve",
    );
    if (note === null) return;
    setBusy(row.id);
    try {
      if (kind === "approve") await approveFinanceWithdrawal(row.id, note);
      else if (kind === "reject") await rejectFinanceWithdrawal(row.id, note!);
      else await failFinanceWithdrawal(row.id, note!);
      await load();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  }

  async function preparePayment(row: FinanceWithdrawal) {
    setBusy(row.id);
    try {
      const instructions = await getPaymentInstructions(row.id);
      setPaying({ row, instructions });
      setPayment({ bank_reference: "", paid_amount_cny: String(row.net_amount_cny), paid_at: toLocalDateTimeInputValue() });
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  }

  async function submitPayment(event: FormEvent) {
    event.preventDefault();
    if (!paying || !receipt) {
      setError("请上传银行打款凭证");
      return;
    }
    setBusy(paying.row.id);
    try {
      await markFinanceWithdrawalPaid(paying.row.id, receipt, {
        ...payment,
        paid_at: localDateTimeInputToUtcIso(payment.paid_at),
        reveal_token: paying.instructions.reveal_token,
      });
      setPaying(null);
      setReceipt(null);
      await load();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  }

  return <section className="workspace-page commerce-workspace admin-settlement">
    <div className="workspace-page__head">
      <p>FINANCE / PAYOUTS</p>
      <h1>提现结算</h1>
      <span>审核与付款确认必须由两名不同管理员完成；审批后首位查看完整收款信息的非审批管理员会被锁定为唯一付款经办人，其他人不得接管、转账或解冻。</span>
    </div>
    <div className="refund-toolbar">
      <select value={status} onChange={(event) => changeStatus(event.target.value)}>
        <option value="reviewing">待审核</option>
        <option value="manual_payment_pending">待打款</option>
        <option value="paid">已打款</option>
        <option value="rejected">已驳回</option>
        <option value="failed">打款失败</option>
        <option value="canceled">已取消</option>
        <option value="">全部</option>
      </select>
      <AdminPlatformFilter value={platform} onChange={changePlatform}/>
      <button disabled={loading} onClick={() => void load()}><ArrowClockwise size={15}/>{loading ? "读取中" : "刷新"}</button>
    </div>
    {error && <div className="commerce-error">{error}</div>}
    {paying && <form className="finance-payment-form" onSubmit={submitPayment}>
      <header><Bank size={20}/><div><small>{paying.row.order_no}</small><h2>登记银行打款</h2></div></header>
      <div className="finance-payment-instructions">
        <span><small>收款人</small><strong data-i18n-skip>{paying.instructions.holder}</strong></span>
        <span><small>开户行</small><strong data-i18n-skip>{paying.instructions.bank_name}</strong></span>
        <span><small>银行卡号</small><strong>{paying.instructions.card_number}</strong></span>
      </div>
      <label>银行流水号<input required value={payment.bank_reference} onChange={(event) => setPayment({ ...payment, bank_reference: event.target.value })}/></label>
      <label>实付金额（元）<input required step="0.01" type="number" value={payment.paid_amount_cny} onChange={(event) => setPayment({ ...payment, paid_amount_cny: event.target.value })}/></label>
      <label>打款时间（本地时间）<input required type="datetime-local" value={payment.paid_at} onChange={(event) => setPayment({ ...payment, paid_at: event.target.value })}/></label>
      <label>打款凭证<input required type="file" accept={PAYOUT_RECEIPT_ACCEPT} onChange={(event) => setReceipt(event.target.files?.[0] || null)}/><small>{PAYOUT_RECEIPT_HELP_TEXT}</small></label>
      <footer>
        <button type="button" onClick={() => { setPaying(null); setReceipt(null); }}>取消</button>
        <button className="commerce-primary" disabled={busy === paying.row.id}>确认已打款</button>
      </footer>
    </form>}
    <div className="admin-settlement-list">
      {rows.length ? rows.map((row) => <article key={row.id}>
        <header>
          <div>
            <small>{row.order_no} · {platformLabel(row.created_platform)}</small>
            <h2 data-i18n-skip={Boolean(row.user?.username) || undefined}>{row.user?.username || `用户 #${row.user?.id || "-"}`}</h2>
            <span>申请时间（北京时间） {formatPlatformDateTime(row.created_at)} · 最后操作 {platformLabel(row.last_modified_platform)}</span>
          </div>
          <strong>¥ {formatFinancialAmount(row.net_amount_cny)}</strong>
          <b className={`status-chip status-chip--${row.status === "paid" ? "published" : ["rejected", "failed", "canceled"].includes(row.status) ? "rejected" : "pending_review"}`}>{labels[row.status]}</b>
        </header>
        <div className="admin-bank-slip"><Bank size={20}/><dl>
          <div><dt>收款人</dt><dd data-i18n-skip>{row.bank_card.holder}</dd></div>
          <div><dt>开户银行</dt><dd data-i18n-skip>{row.bank_card.bank_name}</dd></div>
          <div><dt>银行卡</dt><dd>尾号 {row.bank_card.card_last4 || row.bank_card.card_number.slice(-4)}</dd></div>
          <div><dt>申请提现金额</dt><dd>{formatLedgerMoney(row.amount_card_hours)}</dd></div>
        </dl></div>
        {row.review_note && <p data-i18n-skip>{row.review_note}</p>}
        {row.failure_reason && <p data-i18n-skip>{row.failure_reason}</p>}
        {row.status === "paid" && <p>打款时间（北京时间）：{formatPlatformDateTime(row.paid_at)}</p>}
        {canViewPayoutReceipt(row) && <div className="finance-photo-links"><a href={financeWithdrawalReceipt(row.id)} target="_blank" rel="noreferrer">下载打款凭证</a></div>}
        <footer>
          {row.status === "reviewing" && <>
            <button disabled={busy === row.id} onClick={() => void action(row, "reject")}><X size={15}/>驳回</button>
            <button className="commerce-primary" disabled={busy === row.id} onClick={() => void action(row, "approve")}><Check size={15}/>批准提现</button>
          </>}
          {row.status === "manual_payment_pending" && <>
            <button disabled={busy === row.id} onClick={() => void action(row, "failed")}><Warning size={15}/>标记失败</button>
            <button className="commerce-primary" disabled={busy === row.id} onClick={() => void preparePayment(row)}><Money size={15}/>登记打款</button>
          </>}
        </footer>
      </article>) : <div className="commerce-empty"><Bank size={25}/><strong>{loading ? "正在读取队列…" : "当前队列为空"}</strong></div>}
    </div>
    <AdminQueuePagination page={page} total={total} loading={loading} onPageChange={changePage}/>
  </section>;
}
