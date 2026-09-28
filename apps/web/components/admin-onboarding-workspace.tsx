"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { ArrowClockwise, Check, HardDrives, Phone, ShieldCheck, UserFocus, X } from "@phosphor-icons/react";
import { AdminPlatformFilter, platformLabel } from "@/components/admin-platform-filter";
import { AdminQueuePagination } from "@/components/admin-queue-pagination";
import { useI18n } from "@/components/locale-root";
import {
  listAdminOnboardings,
  reviewAdminOnboarding,
  type AdminOnboardingItem,
} from "@/lib/admin-audit-api";
import { normalizeAdminReviewPrompt } from "@/lib/admin-review-prompt";
import { ADMIN_QUEUE_PAGE_SIZE, adminQueuePageCount } from "@/lib/admin-queue-pagination";
import { errorMessage, formatDate } from "@/lib/commerce-ui";
import type { AuditPlatform } from "@/lib/mobile-finance-api";

type ReviewStatus = "contacted" | "approved" | "rejected";

export function AdminOnboardingWorkspace() {
  const { t } = useI18n();
  const [rows, setRows] = useState<AdminOnboardingItem[]>([]);
  const [status, setStatus] = useState("submitted");
  const [entityType, setEntityType] = useState<"personal" | "company" | "">("");
  const [platform, setPlatform] = useState<AuditPlatform | "">("");
  const [searchDraft, setSearchDraft] = useState("");
  const [keyword, setKeyword] = useState("");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(0);
  const [error, setError] = useState("");
  const queryRef = useRef({ status, entityType, platform, keyword, page });
  const requestSequence = useRef(0);
  queryRef.current = { status, entityType, platform, keyword, page };

  const statusLabel = (value: string) => ({
    submitted: t("admin.onboarding.status.submitted", "待受理"),
    contacted: t("admin.onboarding.status.contacted", "已联系"),
    approved: t("admin.onboarding.status.approved", "已通过"),
    rejected: t("admin.onboarding.status.rejected", "已驳回"),
  }[value] || value);

  const load = useCallback(async () => {
    const requestId = ++requestSequence.current;
    const query = queryRef.current;
    const current = () => requestId === requestSequence.current
      && query.status === queryRef.current.status
      && query.entityType === queryRef.current.entityType
      && query.platform === queryRef.current.platform
      && query.keyword === queryRef.current.keyword
      && query.page === queryRef.current.page;
    setLoading(true);
    setError("");
    try {
      const result = await listAdminOnboardings({
        status: query.status || undefined,
        entityType: query.entityType,
        platform: query.platform || undefined,
        keyword: query.keyword || undefined,
        page: query.page,
        pageSize: ADMIN_QUEUE_PAGE_SIZE,
      });
      if (!current()) return;
      const pageCount = adminQueuePageCount(result.total);
      setTotal(result.total);
      if (query.page > pageCount) {
        setRows([]);
        setPage(pageCount);
        return;
      }
      setRows(result.items);
    } catch (reason) {
      if (current()) setError(errorMessage(reason));
    } finally {
      if (current()) setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [entityType, keyword, load, page, platform, status]);

  function resetPage() {
    requestSequence.current += 1;
    setPage(1);
  }

  function search(event: FormEvent) {
    event.preventDefault();
    const value = searchDraft.trim();
    if (value === keyword && page === 1) return;
    resetPage();
    setKeyword(value);
  }

  async function review(row: AdminOnboardingItem, nextStatus: ReviewStatus) {
    const required = nextStatus === "rejected";
    const prompt = nextStatus === "contacted"
      ? t("admin.onboarding.prompt.contacted", "联系记录（可选）")
      : nextStatus === "approved"
        ? t("admin.onboarding.prompt.approved", "通过说明（可选）")
        : t("admin.onboarding.prompt.rejected", "请输入驳回原因");
    const defaultNote = nextStatus === "contacted"
      ? t("admin.onboarding.default.contacted", "已与申请人取得联系，等待后续接入资料")
      : nextStatus === "approved"
        ? t("admin.onboarding.default.approved", "资料审核通过，请按客服联系安排完成设备接入")
        : "";
    const note = normalizeAdminReviewPrompt(window.prompt(prompt, defaultNote), required);
    if (note === null) return;
    if (!window.confirm(t("admin.onboarding.confirm", "确认更新这条设备托管申请？处理结果会立即同步给用户。"))) return;
    setBusy(row.id);
    setError("");
    try {
      await reviewAdminOnboarding(row.id, {
        status: nextStatus,
        expected_version: row.version,
        note,
      });
      await load();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(0);
    }
  }

  return <section className="workspace-page commerce-workspace">
    <div className="workspace-page__head">
      <p>OPERATIONS / DEVICE HOSTING</p>
      <h1>{t("admin.onboarding.title", "设备托管审核")}</h1>
      <span>{t("admin.onboarding.description", "受理用户提交的托管申请，记录处理结论，并把状态和处理说明同步到 Web、Android 与 iOS。")}</span>
    </div>
    <form className="refund-toolbar" onSubmit={search}>
      <input aria-label={t("admin.onboarding.searchAria", "搜索托管申请")} value={searchDraft} onChange={(event) => setSearchDraft(event.target.value)} placeholder={t("admin.onboarding.searchPlaceholder", "联系人、电话、账号或设备型号")}/>
      <select value={status} onChange={(event) => { setStatus(event.target.value); resetPage(); }}>
        <option value="submitted">{t("admin.onboarding.status.submitted", "待受理")}</option>
        <option value="contacted">{t("admin.onboarding.status.contacted", "已联系")}</option>
        <option value="approved">{t("admin.onboarding.status.approved", "已通过")}</option>
        <option value="rejected">{t("admin.onboarding.status.rejected", "已驳回")}</option>
        <option value="">{t("admin.onboarding.status.all", "全部状态")}</option>
      </select>
      <select value={entityType} onChange={(event) => { setEntityType(event.target.value as typeof entityType); resetPage(); }}>
        <option value="">{t("admin.onboarding.entity.all", "全部主体")}</option>
        <option value="personal">{t("admin.onboarding.entity.personal", "个人")}</option>
        <option value="company">{t("admin.onboarding.entity.company", "企业")}</option>
      </select>
      <AdminPlatformFilter value={platform} onChange={(value) => { setPlatform(value); resetPage(); }}/>
      <button type="submit" disabled={loading}>{t("admin.onboarding.search", "搜索")}</button>
      <button type="button" disabled={loading} onClick={() => void load()}><ArrowClockwise size={15}/>{loading ? t("admin.onboarding.loading", "读取中") : t("admin.onboarding.refresh", "刷新")}</button>
    </form>
    {error && <div className="commerce-error">{error}</div>}
    <div className="admin-bank-review-list admin-onboarding-list">
      {rows.length ? rows.map((row) => <article key={row.id}>
        <header>
          <HardDrives size={21}/>
          <span>
            <small>HOSTING #{row.id} · USER #{row.user_id} · {platformLabel(row.created_platform)}</small>
            <h2 data-i18n-skip>{row.device_model} × {row.device_count}</h2>
            <p><span data-i18n-skip>{row.username || t("admin.onboarding.userFallback", "用户")}</span> · {row.entity_type === "company" ? t("admin.onboarding.entity.company", "企业") : t("admin.onboarding.entity.personal", "个人")}</p>
          </span>
          <b>{statusLabel(row.status)}</b>
        </header>
        <dl>
          <div><dt>{t("admin.onboarding.contact", "联系人")}</dt><dd data-i18n-skip>{row.contact}</dd></div>
          <div><dt>{t("admin.onboarding.phone", "联系电话")}</dt><dd data-i18n-skip><Phone size={13}/> {row.phone}</dd></div>
          <div><dt>{t("admin.onboarding.location", "设备所在地")}</dt><dd data-i18n-skip>{row.location || t("admin.onboarding.notProvided", "未提供")}</dd></div>
          <div><dt>{t("admin.onboarding.submittedAt", "提交时间")}</dt><dd>{formatDate(row.created_at)}</dd></div>
        </dl>
        {row.remark && <p data-i18n-skip>{row.remark}</p>}
        {row.review_note && <p className="finance-review-reason"><UserFocus size={15}/><span data-i18n-skip>{row.review_note}</span></p>}
        {row.status === "submitted" || row.status === "contacted" ? <footer>
          {row.status === "submitted" && <button disabled={busy === row.id} onClick={() => void review(row, "contacted")}><Phone size={15}/>{t("admin.onboarding.action.contacted", "标记已联系")}</button>}
          <button disabled={busy === row.id} onClick={() => void review(row, "rejected")}><X size={15}/>{t("admin.onboarding.action.reject", "驳回")}</button>
          <button className="commerce-primary" disabled={busy === row.id} onClick={() => void review(row, "approved")}><Check size={15}/>{t("admin.onboarding.action.approve", "通过申请")}</button>
        </footer> : null}
      </article>) : <div className="commerce-empty"><HardDrives size={27}/><strong>{loading ? t("admin.onboarding.loadingQueue", "正在读取托管队列…") : t("admin.onboarding.empty", "当前没有符合条件的托管申请")}</strong></div>}
    </div>
    <AdminQueuePagination page={page} total={total} loading={loading} onPageChange={(value) => { requestSequence.current += 1; setPage(value); }}/>
    <div className="integration-safety-note"><ShieldCheck size={19}/><div><strong>{t("admin.onboarding.boundaryTitle", "处理边界")}</strong><span>{t("admin.onboarding.boundary", "通过仅表示平台接受托管申请，不代表设备已经部署上线；实际接入仍需按处理说明和客服联系完成。")}</span></div></div>
  </section>;
}
