"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Check, MagnifyingGlass, PauseCircle, PlayCircle, ShieldCheck, X } from "@phosphor-icons/react";
import { listSupplierApplications, reviewSupplierApplication, type SupplierApplication } from "@/lib/commerce-api";
import { AdminQueuePagination } from "@/components/admin-queue-pagination";
import { listAdminSupplierProducts, manageAdminSupplierProduct, manageAdminSupplierStatus, type AdminSupplierProduct } from "@/lib/admin-audit-api";
import { errorMessage, formatDate } from "@/lib/commerce-ui";
import { useI18n } from "@/components/locale-root";

const labels = { pending: "待审核", approved: "已通过", rejected: "已驳回", suspended: "已停用" } as const;
const PAGE_SIZE = 30;

function mergeApplications(current: SupplierApplication[], incoming: SupplierApplication[]) {
  const rows = new Map(current.map((row) => [row.id, row]));
  incoming.forEach((row) => rows.set(row.id, row));
  return Array.from(rows.values());
}

export function SupplierReview() {
  const { t } = useI18n();
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
  const [controlReason, setControlReason] = useState("");
  const [products, setProducts] = useState<AdminSupplierProduct[]>([]);
  const [productPage, setProductPage] = useState(1);
  const [productTotal, setProductTotal] = useState(0);
  const [productsLoading, setProductsLoading] = useState(false);

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

  const loadProducts = useCallback(async (supplierId: number, nextPage = 1) => {
    setProductsLoading(true);
    try {
      const result = await listAdminSupplierProducts(supplierId, { page: nextPage, pageSize: 20 });
      setProducts(result.items);
      setProductPage(result.page);
      setProductTotal(result.total);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setProductsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selected && (selected.status === "approved" || selected.status === "suspended")) {
      void loadProducts(selected.id, 1);
    } else {
      setProducts([]);
      setProductTotal(0);
      setProductPage(1);
    }
  }, [loadProducts, selected?.id, selected?.status]);

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

  async function manageSupplier(action: "suspend" | "reactivate") {
    if (!selected) return;
    if (controlReason.trim().length < 2) {
      setError("请填写至少 2 个字的操作原因");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const result = await manageAdminSupplierStatus(selected.id, {
        action,
        expected_status: selected.status as "approved" | "suspended",
        reason: controlReason.trim(),
      });
      setControlReason("");
      if (result.requires_order_follow_up) {
        setError(`商家状态已更新，但仍有 ${result.open_order_count} 笔进行中订单需要运营跟进。`);
      }
      await load(status, search, 1, false);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  async function manageProduct(product: AdminSupplierProduct, nextStatus: "on" | "off") {
    if (!selected) return;
    const reason = controlReason.trim() || (nextStatus === "off" ? "管理员下架复核" : "管理员复核后上架");
    setBusy(true);
    setError("");
    try {
      await manageAdminSupplierProduct(product.id, {
        status: nextStatus,
        expected_version: product.version,
        reason,
      });
      await loadProducts(selected.id, productPage);
    } catch (reasonValue) {
      setError(errorMessage(reasonValue));
    } finally {
      setBusy(false);
    }
  }

  const hasMore = page * PAGE_SIZE < total;

  return <section className="workspace-page commerce-workspace">
    <div className="workspace-page__head"><p>ADMIN / SUPPLIER REVIEW</p><h1>商家准入审核</h1><span>商家入驻资料审核与实名认证是两个独立结论；只有实名认证已完成的申请人才能通过入驻审核。</span></div>
    <div className="review-console"><aside><form onSubmit={submit}><label><MagnifyingGlass size={15} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索主体、联系人或邮箱" /></label><select value={status} onChange={(event) => { setStatus(event.target.value); void load(event.target.value, search, 1, false); }}><option value="pending">待审核</option><option value="approved">已通过</option><option value="suspended">已停用</option><option value="rejected">已驳回</option><option value="">全部</option></select></form>{loading && rows.length === 0 ? <div className="commerce-loading">正在读取申请…</div> : error && rows.length === 0 ? <div className="commerce-error">{error}</div> : rows.length === 0 ? <div className="commerce-empty"><ShieldCheck size={23} /><strong>没有符合条件的申请</strong></div> : <><div className="review-queue">{rows.map((row) => <button className={selected?.id === row.id ? "active" : ""} type="button" key={row.id} onClick={() => { setSelected(row); setNote(row.review_note || ""); setControlReason(""); }}><span><small>#{row.id} · {formatDate(row.created_at)}</small><strong data-i18n-skip>{row.company_name}</strong><em data-i18n-skip>{row.applicant.email || row.applicant.display_name}</em></span><b className={`status-chip status-chip--${row.status}`}>{labels[row.status]}</b></button>)}</div>{hasMore && <button className="admin-dispute-load-more" type="button" disabled={loading} onClick={() => void load(status, search, page + 1, true)}>{loading ? "正在加载…" : t("admin.common.loadMore", "加载更多（已显示 {shown} / {total}）", { shown: rows.length, total })}</button>}</>}</aside>
      <article className="review-dossier">{selected ? <><header><div><p>APPLICATION #{selected.id} / V{selected.version}</p><h2 data-i18n-skip>{selected.company_name}</h2></div><span className={`status-chip status-chip--${selected.status}`}>{labels[selected.status]}</span></header><dl><div><dt>申请账户</dt><dd><span data-i18n-skip>{selected.applicant.display_name}</span><small data-i18n-skip={Boolean(selected.applicant.email) || undefined}>{selected.applicant.email || "未绑定邮箱"}</small></dd></div><div><dt>实名认证</dt><dd>{selected.identity_verified ? "已完成" : "未完成"}<small>{selected.identity_verified ? "满足商家准入前置条件" : "完成实名认证后才可审核通过"}</small></dd></div><div><dt>联系人</dt><dd><span data-i18n-skip>{selected.contact_name}</span><small data-i18n-skip>{selected.contact_phone}</small></dd></div><div><dt>地区</dt><dd data-i18n-skip={Boolean(selected.region) || undefined}>{selected.region || "未填写"}</dd></div><div><dt>当前角色 / 状态</dt><dd>{selected.applicant.role} / {selected.applicant.status}</dd></div></dl><section><h3>商家提交的设备来源与业务说明</h3><p data-i18n-skip={Boolean(selected.description) || undefined}>{selected.description || "申请人未补充说明。"}</p></section>{selected.review_note && selected.status !== "pending" && <section><h3>最近审核意见</h3><p data-i18n-skip>{selected.review_note}</p></section>}{selected.status === "pending" && <footer><label><span>审核意见</span><textarea rows={4} value={note} onChange={(event) => setNote(event.target.value)} placeholder="通过时可选；驳回时必填" /></label><div><button className="commerce-danger" disabled={busy} onClick={() => void review("reject")}><X size={15} />驳回申请</button><button className="commerce-primary" disabled={busy || !selected.identity_verified} title={selected.identity_verified ? undefined : "申请人尚未完成实名认证"} onClick={() => void review("approve")}><Check size={15} />{selected.identity_verified ? "审核通过" : "未实名不可通过"}</button></div></footer>}{(selected.status === "approved" || selected.status === "suspended") && <section className="admin-supplier-control"><h3>商家经营控制</h3><p>停用会立即阻止新交易并下架全部商品；恢复后仍需逐项复核上架。</p><textarea rows={2} value={controlReason} onChange={(event) => setControlReason(event.target.value)} placeholder="填写操作原因（至少 2 个字）"/><button className={selected.status === "approved" ? "commerce-danger" : "commerce-primary"} type="button" disabled={busy || controlReason.trim().length < 2} onClick={() => void manageSupplier(selected.status === "approved" ? "suspend" : "reactivate")}>{selected.status === "approved" ? <><PauseCircle size={16}/>停用商家并下架商品</> : <><PlayCircle size={16}/>恢复商家权限</>}</button></section>}{(selected.status === "approved" || selected.status === "suspended") && <section className="admin-supplier-products"><h3>商家商品</h3>{productsLoading && products.length === 0 ? <div className="commerce-loading">正在读取商品…</div> : products.length === 0 ? <p>该商家暂无商品。</p> : products.map((product) => <div key={product.id}><span><strong data-i18n-skip>{product.name}</strong><small>{product.gpu_model} · {product.memory} · ¥{product.price.toFixed(3)} · 库存 {product.stock}</small>{product.open_order_count > 0 && <em>进行中订单 {product.open_order_count} 笔</em>}</span><button type="button" disabled={busy || (product.status === "off" && selected.status !== "approved")} onClick={() => void manageProduct(product, product.status === "on" ? "off" : "on")}>{product.status === "on" ? "下架" : "上架"}</button></div>)}<AdminQueuePagination page={productPage} total={productTotal} loading={productsLoading} onPageChange={(value) => void loadProducts(selected.id, value)}/></section>}</> : <div className="commerce-empty"><ShieldCheck size={25}/><strong>选择一条申请查看资料</strong></div>}</article>
    </div>{error && rows.length > 0 && <div className="commerce-error">{error}</div>}
  </section>;
}
